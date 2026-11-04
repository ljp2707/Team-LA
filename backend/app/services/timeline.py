"""Task timelines: making a project's tasks, and moving Day 1.

Planning is pure (plan_tasks), so the New Project preview and the real create use
the same math. Writing goes through the Airtable client in batches of 10.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from fastapi import HTTPException, status

from app.airtable import client
from app.airtable.schema import (
    SESSION_IN_PROGRESS,
    Reminders,
    Session,
    Work,
)
from app.services import clock, history
from app.services.logic import due_date_for, fmt_date, is_open, plural
from app.services.records import (
    ProjectRec,
    StepRec,
    TaskRec,
    live_steps,
    load_log,
    load_projects,
    load_reminders,
    load_steps,
    load_tasks,
    load_team,
    load_templates,
    safe,
)

UNDO_HOURS = 24


@dataclass
class SourceItem:
    """One task to create, before it has a date or a person."""

    key: str
    name: str
    role_id: str | None
    anchor: str = "Start"
    days_before: int = 0
    depends_on: list[str] = field(default_factory=list)
    one_off: bool = False
    step_id: str | None = None
    sort_order: float | None = None
    description: str = ""
    # Set when copying a past launch: days from the old Day 1 to the old due date.
    offset_days: int | None = None
    # Set for one-off tasks, which have a fixed date and maybe a fixed person.
    fixed_due: date | None = None
    fixed_user: str | None = None


@dataclass
class PlannedTask:
    key: str
    name: str
    due: date | None
    role_id: str | None
    user_id: str | None
    anchor: str
    days_before: int
    depends_on: list[str]
    one_off: bool
    step_id: str | None
    sort_order: float


@dataclass
class OneOff:
    name: str
    due: date
    role_id: str | None = None
    user_id: str | None = None
    needs_first: list[str] = field(default_factory=list)


def items_from_steps(steps: list[StepRec]) -> list[SourceItem]:
    return [
        SourceItem(
            key=s.id,
            name=s.name,
            role_id=s.role_id,
            anchor=s.anchor or "Start",
            days_before=s.days_before,
            depends_on=list(s.depends_on),
            step_id=s.id,
            sort_order=s.sort_order if s.sort_order is not None else float(i),
            description=s.description,
        )
        for i, s in enumerate(steps)
    ]


def items_from_project(tasks: list[TaskRec], old_day_one: date | None) -> list[SourceItem]:
    """Every task of a past launch except the skipped ones, one-off tasks included."""
    kept = [t for t in tasks if t.status != "Skipped"]
    kept_ids = {t.id for t in kept}
    kept.sort(key=lambda t: (t.sort_order if t.sort_order is not None else 1e9, t.due or date.max))
    items = []
    for i, t in enumerate(kept):
        offset = (t.due - old_day_one).days if (t.due and old_day_one) else None
        items.append(
            SourceItem(
                key=t.id,
                name=t.name,
                role_id=t.role_id,
                anchor=t.anchor or "Start",
                days_before=t.days_before
                if t.days_before is not None
                else (-(offset or 0)),
                depends_on=[d for d in t.depends_on if d in kept_ids],
                one_off=t.one_off,
                step_id=t.step_id,
                sort_order=float(i),
                description=t.description,
                offset_days=offset,
            )
        )
    return items


def items_from_one_offs(one_offs: list[OneOff], start_index: int) -> list[SourceItem]:
    return [
        SourceItem(
            key=f"one-off-{i}",
            name=o.name,
            role_id=o.role_id,
            anchor="Start",
            days_before=0,
            depends_on=list(o.needs_first),
            one_off=True,
            sort_order=float(start_index + i),
            fixed_due=o.due,
            fixed_user=o.user_id,
        )
        for i, o in enumerate(one_offs)
    ]


def plan_tasks(
    items: list[SourceItem],
    start: date | None,
    end: date | None,
    assignments: dict[str, str | None],
    overrides: dict[str, str | None] | None = None,
) -> list[PlannedTask]:
    """Work out each task's due date and person. Pure: writes nothing.

    assignments maps role ID to user ID. overrides maps an item key to a user ID and
    wins over the role. A role with nobody leaves the task unassigned.
    """
    overrides = overrides or {}
    planned = []
    for item in items:
        if item.fixed_due is not None:
            due = item.fixed_due
            days_before = (start - due).days if start else 0
        elif item.offset_days is not None and start is not None:
            due = start + timedelta(days=item.offset_days)
            days_before = item.days_before
        else:
            due = due_date_for(item.anchor, item.days_before, start, end)
            days_before = item.days_before
        user = overrides.get(item.key) or item.fixed_user or (
            assignments.get(item.role_id) if item.role_id else None
        )
        planned.append(
            PlannedTask(
                key=item.key,
                name=item.name,
                due=due,
                role_id=item.role_id,
                user_id=user or None,
                anchor=item.anchor if item.fixed_due is None else "Start",
                days_before=days_before,
                depends_on=list(item.depends_on),
                one_off=item.one_off,
                step_id=item.step_id,
                sort_order=item.sort_order if item.sort_order is not None else 0.0,
            )
        )
    planned.sort(key=lambda p: (p.due or date.max, p.sort_order))
    return planned


def find_cycle(edges: dict[str, list[str]]) -> bool:
    """True if following "needs first" ever leads back to the same task."""
    visiting, done = set(), set()

    def visit(node: str) -> bool:
        if node in done:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        if any(visit(n) for n in edges.get(node, []) if n in edges):
            return True
        visiting.discard(node)
        done.add(node)
        return False

    return any(visit(n) for n in edges)


def work_fields(session_id: str, p: PlannedTask) -> dict:
    fields = {
        Work.SESSION: [session_id],
        Work.TASK_NAME: p.name,
        Work.ANCHOR: p.anchor,
        Work.DAYS_BEFORE_ANCHOR: p.days_before,
        Work.STATUS: "Not Started",
        Work.SORT_ORDER: p.sort_order,
    }
    if p.due:
        fields[Work.DUE_DATE_OVERRIDE] = p.due.isoformat()
    if p.role_id:
        fields[Work.ROLE] = [p.role_id]
    if p.step_id:
        fields[Work.STEPS] = [p.step_id]
    if p.user_id:
        fields[Work.ASSIGNED_TO] = [p.user_id]
    if p.one_off:
        fields[Work.ONE_OFF] = True
    return fields


def write_plan(session_id: str, planned: list[PlannedTask]) -> dict[str, str]:
    """Create the Work rows, then fill Depends On in a second pass.

    Returns a map of item key to new Work ID.
    """
    created = client.create_records(
        Work.TABLE, [work_fields(session_id, p) for p in planned], typecast=True
    )
    key_to_id = {p.key: rec["id"] for p, rec in zip(planned, created)}
    updates = []
    for p in planned:
        deps = [key_to_id[k] for k in p.depends_on if k in key_to_id]
        if deps:
            updates.append({"id": key_to_id[p.key], "fields": {Work.DEPENDS_ON: deps}})
    client.update_records(Work.TABLE, updates)
    return key_to_id


def _session(session_id: str) -> ProjectRec:
    for p in load_projects():
        if p.id == session_id:
            return p
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def generate_timeline(
    session_id: str,
    assignments: dict[str, str | None],
    one_off_tasks: list[OneOff] | None = None,
    overrides: dict[str, str | None] | None = None,
    actor_id: str | None = None,
) -> list[PlannedTask]:
    """Create one Work row per live step of the project's template, plus one-offs."""
    project = _session(session_id)
    if not project.template_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The project has no template")
    steps = live_steps(project.template_id)
    items = items_from_steps(steps) + items_from_one_offs(one_off_tasks or [], len(steps))
    planned = plan_tasks(items, project.start, project.end, assignments, overrides)
    write_plan(session_id, planned)

    template = next((t for t in load_templates() if t.id == project.template_id), None)
    client.update_record(
        Session.TABLE,
        session_id,
        {
            Session.TIMELINE_GENERATED_AT: clock.utc_now_iso(),
            Session.TEMPLATE_VERSION: template.version if template else 1,
            Session.STATUS: SESSION_IN_PROGRESS,
        },
        typecast=True,
    )
    history.log_event(
        session_id,
        None,
        actor_id,
        "Project Created",
        f"created this launch with {plural(len(planned), 'task')}",
    )
    return planned


