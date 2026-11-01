"""Users and roles. Stub: every route answers 501 after checking permissions.

Users and roles, /users (admin):
  People with their roles (a person can hold several) and access level. Hand off
  all of one person's open tasks to someone else. A permissions table for Admin,
  Staff and Partner (phase 2).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import require_admin

router = APIRouter(
    prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)]
)


def _not_built():
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Users are not built yet")


@router.get("")
def list_users():
    _not_built()


@router.post("/hand-off")
def hand_off_tasks():
    _not_built()
