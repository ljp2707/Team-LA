"""Project history: every change a person makes writes an Activity Log row here.

Notes on tasks are Activity Log rows too (Type "Note"), so they share the same
visibility rules: partners only ever see rows marked Shared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.airtable import client
from app.airtable.schema import ActivityLog
from app.permissions import Actor, can_see_history, can_see_internal_notes
from app.services.records import LogRec, load_log

# Types written with typecast, so Airtable adds any that are missing.
TYPES = [
    "Note",
    "Status Change",
    "Date Change",
    "Reassignment",
    "System",
    "Link",
    "Task Added",
    "Handoff",
    "Project Created",
    "Project Closed",
]

INTERNAL = "Internal"
SHARED = "Shared"


@dataclass
class Event:
    session_id: str | None
    work_id: str | None
    author_id: str | None
    type: str
    text: str
    from_value: str | None = None
    to_value: str | None = None
    visibility: str = INTERNAL
    batch: str | None = None


def _fields(event: Event) -> dict[str, Any]:
    fields: dict[str, Any] = {
        ActivityLog.TYPE: event.type,
        ActivityLog.TEXT: event.text,
        ActivityLog.VISIBILITY: event.visibility,
    }
    if event.session_id:
        fields[ActivityLog.SESSION] = [event.session_id]
    if event.work_id:
        fields[ActivityLog.WORK] = [event.work_id]
    if event.author_id:
        fields[ActivityLog.AUTHOR] = [event.author_id]
    if event.from_value is not None:
        fields[ActivityLog.FROM] = str(event.from_value)
    if event.to_value is not None:
        fields[ActivityLog.TO] = str(event.to_value)
    if event.batch:
        fields[ActivityLog.BATCH] = event.batch
    return fields


def log_event(
    session_id: str | None,
    work_id: str | None,
    author_id: str | None,
    type: str,
    text: str,
    from_value: str | None = None,
    to_value: str | None = None,
    visibility: str = INTERNAL,
    batch: str | None = None,
) -> dict[str, Any]:
    """Write one Activity Log entry and return the created record."""
    return log_events(
        [
            Event(
                session_id,
                work_id,
                author_id,
                type,
                text,
                from_value,
                to_value,
                visibility,
                batch,
            )
        ]
    )[0]


def log_events(events: list[Event]) -> list[dict[str, Any]]:
    """Write several entries in batches of 10."""
    return client.create_records(
        ActivityLog.TABLE, [_fields(e) for e in events], typecast=True
    )


def visible_to(row: LogRec, actor: Actor) -> bool:
    if row.visibility == SHARED:
        return True
    return can_see_internal_notes(actor)


def is_detail_row(row: LogRec) -> bool:
    """Per-task rows written alongside a Day 1 move. Kept for undo, not shown."""
    return bool(row.batch) and bool(row.work_id) and row.type == "Date Change"


def for_project(session_id: str, actor: Actor, log: list[LogRec] | None = None) -> list[LogRec]:
    """The project's history, newest first, without rows this viewer may not see.

    Partners never see the history log, so they get an empty list.
    """
    if not can_see_history(actor):
        return []
    rows = load_log() if log is None else log
    mine = [
        r
        for r in rows
        if r.session_id == session_id and not is_detail_row(r) and visible_to(r, actor)
    ]
    return sorted(mine, key=lambda r: (r.created is not None, r.created), reverse=True)


def notes_for_task(work_id: str, actor: Actor, log: list[LogRec] | None = None) -> list[LogRec]:
    """Notes on one task, oldest first, as a thread."""
    rows = load_log() if log is None else log
    notes = [
        r for r in rows if r.work_id == work_id and r.type == "Note" and visible_to(r, actor)
    ]
    return sorted(notes, key=lambda r: (r.created is not None, r.created))
