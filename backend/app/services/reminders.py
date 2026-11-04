"""Task reminders and every other email the app sends.

The daily job (jobs/send_reminders.py) calls run_daily. Assignment and welcome
emails are sent from the API in a background task.

Never send twice: before sending, the Reminders table is checked for a Sent row
with the same Work, Kind, Send On and Recipient. After every attempt a row is
written (or updated) with Sent, Failed or Skipped, so the job is safe to rerun.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from app.airtable import client
from app.airtable.schema import Reminders, Users
from app.config import get_settings
from app.email import gmail, templates
from app.email.templates import TaskLine
from app.services import clock
from app.services.logic import due_text, fmt_date, is_open, waiting_on, waiting_text
from app.services.records import (
    ProjectRec,
    ReminderRec,
    TaskRec,
    UserRec,
    load_projects,
    load_reminders,
    load_sites,
    load_tasks,
    load_team,
    load_users,
    safe,
)

logger = logging.getLogger(__name__)

SEVEN_DAYS = "7 Days Before"
DUE_DATE = "Due Date"
CUSTOM = "Custom"
WEEKLY = "Weekly Digest"
ASSIGNMENT = "Assignment"
WELCOME = "Welcome"

SCHEDULED = "Scheduled"
SENT = "Sent"
FAILED = "Failed"
SKIPPED = "Skipped"
CANCELLED = "Cancelled"

NO_ONE_ASSIGNED = "No one assigned"

DIGEST_WEEKDAY = 0  # Monday
DIGEST_DAYS_AHEAD = 7

# What happens after a task goes overdue. The midterm left this open, so for now an
# overdue task only shows at the top of the weekly digest. This is a decision for
# NMU (see the README). Options later: "daily" or "weekly_digest_and_admin".
OVERDUE_FOLLOW_UP = "weekly_digest_only"

Sender = Callable[[str, str, str, str], object]


@dataclass
class Context:
    """Everything a reminder needs, loaded once per run."""

    today: date
    tasks: list[TaskRec]
    projects: dict[str, ProjectRec]
    site_names: dict[str, str]
    users: dict[str, UserRec]
    team: dict[tuple[str, str], list[str]]
    reminders: list[ReminderRec]
    tasks_by_id: dict[str, TaskRec] = field(default_factory=dict)

    @classmethod
    def load(cls, today: date | None = None) -> "Context":
        tasks = load_tasks()
        team: dict[tuple[str, str], list[str]] = defaultdict(list)
        for row in load_team():
            if row.session_id and row.role_id and row.user_id:
                team[(row.session_id, row.role_id)].append(row.user_id)
        ctx = cls(
            today=today or clock.today(),
            tasks=tasks,
            projects={p.id: p for p in load_projects()},
            site_names={s.id: s.name for s in load_sites()},
            users={u.id: u for u in load_users()},
            team=dict(team),
            reminders=safe(load_reminders),
        )
        ctx.tasks_by_id = {t.id: t for t in tasks}
        return ctx

    def project(self, task: TaskRec) -> ProjectRec | None:
        return self.projects.get(task.session_id or "")

    def site(self, task: TaskRec) -> str:
        project = self.project(task)
        if project is None:
            return "NMU"
        return self.site_names.get(project.site_id or "", project.name)

    def is_active(self, task: TaskRec) -> bool:
        project = self.project(task)
        return project is not None and not project.closed

    def line(self, task: TaskRec) -> TaskLine:
        return TaskLine(
            name=task.name,
            site=self.site(task),
            due_text=due_text(task, self.today),
            url=templates.task_url(task.id),
            waiting=waiting_text(waiting_on(task, self.tasks_by_id)),
        )

    def recipients(self, task: TaskRec) -> list[UserRec]:
        """The assignee, or else the project team for the task's role. Active only."""
        ids = [task.assigned_to] if task.assigned_to else []
        if not ids and task.session_id and task.role_id:
            ids = self.team.get((task.session_id, task.role_id), [])
        return [self.users[i] for i in ids if i in self.users and self.users[i].active]


