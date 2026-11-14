"""Tasks: My Tasks, the task page, status, notes, links, reminders and reassigning.

Staff can open any task, but only change their own. Partners only see tasks in
projects they are listed on. Viewers change nothing.
"""

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status

from app import permissions
from app.airtable import client
from app.airtable.schema import Links, Reminders, Work
from app.auth.deps import current_user, require_admin, require_can_edit
from app.email.templates import task_url
from app.models.task import AssignIn, LinkIn, NoteIn, ReassignIn, ReminderIn, TaskUpdateIn
from app.models.user import CurrentUser
from app.services import calendar_feed, clock, history, logic, reminders
from app.services.links import FILE_KIND, calendar_url, link_kind, read_upload, save_upload
from app.services.records import TaskRec, load_reminders, safe
from app.services.timeline import find_cycle
from app.services.views import World, check_project_access, link_dict, note_dict, task_row

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

DONE_RECENT_DAYS = 7
STAFF_STATUSES = {"Not Started", "In Progress", "Blocked", "Done"}


def _visible_task(world: World, task_id: str, user: CurrentUser) -> TaskRec:
    task = world.task(task_id)
    project = world.projects.get(task.session_id or "")
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    check_project_access(user, project)
    return task


def _require_edit(task: TaskRec, user: CurrentUser) -> None:
    if not permissions.can_edit_task(user.actor, user.id, task.assignees):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You can only change tasks assigned to you"
        )


@router.get("/mine")
def my_tasks(
    filter: str | None = Query(None, pattern="^(week|overdue)$"),
    project: str | None = None,
    user: CurrentUser = Depends(current_user),
):
    world = World()
    today = world.today
    week_end = clock.end_of_week(today)
    mine = [
        t
        for t in world.tasks
        if t.is_assigned(user.id)
        and t.session_id in world.projects
        and not world.projects[t.session_id].closed
        and permissions.can_view_project(user.actor, user.id, world.projects[t.session_id].partner_ids)
    ]
    open_tasks = [t for t in mine if logic.is_open(t.status)]
    overdue = [t for t in open_tasks if logic.is_overdue(t, today)]
    this_week = [t for t in open_tasks if t.due and today <= t.due <= week_end]
    later = [t for t in open_tasks if t not in overdue and t not in this_week]
    recent = [
        t
        for t in mine
        if not logic.is_open(t.status)
        and t.completed
        and t.completed >= today - timedelta(days=DONE_RECENT_DAYS)
    ]

    project_ids = sorted({t.session_id for t in mine if t.session_id}, key=lambda p: world.projects[p].name)
    projects = [{"id": p, "name": world.site_name(world.projects[p])} for p in project_ids]

    def keep(tasks: list[TaskRec]) -> list[TaskRec]:
        if project:
            tasks = [t for t in tasks if t.session_id == project]
        return sorted(tasks, key=lambda t: (t.due is None, t.due, t.name))

    groups = {
        "overdue": keep(overdue),
        "this_week": keep(this_week),
        "later": keep(later),
        "done_recently": sorted(keep(recent), key=lambda t: t.completed, reverse=True),
    }
    if filter == "week":
        groups.update(overdue=[], later=[], done_recently=[])
    elif filter == "overdue":
        groups.update(this_week=[], later=[], done_recently=[])

    first = None
    if open_tasks:
        dependents = world.dependents

        def urgency(t: TaskRec):
            open_deps = [d for d in dependents.get(t.id, []) if logic.is_open(d.status)]
            return (0 if logic.is_overdue(t, today) else 1, -len(open_deps), t.due or today + timedelta(days=3650))

        best = min(open_tasks, key=urgency)
        open_deps = [d for d in dependents.get(best.id, []) if logic.is_open(d.status)]
        project_rec = world.projects[best.session_id]
        site = world.site_name(project_rec)
        parts = []
        if logic.is_overdue(best, today):
            parts.append(f"{site} is waiting on it.")
        else:
            parts.append(f"{logic.due_text(best, today)} for {site}.")
        if open_deps:
            parts.append(
                f"{logic.plural(len(open_deps), 'task')} {'depends' if len(open_deps) == 1 else 'depend'} on this one."
            )
        first = {"id": best.id, "name": best.name, "reason": " ".join(parts)}

    return {
        "groups": {k: [task_row(world, t, user) for t in v] for k, v in groups.items()},
        "counts": {
            "overdue": len(overdue),
            "this_week": len(this_week),
            "open": len(open_tasks),
        },
        "projects": projects,
        "do_this_first": first,
        "can_edit": permissions.can_update_own_tasks(user.actor),
    }


