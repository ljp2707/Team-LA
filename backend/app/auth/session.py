"""Reading and writing the signed in user in the signed session cookie."""

from fastapi import Request

from app.models.user import SessionUser
from app.permissions import View

USER_KEY = "user"
VIEW_KEY = "view"


def get_session_user(request: Request) -> SessionUser | None:
    data = request.session.get(USER_KEY)
    return SessionUser(**data) if data else None


def set_session_user(request: Request, user: SessionUser) -> None:
    request.session[USER_KEY] = user.model_dump()


def get_stored_view(request: Request) -> str | None:
    return request.session.get(VIEW_KEY)


def set_stored_view(request: Request, view: View) -> None:
    request.session[VIEW_KEY] = view


def clear_session(request: Request) -> None:
    request.session.clear()
