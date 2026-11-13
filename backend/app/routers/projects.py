"""Projects: the dashboard, starting a launch, a project's page, Day 1 and closing.

Dashboard (/dashboard, admin) and Projects (/projects, staff, read only) use
GET /api/projects. Partners get only the projects they are listed on.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app import permissions
from app.airtable import client
from app.airtable.schema import Links, Work
from app.auth.deps import current_user, require_admin, require_internal
from app.models.project import (
    CloseIn,
    MoveDayOneIn,
    ProjectCreateIn,
    ProjectDetailsIn,
    ProjectPreviewIn,
    UndoIn,
)
from app.models.task import LinkIn, OneOffTaskIn
from app.models.user import CurrentUser
from app.services import history, logic, projects, reminders, timeline
from app.services.links import link_kind
from app.services.records import load_reminders, safe
from app.services.views import (
    World,
    check_project_access,
    dashboard_summary,
    history_dict,
    link_dict,
    project_card,
    sort_cards,
    task_row,
    visible_projects,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

HISTORY_PAGE_SIZE = 20
HISTORY_ON_PAGE = 5


@router.get("")
def list_projects(
    status_filter: str = Query("active", alias="status", pattern="^(active|closed)$"),
    sort: str | None = Query(None, pattern="^(day1|overdue|type)$"),
    region: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    if status_filter == "closed" and not permissions.can_see_archive(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can see closed launches")
    world = World()
    wanted_closed = status_filter == "closed"
    cards = [
        project_card(world, p)
        for p in visible_projects(world, user)
        if p.closed == wanted_closed
    ]
    regions = sorted(
        {(c["region_id"], c["region"]) for c in cards if c["region_id"]}, key=lambda r: r[1]
    )
    types = sorted({c["program_type"] for c in cards})
    if region:
        cards = [c for c in cards if c["region_id"] == region]
    return {
        "projects": sort_cards(cards, sort),
        "summary": dashboard_summary(cards, world.today),
        "regions": [{"id": r[0], "name": r[1]} for r in regions],
        "program_types": types,
    }


@router.post("/preview")
def preview_project(body: ProjectPreviewIn, _: CurrentUser = Depends(require_admin)):
    """The task list a new launch would get. Writes nothing."""
    return projects.preview(World(), body)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreateIn,
    background: BackgroundTasks,
    user: CurrentUser = Depends(require_admin),
):
    project_id, by_user = projects.create(World(), body, user)
    background.add_task(reminders.send_assignment_emails, by_user, user.name)
    return {"id": project_id}


def _project_detail(world: World, project_id: str, user: CurrentUser) -> dict:
    project = world.project(project_id)
    check_project_access(user, project)
    card = project_card(world, project)
    tasks = sorted(
        world.tasks_by_project.get(project.id, []),
        key=lambda t: (t.due is None, t.due, t.sort_order or 0, t.name),
    )
    rows = [task_row(world, t, user) for t in tasks]
    groups = [
        {"phase": phase, "tasks": [r for r in rows if r["phase"] == phase]}
        for phase in logic.PHASES
    ]
    site = world.sites.get(project.site_id or "")
    template = world.templates.get(project.template_id or "")
    can_see_history = permissions.can_see_history(user.actor)
    log = history.for_project(project.id, user.actor, world.log) if can_see_history else []
    is_admin = permissions.can_manage_projects(user.actor)
    return {
        **card,
        "template_version": project.template_version or (template.version if template else None),
        "program_hours": project.hours,
        "location": project.location or (site.location if site else ""),
        "partner": {
            "name": project.partner_name,
            "email": project.partner_email,
            "phone": project.partner_phone,
        },
        "shipping_address": project.shipping_address,
        "drive_folder": project.drive_folder,
        "groups": groups,
        "links": [
            link_dict(world, link, is_admin)
            for link in world.links
            if link.session_id == project.id and not link.work_id
        ],
        "history": [history_dict(world, r) for r in log[:HISTORY_ON_PAGE]],
        "history_count": len(log),
        "can_see_history": can_see_history,
        "team": [
            {
                "role_id": t.role_id,
                "role": world.role_name(t.role_id),
                "user_id": t.user_id,
                "user": world.user_short(t.user_id),
            }
            for t in world.team_for(project.id)
        ],
        "partners": [
            {"id": u, "name": world.user_name(u)} for u in project.partner_ids if u in world.users
        ],
        "open_tasks": sum(1 for t in tasks if logic.is_open(t.status)),
        "can_manage": is_admin,
        "can_delete": permissions.can_delete_projects(user.actor),
        "can_close": is_admin
        and not project.closed
        and project.start is not None
        and project.start <= world.today,
        "edit": {
            "name": project.name,
            "site_id": project.site_id,
            "site_type": project.site_type,
            "day_one": project.start.isoformat() if project.start else None,
            "end_date": project.end.isoformat() if project.end else None,
            "program_hours": project.hours,
            "location": project.location,
            "instructor_ids": project.instructor_ids,
            "partner_name": project.partner_name,
            "partner_email": project.partner_email,
            "partner_phone": project.partner_phone,
            "shipping_address": project.shipping_address,
            "drive_folder": project.drive_folder,
            "partner_ids": project.partner_ids,
        }
        if is_admin
        else None,
    }


@router.get("/{project_id}")
def get_project(project_id: str, user: CurrentUser = Depends(current_user)):
    return _project_detail(World(), project_id, user)


@router.patch("/{project_id}")
def update_project(
    project_id: str, body: ProjectDetailsIn, user: CurrentUser = Depends(require_admin)
):
    world = World()
    projects.update_details(world, world.project(project_id), body, user)
    return _project_detail(World(), project_id, user)


@router.delete("/{project_id}")
def delete_project(project_id: str, user: CurrentUser = Depends(require_admin)):
    """Delete a launch and everything that belongs to it. Admins only. Cannot be undone."""
    if not permissions.can_delete_projects(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can delete launches")
    world = World()
    return projects.delete(world, world.project(project_id), user)


@router.post("/{project_id}/move-day-one")
def move_day_one(
    project_id: str, body: MoveDayOneIn, user: CurrentUser = Depends(require_admin)
):
    world = World()
    project = world.project(project_id)
    if project.closed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reopen the launch before moving Day 1")
    if body.preview:
        plan = timeline.plan_shift(project, world.tasks, safe(load_reminders), body.new_day_one)
        return {
            "moved_tasks": len(plan.moved),
            "kept_tasks": len(plan.kept),
            "moved_reminders": len(plan.reminder_ids),
            "delta_days": plan.delta,
            "message": plan.preview_text(),
        }
    return timeline.shift_day_one(project_id, body.new_day_one, user.id)


@router.post("/{project_id}/move-day-one/undo")
def undo_move_day_one(project_id: str, body: UndoIn, user: CurrentUser = Depends(require_admin)):
    return timeline.undo_shift(project_id, body.batch, user.id)


@router.post("/{project_id}/tasks", status_code=status.HTTP_201_CREATED)
def add_one_off_task(
    project_id: str,
    body: OneOffTaskIn,
    background: BackgroundTasks,
    user: CurrentUser = Depends(require_admin),
):
    world = World()
    project = world.project(project_id)
    if body.role_id and body.role_id not in world.roles:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a role from the list")
    picked = list(dict.fromkeys([*([body.user_id] if body.user_id else []), *body.user_ids]))
    if any(u not in world.users for u in picked):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a person from the list")
    in_project = {t.id: t for t in world.tasks_by_project.get(project.id, [])}
    mine = set(in_project)
    needs_first = list(dict.fromkeys(body.needs_first))
    comes_before = list(dict.fromkeys(body.comes_before))
    if any(d not in mine for d in needs_first):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Needs first must be a task in this project"
        )
    if any(d not in mine for d in comes_before):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Comes before must be a task in this project"
        )
    # The new task sits between the two: it waits on needs_first, and every
    # comes_before task waits on it. Refuse anything that makes a circle.
    edges = {t.id: list(t.depends_on) for t in in_project.values()}
    edges["new"] = needs_first
    for d in comes_before:
        edges[d] = [*edges[d], "new"]
    if timeline.find_cycle(edges):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "That would make the tasks wait on each other in a circle.",
        )
    fields = {
        Work.SESSION: [project.id],
        Work.TASK_NAME: body.name.strip(),
        Work.ANCHOR: "Start",
        Work.DAYS_BEFORE_ANCHOR: (project.start - body.due_date).days if project.start else 0,
        Work.DUE_DATE_OVERRIDE: body.due_date.isoformat(),
        Work.STATUS: "Not Started",
        Work.ONE_OFF: True,
        Work.SORT_ORDER: float(len(mine)),
    }
    if not picked and body.role_id:
        team = [t.user_id for t in world.team_for(project.id) if t.role_id == body.role_id and t.user_id]
        picked = team[:1]
    if body.role_id:
        fields[Work.ROLE] = [body.role_id]
    if picked:
        fields[Work.ASSIGNED_TO] = picked
    if needs_first:
        fields[Work.DEPENDS_ON] = needs_first
    created = client.create_record(Work.TABLE, fields, typecast=True)
    for d in comes_before:
        later = in_project[d]
        client.update_record(Work.TABLE, d, {Work.DEPENDS_ON: [*later.depends_on, created["id"]]})
    text = f"added the task {body.name.strip()}"
    if comes_before:
        text += f" before {logic.name_list([in_project[d].name for d in comes_before], 3)}"
    history.log_event(project.id, created["id"], user.id, "Task Added", text)
    # A closed launch sends no reminders, so it sends no new-task email either.
    emails = {u: [created["id"]] for u in picked if u != user.id}
    if emails and not project.closed:
        background.add_task(reminders.send_assignment_emails, emails, user.name)
    # Dates never move on their own. Say which ones are now out of order instead.
    name = body.name.strip()
    warnings = [
        f"{name} is due before {in_project[d].name} ({logic.fmt_date(in_project[d].due, world.today)}), which it needs first."
        for d in needs_first
        if logic.is_open(in_project[d].status) and in_project[d].due and in_project[d].due > body.due_date
    ] + [
        f"{in_project[d].name} ({logic.fmt_date(in_project[d].due, world.today)}) is due before {name}, which it now waits on."
        for d in comes_before
        if logic.is_open(in_project[d].status) and in_project[d].due and in_project[d].due < body.due_date
    ]
    return {"id": created["id"], "warnings": warnings}


@router.post("/{project_id}/close")
def close_project(project_id: str, body: CloseIn, user: CurrentUser = Depends(require_admin)):
    world = World()
    return projects.close(world, world.project(project_id), body.skip_open, user)


@router.post("/{project_id}/reopen")
def reopen_project(project_id: str, user: CurrentUser = Depends(require_admin)):
    world = World()
    projects.reopen(world.project(project_id), user)
    return {"reopened": True}


@router.get("/{project_id}/history")
def project_history(
    project_id: str,
    page: int = Query(1, ge=1),
    user: CurrentUser = Depends(require_internal),
):
    world = World()
    project = world.project(project_id)
    rows = history.for_project(project.id, user.actor, world.log)
    start = (page - 1) * HISTORY_PAGE_SIZE
    return {
        "entries": [history_dict(world, r) for r in rows[start : start + HISTORY_PAGE_SIZE]],
        "page": page,
        "pages": max(1, -(-len(rows) // HISTORY_PAGE_SIZE)),
        "total": len(rows),
    }


@router.post("/{project_id}/links", status_code=status.HTTP_201_CREATED)
def add_project_link(project_id: str, body: LinkIn, user: CurrentUser = Depends(require_admin)):
    world = World()
    project = world.project(project_id)
    kind = link_kind(body.url)
    created = client.create_record(
        Links.TABLE,
        {
            Links.TITLE: body.title.strip(),
            Links.URL: body.url,
            Links.KIND: kind,
            Links.SESSION: [project.id],
            Links.ADDED_BY: [user.id],
        },
        typecast=True,
    )
    history.log_event(project.id, None, user.id, "Link", f"added the link {body.title.strip()}")
    return {"id": created["id"], "kind": kind}
