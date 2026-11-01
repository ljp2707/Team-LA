"""Health checks: /api/health and /api/health/airtable."""

from fastapi import APIRouter, Depends

from app.airtable import client
from app.auth.deps import require_admin
from app.models.user import CurrentUser

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
def health():
    """Public, so Railway can tell the app is running."""
    return {"status": "ok"}


@router.get("/airtable")
def airtable_health(_: CurrentUser = Depends(require_admin)):
    """Admin only. The record count for each table, to confirm the connection."""
    tables = client.table_counts()
    return {"connected": all(t["error"] is None for t in tables), "tables": tables}
