"""Projects. Stub: every route answers 501 after checking permissions.

Dashboard, /dashboard (admin view):
  One card per active project with site, program type, Day 1, % complete, overdue
  count, next milestone and lead instructor. A summary row (active launches, overdue,
  blocked, next Day 1). Sort and filter. Clicking a card opens the project.

Projects, /projects (staff view):
  The same cards as the dashboard, read only.

New project, /projects/new (admin):
  Start from a template or a past launch. Program type, site, site type, program
  name, Day 1, program hours, location, lead instructors, partner contact, Google
  Drive folder link. Site profile pre-fills. Preview of the generated task list with
  default owner by role and an optional person per task. Add a one-off task. Create.

Project detail, /projects/:id:
  Summary (Day 1, % complete, overdue, hours, lead instructor). Move Day 1, which
  shifts open due dates and reminders and keeps finished tasks' dates, with an undo
  notice. Tasks grouped before, during and after the program. Late tasks show how
  many tasks depend on them. One-off tasks. Partner contact and Drive link. History log.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import current_user, require_admin
from app.models.user import CurrentUser

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _not_built():
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Projects are not built yet")


@router.get("")
def list_projects(_: CurrentUser = Depends(current_user)):
    _not_built()


@router.post("")
def create_project(_: CurrentUser = Depends(require_admin)):
    _not_built()


@router.get("/{project_id}")
def get_project(project_id: str, _: CurrentUser = Depends(current_user)):
    _not_built()


@router.post("/{project_id}/move-day-one")
def move_day_one(project_id: str, _: CurrentUser = Depends(require_admin)):
    _not_built()