def start_from_past_launch(
    past_session_id: str,
    new_session_id: str,
    assignments: dict[str, str | None],
    one_off_tasks: list[OneOff] | None = None,
    overrides: dict[str, str | None] | None = None,
    actor_id: str | None = None,
) -> list[PlannedTask]:
    """Copy a past launch's tasks onto a new Day 1, keeping each one's offset."""
    past = _session(past_session_id)
    new = _session(new_session_id)
    past_tasks = [t for t in load_tasks() if t.session_id == past_session_id]
    items = items_from_project(past_tasks, past.start)
    items += items_from_one_offs(one_off_tasks or [], len(items))
    planned = plan_tasks(items, new.start, new.end, assignments, overrides)
    write_plan(new_session_id, planned)
    client.update_record(
        Session.TABLE,
        new_session_id,
        {
            Session.TIMELINE_GENERATED_AT: clock.utc_now_iso(),
            Session.TEMPLATE_VERSION: past.template_version or 1,
            Session.STATUS: SESSION_IN_PROGRESS,
            Session.CREATED_FROM: [past_session_id],
        },
        typecast=True,
    )
    history.log_event(
        new_session_id,
        None,
        actor_id,
        "Project Created",
        f"created this launch from {past.name} with {plural(len(planned), 'task')}",
    )
    return planned


