"""Signing someone out on every device at once (findings F15 option A, F30).

The session cookie is signed, not stored on the server, so the server cannot delete it.
Instead each Users row has a Session Version number. Sign-in copies it into the cookie,
and every request compares the two (current_user in auth/deps.py, through the cached
Users lookup). Raising the number on the row makes every cookie issued before it stop
working on that person's next request, on every device.

The number goes up when:
- the person chooses "Sign out of all devices",
- an admin chooses "Sign out everywhere" for them,
- an admin deactivates them or removes their access, changes their access level, or
  takes a role away from them (so a session never keeps powers they no longer have),
- an admin erases their personal details.
"""

from app.airtable import client
from app.airtable.schema import Users

ACTIVE = "Active"


def is_revoked(cookie_version: int, row_version: int) -> bool:
    """True if the person was signed out everywhere after this cookie was issued."""
    return row_version > cookie_version


def next_version_fields(current_version: int) -> dict:
    """The field change that signs the person out everywhere. Add it to another update,
    or write it with sign_out_everywhere."""
    return {Users.SESSION_VERSION: current_version + 1}


def change_ends_sessions(
    old_status: str | None,
    new_status: str | None,
    old_level: str | None,
    new_level: str | None,
    old_roles: list[str],
    new_roles: list[str] | None,
) -> bool:
    """True if an admin's change to someone takes away access, so their sessions must end."""
    if new_status is not None and new_status != old_status and new_status != ACTIVE:
        return True
    if new_level is not None and new_level != old_level:
        return True
    return new_roles is not None and bool(set(old_roles) - set(new_roles))


def sign_out_everywhere(user_id: str, current_version: int) -> None:
    """Raise the person's Session Version, ending every session they have."""
    client.update_record(Users.TABLE, user_id, next_version_fields(current_version))
