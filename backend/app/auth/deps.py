"""FastAPI dependencies that protect routes.

Every API route must use one of these. The frontend guards are only a convenience.
"""

import logging

from fastapi import Depends, HTTPException, Request, status
from requests import RequestException

from app import permissions
from app.auth.session import (
    clear_session,
    get_session_user,
    get_stored_view,
    set_session_user,
)
from app.config import get_settings
from app.models.user import CurrentUser, find_active_user_by_id

logger = logging.getLogger(__name__)


def current_user(request: Request) -> CurrentUser:
    """Return the signed in user, or answer 401.

    The cookie is only trusted for who the person is. Their Status and Access Level
    are checked against Airtable (cached 30 seconds), so deactivating someone or
    changing their access takes effect right away, not when they next sign in.
    """
    session_user = get_session_user(request)
    if session_user is None:
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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    set_session_user(request, fresh)
    view = permissions.effective_view(
        fresh.access_level,
        get_stored_view(request),
        get_settings().DEV_ALLOW_VIEW_SWITCH,
    )
    return CurrentUser(**fresh.model_dump(), view=view)


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Allow only someone currently in admin view."""
    if user.view != permissions.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin view required")
    return user


def require_can_edit(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    """Allow anyone except read only users such as Viewers."""
    if not permissions.can_update_own_tasks(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read only access")
    return user
