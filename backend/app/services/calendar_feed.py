"""A private calendar feed (iCalendar, .ics) of one person's tasks.

Someone turns it on from My Tasks. They get a secret link that Google Calendar
(or Apple Calendar, Outlook) subscribes to and checks every few hours. The link is
the only key: anyone with it can read that person's task list, so the token is
long and random, can be reset, and is cleared when the person loses access.

The text is written here directly (no iCalendar library is installed), following
RFC 5545: CRLF line endings, text escaping, and long lines folded at 75 bytes.
"""

from __future__ import annotations

import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from app import permissions
from app.config import get_settings
from app.email.templates import task_url
from app.permissions import Actor
from app.services import logic
from app.services.records import TaskRec, UserRec
from app.services.views import World

# 32 random bytes, about 43 URL-safe characters.
TOKEN_BYTES = 32
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,128}$")
UID_DOMAIN = "nmu-launches"


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def feed_url(token: str) -> str:
    return f"{get_settings().APP_URL.rstrip('/')}/calendar/{token}.ics"


def google_subscribe_url(token: str) -> str:
    """Opens Google Calendar's "add calendar by URL" screen with the feed filled in."""
    webcal = re.sub(r"^https?://", "webcal://", feed_url(token))
    return f"https://calendar.google.com/calendar/render?cid={quote(webcal, safe='')}"


def user_for_token(world: World, token: str) -> UserRec | None:
    """The Active person whose feed this is, or None. Compared in constant time."""
    if not TOKEN_PATTERN.match(token or ""):
        return None
    found = None
    for user in world.users.values():
        if user.calendar_token and hmac.compare_digest(user.calendar_token, token):
            found = user
    return found if found and found.active else None


def feed_tasks(world: World, user: UserRec) -> list[TaskRec]:
    """Their open tasks with a due date, on launches that are not closed.

    The same tasks as My Tasks, without finished ones and those with no date.
    Partners only ever get tasks on launches they are listed on.
    """
    actor = Actor(user.access_level, permissions.base_view(user.access_level))
    out = []
    for t in world.tasks:
        project = world.projects.get(t.session_id or "")
        if (
            t.is_assigned(user.id)
            and t.due is not None
            and logic.is_open(t.status)
            and project is not None
            and not project.closed
            and permissions.can_view_project(actor, user.id, project.partner_ids)
        ):
            out.append(t)
    return sorted(out, key=lambda t: (t.due, t.name))


# --- iCalendar text ------------------------------------------------------------


def escape_text(value: str) -> str:
    """Escape a TEXT value: backslash, semicolon, comma and line breaks."""
    value = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return re.sub(r"\r\n|\r|\n", "\\\\n", value)


def fold(line: str) -> str:
    """Split a content line into pieces of at most 75 bytes, never inside a character."""
    out: list[str] = []
    current = ""
    size = 0
    limit = 75
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > limit:
            out.append(current)
            current, size, limit = " ", 1, 75  # Continuation lines start with a space
        current += char
        size += width
    out.append(current)
    return "\r\n".join(out)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_feed(world: World, user: UserRec, now: datetime | None = None) -> str:
    stamp = _stamp(now or datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//No More Under//NMU Launches//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text('NMU Launches tasks')}",
        f"X-WR-CALDESC:{escape_text(f'Tasks assigned to {user.name} in NMU Launches')}",
        # Hints for apps that honor them. Google Calendar picks its own schedule.
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for t in feed_tasks(world, user):
        project = world.projects[t.session_id or ""]
        waiting = logic.waiting_on(t, world.tasks_by_id)
        link = task_url(t.id)
        description = (
            f"Status: {logic.display_status(t, waiting)}\n"
            f"Launch: {project.name}\n"
            f"Open in NMU Launches: {link}"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:{t.id}@{UID_DOMAIN}",  # Stable, so a changed task updates its event
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{t.due:%Y%m%d}",
            f"DTEND;VALUE=DATE:{t.due + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{escape_text(f'[{project.name}] {t.name}')}",
            f"DESCRIPTION:{escape_text(description)}",
            f"URL:{link}",
            "TRANSP:TRANSPARENT",  # All-day tasks do not mark the person as busy
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(fold(line) + "\r\n" for line in lines)
