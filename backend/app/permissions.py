"""All role and permission rules live here, in one place.

Two ideas to keep straight:

- Access Level comes from the Airtable Users table. It never changes in the app.
- View is "admin", "staff" or "partner". It decides what the person can do right
  now. An admin who switches to staff view gets staff permissions until they switch
  back. Partners always use partner view and cannot switch.

The view logic is mirrored for display only in frontend/src/auth/AuthContext.tsx,
and the "What each level can do" table in frontend/src/permissionsTable.ts mirrors
the rules below. The rules here are the ones that count, because the backend
enforces them.
"""

from dataclasses import dataclass
from typing import Literal

View = Literal["admin", "staff", "partner"]

ADMIN: View = "admin"
STAFF: View = "staff"
PARTNER: View = "partner"

# Which view each Access Level starts in.
# Project Lead is an assumption that is still being decided. To change it, edit
# this one line, then update the test that documents it in test_permissions.py.
BASE_VIEW_BY_ACCESS_LEVEL: dict[str, View] = {
    "Admin": ADMIN,
    "Project Lead": ADMIN,
    "Staff": STAFF,
    "Viewer": STAFF,
    "Partner": PARTNER,
}

ACCESS_LEVELS = ["Admin", "Project Lead", "Staff", "Viewer", "Partner"]

# Only these Access Levels may change anything. A blank or unknown Access Level
# is treated like Viewer, so a typo in Airtable never grants extra access.
ACCESS_LEVELS_THAT_CAN_EDIT = {"Admin", "Project Lead", "Staff", "Partner"}

# Access Levels that count as an admin when checking "at least one Active Admin".
ADMIN_ACCESS_LEVELS = {"Admin"}

# How long an author may delete their own note.
NOTE_DELETE_MINUTES = 15


def base_view(access_level: str | None) -> View:
    """Return the view an Access Level starts in (staff if unknown)."""
    return BASE_VIEW_BY_ACCESS_LEVEL.get(access_level or "", STAFF)


def can_choose_view(access_level: str | None, view: View, dev_switch: bool) -> bool:
    """May this person use this view?

    Partners only ever use partner view, and nobody else may choose it. Everyone
    else may use staff view, and admin view needs an admin Access Level (or the dev
    switch).
    """
    if base_view(access_level) == PARTNER:
        return view == PARTNER
    if view == PARTNER:
        return False
    return view == STAFF or dev_switch or base_view(access_level) == ADMIN


def can_switch_views(access_level: str | None, dev_switch: bool) -> bool:
    """Should this person see the view switch at all?"""
    if base_view(access_level) == PARTNER:
        return False
    return can_choose_view(access_level, ADMIN, dev_switch)


def effective_view(
    access_level: str | None, stored_view: str | None, dev_switch: bool
) -> View:
    """Work out the current view from what is stored in the session.

    Falls back to the base view if nothing valid is stored, or if the person is
    no longer allowed the stored view (for example, they were moved to Staff).
    """
    if stored_view in (ADMIN, STAFF, PARTNER) and can_choose_view(
        access_level, stored_view, dev_switch  # type: ignore[arg-type]
    ):
        return stored_view  # type: ignore[return-value]
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

    @property
    def is_partner(self) -> bool:
        return self.view == PARTNER


def can_update_own_tasks(actor: Actor) -> bool:
    """Update own tasks, notes, links and reminders."""
    return actor.is_admin or actor.access_level in ACCESS_LEVELS_THAT_CAN_EDIT


def can_view_all_projects(actor: Actor) -> bool:
    """See every project. Read only unless can_manage_projects is also true.

    Partners only see the projects they are listed on (see can_view_project).
    """
    return not actor.is_partner


def can_view_project(actor: Actor, user_id: str, partner_ids: list[str]) -> bool:
    """See one project."""
    if actor.is_partner:
        return user_id in partner_ids
    return True


