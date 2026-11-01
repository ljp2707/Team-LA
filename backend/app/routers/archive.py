"""Archive. Stub: every route answers 501 after checking permissions.

Archive, /archive (admin):
  Finished projects, searchable by site and date. Planned vs actual dates per task,
  with late, skipped and added markers. Start a new launch from a past one.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import require_admin

router = APIRouter(
    prefix="/api/archive", tags=["archive"], dependencies=[Depends(require_admin)]
)


@router.get("")
def list_archive():
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Archive is not built yet")
