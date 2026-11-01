"""Templates. Stub: every route answers 501 after checking permissions.

Templates, /templates (admin):
  One template per program type, a list of steps with timing, default role and
  dependencies. Duplicate, save a project as a template, version drafts that do not
  affect running projects. A "From past launches" panel showing steps often late,
  skipped or added.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import require_admin
from app.models.user import CurrentUser

router = APIRouter(
    prefix="/api/templates", tags=["templates"], dependencies=[Depends(require_admin)]
)


def _not_built():
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Templates are not built yet")


@router.get("")
def list_templates():
    _not_built()


@router.post("")
def create_template():
    _not_built()


@router.get("/{template_id}")
def get_template(template_id: str):
    _not_built()