# --- Moving Day 1 -------------------------------------------------------------


@dataclass
class ShiftPlan:
    old_day_one: date
    new_day_one: date
    delta: int
    moved: list[TaskRec]
    kept: list[TaskRec]
    reminder_ids: list[str]

    def summary(self, today: date) -> str:
        weeks = abs(self.delta) // 7 if self.delta % 7 == 0 else None
        amount = (
            plural(weeks, "week") if weeks else plural(abs(self.delta), "day")
        )
        direction = "later" if self.delta > 0 else "earlier"
        if weeks == 1:
            amount = "a week"
        return (
            f"Day 1 moved from {fmt_date(self.old_day_one, today)} to "
            f"{fmt_date(self.new_day_one, today)}. "
            f"{plural(len(self.moved), 'open task')} and {'its' if len(self.moved) == 1 else 'their'} reminders moved {amount} "
            f"{direction}."
            + (
                f" {plural(len(self.kept), 'finished task')} "
                f"{'kept its date' if len(self.kept) == 1 else 'kept their dates'}."
                if self.kept
                else ""
            )
        )

    def preview_text(self) -> str:
        weeks = abs(self.delta) // 7 if self.delta % 7 == 0 else None
        amount = plural(weeks, "week") if weeks else plural(abs(self.delta), "day")
        direction = "later" if self.delta > 0 else "earlier"
        return (
            f"{plural(len(self.moved), 'open task')} and {'its' if len(self.moved) == 1 else 'their'} reminders will move "
            f"{amount} {direction}."
            + (
                f" {plural(len(self.kept), 'finished task')} "
                f"{'keeps its date' if len(self.kept) == 1 else 'keep their dates'}."
                if self.kept
                else ""
            )
        )


def plan_shift(
    project: ProjectRec, tasks: list[TaskRec], reminders, new_day_one: date
) -> ShiftPlan:
    """Pure: which tasks and custom reminders a Day 1 move would touch."""
    if project.start is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This project has no Day 1 yet")
    delta = (new_day_one - project.start).days
    mine = [t for t in tasks if t.session_id == project.id]
    moved = [t for t in mine if is_open(t.status)]
    kept = [t for t in mine if not is_open(t.status)]
    moved_ids = {t.id for t in moved}
    reminder_ids = [
        r.id
        for r in reminders
        if r.work_id in moved_ids and r.kind == "Custom" and r.status == "Scheduled"
    ]
    return ShiftPlan(project.start, new_day_one, delta, moved, kept, reminder_ids)


def _shift_tasks(tasks: list[TaskRec], delta: int) -> None:
    client.update_records(
        Work.TABLE,
        [
            {
                "id": t.id,
                "fields": {Work.DUE_DATE_OVERRIDE: (t.due + timedelta(days=delta)).isoformat()},
            }
            for t in tasks
            if t.due
        ],
    )


def _shift_reminders(reminder_ids: list[str], delta: int) -> int:
    by_id = {r.id: r for r in safe(load_reminders)}
    updates = [
        {
            "id": rid,
            "fields": {
                Reminders.SEND_ON: (by_id[rid].send_on + timedelta(days=delta)).isoformat()
            },
        }
        for rid in reminder_ids
        if rid in by_id and by_id[rid].send_on
    ]
    client.update_records(Reminders.TABLE, updates)
    return len(updates)