def _in_calendar_feed(world: World, task: TaskRec, user: CurrentUser) -> bool:
    me = world.users.get(user.id)
    return bool(me and me.calendar_token) and task.id in {
        t.id for t in calendar_feed.feed_tasks(world, me)
    }


@router.get("/{task_id}")
def get_task(task_id: str, user: CurrentUser = Depends(current_user)):
    world = World()
    task = _visible_task(world, task_id, user)
    project = world.projects[task.session_id]
    row = task_row(world, task, user)
    can_edit = row["can_edit"]
    is_admin = permissions.can_assign_tasks(user.actor)
    today = world.today

    needs_first = [
        {
            "id": d.id,
            "name": d.name,
            "status": d.status,
            "overdue": logic.is_overdue(d, today),
            "due": d.due.isoformat() if d.due else None,
            "due_short": logic.fmt_date(d.due, today) if d.due else "",
        }
        for d in (world.tasks_by_id[i] for i in task.depends_on if i in world.tasks_by_id)
    ]
    waiting_on_this = [
        {
            "id": d.id,
            "name": d.name,
            "status": d.status,
            "due": d.due.isoformat() if d.due else None,
            "due_short": logic.fmt_date(d.due, today) if d.due else "",
        }
        for d in world.dependents.get(task.id, [])
    ]
    open_waiting = [d for d in waiting_on_this if logic.is_open(d["status"])]
    links = [
        link_dict(world, link, can_edit)
        for link in world.links
        if link.work_id == task.id
    ]
    if task.resource_link:
        links.insert(
            0,
            {
                "id": None,
                "title": "Resource from the template",
                "url": task.resource_link,
                "kind": link_kind(task.resource_link),
                "is_file": False,
                "file_name": None,
                "file_size": None,
                "added_by": None,
                "can_remove": False,
            },
        )
    notes = history.notes_for_task(task.id, user.actor, world.log)
    in_project = sorted(
        (t for t in world.tasks_by_project.get(project.id, []) if t.id != task.id),
        key=lambda t: (t.due is None, t.due, t.name),
    )
    return {
        **row,
        "description": task.description,
        "timing": logic.timing_label(task.anchor, task.days_before),
        "site_type": project.site_type,
        "day_one": project.start.isoformat() if project.start else None,
        "needs_first": needs_first,
        "waiting_on_this": waiting_on_this,
        "risk_note": (
            f"{logic.name_list([d['name'] for d in open_waiting])} "
            f"{'is' if len(open_waiting) == 1 else 'are'} waiting on this task. "
            f"{'It' if len(open_waiting) == 1 else 'They'} will show as at risk until this is done."
            if open_waiting and logic.is_open(task.status)
            else None
        ),
        "date_warnings": [
            f"Due before {d.name} ({logic.fmt_date(d.due, today)}), which it needs first."
            for d in logic.due_too_early(task, world.tasks_by_id)
        ]
        + [
            f"Due after {d.name} ({logic.fmt_date(d.due, today)}), which waits on it."
            for d in sorted(world.dependents.get(task.id, []), key=lambda d: (d.due or today, d.name))
            if task.id in {x.id for x in logic.due_too_early(d, world.tasks_by_id)}
        ],
        "notes": [note_dict(world, n, user) for n in notes],
        "links": links,
        "reminders": reminders.task_panel(task, user.id, today),
        "calendar_url": calendar_url(
            f"{task.name} ({world.site_name(project)})", row["due"], task_url(task.id)
        ),
        # True when their calendar feed is on and already includes this task, so the
        # page can say so next to Add to Google Calendar.
        "in_calendar_feed": _in_calendar_feed(world, task, user),
        "can_edit": can_edit,
        "can_admin": is_admin,
        "can_set_reminder": permissions.can_set_reminder(user.actor),
        "can_share_notes": permissions.can_share_notes(user.actor) and can_edit,
        "back": (
            {"label": "My Tasks", "to": "/my-tasks"}
            if task.is_assigned(user.id)
            else {"label": world.site_name(project), "to": f"/projects/{project.id}"}
        ),
        "people": (
            [
                {"id": u.id, "name": u.name}
                for u in sorted(world.users.values(), key=lambda u: u.name)
                if u.active and u.access_level != "Viewer"
            ]
            if is_admin
            else []
        ),
        "project_tasks": (
            [{"id": t.id, "name": t.name} for t in in_project] if is_admin else []
        ),
        "today": today.isoformat(),
    }