def can_manage_projects(actor: Actor) -> bool:
    """Create projects, move Day 1, add one-off tasks, close and reopen."""
    return actor.is_admin


def can_delete_projects(actor: Actor) -> bool:
    """Delete a launch with its tasks, team, history, links and reminders."""
    return actor.is_admin


def can_export_projects(actor: Actor) -> bool:
    """Download a launch's tasks as a CSV file."""
    return actor.is_admin


def can_view_user_work(actor: Actor) -> bool:
    """See another person's launches and the tasks they have on each."""
    return actor.is_admin


def can_assign_tasks(actor: Actor) -> bool:
    """Assign or change anyone's task."""
    return actor.is_admin


def can_edit_task(actor: Actor, user_id: str, assigned_to: str | list[str] | None) -> bool:
    """Change a task's status, or add notes and links to it.

    Admins may change any task. Staff and partners only their own. Viewers none.
    """
    if actor.is_admin:
        return True
    people = assigned_to if isinstance(assigned_to, list) else [assigned_to] if assigned_to else []
    return can_update_own_tasks(actor) and bool(user_id) and user_id in people


def can_edit_task_details(actor: Actor) -> bool:
    """Change a task's due date, name or dependencies, or skip it."""
    return actor.is_admin


def can_edit_setup(actor: Actor) -> bool:
    """Edit templates, users and roles."""
    return actor.is_admin


def can_see_archive(actor: Actor) -> bool:
    """See the archive."""
    return actor.is_admin


def can_see_internal_notes(actor: Actor) -> bool:
    """See notes marked Internal. Partners only see Shared notes."""
    return not actor.is_partner


def can_see_history(actor: Actor) -> bool:
    """See a project's history log."""
    return not actor.is_partner


def can_share_notes(actor: Actor) -> bool:
    """Flip a note between Internal and Shared with partners."""
    return not actor.is_partner and can_update_own_tasks(actor)


def default_note_visibility(actor: Actor) -> str:
    """Partners' notes are shared with everyone on the project. Others are internal."""
    return "Shared" if actor.is_partner else "Internal"


def can_delete_note(actor: Actor, is_author: bool, minutes_old: float) -> bool:
    """Admins may delete any note. Authors may delete their own for 15 minutes."""
    if actor.is_admin:
        return True
    return (
        can_update_own_tasks(actor) and is_author and minutes_old <= NOTE_DELETE_MINUTES
    )


def can_set_reminder(actor: Actor) -> bool:
    """Set a reminder for yourself on any task you can see. Viewers cannot write."""
    return can_update_own_tasks(actor)


# --- User management, reassignment and archive (merged from the user management
# prototype in landerstuff/) ---------------------------------------------------

# A plain-English summary of what each Access Level reaches, shown with each person.
PROGRAM_ACCESS: dict[str, str] = {
    "Admin": "All programs",
    "Project Lead": "All programs",
    "Staff": "Program Assistants, Operations, Marketing, Grants",
    "Viewer": "Assigned program only",
    "Partner": "Launches they are added to",
}


def program_access(access_level: str | None) -> str:
    """What this Access Level can see (read only if unknown, like Viewer)."""
    return PROGRAM_ACCESS.get(access_level or "", PROGRAM_ACCESS["Viewer"])


def is_admin_level(access_level: str | None) -> bool:
    """Does this Access Level start in admin view (Admin, and Project Lead for now)?"""
    return base_view(access_level) == ADMIN


def can_reassign_tasks(actor: Actor) -> bool:
    """Move a batch of open tasks from one person to another."""
    return actor.is_admin


def can_remove_access(actor: Actor) -> bool:
    """Remove someone's access. Blocked while they still have open tasks."""
    return can_edit_setup(actor)


def can_see_directory(actor: Actor) -> bool:
    """See teammates' names for assignee labels. Partners are outside NMU, so no."""
    return not actor.is_partner