def shift_day_one(session_id: str, new_day_one: date, actor_id: str | None) -> dict:
    """Move Day 1. Open tasks and their custom reminders move; finished ones stay.

    Returns {moved_tasks, kept_tasks, moved_reminders, batch, message}.
    """
    project = _session(session_id)
    tasks = load_tasks()
    plan = plan_shift(project, tasks, safe(load_reminders), new_day_one)
    if plan.delta == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That is already Day 1")
    batch = uuid.uuid4().hex[:12]

    _shift_tasks(plan.moved, plan.delta)
    # Older tasks without a stored date follow Day 1 through a formula, so give
    # finished ones a fixed date first, which keeps them where they are.
    client.update_records(
        Work.TABLE,
        [
            {"id": t.id, "fields": {Work.DUE_DATE_OVERRIDE: t.due.isoformat()}}
            for t in plan.kept
            if t.due and not t.has_override
        ],
    )
    moved_reminders = _shift_reminders(plan.reminder_ids, plan.delta)
    client.update_record(
        Session.TABLE, session_id, {Session.START_DATE: new_day_one.isoformat()}
    )

    today = clock.today()
    events = [
        history.Event(
            session_id,
            None,
            actor_id,
            "Date Change",
            f"moved Day 1 to {fmt_date(new_day_one, today)}",
            plan.old_day_one.isoformat(),
            new_day_one.isoformat(),
            batch=batch,
        )
    ]
    events += [
        history.Event(
            session_id,
            t.id,
            actor_id,
            "Date Change",
            "moved with Day 1",
            t.due.isoformat() if t.due else "",
            (t.due + timedelta(days=plan.delta)).isoformat() if t.due else "",
            batch=batch,
        )
        for t in plan.moved
    ]
    history.log_events(events)
    return {
        "moved_tasks": len(plan.moved),
        "kept_tasks": len(plan.kept),
        "moved_reminders": moved_reminders,
        "batch": batch,
        "message": plan.summary(today),
    }


def undo_shift(session_id: str, batch: str, actor_id: str | None) -> dict:
    """Undo the latest Day 1 move, if it is less than 24 hours old."""
    project = _session(session_id)
    log = load_log()
    project_moves = sorted(
        (
            r
            for r in log
            if r.session_id == session_id and r.type == "Date Change" and not r.work_id
        ),
        key=lambda r: (r.created is not None, r.created),
    )
    latest = project_moves[-1] if project_moves else None
    if latest is None or latest.batch != batch:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This Day 1 move can no longer be undone, because Day 1 has changed since.",
        )
    now = clock.now()
    created = latest.created or now
    if now - created > timedelta(hours=UNDO_HOURS):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This Day 1 move is more than 24 hours old, so it cannot be undone. "
            "Move Day 1 again instead.",
        )
    old_day_one = date.fromisoformat(latest.from_value)
    new_day_one = date.fromisoformat(latest.to_value)
    delta = (new_day_one - old_day_one).days

    moved_ids = {r.work_id for r in log if r.batch == batch and r.work_id}
    tasks = [t for t in load_tasks() if t.id in moved_ids]
    _shift_tasks(tasks, -delta)
    reminder_ids = [
        r.id
        for r in safe(load_reminders)
        if r.work_id in moved_ids and r.kind == "Custom" and r.status == "Scheduled"
    ]
    moved_reminders = _shift_reminders(reminder_ids, -delta)
    client.update_record(
        Session.TABLE, session_id, {Session.START_DATE: old_day_one.isoformat()}
    )
    today = clock.today()
    history.log_event(
        session_id,
        None,
        actor_id,
        "Date Change",
        f"undid the Day 1 move, so Day 1 is back to {fmt_date(old_day_one, today)}",
        new_day_one.isoformat(),
        old_day_one.isoformat(),
    )
    return {
        "moved_tasks": len(tasks),
        "moved_reminders": moved_reminders,
        "message": f"Day 1 is back to {fmt_date(old_day_one, today)}. "
        f"{plural(len(tasks), 'task')} moved back.",
        "project": project.id,
    }


def team_for(session_id: str) -> dict[str, str | None]:
    """The project's role to person map, from Session Team."""
    return {
        t.role_id: t.user_id for t in load_team() if t.session_id == session_id and t.role_id
    }


__all__ = [
    "OneOff",
    "PlannedTask",
    "SourceItem",
    "find_cycle",
    "generate_timeline",
    "items_from_one_offs",
    "items_from_project",
    "items_from_steps",
    "load_steps",
    "plan_shift",
    "plan_tasks",
    "shift_day_one",
    "start_from_past_launch",
    "team_for",
    "undo_shift",
]