def apply_status(world: World, task: TaskRec, new_status: str, user: CurrentUser) -> None:
    """Change a task's status and log it. Done records today and who did it."""
    if new_status == task.status:
        return
    fields: dict = {Work.STATUS: new_status}
    today = world.today
    if new_status == "Done":
        fields[Work.COMPLETED_DATE] = today.isoformat()
        fields[Work.COMPLETED_BY] = [user.id]
    elif task.status in ("Done", "Skipped"):
        fields[Work.COMPLETED_DATE] = None
        fields[Work.COMPLETED_BY] = []
    client.update_record(Work.TABLE, task.id, fields)
    if new_status in ("Done", "Skipped"):
        reminders.cancel_custom_for_task(task.id)
    text = {
        "Done": f"completed {task.name}",
        "Skipped": f"skipped {task.name}",
    }.get(new_status, f"marked {task.name} {new_status.lower()}")
    history.log_event(
        task.session_id, task.id, user.id, "Status Change", text, task.status, new_status
    )


@router.patch("/{task_id}")
def update_task(task_id: str, body: TaskUpdateIn, user: CurrentUser = Depends(require_can_edit)):
    world = World()
    task = _visible_task(world, task_id, user)
    sent = body.model_fields_set
    admin_fields = sent & {"due_date", "name", "depends_on"}
    if admin_fields and not permissions.can_edit_task_details(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can change that")
    if "status" in sent and body.status:
        _require_edit(task, user)
        if body.status not in STAFF_STATUSES and not permissions.can_edit_task_details(user.actor):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can skip a task")
        apply_status(world, task, body.status, user)

    today = world.today
    if "due_date" in sent and body.due_date and body.due_date != task.due:
        client.update_record(Work.TABLE, task.id, {Work.DUE_DATE_OVERRIDE: body.due_date.isoformat()})
        history.log_event(
            task.session_id,
            task.id,
            user.id,
            "Date Change",
            f"moved {task.name} to {logic.fmt_date(body.due_date, today)}",
            task.due.isoformat() if task.due else "",
            body.due_date.isoformat(),
        )
    if "name" in sent and body.name and body.name.strip() != task.name:
        client.update_record(Work.TABLE, task.id, {Work.TASK_NAME: body.name.strip()})
        history.log_event(
            task.session_id, task.id, user.id, "System", f"renamed {task.name} to {body.name.strip()}", task.name, body.name.strip()
        )
    if "depends_on" in sent and body.depends_on is not None:
        same_project = {t.id: t for t in world.tasks_by_project.get(task.session_id or "", [])}
        deps = [d for d in dict.fromkeys(body.depends_on) if d != task.id]
        if any(d not in same_project for d in deps):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Needs first must be a task in this project")
        edges = {t.id: list(t.depends_on) for t in same_project.values()}
        edges[task.id] = deps
        if find_cycle(edges):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "That would make the tasks wait on each other in a circle.",
            )
        if sorted(deps) != sorted(task.depends_on):
            client.update_record(Work.TABLE, task.id, {Work.DEPENDS_ON: deps})
            names = [same_project[d].name for d in deps]
            history.log_event(
                task.session_id,
                task.id,
                user.id,
                "System",
                f"set {task.name} to need {logic.name_list(names, 3)} first" if names else f"cleared what {task.name} needs first",
            )
    fresh = World()
    return task_row(fresh, fresh.task(task.id), user)


