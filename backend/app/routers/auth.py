"""Sign in and sign out: /auth/login, /auth/callback, /auth/logout, /auth/denied.

Any Google account may try to sign in. The Airtable Users table alone decides who
gets in: there must be an Active row with that email. The only exception is
BOOTSTRAP_ADMIN_EMAILS, which creates a first Admin row when none exists yet.
"""

import logging

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from requests import RequestException

from app import permissions
from app.airtable import client
from app.airtable.schema import ACTIVE, Users
from app.auth import revocation
from app.auth.deps import current_user
from app.auth.google import allowed_domain, callback_url, email_allowed, oauth
from app.auth.session import (
    clear_session,
    regenerate_session,
    set_session_user,
    set_stored_view,
    start_session_clock,
)
from app.config import get_settings
from app.models.user import find_active_user_by_email, find_user_record_by_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

DENIED_EMAIL_KEY = "denied_email"


def _to_frontend(path: str) -> RedirectResponse:
    base = get_settings().FRONTEND_URL.rstrip("/")
    return RedirectResponse(f"{base}{path}", status_code=302)


def ensure_bootstrap_admin(email: str, first_name: str = "", last_name: str = "") -> None:
    """Create an Active Admin row for a bootstrap email that has no row at all.

    An existing row is never changed, because Airtable stays the source of truth.
    """
    wanted = email.strip().lower()
    if wanted not in get_settings().bootstrap_admins:
        return
    existing = find_user_record_by_email(wanted)
    if existing is None:
        client.create_record(
            Users.TABLE,
            {
                Users.EMAIL: wanted,
                Users.FIRST_NAME: first_name,
                Users.LAST_NAME: last_name,
                Users.STATUS: ACTIVE,
                Users.ACCESS_LEVEL: "Admin",
            },
        )
        logger.info("Created a bootstrap Admin row for a BOOTSTRAP_ADMIN_EMAILS address.")
        return
    fields = existing["fields"]
    if fields.get(Users.STATUS) != ACTIVE or fields.get(Users.ACCESS_LEVEL) != "Admin":
        logger.warning(
            "A BOOTSTRAP_ADMIN_EMAILS address already has a Users row that is not an "
            "Active Admin. Following the row, as Airtable is the source of truth."
        )


async def _finish_sign_in(
    request: Request, email: str, hosted_domain: str | None, first_name: str = "", last_name: str = ""
) -> RedirectResponse:
    """Check an email against the rules and Airtable, then start the session."""
    if not email_allowed(email, hosted_domain):
        return _to_frontend("/not-authorized?reason=domain")

    try:
        await run_in_threadpool(ensure_bootstrap_admin, email, first_name, last_name)
        user = await run_in_threadpool(find_active_user_by_email, email)
    except RequestException as error:
        logger.warning("Airtable lookup failed: %s", type(error).__name__)
        return _to_frontend("/not-authorized?reason=airtable")
    if user is None:
        clear_session(request)
        request.session[DENIED_EMAIL_KEY] = email.strip()
        return _to_frontend("/not-authorized")

    # Start from a clean session so nothing carries over from before sign in.
    clear_session(request)
    set_session_user(request, user)
    start_session_clock(request)
    view = permissions.base_view(user.access_level)
    set_stored_view(request, view)
    regenerate_session(request)  # A new session ID for every sign in (F31)
    return _to_frontend(permissions.home_path(view))


@router.get("/login")
async def login(request: Request):
    settings = get_settings()
    # Local testing without Google. config.py refuses this outside localhost.
    if settings.DEV_LOGIN_EMAIL:
        # No Google here, so treat the address's own domain as its hosted domain.
        dev_domain = settings.DEV_LOGIN_EMAIL.rsplit("@", 1)[-1]
        return await _finish_sign_in(request, settings.DEV_LOGIN_EMAIL, dev_domain)
    if not settings.google_configured:
        return _to_frontend("/not-authorized?reason=not-configured")
    # select_account lets people signed in to several Google accounts pick one.
    extra = {}
    if allowed_domain():
        # Only a hint so Google offers the work account first; the callback checks "hd" (F32).
        extra["hd"] = allowed_domain()
    return await oauth.google.authorize_redirect(
        request, callback_url(), prompt="select_account", **extra
    )


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
    return await _finish_sign_in(
        request,
        email,
        google_user.get("hd"),
        google_user.get("given_name", "") or "",
        google_user.get("family_name", "") or "",
    )


@router.get("/denied")
async def denied(request: Request):
    """The email of the last refused sign in, shown once on Not Authorized."""
    email = request.session.pop(DENIED_EMAIL_KEY, None)
    return {"email": email}


@router.post("/logout")
async def logout(request: Request):
    """Sign out. POST only: the SameSite cookie is never sent with another site's POST,
    so no other website can sign people out (findings F8)."""
    clear_session(request)
    # 303 so the browser follows with a GET to the home page. "/" rather than
    # FRONTEND_URL: the form is always posted from our own site, and the CSP's
    # form-action 'self' would block a redirect to any other address.
    return RedirectResponse("/", status_code=303)


@router.post("/logout-everywhere")
def logout_everywhere(request: Request):
    """Sign out on this device and every other one (F30). POST only, like /logout.

    Only a session that is still valid can do this, so an old copied cookie cannot be
    used to keep signing its owner out.
    """
    try:
        user = current_user(request)
    except HTTPException:
        user = None
    if user is not None:
        revocation.sign_out_everywhere(user.id, user.session_version)
        logger.info("Signed out everywhere: %s", user.id)
    clear_session(request)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def old_logout_link(request: Request):
    """Old bookmarks: go home without signing out, since any site could link here."""
    return _to_frontend("/")
