"""Protections that wrap every request: CSRF origin check, security headers, request IDs
and a safe answer for unexpected errors.

Both classes are plain ASGI middleware (not @app.middleware), so they also see the
responses made by other middleware and by crashes, and add their headers to those too.
"""

import json
import logging
import re
import uuid
from urllib.parse import urlparse

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.config import Settings, get_settings
from app.log_redaction import redact_path

logger = logging.getLogger("app.errors")


# --- CSRF: refuse changes sent from other websites -----------------------------------

CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# F23: the shape of an Airtable record ID, for record IDs that arrive as query parameters.
# Real IDs are "rec" plus exactly 14 letters or digits; shorter ones are accepted so the
# readable IDs in the tests (such as recProj) still work. What matters is that the value is
# short and holds only letters and digits.
RECORD_ID_PATTERN = r"^rec[A-Za-z0-9]{1,24}$"
CHECKED_PREFIXES = ("/api/", "/auth/")
CSRF_MESSAGE = "This request came from another website, so it was refused."
# Browsers send CSP reports on their own, sometimes with no Origin header, and the route
# changes nothing, so a forged one can do no harm. It has its own rate and size limits.
ORIGIN_CHECK_EXEMPT = frozenset({"/api/security/csp-report"})


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
            and scope["path"] not in ORIGIN_CHECK_EXEMPT
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
        # Where browsers report what the policy blocked (F25). report-uri for browsers
        # that only know the older way, report-to for the Reporting API.
        "report-uri /api/security/csp-report",
        "report-to csp-endpoint",
    ]
)
# Names the report-to endpoint above. Sent with the policy.
REPORTING_ENDPOINTS = 'csp-endpoint="/api/security/csp-report"'
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
        headers.setdefault("Reporting-Endpoints", REPORTING_ENDPOINTS)
    if keep_out_of_caches(path):
        headers.setdefault("Cache-Control", "no-store")


# --- CSP violation reports (F25) -------------------------------------------------------

# Browsers POST here when the Content-Security-Policy blocks (or, in report-only mode,
# would block) something. Reports carry no personal data we want, so only three cleaned
# values are kept: which rule, what kind of thing or which site was blocked, and the path
# of the page. Never the query string, the full blocked URL, the sample of blocked code,
# or anything else in the report.
CSP_REPORT_PATH = "/api/security/csp-report"
CSP_REPORT_GROUP = "csp-endpoint"  # The name report-to uses for the endpoint below
CSP_REPORTS_PER_REQUEST = 20  # More than this in one request is ignored, not logged
CSP_REPORT_TYPES = ("application/csp-report", "application/reports+json", "application/json")

_DIRECTIVE = re.compile(r"^[a-z-]{1,40}$")
_KEYWORD = re.compile(r"^[a-z-]{1,30}$")  # inline, eval, data, blob, wasm-eval and so on


def _clean_directive(value) -> str:
    """'style-src-elem' stays; anything that is not a plain directive name becomes 'unknown'."""
    value = str(value or "").strip().lower().split(" ")[0]
    return value if _DIRECTIVE.match(value) else "unknown"


def _clean_blocked(value) -> str:
    """Only the site (https://evil.example) for a URL, or the keyword (inline, eval)."""
    value = str(value or "").strip()
    site = origin_of(value)
    if site:
        return site
    keyword = value.lower().rstrip(":")
    return keyword if _KEYWORD.match(keyword) else "other"


def _clean_page(value) -> str:
    """Only the path of the page (no query string or fragment), with tokens redacted."""
    path = urlparse(str(value or "")).path or "/"
    path = "".join(ch for ch in path if ch.isprintable())[:200]
    return redact_path(path)


def parse_csp_reports(body: bytes, content_type: str) -> list[dict[str, str]] | None:
    """The cleaned reports in a request, or None if it is not a CSP report at all.

    Accepts both formats browsers use: the older report-uri one, {"csp-report": {...}}
    with kebab-case keys, and the Reporting API one, a list of {"type": "csp-violation",
    "body": {...}} with camelCase keys.
    """
    if content_type.split(";")[0].strip().lower() not in CSP_REPORT_TYPES:
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("csp-report"), dict):
        report = data["csp-report"]
        raw = [
            (
                report.get("effective-directive") or report.get("violated-directive"),
                report.get("blocked-uri"),
                report.get("document-uri"),
            )
        ]
    elif isinstance(data, list):
        raw = [
            (r["body"].get("effectiveDirective"), r["body"].get("blockedURL"), r["body"].get("documentURL"))
            for r in data[:CSP_REPORTS_PER_REQUEST]
            if isinstance(r, dict) and r.get("type") == "csp-violation" and isinstance(r.get("body"), dict)
        ]
    else:
        return None
    return [
        {"directive": _clean_directive(d), "blocked": _clean_blocked(b), "page": _clean_page(p)} for d, b, p in raw
    ]


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
