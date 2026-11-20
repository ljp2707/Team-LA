"""The FastAPI app: middleware, API routes, and the built frontend."""

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
from app.security import OriginCheck, RequestContext, RetireOldSessionCookie, session_cookie_options
from app.routers.auth import warn_if_bootstrap_not_needed
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
    security_reports,
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
    # In the background, so a slow Airtable never holds up startup (findings F33).
    threading.Thread(target=warn_if_bootstrap_not_needed, daemon=True).start()
    warm_cache()  # In the background, so the first sign in does not wait on Airtable
    yield


def api_docs_urls(current: Settings) -> dict:
    """The interactive API docs, on a laptop only.

    In production they would publish a map of every route, admin ones included (findings F2).
    """
    if current.is_production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


app = FastAPI(title="NMU Programs", lifespan=lifespan, **api_docs_urls(settings))

# Caps request size before sign-in or form parsing read the body (findings F6). Added
# first, so it sits next to the routes. Middleware added later wraps around it.
app.add_middleware(RequestSizeLimit)
# Limits requests per person or address, so no one can push Airtable past its rate
# limit (findings F5). Added before SessionMiddleware, so it runs inside it and can
# tell who is signed in.
app.add_middleware(RateLimit)

# Refuses changes sent from other websites (CSRF). Outside RateLimit, so a forged
# request is refused before it counts against the person it targets.
app.add_middleware(OriginCheck)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    # __Host-nmu_session in production, nmu_session on localhost (findings F29)
    **session_cookie_options(settings, max_age=MAX_SESSION_DAYS * 24 * 60 * 60),
)
# Deletes the pre-F29 cookie in production. Outside SessionMiddleware, so it sees every answer.
app.add_middleware(RetireOldSessionCookie)
# Only answer to our own host names, so a forged Host header cannot reach the app (F14).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
# Outermost: request IDs, security headers on every answer (errors included), and a
# plain message instead of a stack trace when something crashes.
app.add_middleware(RequestContext)

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
    security_reports,
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