@dataclass
class Result:
    sent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    planned: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{len(self.sent)} sent, {len(self.failed)} failed, {len(self.skipped)} skipped, "
            f"{len(self.already)} already sent earlier"
        )


def _find_row(
    reminders: list[ReminderRec], work_id: str | None, kind: str, send_on: date, recipient: str | None
) -> ReminderRec | None:
    for r in reminders:
        if (
            r.kind == kind
            and r.send_on == send_on
            and (r.work_id or None) == (work_id or None)
            and (r.recipient_id or None) == (recipient or None)
        ):
            return r
    return None


def _write_row(
    existing: ReminderRec | None,
    name: str,
    kind: str,
    send_on: date,
    status: str,
    work_id: str | None = None,
    recipient: str | None = None,
    error: str = "",
) -> None:
    fields = {
        Reminders.NAME: name[:250],
        Reminders.KIND: kind,
        Reminders.SEND_ON: send_on.isoformat(),
        Reminders.STATUS: status,
        Reminders.ERROR: error,
    }
    if status == SENT:
        fields[Reminders.SENT_AT] = clock.utc_now_iso()
    if work_id:
        fields[Reminders.WORK] = [work_id]
    if recipient:
        fields[Reminders.RECIPIENT] = [recipient]
    if existing:
        client.update_record(Reminders.TABLE, existing.id, fields, typecast=True)
    else:
        client.create_record(Reminders.TABLE, fields, typecast=True)


def _attempt(
    ctx: Context,
    result: Result,
    send: Sender,
    dry_run: bool,
    *,
    kind: str,
    name: str,
    recipient: UserRec,
    email,
    work_id: str | None,
    send_on: date,
    existing: ReminderRec | None,
) -> None:
    label = f"{kind} to {recipient.email}: {email[0]}"
    if existing and existing.status == SENT:
        result.already.append(label)
        return
    if dry_run:
        result.planned.append(label)
        return
    try:
        send(recipient.email, *email)
    except Exception as error:  # noqa: BLE001 - any failure is logged on the row
        message = str(error) if isinstance(error, gmail.EmailError) else type(error).__name__
        _write_row(existing, name, kind, send_on, FAILED, work_id, recipient.id, message)
        result.failed.append(f"{label} ({message})")
        return
    _write_row(existing, name, kind, send_on, SENT, work_id, recipient.id)
    result.sent.append(label)


def automatic_due(ctx: Context, day: date) -> list[tuple[str, TaskRec]]:
    """(kind, task) for every open task in an active project due in 7 days or today."""
    out = []
    for task in ctx.tasks:
        if not is_open(task.status) or task.due is None or not ctx.is_active(task):
            continue
        if task.due == day + timedelta(days=7):
            out.append((SEVEN_DAYS, task))
        elif task.due == day:
            out.append((DUE_DATE, task))
    return out


def run_auto(ctx: Context, day: date, send: Sender, dry_run: bool, result: Result) -> None:
    for kind, task in automatic_due(ctx, day):
        prefix = "7 day" if kind == SEVEN_DAYS else "Due date"
        name = f"{prefix}: {task.name}"
        people = ctx.recipients(task)
        if not people:
            existing = _find_row(ctx.reminders, task.id, kind, day, None)
            if existing is None and not dry_run:
                _write_row(None, name, kind, day, SKIPPED, task.id, None, NO_ONE_ASSIGNED)
            result.skipped.append(f"{kind}: {task.name} ({NO_ONE_ASSIGNED})")
            continue
        line = ctx.line(task)
        email = templates.due_in_seven(line) if kind == SEVEN_DAYS else templates.due_today(line)
        for person in people:
            _attempt(
                ctx,
                result,
                send,
                dry_run,
                kind=kind,
                name=name,
                recipient=person,
                email=email,
                work_id=task.id,
                send_on=day,
                existing=_find_row(ctx.reminders, task.id, kind, day, person.id),
            )


