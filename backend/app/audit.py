"""The audit trail: one Audit Log row for every admin action (findings F34).

How it works:
- require_admin (auth/deps.py) calls mark_admin_action, which notes the admin's record ID
  on the request. Routes that check admin rights another way call it too.
- AuditTrail, a middleware, writes one row after the route answers, but only for a change
  (POST, PUT, PATCH, DELETE) that succeeded (status below 400). Refused and failed
  requests change nothing, and the security log already records refusals.

A row holds the method and route ("PATCH /api/users/{user_id}"), the admin's record ID,
the record IDs from the address, the status code, the time and the request ID. Never the
request body, names or emails: an audit row must not need changing when someone's
details are erased, and the table is append only (client.APPEND_ONLY_TABLES).

If Airtable cannot take the row, the action still stands (it already happened), and an
"audit_write_failed" security event goes to the server log with the same details, so the
log is the backup copy.
"""

import logging
from datetime import timezone

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from app.airtable import client
from app.airtable.schema import AuditLog
from app.security_events import security_event
from app.services import clock

ACTOR_STATE_KEY = "audit_actor"
CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_TARGET_LENGTH = 200

logger = logging.getLogger(__name__)

# Plain words for the Audit page. Anything missing is shown as its route.
ACTION_LABELS = {
    "POST /api/users": "Added a person",
    "PATCH /api/users/{user_id}": "Changed a person",
    "DELETE /api/users/{user_id}": "Removed a person's access",
    "POST /api/users/{user_id}/erase": "Removed a person's personal details",
    "POST /api/users/{user_id}/sign-out-everywhere": "Signed a person out everywhere",
    "POST /api/users/hand-off": "Handed off a person's tasks",
    "POST /api/roles": "Added a role",
    "PATCH /api/roles/{role_id}": "Changed a role",
}


def mark_admin_action(request: Request, actor_id: str) -> None:
    """Note that this request is an admin action by this person."""
    setattr(request.state, ACTOR_STATE_KEY, actor_id)


def nothing_changed(request: Request) -> None:
    """For an admin route that answered without doing anything (such as a nudge in dry run
    mode): no audit row."""
    setattr(request.state, ACTOR_STATE_KEY, None)


def label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def build_row(method: str, route: str, path_params: dict, actor_id: str, status: int, request_id: str) -> dict:
    target = ", ".join(f"{key}={value}" for key, value in sorted(path_params.items()))
    return {
        AuditLog.ACTION: f"{method} {route}",
        AuditLog.WHEN: clock.now().astimezone(timezone.utc).isoformat(timespec="seconds"),
        AuditLog.ACTOR: actor_id,
        AuditLog.TARGET: target[:MAX_TARGET_LENGTH],
        AuditLog.STATUS: status,
        AuditLog.REQUEST_ID: request_id,
    }


def write_row(row: dict) -> None:
    try:
        client.create_records(AuditLog.TABLE, [row])
    except Exception as error:  # Any failure: the log line below is the record instead
        security_event(
            "audit_write_failed",
            level=logging.ERROR,
            action=row[AuditLog.ACTION],
            actor=row[AuditLog.ACTOR],
            target=row[AuditLog.TARGET],
            status=row[AuditLog.STATUS],
            error=type(error).__name__,
        )


class AuditTrail:
    """Write an Audit Log row after each successful admin change."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in CHANGING_METHODS:
            return await self.app(scope, receive, send)
        status = 0

        async def send_and_note_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        await self.app(scope, receive, send_and_note_status)

        state = scope.get("state", {})
        actor = state.get(ACTOR_STATE_KEY)
        route = scope.get("route")
        if not actor or route is None or not 200 <= status < 400:
            return
        row = build_row(
            scope["method"], route.path, scope.get("path_params", {}), actor, status, state.get("request_id", "")
        )
        security_event("admin_action", action=row[AuditLog.ACTION], actor=actor, target=row[AuditLog.TARGET], status=status)
        # After the answer is sent, so the admin never waits on this write.
        await run_in_threadpool(write_row, row)
