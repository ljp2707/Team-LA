"""Admin tools: the test email on the Users page System card."""

from fastapi import APIRouter, Depends

from app.auth.deps import require_admin
from app.config import get_settings
from app.email import gmail, templates
from app.models.user import CurrentUser

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/test-email")
def send_test_email(user: CurrentUser = Depends(require_admin)):
    """Send the signed in admin a test email, and show Gmail's error if it fails."""
    email = templates.test_email(user.first_name)
    dry_run = get_settings().REMINDERS_DRY_RUN
    try:
        gmail.send_email(user.email, *email)
    except gmail.EmailError as error:
        return {"sent": False, "dry_run": dry_run, "error": str(error), "to": user.email}
    except Exception as error:  # noqa: BLE001 - shown to the admin, never secret values
        return {"sent": False, "dry_run": dry_run, "error": type(error).__name__, "to": user.email}
    if dry_run:
        return {
            "sent": False,
            "dry_run": True,
            "to": user.email,
            "error": "REMINDERS_DRY_RUN is true, so the email was logged and not sent.",
        }
    return {"sent": True, "dry_run": False, "to": user.email, "error": None}
