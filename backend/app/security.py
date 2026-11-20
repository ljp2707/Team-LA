"""Protections that wrap every request: CSRF origin check, security headers, request IDs
and a safe answer for unexpected errors.

Both classes are plain ASGI middleware (not @app.middleware), so they also see the
responses made by other middleware and by crashes, and add their headers to those too.
"""

import logging
import uuid
from urllib.parse import urlparse

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.config import Settings, get_settings
from app.log_redaction import redact_path

logger = logging.getLogger("app.errors")


# --- CSRF: refuse changes sent from other websites -----------------------------------

CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CHECKED_PREFIXES = ("/api/", "/auth/")
CSRF_MESSAGE = "This request came from another website, so it was refused."


def origin_of(url: str | None) -> str | None:
    """'https://site.org/page?x=1' -> 'https://site.org'. None if it is not a web address."""
    parts = urlparse((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def trusted_origins(settings: Settings) -> set[str]:
    """The only sites allowed to send changes: this app and its frontend."""
    return {o for o in (origin_of(settings.APP_URL), origin_of(settings.FRONTEND_URL)) if o}


class OriginCheck:
    """Refuse POST, PUT, PATCH and DELETE on /api and /auth from any other website.

    The SameSite=Lax cookie already stops most cross-site requests. This is a second
    check that does not depend on how browsers treat sibling subdomains. Browsers send
    Origin with every such request; Referer is the fallback. A request with neither
    is refused too, since every browser request we make has one.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["method"] in CHANGING_METHODS
            and scope["path"].startswith(CHECKED_PREFIXES)
        ):
            headers = Headers(scope=scope)
            origin = origin_of(headers.get("origin")) or origin_of(headers.get("referer"))
            if origin not in trusted_origins(get_settings()):
                response = JSONResponse({"detail": CSRF_MESSAGE}, status_code=403)
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


# --- Security headers ----------------------------------------------------------------

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # Files are only ever read as the type they say
    "X-Frame-Options": "DENY",  # No other site can show the app inside a frame
    "Referrer-Policy": "strict-origin-when-cross-origin",  # Links out do not leak task URLs
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",  # The app never needs these
}

# Browsers only ever use https for this site once they have seen it (production only:
# on localhost it would stop http://localhost working for a year). Findings F1.
HSTS_VALUE = "max-age=31536000; includeSubDomains"

# Only what the built app loads: its own scripts, styles, fonts (self-hosted in
# /fonts) and images. Nothing from other sites, and no other site may frame it.
# A second line of defence if a bad link or value ever reaches the page (F1).
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self' https://accounts.google.com",
    ]
)
CSP_HEADER_BY_MODE = {
    "report-only": "Content-Security-Policy-Report-Only",  # Browsers warn, nothing is blocked
    "enforce": "Content-Security-Policy",
}

# API answers that are the same for everyone, so caching them is harmless.
CACHEABLE_API_PATHS = ("/api/health", "/api/public/")


def keep_out_of_caches(path: str) -> bool:
    """API and sign-in answers carry people's names, tasks and notes. Browsers and
    proxies must not keep a copy, for example on a shared computer."""
    if path.startswith(CACHEABLE_API_PATHS):
        return False
    return path.startswith(CHECKED_PREFIXES)


def add_security_headers(headers: MutableHeaders, path: str, request_id: str) -> None:
    settings = get_settings()
    for name, value in SECURITY_HEADERS.items():
        headers.setdefault(name, value)
    headers["X-Request-ID"] = request_id
    if settings.is_production:
        headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
    csp_header = CSP_HEADER_BY_MODE.get(settings.CSP_MODE)
    if csp_header:
        headers.setdefault(csp_header, CONTENT_SECURITY_POLICY)
    if keep_out_of_caches(path):
        headers.setdefault("Cache-Control", "no-store")


# --- Request IDs and unexpected errors ------------------------------------------------

ERROR_MESSAGE = "Something went wrong. If it keeps happening, send this code to the NMU team."


class RequestContext:
    """Give every request an ID, add the security headers to every response, and turn
    crashes into a plain message.

    The outermost middleware, so its headers reach every answer: errors, refused hosts,
    oversized requests. A crash is logged with its request ID, and the person gets
    only that ID back, never a stack trace (which could show code, data or settings).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Made here rather than taken from the request, so nobody can choose their own.
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        response_started = False

        async def send_with_headers(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                add_security_headers(MutableHeaders(scope=message), scope["path"], request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            # The path only: never the query string or body, which can hold secrets.
            logger.exception(
                "Unexpected error on %s %s (request %s)",
                scope["method"],
                redact_path(scope["path"]),
                request_id,
            )
            if response_started:
                raise  # Too late to send a different answer
            response = JSONResponse({"detail": ERROR_MESSAGE, "request_id": request_id}, status_code=500)
            await response(scope, receive, send_with_headers)
