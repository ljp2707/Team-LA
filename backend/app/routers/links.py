"""Removing links, and deleting or sharing notes: /api/links/{id} and /api/notes/{id}."""

from fastapi import APIRouter, Depends, HTTPException, status

from app import permissions
from app.airtable import client
from app.airtable.schema import ActivityLog, Links
from app.auth.deps import require_can_edit
from app.models.task import NoteVisibilityIn
from app.models.user import CurrentUser
from app.services import clock, history
from app.services.views import World, check_project_access, note_dict

router = APIRouter(prefix="/api", tags=["links and notes"])


@router.delete("/links/{link_id}")
def remove_link(link_id: str, user: CurrentUser = Depends(require_can_edit)):
    world = World()
    link = next((l for l in world.links if l.id == link_id), None)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    session_id = link.session_id
    if link.work_id:
        task = world.task(link.work_id)
        check_project_access(user, world.project(task.session_id or ""))
        if not permissions.can_edit_task(user.actor, user.id, task.assignees):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only change tasks assigned to you")
        session_id = task.session_id
        what = f"removed the link {link.title} from {task.name}"
    else:
        if not permissions.can_manage_projects(user.actor):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can change project links")
        what = f"removed the link {link.title}"
    client.delete_records(Links.TABLE, [link.id])
    history.log_event(session_id, link.work_id, user.id, "Link", what)
    return {"removed": True}


def _note(world: World, note_id: str, user: CurrentUser):
    row = next((r for r in world.log if r.id == note_id and r.type == "Note"), None)
    if row is None or not history.visible_to(row, user.actor):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    if row.session_id:
        check_project_access(user, world.project(row.session_id))
    return row


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, user: CurrentUser = Depends(require_can_edit)):
    world = World()
    row = _note(world, note_id, user)
    minutes = (clock.now() - row.created).total_seconds() / 60 if row.created else 1e9
    if not permissions.can_delete_note(user.actor, row.author_id == user.id, minutes):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"You can delete your own notes for {permissions.NOTE_DELETE_MINUTES} minutes after posting.",
        )
    client.delete_records(ActivityLog.TABLE, [row.id])
    task = world.tasks_by_id.get(row.work_id or "")
    author = world.user_short(row.author_id) or "someone"
    history.log_event(
        row.session_id,
        row.work_id,
        user.id,
        "System",
        f"deleted a note by {author}" + (f" on {task.name}" if task else ""),
    )
    return {"deleted": True}


@router.patch("/notes/{note_id}")
def share_note(note_id: str, body: NoteVisibilityIn, user: CurrentUser = Depends(require_can_edit)):
    world = World()
    row = _note(world, note_id, user)
    task = world.tasks_by_id.get(row.work_id or "")
    if not permissions.can_share_notes(user.actor) or (
        task and not permissions.can_edit_task(user.actor, user.id, task.assignees)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot change who sees this note")
    if body.visibility != row.visibility:
        client.update_record(ActivityLog.TABLE, row.id, {ActivityLog.VISIBILITY: body.visibility}, typecast=True)
    fresh = World()
    updated = next(r for r in fresh.log if r.id == row.id)
    return note_dict(fresh, updated, user)
