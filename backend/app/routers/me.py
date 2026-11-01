"""The signed in user: /api/me and /api/me/view."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app import permissions
from app.auth.deps import current_user
from app.auth.session import set_stored_view
from app.config import get_settings
from app.models.user import CurrentUser

router = APIRouter(prefix="/api/me", tags=["me"])


class ViewChoice(BaseModel):
    view: permissions.View


def _describe(user: CurrentUser) -> dict:
    dev_switch = get_settings().DEV_ALLOW_VIEW_SWITCH
    return {
        "user": {
            "id": user.airtable_record_id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "roles": user.roles,
        },
        "access_level": user.access_level,
        "base_view": permissions.base_view(user.access_level),
        "view": user.view,
        "home": permissions.home_path(user.view),
        "can_switch_view": permissions.can_switch_views(user.access_level, dev_switch),
        "dev_mode": dev_switch,
    }


@router.get("")
def get_me(user: CurrentUser = Depends(current_user)):
    return _describe(user)


@router.post("/view")
def switch_view(
    choice: ViewChoice, request: Request, user: CurrentUser = Depends(current_user)
):
    dev_switch = get_settings().DEV_ALLOW_VIEW_SWITCH
    if not permissions.can_choose_view(user.access_level, choice.view, dev_switch):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot use that view")
    set_stored_view(request, choice.view)
    return _describe(user.model_copy(update={"view": choice.view}))
