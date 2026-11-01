"""Sign in and sign out: /auth/login, /auth/callback, /auth/logout."""

import logging

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from requests import RequestException

from app import permissions
from app.auth.google import callback_url, email_allowed, oauth
from app.auth.session import clear_session, set_session_user, set_stored_view
from app.config import get_settings
from app.models.user import find_active_user_by_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _to_frontend(path: str) -> RedirectResponse:
    base = get_settings().FRONTEND_URL.rstrip("/")
    return RedirectResponse(f"{base}{path}", status_code=302)


async def _finish_sign_in(request: Request, email: str) -> RedirectResponse:
    """Check an email against the rules and Airtable, then start the session."""
    if not email_allowed(email):
        return _to_frontend("/not-authorized?reason=domain")

    try:
        user = await run_in_threadpool(find_active_user_by_email, email)
    except RequestException as error:
        logger.warning("Airtable lookup failed: %s", type(error).__name__)
        return _to_frontend("/not-authorized?reason=airtable")
    if user is None:
        return _to_frontend("/not-authorized")

    # Start from a clean session so nothing carries over from before sign in.
    clear_session(request)
    set_session_user(request, user)
    view = permissions.base_view(user.access_level)
    set_stored_view(request, view)
    return _to_frontend(permissions.home_path(view))


@router.get("/login")
async def login(request: Request):
    # Local testing without Google. config.py refuses this outside localhost.
    dev_email = get_settings().DEV_LOGIN_EMAIL
    if dev_email:
        return await _finish_sign_in(request, dev_email)
    return await oauth.google.authorize_redirect(request, callback_url())


@router.get("/callback")
async def callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        logger.warning("Google sign in failed: %s", error.error)
        return _to_frontend("/not-authorized?reason=google")

    google_user = token.get("userinfo") or {}
    email = google_user.get("email", "")
    if not email or not google_user.get("email_verified"):
        return _to_frontend("/not-authorized?reason=google")
    return await _finish_sign_in(request, email)


@router.get("/logout")
async def logout(request: Request):
    clear_session(request)
    return _to_frontend("/")
