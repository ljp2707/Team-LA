"""Archive, /archive (admin): every closed launch, kept for good.

Planned vs actual dates per task, with on time, late, skipped and added markers.
"""

import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import require_admin
from app.models.user import CurrentUser
from app.services import history, logic
from app.services.records import ProjectRec, TaskRec
from app.services.views import World, history_dict

router = APIRouter(prefix="/api/archive", tags=["archive"], dependencies=[Depends(require_admin)])


def _parse_bound(value: str | None, end: bool) -> date | None:
    """Accept YYYY-MM-DD or YYYY-MM (a whole month)."""
    if not value:
        return None
    try:
        if len(value) == 7:
            year, month = (int(p) for p in value.split("-"))
            return date(year, month, calendar.monthrange(year, month)[1] if end else 1)
        return date.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Dates must look like 2026-07") from error


def on_time_percent(tasks: list[TaskRec]) -> int | None:
    """Tasks done on or before their due date, out of tasks done."""
    done = [t for t in tasks if t.status == "Done"]
    if not done:
        return None
    on_time = [t for t in done if t.completed and t.due and t.completed <= t.due]
    return round(len(on_time) * 100 / len(done))


def task_outcome(task: TaskRec) -> tuple[str, str]:
    """(label, tone) for one archived task."""
    if task.one_off:
        return "Added", "progress"
    if task.status == "Skipped":
        return "Skipped", "idle"
    if task.status != "Done":
        return "Not done", "late"
    if task.completed and task.due and task.completed > task.due:
        days = (task.completed - task.due).days
        return f"{logic.plural(days, 'day')} late", "late"
    return "On time", "done"


def _summary(world: World, p: ProjectRec) -> dict:
    tasks = world.tasks_by_project.get(p.id, [])
    return {
        "id": p.id,
        "name": p.name,
        "site": world.site_name(p),
        "program_type": world.template_name(p),
        "day_one": p.start.isoformat() if p.start else None,
        "day_one_text": logic.fmt_date(p.start, date(1, 1, 1)) if p.start else "No Day 1",
        "on_time": on_time_percent(tasks),
    }


@router.get("")
def list_archive(
    site: str | None = Query(None, max_length=100),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    world = World()
    start, end = _parse_bound(from_, False), _parse_bound(to, True)
    rows = []
    for p in world.projects.values():
        if not p.closed:
            continue
        if site and site.strip().lower() not in world.site_name(p).lower() and site.strip().lower() not in p.name.lower():
            continue
        if start and (p.start is None or p.start < start):
            continue
        if end and (p.start is None or p.start > end):
            continue
        rows.append(_summary(world, p))
    rows.sort(key=lambda r: r["day_one"] or "", reverse=True)
    return {"launches": rows}


@router.get("/{project_id}")
def archive_detail(project_id: str, user: CurrentUser = Depends(require_admin)):
    world = World()
    p = world.project(project_id)
    if not p.closed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That launch is not closed")
    tasks = sorted(
        world.tasks_by_project.get(p.id, []), key=lambda t: (t.due is None, t.due, t.name)
    )
    rows = []
    for t in tasks:
        label, tone = task_outcome(t)
        rows.append(
            {
                "id": t.id,
                "name": t.name,
                "label": label,
                "tone": tone,
                "planned": logic.fmt_date(t.due, p.start or world.today) if t.due and not t.one_off else "None",
                "actual": logic.fmt_date(t.completed, p.start or world.today) if t.completed else "None",
                "actual_late": tone == "late" and t.completed is not None,
                "done_by": world.user_short(t.completed_by),
            }
        )
    template = world.templates.get(p.template_id or "")
    version = p.template_version or (template.version if template else None)
    year_ref = p.start or world.today
    parts = [f"{world.template_name(p)}{f' v{version}' if version else ''}"]
    if p.start:
        parts.append(f"Day 1 {logic.fmt_date(p.start, date(1, 1, 1))}")
    if p.closed_date:
        parts.append(f"closed {logic.fmt_date(p.closed_date, year_ref)}")
    log = history.for_project(p.id, user.actor, world.log)
    return {
        **_summary(world, p),
        "subtitle": " · ".join(parts),
        "counts": {
            "tasks": len(tasks),
            "late": sum(1 for r in rows if r["tone"] == "late" and r["label"] != "Not done"),
            "skipped": sum(1 for t in tasks if t.status == "Skipped"),
            "added": sum(1 for t in tasks if t.one_off),
        },
        "tasks": rows,
        "history": [history_dict(world, r) for r in log],
    }
