"""My reminders, and cancelling a custom reminder."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.airtable import client
from app.airtable.schema import Reminders
from app.auth.deps import current_user, require_can_edit
from app.models.user import CurrentUser
from app.services import reminders
from app.services.records import load_reminders, safe
from app.services.views import World, visible_projects

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("/mine")
def my_reminders(user: CurrentUser = Depends(current_user)):
    """Sent in the last 7 days, or scheduled for the next 14."""
    world = World()
    active = {p.id for p in visible_projects(world, user) if not p.closed}
    return {"reminders": reminders.mine(user.id, world.today, world.tasks, active)}


@router.delete("/{reminder_id}")
def cancel_reminder(reminder_id: str, user: CurrentUser = Depends(require_can_edit)):
    row = next((r for r in safe(load_reminders) if r.id == reminder_id), None)
    if row is None or row.kind != reminders.CUSTOM or user.id not in (row.recipient_id, row.created_by):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    if row.status != reminders.SCHEDULED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only scheduled reminders can be cancelled")
    client.update_record(Reminders.TABLE, row.id, {Reminders.STATUS: reminders.CANCELLED})
    return {"cancelled": True}