def run_custom(ctx: Context, day: date, send: Sender, dry_run: bool, result: Result) -> None:
    for reminder in ctx.reminders:
        if reminder.kind != CUSTOM or reminder.status not in (SCHEDULED, FAILED):
            continue
        if reminder.send_on is None or reminder.send_on > day:
            continue
        task = ctx.tasks_by_id.get(reminder.work_id or "")
        person = ctx.users.get(reminder.recipient_id or "")
        if task is None or not is_open(task.status) or not ctx.is_active(task):
            if not dry_run:
                client.update_record(Reminders.TABLE, reminder.id, {Reminders.STATUS: CANCELLED})
            result.skipped.append(f"Custom: {reminder.name} (task is finished)")
            continue
        if person is None or not person.active:
            if not dry_run:
                client.update_record(
                    Reminders.TABLE,
                    reminder.id,
                    {Reminders.STATUS: SKIPPED, Reminders.ERROR: "The person is no longer active"},
                    typecast=True,
                )
            result.skipped.append(f"Custom: {reminder.name} (person inactive)")
            continue
        email = templates.custom_reminder(ctx.line(task), reminder.note)
        label = f"Custom to {person.email}: {email[0]}"
        if dry_run:
            result.planned.append(label)
            continue
        try:
            send(person.email, *email)
        except Exception as error:  # noqa: BLE001
            message = str(error) if isinstance(error, gmail.EmailError) else type(error).__name__
            client.update_record(
                Reminders.TABLE,
                reminder.id,
                {Reminders.STATUS: FAILED, Reminders.ERROR: message},
            )
            result.failed.append(f"{label} ({message})")
            continue
        client.update_record(
            Reminders.TABLE,
            reminder.id,
            {Reminders.STATUS: SENT, Reminders.SENT_AT: clock.utc_now_iso(), Reminders.ERROR: ""},
        )
        result.sent.append(label)


def digest_tasks(ctx: Context, day: date) -> dict[str, tuple[list[TaskRec], list[TaskRec]]]:
    """For each person: (overdue, due in the next 7 days). Overdue comes first."""
    out: dict[str, tuple[list[TaskRec], list[TaskRec]]] = {}
    horizon = day + timedelta(days=DIGEST_DAYS_AHEAD)
    for task in ctx.tasks:
        if not is_open(task.status) or task.due is None or not ctx.is_active(task):
            continue
        if task.due > horizon:
            continue
        for person in ctx.recipients(task):
            overdue, upcoming = out.setdefault(person.id, ([], []))
            (overdue if task.due < day else upcoming).append(task)
    for overdue, upcoming in out.values():
        overdue.sort(key=lambda t: t.due)
        upcoming.sort(key=lambda t: t.due)
    return out


def run_weekly(ctx: Context, day: date, send: Sender, dry_run: bool, result: Result) -> None:
    if day.weekday() != DIGEST_WEEKDAY:
        return
    for user_id, (overdue, upcoming) in digest_tasks(ctx, day).items():
        person = ctx.users[user_id]
        email = templates.weekly_digest(
            fmt_date(day, ctx.today),
            person.short_name,
            [ctx.line(t) for t in overdue],
            [ctx.line(t) for t in upcoming],
        )
        _attempt(
            ctx,
            result,
            send,
            dry_run,
            kind=WEEKLY,
            name=f"Weekly digest: {person.name}",
            recipient=person,
            email=email,
            work_id=None,
            send_on=day,
            existing=_find_row(ctx.reminders, None, WEEKLY, day, person.id),
        )


def run_daily(
    day: date | None = None,
    only: str | None = None,
    dry_run: bool | None = None,
    send: Sender | None = None,
) -> Result:
    """Run every reminder kind for one day (today in Pacific time by default)."""
    ctx = Context.load()
    day = day or ctx.today
    ctx.today = day
    dry_run = get_settings().REMINDERS_DRY_RUN if dry_run is None else dry_run
    send = send or gmail.send_email
    result = Result()
    if only in (None, "auto"):
        run_auto(ctx, day, send, dry_run, result)
    if only in (None, "custom"):
        run_custom(ctx, day, send, dry_run, result)
    if only in (None, "weekly"):
        run_weekly(ctx, day, send, dry_run, result)
    return result


