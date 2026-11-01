"""All role and permission rules live here, in one place.

Two ideas to keep straight:

- Access Level comes from the Airtable Users table. It never changes in the app.
- View is "admin" or "staff". It decides what the person can do right now. An
  admin who switches to staff view gets staff permissions until they switch back.

The view logic is mirrored for display only in frontend/src/auth/AuthContext.tsx.
The rules below are the ones that count, because the backend enforces them.
"""

from dataclasses import dataclass
from typing import Literal

View = Literal["admin", "staff"]

ADMIN: View = "admin"
STAFF: View = "staff"

# Which view each Access Level starts in.
# Project Lead is an assumption that is still being decided. To change it, edit
# this one line, then update the test that documents it in test_permissions.py.
BASE_VIEW_BY_ACCESS_LEVEL: dict[str, View] = {
    "Admin": ADMIN,
    "Project Lead": ADMIN,
    "Staff": STAFF,
    "Viewer": STAFF,
}

# Only these Access Levels may change anything. A blank or unknown Access Level
# is treated like Viewer, so a typo in Airtable never grants extra access.
ACCESS_LEVELS_THAT_CAN_EDIT = {"Admin", "Project Lead", "Staff"}


def base_view(access_level: str | None) -> View:
    """Return the view an Access Level starts in (staff if unknown)."""
    return BASE_VIEW_BY_ACCESS_LEVEL.get(access_level or "", STAFF)


def can_choose_view(access_level: str | None, view: View, dev_switch: bool) -> bool:
    """May this person use this view? Everyone may use staff view."""
    return view == STAFF or dev_switch or base_view(access_level) == ADMIN


def can_switch_views(access_level: str | None, dev_switch: bool) -> bool:
    """Should this person see the view switch at all?"""
    return can_choose_view(access_level, ADMIN, dev_switch)


def effective_view(
    access_level: str | None, stored_view: str | None, dev_switch: bool
) -> View:
    """Work out the current view from what is stored in the session.

    Falls back to the base view if nothing valid is stored, or if the person is
    no longer allowed the stored view (for example, they were moved to Staff).
    """
    if stored_view in (ADMIN, STAFF) and can_choose_view(
        access_level, stored_view, dev_switch
    ):
        return stored_view
    return base_view(access_level)


def home_path(view: View) -> str:
    """Where someone lands after signing in."""
    return "/dashboard" if view == ADMIN else "/my-tasks"


@dataclass(frozen=True)
class Actor:
    """The two facts every permission check below depends on."""

    access_level: str | None
    view: View

    @property
    def is_admin(self) -> bool:
        return self.view == ADMIN


def can_update_own_tasks(actor: Actor) -> bool:
    """Update own tasks, notes, links and reminders."""
    return actor.is_admin or actor.access_level in ACCESS_LEVELS_THAT_CAN_EDIT


def can_view_all_projects(actor: Actor) -> bool:
    """See every project. Read only unless can_manage_projects is also true."""
    return True


def can_manage_projects(actor: Actor) -> bool:
    """Create projects and move Day 1."""
    return actor.is_admin


def can_assign_tasks(actor: Actor) -> bool:
    """Assign or change anyone's task."""
    return actor.is_admin


def can_edit_setup(actor: Actor) -> bool:
    """Edit templates, users and roles."""
    return actor.is_admin


def can_see_archive(actor: Actor) -> bool:
    """See the archive."""
    return actor.is_admin
