"""Reading and writing the signed in user in the signed session cookie."""

from fastapi import Request

from app.config import get_settings
from app.models.user import SessionUser
from app.permissions import View
from app.services import clock

USER_KEY = "user"
VIEW_KEY = "view"
SIGNED_IN_AT_KEY = "signed_in_at"
SEEN_AT_KEY = "seen_at"

# A session ends this long after sign in, however active it is (findings F15).
MAX_SESSION_DAYS = 7
# Only rewrite the "last seen" time this often, to keep the cookie from changing on every request.
SEEN_AT_STEP_SECONDS = 5 * 60


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


def start_session_clock(request: Request) -> None:
    """Record when someone signed in. Called right after sign in."""
    now = clock.now().timestamp()
    request.session[SIGNED_IN_AT_KEY] = now
    request.session[SEEN_AT_KEY] = now


def session_expired(request: Request) -> bool:
    """True if the session was idle too long, or is older than MAX_SESSION_DAYS.

    The signed cookie cannot be cancelled on the server, so a copied cookie would
    otherwise keep working for as long as its owner stays active (findings F15).
    Otherwise this notes that the person was just seen.
    """
    now = clock.now().timestamp()
    # Sessions from before this check have no times yet: start their clock now.
    signed_in_at = request.session.setdefault(SIGNED_IN_AT_KEY, now)
    seen_at = request.session.setdefault(SEEN_AT_KEY, now)
    idle_limit = get_settings().SESSION_IDLE_HOURS * 60 * 60
    if now - seen_at > idle_limit or now - signed_in_at > MAX_SESSION_DAYS * 24 * 60 * 60:
        return True
    if now - seen_at > SEEN_AT_STEP_SECONDS:
        request.session[SEEN_AT_KEY] = now
    return False
