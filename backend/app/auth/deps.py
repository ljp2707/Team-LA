"""FastAPI dependencies that protect routes.

Every API route must use one of these. The frontend guards are only a convenience.
"""

import logging

from fastapi import Depends, HTTPException, Request, status
from requests import RequestException

from app import audit, permissions
from app.auth import revocation
from app.auth.session import (
    clear_session,
    get_session_user,
    get_stored_view,
    session_expired,
    set_session_user,
)
from app.config import get_settings
from app.security_events import security_event
from app.models.user import CurrentUser, find_active_user_by_id

logger = logging.getLogger(__name__)


def current_user(request: Request) -> CurrentUser:
    """Return the signed in user, or answer 401.

    The cookie is only trusted for who the person is. Their Status and Access Level
    are checked against Airtable (cached 30 seconds), so deactivating someone or
    changing their access takes effect right away, not when they next sign in. Their
    Session Version is checked too, so "sign out everywhere" ends this cookie (F30).
    """
    session_user = get_session_user(request)
    if session_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    if session_expired(request):
        clear_session(request)
        security_event("session_expired", user=session_user.airtable_record_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    try:
        fresh = find_active_user_by_id(session_user.airtable_record_id)
    except RequestException as error:
        logger.warning("Airtable lookup failed: %s", type(error).__name__)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Airtable is not reachable"
        ) from error

    if fresh is None:
        clear_session(request)
        # Deactivated, or removed from Users, while signed in
        security_event("session_ended_inactive_user", level=logging.WARNING, user=session_user.airtable_record_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    # F30: signed out everywhere since this cookie was issued. Checked before the cookie
    # is refreshed below, which would otherwise copy in the new number.
    if revocation.is_revoked(session_user.session_version, fresh.session_version):
        clear_session(request)
        # Normal after "sign out everywhere"; many in a row for one person can mean a copied cookie.
        security_event("session_revoked", level=logging.WARNING, user=session_user.airtable_record_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    request.state.user_id = fresh.airtable_record_id  # For security events (F36)

    set_session_user(request, fresh)
    view = permissions.effective_view(
        fresh.access_level,
        get_stored_view(request),
        get_settings().DEV_ALLOW_VIEW_SWITCH,
    )
    return CurrentUser(**fresh.model_dump(), view=view)


def require_admin(request: Request, user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Allow only someone currently in admin view. Their changes go in the audit trail (F34)."""
    if not permissions.can_use_admin_pages(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin view required")
    audit.mark_admin_action(request, user.id)
    return user


def require_can_edit(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Allow anyone except read only users such as Viewers."""
    if not permissions.can_update_own_tasks(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read only access")
    return user


def require_internal(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Allow NMU staff and admins, but not partners. Used for launch history."""
    if not permissions.can_see_history(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available to partners")
    return user
