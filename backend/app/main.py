"""The FastAPI app: middleware, API routes, and the built frontend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import log_redaction
from app.airtable.client import warm_cache, warn_about_schema_problems
from app.auth.google import callback_url
from app.auth.session import MAX_SESSION_DAYS
from app.config import Settings, get_settings
from app.rate_limit import RateLimit
from app.request_limits import RequestSizeLimit
from app.routers import (
    admin,
    archive,
    auth,
    calendar,
    health,
    links,
    me,
    projects,
    public,
    reminders,
    sites,
    tasks,
    templates,
    users,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")
log_redaction.install()  # Calendar tokens and sign-in codes never reach the logs (findings F3)

STATIC_DIR = Path(__file__).resolve().parent / "static"

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Google sign in redirect URI: %s. This must be listed on the Google OAuth client.",
        callback_url(),
    )
    if not settings.is_production:
        warn_about_schema_problems()
    warm_cache()  # In the background, so the first sign in does not wait on Airtable
    yield


def api_docs_urls(current: Settings) -> dict:
    """The interactive API docs, on a laptop only.

    In production they would publish a map of every route, admin ones included (findings F2).
    """
    if current.is_production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


app = FastAPI(title="NMU Launches", lifespan=lifespan, **api_docs_urls(settings))

# Caps request size before sign-in or form parsing read the body (findings F6). Added
# first, so it sits next to the routes, where its 413 answers still get the headers below.
app.add_middleware(RequestSizeLimit)
# Limits requests per person or address, so no one can push Airtable past its rate
# limit (findings F5). Added before SessionMiddleware, so it runs inside it and can
# tell who is signed in.
app.add_middleware(RateLimit)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # Files are only ever read as the type they say
    "X-Frame-Options": "DENY",  # No other site can show the app inside a frame
    "Referrer-Policy": "strict-origin-when-cross-origin",  # Links out do not leak task URLs
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",  # The app never needs these
}

# Browsers only ever use https for this site once they have seen it (production only:
# on localhost it would stop http://localhost working for a year). Findings F1.
HSTS_VALUE = "max-age=31536000"

# Only this site's own scripts, styles, fonts and images may load, and no other site may
# frame it. A second line of defence if a bad link or value ever reaches the page (F1).
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
        "base-uri 'none'",
        "form-action 'self'",
    ]
)
CSP_HEADER_BY_MODE = {
    "report-only": "Content-Security-Policy-Report-Only",  # Browsers warn, nothing is blocked
    "enforce": "Content-Security-Policy",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    current = get_settings()
    if current.is_production:
        response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
    csp_header = CSP_HEADER_BY_MODE.get(current.CSP_MODE)
    if csp_header:
        response.headers.setdefault(csp_header, CONTENT_SECURITY_POLICY)
    return response


app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    session_cookie="nmu_session",
    max_age=MAX_SESSION_DAYS * 24 * 60 * 60,
    same_site="lax",
    https_only=settings.is_production,
)
# Only answer to our own host names, so a forged Host header cannot reach the app (F14).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

for module in (
    auth,
    me,
    health,
    public,
    projects,
    tasks,
    links,
    reminders,
    templates,
    users,
    archive,
    sites,
    admin,
    calendar,
):
    app.include_router(module.router)
app.include_router(users.roles_router)
app.include_router(users.directory_router)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    """Serve built frontend files, and index.html so React Router works on refresh."""
    if path == "api" or path.startswith(("api/", "auth/")):
        raise HTTPException(404, "Not found")

    file = (STATIC_DIR / path).resolve()
    if path and file.is_file() and file.is_relative_to(STATIC_DIR):
        return FileResponse(file)

    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "Frontend is not built. In development, use port 5173.")
    return FileResponse(index)
