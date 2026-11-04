"""Health checks: /api/health, /api/health/airtable and /api/health/auth."""

from fastapi import APIRouter, Depends

from app.airtable import client
from app.auth.deps import require_admin
from app.auth.google import callback_url
from app.config import get_settings
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


@router.get("/auth")
def auth_health(_: CurrentUser = Depends(require_admin)):
    """Admin only. Sign in settings, never the secret values themselves."""
    settings = get_settings()
    return {
        "client_id_set": settings.google_configured,
        "client_secret_set": bool(settings.GOOGLE_CLIENT_SECRET.strip())
        and settings.GOOGLE_CLIENT_SECRET.strip() != "replace-me",
        "callback_url": callback_url(),
        "dev_login": bool(settings.DEV_LOGIN_EMAIL),
        "allowed_email_domain": settings.ALLOWED_EMAIL_DOMAIN,
        "gmail_ready": bool(settings.GMAIL_REFRESH_TOKEN and settings.GMAIL_SENDER),
        "gmail_sender": settings.GMAIL_SENDER,
        "reminders_dry_run": settings.REMINDERS_DRY_RUN,
    }