# --- Emails sent from the API --------------------------------------------------


def send_assignment_emails(by_user: dict[str, list[str]], assigned_by: str) -> None:
    """One email per person, listing every task they were just given.

    Runs in a FastAPI background task, so it logs failures instead of raising.
    """
    if not by_user:
        return
    try:
        ctx = Context.load()
        dry_run = get_settings().REMINDERS_DRY_RUN
        for user_id, task_ids in by_user.items():
            person = ctx.users.get(user_id)
            tasks = [ctx.tasks_by_id[t] for t in task_ids if t in ctx.tasks_by_id]
            tasks = [t for t in tasks if is_open(t.status)]
            if person is None or not person.active or not tasks:
                continue
            email = templates.assignment([ctx.line(t) for t in tasks], assigned_by)
            if dry_run:
                logger.info("Dry run email to %s: %s", person.email, email[0])
                continue
            status, error = SENT, ""
            try:
                gmail.send_email(person.email, *email)
            except Exception as exc:  # noqa: BLE001
                status = FAILED
                error = str(exc) if isinstance(exc, gmail.EmailError) else type(exc).__name__
                logger.warning("Assignment email failed: %s", error)
            _write_row(
                None,
                f"Assignment: {email[0]}",
                ASSIGNMENT,
                ctx.today,
                status,
                tasks[0].id if len(tasks) == 1 else None,
                person.id,
                error,
            )
    except Exception as exc:  # noqa: BLE001 - never crash the background worker
        logger.warning("Assignment emails failed: %s", type(exc).__name__)


def send_welcome(user_id: str) -> None:
    """The welcome email for a newly added person. Runs in a background task."""
    try:
        person = next((u for u in load_users() if u.id == user_id), None)
        if person is None:
            return
        email = templates.welcome(person.first_name, person.email)
        today = clock.today()
        if get_settings().REMINDERS_DRY_RUN:
            logger.info("Dry run email to %s: %s", person.email, email[0])
            return
        status, error = SENT, ""
        try:
            gmail.send_email(person.email, *email)
            client.update_record(
                Users.TABLE, person.id, {Users.WELCOME_EMAIL_SENT: clock.utc_now_iso()}
            )
        except Exception as exc:  # noqa: BLE001
            status = FAILED
            error = str(exc) if isinstance(exc, gmail.EmailError) else type(exc).__name__
            logger.warning("Welcome email failed: %s", error)
        _write_row(None, f"Welcome: {person.name}", WELCOME, today, status, None, person.id, error)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Welcome email failed: %s", type(exc).__name__)


def cancel_custom_for_task(task_id: str) -> int:
    """When a task becomes Done or Skipped, its scheduled custom reminders stop."""
    ids = [
        r.id
        for r in safe(load_reminders)
        if r.work_id == task_id and r.kind == CUSTOM and r.status == SCHEDULED
    ]
    client.update_records(
        Reminders.TABLE, [{"id": i, "fields": {Reminders.STATUS: CANCELLED}} for i in ids]
    )
    return len(ids)


# --- Reminder panels -----------------------------------------------------------


def _status_text(kind: str, send_on: date | None, rows: list[ReminderRec], today: date) -> str:
    sent = [r for r in rows if r.kind == kind and r.status == SENT]
    if sent:
        d = clock.parse_date(sent[0].sent_at) or sent[0].send_on
        return f"Sent {fmt_date(d, today)}"
    if any(r.kind == kind and r.status == SKIPPED for r in rows):
        return "Skipped"
    if any(r.kind == kind and r.status == FAILED for r in rows):
        return "Failed"
    if send_on is None:
        return "No due date"
    if send_on >= today:
        return f"Scheduled {fmt_date(send_on, today)}"
    return "Not sent"


