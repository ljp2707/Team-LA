"""Simple per-person and per-address request limits (findings F5).

Too many requests at once can push Airtable past 5 requests a second, and Airtable
then locks the whole base for 30 seconds. These limits stop one script, or one
stuck browser tab, from doing that. The app runs as one process on Railway, so
counting in memory is enough.
"""

import math
import re
import threading
from collections import deque
from dataclasses import dataclass

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services import clock


@dataclass(frozen=True)
class Rule:
    name: str
    methods: frozenset[str]
    path: re.Pattern
    limit: int  # requests allowed...
    seconds: int  # ...in this many seconds
    per_person: bool  # count by signed-in person, otherwise by internet address
    message: str = "Too many requests. Please wait a minute and try again."


WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Each nudge sends real email, so one admin is capped per hour on top of the usual write
# limit. (Once per person per task per day is checked in the route, from Airtable.)
NUDGES_PER_HOUR = 20

# The first rule that matches a request applies. Requests no rule matches are not limited.
RULES = [
    Rule("sign-in", frozenset({"GET"}), re.compile(r"^/auth/(login|callback)$"), 10, 60, per_person=False),
    Rule(
        "nudges",
        frozenset({"POST"}),
        re.compile(r"^/api/tasks/[^/]+/nudge$"),
        NUDGES_PER_HOUR,
        3600,
        per_person=True,
        message="You have sent a lot of nudges this hour. Please try again later.",
    ),
    # Browsers send these on their own; this stops anyone flooding the logs (F25).
    Rule("csp reports", frozenset({"POST"}), re.compile(r"^/api/security/csp-report$"), 30, 60, per_person=False),
    Rule("uploads", frozenset({"POST"}), re.compile(r"^/api/.+/files$"), 20, 3600, per_person=True),
    Rule("calendar feed", frozenset({"GET"}), re.compile(r"^/calendar/"), 60, 60, per_person=False),
    Rule("public", frozenset({"GET"}), re.compile(r"^/api/public/"), 60, 60, per_person=False),
    Rule("writes", WRITES, re.compile(r"^/api/"), 60, 60, per_person=True),
]

# Forget the oldest addresses rather than grow without end.
MAX_KEYS = 10_000

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = {}


def reset() -> None:
    """Forget every count. Used by the tests."""
    with _lock:
        _hits.clear()


def _key(rule: Rule, scope: Scope) -> str:
    if rule.per_person:
        user = (scope.get("session") or {}).get("user") or {}
        if user.get("airtable_record_id"):
            return "user:" + user["airtable_record_id"]
    client = scope.get("client")
    return "ip:" + (client[0] if client else "unknown")


def check(rule: Rule, key: str) -> int:
    """Count this request. Returns 0 if allowed, or the seconds to wait if not."""
    now = clock.now().timestamp()
    with _lock:
        hits = _hits.setdefault((rule.name, key), deque())
        while hits and hits[0] <= now - rule.seconds:
            hits.popleft()
        if len(hits) >= rule.limit:
            return max(1, math.ceil(hits[0] + rule.seconds - now))
        hits.append(now)
        if len(_hits) > MAX_KEYS:
            _hits.pop(next(iter(_hits)))
        return 0


class RateLimit:
    """Answers 429 with Retry-After when a rule's limit is used up.

    Must sit inside SessionMiddleware, so it can tell who is signed in.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            rule = next(
                (r for r in RULES if scope["method"] in r.methods and r.path.match(scope["path"])),
                None,
            )
            if rule:
                wait = check(rule, _key(rule, scope))
                if wait:
                    response = JSONResponse(
                        {"detail": rule.message},
                        status_code=429,
                        headers={"Retry-After": str(wait)},
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
