"""Tasks. Stub: every route answers 501 after checking permissions.

My Tasks, /my-tasks (everyone):
  Only the user's tasks across every project, sorted by due date with overdue on
  top. One-click status (Not Started, In Progress, Blocked, Done). Blocked tasks
  show "Waiting on [task]". Filters for this week and by project. A "Do this first"
  card and upcoming reminders.

Task detail, /tasks/:id:
  Status control, notes, Drive and Canva links, due date and timing rule, role and
  assignee (only admins can reassign), what must finish first and what is waiting
  on this, automatic reminders (7 days before and on the due date) and custom
  reminders.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import current_user, require_admin, require_can_edit
from app.models.user import CurrentUser

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _not_built():
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Tasks are not built yet")


@router.get("/mine")
def my_tasks(_: CurrentUser = Depends(current_user)):
    _not_built()


@router.get("/{task_id}")
def get_task(task_id: str, _: CurrentUser = Depends(current_user)):
    _not_built()


@router.patch("/{task_id}")
def update_task(task_id: str, _: CurrentUser = Depends(require_can_edit)):
    """When built, also check non-admins own the task, using the Assigned To field."""
    _not_built()


@router.post("/{task_id}/assign")
def assign_task(task_id: str, _: CurrentUser = Depends(require_admin)):
    _not_built()