def task_panel(task: TaskRec, viewer_id: str, today: date, reminders: list[ReminderRec] | None = None) -> dict:
    """The task page reminders panel: the two automatic ones and my custom ones."""
    rows = [r for r in (safe(load_reminders) if reminders is None else reminders) if r.work_id == task.id]
    seven = task.due - timedelta(days=7) if task.due else None
    finished = not is_open(task.status)
    auto = [
        {
            "label": "7 days before",
            "status": "Not needed, task finished" if finished and not any(r.kind == SEVEN_DAYS and r.status == SENT for r in rows) else _status_text(SEVEN_DAYS, seven, rows, today),
        },
        {
            "label": "On the due date",
            "status": "Not needed, task finished" if finished and not any(r.kind == DUE_DATE and r.status == SENT for r in rows) else _status_text(DUE_DATE, task.due, rows, today),
        },
    ]
    custom = [
        {
            "id": r.id,
            "label": "My reminder",
            "date": r.send_on.isoformat() if r.send_on else None,
            "date_text": fmt_date(r.send_on, today, weekday=True) if r.send_on else "",
            "status": r.status,
            "note": r.note,
            "can_cancel": r.status == SCHEDULED,
        }
        for r in rows
        if r.kind == CUSTOM and r.recipient_id == viewer_id and r.status != CANCELLED
    ]
    custom.sort(key=lambda c: c["date"] or "")
    return {"automatic": auto, "custom": custom}


def mine(user_id: str, today: date, tasks: list[TaskRec], active_ids: set[str]) -> list[dict]:
    """My Tasks reminders: sent in the last 7 days, or coming in the next 14."""
    reminders = safe(load_reminders)
    tasks_by_id = {t.id: t for t in tasks}
    out = []
    week_ago = today - timedelta(days=7)
    horizon = today + timedelta(days=14)
    sent_keys = set()
    for r in reminders:
        if r.recipient_id != user_id:
            continue
        task = tasks_by_id.get(r.work_id or "")
        task_name = task.name if task else ""
        if r.status == SENT:
            sent_on = clock.parse_date(r.sent_at) or r.send_on
            if sent_on and week_ago <= sent_on <= today:
                sent_keys.add((r.work_id, r.kind))
                what = {
                    SEVEN_DAYS: f"7 day email sent for {task_name}",
                    DUE_DATE: f"Due date email sent for {task_name}",
                    CUSTOM: f"Your custom reminder for {task_name} was sent",
                    WEEKLY: "Weekly digest sent",
                    ASSIGNMENT: "New task email sent" + (f" for {task_name}" if task_name else ""),
                    WELCOME: "Welcome email sent",
                }.get(r.kind, f"{r.kind} email sent")
                out.append({"date": sent_on, "text": what, "task_id": r.work_id, "sent": True})
        elif r.status == SCHEDULED and r.kind == CUSTOM and r.send_on and r.send_on <= horizon:
            if task and is_open(task.status):
                out.append(
                    {
                        "date": r.send_on,
                        "text": f"Your custom reminder for {task_name}",
                        "task_id": r.work_id,
                        "sent": False,
                    }
                )
    for task in tasks:
        if task.assigned_to != user_id or not is_open(task.status) or task.due is None:
            continue
        if task.session_id not in active_ids:
            continue
        for kind, when, text in (
            (SEVEN_DAYS, task.due - timedelta(days=7), f"7 day email for {task.name}"),
            (DUE_DATE, task.due, f"Due date email for {task.name}"),
        ):
            if today <= when <= horizon and (task.id, kind) not in sent_keys:
                out.append({"date": when, "text": text, "task_id": task.id, "sent": False})
    out.sort(key=lambda r: (r["date"], r["text"]))
    return [
        {
            "date": r["date"].isoformat(),
            "when": "Today" if r["date"] == today else fmt_date(r["date"], today, weekday=True),
            "text": r["text"],
            "task_id": r["task_id"],
            "sent": r["sent"],
        }
        for r in out
    ]
