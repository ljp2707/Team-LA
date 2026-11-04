"""Pure rules about tasks and projects: no Airtable, so they are easy to test.

Open, overdue, waiting on, at risk, complete %, next milestone, timing labels,
phases and due date math all live here.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Iterable

from app.services.records import TaskRec

DONE = "Done"
SKIPPED = "Skipped"
BLOCKED = "Blocked"
FINISHED = {DONE, SKIPPED}

BEFORE = "Before the program"
PROGRAM_WEEK = "Program week"
AFTER = "After the program"
PHASES = [BEFORE, PROGRAM_WEEK, AFTER]


# --- Status -----------------------------------------------------------------


def is_open(status: str | None) -> bool:
    return (status or "Not Started") not in FINISHED


def is_overdue(task: TaskRec, today: date) -> bool:
    return is_open(task.status) and task.due is not None and task.due < today


def days_late(task: TaskRec, today: date) -> int:
    if not is_overdue(task, today):
        return 0
    return (today - task.due).days  # type: ignore[operator]


def waiting_on(task: TaskRec, tasks_by_id: dict[str, TaskRec]) -> list[TaskRec]:
    """The task's dependencies that are still open, earliest due first."""
    deps = [tasks_by_id[i] for i in task.depends_on if i in tasks_by_id]
    return sorted(
        (d for d in deps if is_open(d.status)), key=lambda d: (d.due or date.max, d.name)
    )


def waiting_text(waiting: list[TaskRec]) -> str | None:
    if not waiting:
        return None
    if len(waiting) == 1:
        return f"Waiting on {waiting[0].name}"
    return f"Waiting on {waiting[0].name} and {len(waiting) - 1} more"


def dependents_map(tasks: Iterable[TaskRec]) -> dict[str, list[TaskRec]]:
    """For each task ID, the tasks that list it in Depends On."""
    out: dict[str, list[TaskRec]] = {}
    for task in tasks:
        for dep in task.depends_on:
            out.setdefault(dep, []).append(task)
    return out


def is_at_risk(task: TaskRec, tasks_by_id: dict[str, TaskRec], today: date) -> bool:
    """An open task with a dependency that is overdue."""
    if not is_open(task.status):
        return False
    return any(
        is_overdue(tasks_by_id[d], today) for d in task.depends_on if d in tasks_by_id
    )


def display_status(task: TaskRec, waiting: list[TaskRec]) -> str:
    """An open task with an open dependency shows as Blocked, whatever is stored."""
    if is_open(task.status) and waiting:
        return BLOCKED
    return task.status or "Not Started"


def complete_percent(tasks: list[TaskRec]) -> int:
    """(Done + Skipped) / all tasks, rounded down."""
    if not tasks:
        return 0
    finished = sum(1 for t in tasks if not is_open(t.status))
    return math.floor(finished * 100 / len(tasks))


def next_milestone(tasks: list[TaskRec]) -> TaskRec | None:
    """The open task with the earliest due date."""
    open_tasks = [t for t in tasks if is_open(t.status) and t.due]
    if not open_tasks:
        return None
    return min(open_tasks, key=lambda t: (t.due, t.sort_order or 0, t.name))


# --- Dates ------------------------------------------------------------------


def due_date_for(
    anchor: str | None, days_before: int, start: date | None, end: date | None
) -> date | None:
    """Anchor date minus Days Before Anchor. A negative number means after."""
    anchor_date = end if anchor == "End" else start
    if anchor == "End" and anchor_date is None:
        anchor_date = start
    if anchor_date is None:
        return None
    return anchor_date - timedelta(days=days_before)


def timing_label(anchor: str | None, days_before: int | None) -> str:
    """"6 weeks before Day 1", "On Day 1", "3 days after the program ends"."""
    if days_before is None:
        return "No set timing"
    end = anchor == "End"
    if days_before == 0:
        return "When the program ends" if end else "On Day 1"
    n = abs(days_before)
    if n % 7 == 0:
        count = n // 7
        unit = "week" if count == 1 else "weeks"
    else:
        count = n
        unit = "day" if count == 1 else "days"
    direction = "before" if days_before > 0 else "after"
    target = "the program ends" if end else "Day 1"
    return f"{count} {unit} {direction} {target}"


def short_timing(anchor: str | None, days_before: int | None) -> str:
    """The template WHEN column: "6 weeks before", "Day 1", "1 week after"."""
    label = timing_label(anchor, days_before)
    if label == "On Day 1":
        return "Day 1"
    if anchor == "End":
        return label.replace("the program ends", "the end")
    return label.replace(" Day 1", "")


def phase_for(due: date | None, start: date | None, end: date | None) -> str:
    if due is None or start is None or due < start:
        return BEFORE
    if due <= (end or start):
        return PROGRAM_WEEK
    return AFTER


def lead_days(days_list: Iterable[int]) -> int:
    values = list(days_list)
    return max(values) if values else 0


def lead_time_text(steps_days: list[int]) -> str:
    """"starts 6 weeks before Day 1", from the step with the largest Days Before."""
    lead = lead_days(steps_days)
    if lead <= 0:
        return "starts on Day 1"
    return "starts " + timing_label("Start", lead)


def weeks_out_label(due: date | None, start: date | None) -> str:
    """Preview grouping: "6 WEEKS OUT", "THIS WEEK", "PROGRAM WEEK", "AFTER"."""
    if due is None or start is None:
        return "NO DATE"
    days = (start - due).days
    if days < 0:
        return "AFTER DAY 1"
    if days == 0:
        return "DAY 1"
    weeks = days // 7
    if weeks == 0:
        return "DAY 1 WEEK"
    return f"{weeks} WEEK{'S' if weeks != 1 else ''} OUT"


# --- Text -------------------------------------------------------------------


def fmt_date(d: date | None, today: date, weekday: bool = False) -> str:
    """"Oct 26", "Thu, Oct 30", and "Jul 14, 2026" outside the current year."""
    if d is None:
        return "No date"
    text = f"{d:%b} {d.day}"
    if weekday:
        text = f"{d:%a}, {text}"
    if d.year != today.year:
        text = f"{text}, {d.year}"
    return text


def due_text(task: TaskRec, today: date) -> str:
    """"Due Oct 26, 2 days late", "Due today", "Due Thu, Oct 30", "Due Nov 7"."""
    if task.due is None:
        return "No due date"
    if is_overdue(task, today):
        late = (today - task.due).days
        return f"Due {fmt_date(task.due, today)}, {late} day{'s' if late != 1 else ''} late"
    if task.due == today and is_open(task.status):
        return "Due today"
    week_end = today + timedelta(days=6 - today.weekday())
    if today <= task.due <= week_end:
        return f"Due {fmt_date(task.due, today, weekday=True)}"
    return f"Due {fmt_date(task.due, today)}"


def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


def name_list(names: list[str], limit: int = 2) -> str:
    """"A, B and 4 more"."""
    if not names:
        return ""
    if len(names) <= limit:
        return " and ".join(names) if len(names) == 2 else names[0]
    return f"{', '.join(names[:limit])} and {len(names) - limit} more"