@router.post("/reassign")
def reassign_tasks(body: ReassignIn, background: BackgroundTasks, user: CurrentUser = Depends(require_admin)):
    """Admin only: move the chosen open tasks to one active person.

    Every task must exist, be open and be on a launch that is not closed, or
    nothing moves.
    """
    if not permissions.can_reassign_tasks(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin view required")
    world = World()
    taker = world.users.get(body.to_user)
    if taker is None or not taker.active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The person taking over must be active")
    giver = world.users.get(body.from_user) if body.from_user else None
    if body.from_user and giver is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Person not found")
    tasks = []
    for task_id in dict.fromkeys(body.task_ids):
        task = world.task(task_id)
        project = world.projects.get(task.session_id or "")
        if not logic.is_open(task.status) or project is None or project.closed:
            raise HTTPException(status.HTTP_409_CONFLICT, "Only open tasks can be reassigned")
        if giver and not task.is_assigned(giver.id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{task.name} is not assigned to {giver.short_name}")
        tasks.append(task)

    def new_people(t: TaskRec) -> list[str]:
        if giver:
            return list(dict.fromkeys(taker.id if a == giver.id else a for a in t.assignees))
        return [taker.id]

    changed = [t for t in tasks if new_people(t) != t.assignees]
    if changed:
        client.update_records(Work.TABLE, [{"id": t.id, "fields": {Work.ASSIGNED_TO: new_people(t)}} for t in changed])
        names = lambda ids: logic.name_list([world.user_name(i) or "Someone" for i in ids], 3)  # noqa: E731
        history.log_events(
            [
                history.Event(
                    t.session_id,
                    t.id,
                    user.id,
                    "Reassignment",
                    f"gave {t.name} to {taker.name}",
                    names(t.assignees) if t.assignees else "Nobody",
                    names(new_people(t)),
                )
                for t in changed
            ]
        )
        emailed = [t.id for t in changed if taker.id not in t.assignees]
        if emailed and taker.id != user.id:
            background.add_task(reminders.send_assignment_emails, {taker.id: emailed}, user.name)
    fresh = World()
    return {"moved": len(changed), "tasks": [task_row(fresh, fresh.task(t.id), user) for t in tasks]}


@router.post("/{task_id}/assign")
def assign_task(
    task_id: str, body: AssignIn, background: BackgroundTasks, user: CurrentUser = Depends(require_admin)
):
    world = World()
    task = world.task(task_id)
    # user_ids sets everyone on the task. user_id (one person) still works.
    if body.user_ids is not None:
        wanted = list(dict.fromkeys(i for i in body.user_ids if i))
    else:
        wanted = [body.user_id] if body.user_id else []
    for uid in wanted:
        # Someone already on the task can stay even if they have since been deactivated.
        if uid not in world.users or (not world.users[uid].active and uid not in task.assignees):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick active people")
    if wanted == task.assignees:
        return task_row(world, task, user)
    client.update_record(Work.TABLE, task.id, {Work.ASSIGNED_TO: wanted})
    names = lambda ids: logic.name_list([world.user_name(i) or "Someone" for i in ids], 3)  # noqa: E731
    old = names(task.assignees) if task.assignees else "Nobody"
    new = names(wanted) if wanted else "Nobody"
    added = [i for i in wanted if i not in task.assignees]
    removed = [i for i in task.assignees if i not in wanted]
    if not task.assignees or not wanted or not (set(wanted) & set(task.assignees)):
        text = f"gave {task.name} to {new}"
    elif added and not removed:
        text = f"added {names(added)} to {task.name}"
    elif removed and not added:
        text = f"took {names(removed)} off {task.name}"
    else:
        text = f"gave {task.name} to {new}"
    history.log_event(task.session_id, task.id, user.id, "Reassignment", text, old, new)
    project = world.projects.get(task.session_id or "")
    emails = {i: [task.id] for i in added if i != user.id}
    if emails and logic.is_open(task.status) and project and not project.closed:
        background.add_task(reminders.send_assignment_emails, emails, user.name)
    fresh = World()
    return task_row(fresh, fresh.task(task.id), user)


@router.post("/{task_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(task_id: str, body: NoteIn, user: CurrentUser = Depends(require_can_edit)):
    world = World()
    task = _visible_task(world, task_id, user)
    _require_edit(task, user)
    history.log_event(
        task.session_id,
        task.id,
        user.id,
        "Note",
        body.text,
        visibility=permissions.default_note_visibility(user.actor),
    )
    fresh = World()
    notes = history.notes_for_task(task.id, user.actor, fresh.log)
    return {"notes": [note_dict(fresh, n, user) for n in notes]}


@router.post("/{task_id}/links", status_code=status.HTTP_201_CREATED)
def add_task_link(task_id: str, body: LinkIn, user: CurrentUser = Depends(require_can_edit)):
    world = World()
    task = _visible_task(world, task_id, user)
    _require_edit(task, user)
    kind = link_kind(body.url)
    created = client.create_record(
        Links.TABLE,
        {
            Links.TITLE: body.title.strip(),
            Links.URL: body.url,
            Links.KIND: kind,
            Links.WORK: [task.id],
            Links.SESSION: [task.session_id] if task.session_id else [],
            Links.ADDED_BY: [user.id],
        },
        typecast=True,
    )
    history.log_event(
        task.session_id,
        task.id,
        user.id,
        "Link",
        f"added the link {body.title.strip()} to {task.name}",
        visibility=permissions.default_note_visibility(user.actor),
    )
    return {"id": created["id"], "kind": kind}


@router.post("/{task_id}/files", status_code=status.HTTP_201_CREATED)
def add_task_file(
    task_id: str,
    file: UploadFile = File(...),
    title: str = Form("", max_length=200),
    user: CurrentUser = Depends(require_can_edit),
):
    """Upload a file or photo from someone's computer. Same rules as adding a link."""
    world = World()
    task = _visible_task(world, task_id, user)
    _require_edit(task, user)
    try:
        filename, content, content_type = read_upload(file)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    name = title.strip() or filename
    created = save_upload(name, filename, content, content_type, user.id, task.session_id, task.id)
    history.log_event(
        task.session_id,
        task.id,
        user.id,
        "Link",
        f"uploaded the file {name} to {task.name}",
        visibility=permissions.default_note_visibility(user.actor),
    )
    return {"id": created["id"], "kind": FILE_KIND}


@router.post("/{task_id}/reminders", status_code=status.HTTP_201_CREATED)
def add_reminder(task_id: str, body: ReminderIn, user: CurrentUser = Depends(require_can_edit)):
    world = World()
    task = _visible_task(world, task_id, user)
    if not permissions.can_set_reminder(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read only access")
    if body.send_on < world.today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick today or a later date")
    if not logic.is_open(task.status):
        raise HTTPException(status.HTTP_409_CONFLICT, "This task is already finished")
    client.create_record(
        Reminders.TABLE,
        {
            Reminders.NAME: f"Custom: {task.name}"[:250],
            Reminders.WORK: [task.id],
            Reminders.RECIPIENT: [user.id],
            Reminders.CREATED_BY: [user.id],
            Reminders.KIND: "Custom",
            Reminders.SEND_ON: body.send_on.isoformat(),
            Reminders.STATUS: "Scheduled",
            Reminders.NOTE: body.note.strip(),
        },
        typecast=True,
    )
    return reminders.task_panel(task, user.id, world.today, safe(load_reminders))
