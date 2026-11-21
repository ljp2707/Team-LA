"""Audit page, /api/audit (admin, read only): who did which admin action, newest first (F35).

The Audit Log rows hold record IDs only (findings F34). Names are looked up here, at
read time, so a person whose details were erased shows as "Former team member" without
the audit rows ever changing. There are no routes that change or delete audit rows.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app import audit
from app.airtable import client
from app.airtable.schema import AuditLog
from app.auth.deps import require_admin
from app.security import RECORD_ID_PATTERN
from app.services import clock
from app.services.views import World

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_admin)])

MAX_ENTRIES = 500


def _when(fields: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(fields.get(AuditLog.WHEN, ""))
    except ValueError:
        return None


def _target_text(world: World, target: str) -> str:
    """ "user_id=rec1, task_id=rec2" as "Sam Lee, Design flyer", keeping IDs it cannot name."""
    lookups = {
        "user_id": world.users,
        "role_id": world.roles,
        "project_id": world.projects,
        "task_id": world.tasks_by_id,
        "template_id": world.templates,
        "site_id": world.sites,
    }
    parts = []
    for pair in filter(None, (p.strip() for p in target.split(","))):
        key, _, record_id = pair.partition("=")
        record = lookups.get(key, {}).get(record_id)
        parts.append(getattr(record, "name", "") or record_id)
    return ", ".join(parts)


@router.get("")
def list_audit(
    days: int = Query(30, ge=1, le=3660),
    actor: str | None = Query(None, pattern=RECORD_ID_PATTERN),
):
    world = World()
    since = clock.now().astimezone(timezone.utc) - timedelta(days=days)
    rows = []
    for record in client.all_records(AuditLog.TABLE):
        fields = record["fields"]
        when = _when(fields)
        if when is None or when < since:
            continue
        if actor and fields.get(AuditLog.ACTOR) != actor:
            continue
        rows.append((when, fields))
    rows.sort(key=lambda pair: pair[0], reverse=True)

    def person(record_id: str) -> str:
        user = world.users.get(record_id)
        return user.name if user else record_id

    entries = [
        {
            "when": when.isoformat(),
            "action": fields.get(AuditLog.ACTION, ""),
            "label": audit.label(fields.get(AuditLog.ACTION, "")),
            "actor_id": fields.get(AuditLog.ACTOR, ""),
            "actor_name": person(fields.get(AuditLog.ACTOR, "")),
            "target": _target_text(world, fields.get(AuditLog.TARGET, "")),
            "status": fields.get(AuditLog.STATUS),
            "request_id": fields.get(AuditLog.REQUEST_ID, ""),
        }
        for when, fields in rows[:MAX_ENTRIES]
    ]
    # Everyone who has ever done an admin action, for the filter.
    actor_ids = {r["fields"].get(AuditLog.ACTOR, "") for r in client.all_records(AuditLog.TABLE)} - {""}
    actors = sorted(actor_ids, key=person)
    return {
        "entries": entries,
        "more": len(rows) > MAX_ENTRIES,
        "actors": [{"id": a, "name": person(a)} for a in actors],
    }
