"""Exporting a launch's tasks as a CSV file that opens in Google Sheets or Excel.

One row per task, sorted by due date. Dates are YYYY-MM-DD so spreadsheets read
them as real dates. The csv module quotes any cell with a comma, quote or line
break, so a task name can never spill into the next column.
"""

from __future__ import annotations

import csv
import io
import re

from app.services import logic
from app.services.records import ProjectRec
from app.services.views import World

COLUMNS = [
    "Launch",
    "Task",
    "Assigned to",
    "Status",
    "Due date",
    "Completed date",
    "Phase",
    "Role",
    "Program type",
    "Site type",
]

UNASSIGNED = "Unassigned"

# A spreadsheet runs a cell starting with one of these as a formula. Task names are
# typed by people, so text cells that start this way get a leading apostrophe,
# which makes Sheets and Excel show them as plain text.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _text(value: str | None) -> str:
    value = value or ""
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def _date(value) -> str:
    return value.isoformat() if value else ""


def filename(project: ProjectRec, world: World) -> str:
    """For example "Bellevue-Launch-tasks-2026-11-12.csv". Only letters, digits, - and _."""
    stem = re.sub(r"[^A-Za-z0-9_]+", "-", project.name or world.site_name(project)).strip("-_")
    return f"{stem[:80].rstrip('-_') or 'launch'}-tasks-{world.today.isoformat()}.csv"


def project_csv(world: World, project: ProjectRec) -> str:
    """The launch's tasks as CSV text, header first. A launch with no tasks gets just the header."""
    tasks = sorted(
        world.tasks_by_project.get(project.id, []),
        key=lambda t: (t.due is None, t.due, t.sort_order or 0, t.name),
    )
    program_type = world.template_name(project)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for t in tasks:
        names = [world.user_name(u) for u in t.assignees]
        people = ", ".join(n for n in names if n)
        waiting = logic.waiting_on(t, world.tasks_by_id)
        writer.writerow(
            [
                _text(project.name),
                _text(t.name),
                _text(people) or UNASSIGNED,
                logic.display_status(t, waiting),
                _date(t.due),
                _date(t.completed),
                logic.phase_for(t.due, project.start, project.end),
                _text(world.role_name(t.role_id)),
                _text(program_type),
                _text(project.site_type),
            ]
        )
    return out.getvalue()
