"""Starting, editing and closing launches."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException, status

from app.airtable import client
from app.airtable.schema import (
    SESSION_COMPLETE,
    SESSION_IN_PROGRESS,
    SESSION_NOT_STARTED,
    SITE_TYPES,
    ActivityLog,
    Links,
    Reminders,
    Session,
    SessionTeam,
    Site,
    Work,
)
from app.models.project import OneOffIn, ProjectCreateIn, ProjectDetailsIn, ProjectPreviewIn
from app.models.user import CurrentUser
from app.services import clock, history, logic
from app.services.records import ProjectRec, live_steps, load_reminders, safe
from app.services.timeline import (
    OneOff,
    SourceItem,
    generate_timeline,
    items_from_one_offs,
    items_from_project,
    items_from_steps,
    plan_tasks,
    start_from_past_launch,
)
from app.services.views import World

PREVIEW_FIRST = 5


def _one_offs(rows: list[OneOffIn]) -> list[OneOff]:
    return [OneOff(r.name.strip(), r.due_date, r.role_id, r.user_id, list(r.needs_first)) for r in rows]


def source_items(world: World, body: ProjectPreviewIn) -> tuple[list[SourceItem], str | None, ProjectRec | None]:
    """The tasks a new launch would get, from a template or from a past launch."""
    if body.from_project_id:
        past = world.project(body.from_project_id)
        tasks = world.tasks_by_project.get(past.id, [])
        return items_from_project(tasks, past.start), past.template_id, past
    if not body.template_id or body.template_id not in world.templates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a program type")
    steps = live_steps(body.template_id, world.steps)
    return items_from_steps(steps), body.template_id, None


def role_candidates(world: World, role_id: str) -> list[dict]:
    return sorted(
        (
            {"id": u.id, "name": u.name}
            for u in world.users.values()
            if u.active and role_id in u.role_ids and u.access_level not in ("Partner", "Viewer")
        ),
        key=lambda u: u["name"],
    )


def resolve_assignments(
    world: World, role_ids: list[str], chosen: dict[str, str | None]
) -> dict[str, str | None]:
    """The person for each role: the form's choice, else the only person with the role."""
    out: dict[str, str | None] = {}
    for role_id in role_ids:
        if role_id in chosen:
            user = chosen[role_id]
            out[role_id] = user if user in world.users else None
            continue
        candidates = role_candidates(world, role_id)
        out[role_id] = candidates[0]["id"] if len(candidates) == 1 else None
    return out


def preview(world: World, body: ProjectPreviewIn) -> dict:
    """What Create launch would make. Writes nothing."""
    items, template_id, past = source_items(world, body)
    one_offs = _one_offs(body.one_offs)
    items = items + items_from_one_offs(one_offs, len(items))
    role_ids = []
    for item in items:
        if item.role_id and item.role_id not in role_ids:
            role_ids.append(item.role_id)
    assignments = resolve_assignments(world, role_ids, body.assignments)
    start = body.day_one
    end = body.end_date or start
    planned = plan_tasks(items, start, end, assignments, body.overrides)
    names = {i.key: i.name for i in items}
    today = world.today
    tasks = [
        {
            "key": p.key,
            "name": p.name,
            "due": p.due.isoformat() if p.due else None,
            "due_text": logic.fmt_date(p.due, today) if p.due else "Pick Day 1",
            "group": logic.weeks_out_label(p.due, start),
            "role_id": p.role_id,
            "role": world.role_name(p.role_id),
            "user_id": p.user_id,
            "user": world.user_short(p.user_id),
            "override": body.overrides.get(p.key),
            "one_off": p.one_off,
            "after": [names[d] for d in p.depends_on if d in names],
        }
        for p in planned
    ]
    template = world.templates.get(template_id or "")
    last = tasks[-1] if tasks else None
    return {
        "template_id": template_id,
        "template_name": template.name if template else None,
        "from_project": (
            {"id": past.id, "name": past.name, "day_one": past.start.isoformat() if past.start else None}
            if past
            else None
        ),
        "count": len(tasks),
        "tasks": tasks,
        "first": PREVIEW_FIRST,
        "last_task": {"name": last["name"], "due_text": last["due_text"]} if last else None,
        "roles": [
            {
                "role_id": role_id,
                "role": world.role_name(role_id) or "Unknown role",
                "candidates": role_candidates(world, role_id),
                "user_id": assignments.get(role_id),
            }
            for role_id in role_ids
        ],
        "needs_owner": sum(1 for t in tasks if not t["user_id"]),
    }


def _detail_fields(body: ProjectDetailsIn, world: World) -> dict:
    """Session fields from the form. Only fields that were sent are included."""
    sent = body.model_fields_set
    fields: dict = {}
    if "name" in sent and body.name is not None:
        fields[Session.PROGRAM_NAME] = body.name.strip()
    if "site_id" in sent and body.site_id:
        if body.site_id not in world.sites:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a site from the list")
        fields[Session.SITE] = [body.site_id]
    if "site_type" in sent:
        if body.site_type and body.site_type not in SITE_TYPES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a site type from the list")
        fields[Session.SITE_TYPE] = body.site_type or None
    simple = {
        "program_hours": Session.PROGRAM_HOURS,
        "location": Session.LOCATION,
        "partner_name": Session.PARTNER_CONTACT_NAME,
        "partner_email": Session.PARTNER_CONTACT_EMAIL,
        "partner_phone": Session.PARTNER_CONTACT_PHONE,
        "shipping_address": Session.SHIPPING_ADDRESS,
        "drive_folder": Session.DRIVE_FOLDER,
    }
    for attr, name in simple.items():
        if attr in sent:
            value = getattr(body, attr)
            fields[name] = (value or "").strip() or None
    if "instructor_ids" in sent and body.instructor_ids is not None:
        fields[Session.INSTRUCTORS] = [i for i in body.instructor_ids if i in world.instructors]
    if "partner_ids" in sent and body.partner_ids is not None:
        partners = [u for u in body.partner_ids if u in world.users]
        if any(world.users[u].access_level != "Partner" for u in partners):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Only people with the Partner level can be partners"
            )
        fields[Session.PARTNERS] = partners
    return fields


def _duration(day_one: date, end: date | None) -> int | None:
    if end is None:
        return None
    if end < day_one:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "The end date must be on or after Day 1"
        )
    return (end - day_one).days + 1


def create(world: World, body: ProjectCreateIn, user: CurrentUser) -> tuple[str, dict[str, list[str]]]:
    """Create the Session, its team and its tasks. Returns (id, tasks by person)."""
    items, template_id, past = source_items(world, body)
    if template_id and not body.from_project_id and not world.templates[template_id].active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That template is inactive")
    if body.site_id not in world.sites:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a site from the list")

    role_ids = list(dict.fromkeys(i.role_id for i in items if i.role_id))
    role_ids += [o.role_id for o in body.one_offs if o.role_id and o.role_id not in role_ids]
    assignments = resolve_assignments(world, role_ids, body.assignments)

    fields = _detail_fields(body, world)
    fields.update(
        {
            Session.PROGRAM_NAME: body.name.strip(),
            Session.START_DATE: body.day_one.isoformat(),
            Session.SITE: [body.site_id],
            Session.STATUS: SESSION_NOT_STARTED,
            Session.PROJECT_LEAD: [user.id],
        }
    )
    duration = _duration(body.day_one, body.end_date)
    if duration:
        fields[Session.DURATION_DAYS] = duration
    if template_id:
        fields[Session.TEMPLATE] = [template_id]
    fields = {k: v for k, v in fields.items() if v not in (None, "", [])}
    session = client.create_record(Session.TABLE, fields, typecast=True)
    session_id = session["id"]

    client.create_records(
        SessionTeam.TABLE,
        [
            {SessionTeam.SESSION: [session_id], SessionTeam.ROLE: [role_id], SessionTeam.USER: [user_id]}
            for role_id, user_id in assignments.items()
            if user_id
        ],
    )

    one_offs = _one_offs(body.one_offs)
    if body.from_project_id:
        start_from_past_launch(
            body.from_project_id, session_id, assignments, one_offs, body.overrides, user.id
        )
    else:
        generate_timeline(session_id, assignments, one_offs, body.overrides, user.id)

    if body.update_site_profile:
        update_site_profile(world, body)

    by_user: dict[str, list[str]] = defaultdict(list)
    for task in World().tasks_by_project.get(session_id, []):
        for uid in task.assignees:
            if uid != user.id:
                by_user[uid].append(task.id)
    return session_id, dict(by_user)


def update_site_profile(world: World, body: ProjectDetailsIn) -> None:
    """Write partner, shipping and type changes from the form back to the Site."""
    site = world.sites.get(body.site_id or "")
    if site is None:
        return
    wanted = {
        Site.PARTNER_CONTACT_NAME: (body.partner_name or "", site.partner_name),
        Site.PARTNER_CONTACT_EMAIL: (body.partner_email or "", site.partner_email),
        Site.PARTNER_CONTACT_PHONE: (body.partner_phone or "", site.partner_phone),
        Site.SHIPPING_ADDRESS: (body.shipping_address or "", site.shipping_address),
        Site.SITE_TYPE: (body.site_type or "", site.site_type or ""),
    }
    changes = {name: new or None for name, (new, old) in wanted.items() if new and new != old}
    if changes:
        client.update_record(Site.TABLE, site.id, changes, typecast=True)


def update_details(world: World, project: ProjectRec, body: ProjectDetailsIn, user: CurrentUser) -> None:
    if "day_one" in body.model_fields_set and body.day_one and body.day_one != project.start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Use Move Day 1 to change Day 1, so tasks move too"
        )
    fields = _detail_fields(body, world)
    if "end_date" in body.model_fields_set and project.start:
        fields[Session.DURATION_DAYS] = _duration(project.start, body.end_date)
    if not fields:
        return
    client.update_record(Session.TABLE, project.id, fields, typecast=True)
    changed = []
    labels = {
        Session.PROGRAM_NAME: "name",
        Session.SITE: "site",
        Session.SITE_TYPE: "site type",
        Session.PROGRAM_HOURS: "hours",
        Session.LOCATION: "location",
        Session.INSTRUCTORS: "lead instructors",
        Session.PARTNER_CONTACT_NAME: "partner contact",
        Session.PARTNER_CONTACT_EMAIL: "partner contact",
        Session.PARTNER_CONTACT_PHONE: "partner contact",
        Session.SHIPPING_ADDRESS: "shipping address",
        Session.DRIVE_FOLDER: "Drive folder",
        Session.PARTNERS: "partners",
        Session.DURATION_DAYS: "end date",
    }
    for name in fields:
        label = labels.get(name)
        if label and label not in changed:
            changed.append(label)
    history.log_event(
        project.id, None, user.id, "System", "edited the " + logic.name_list(changed, 3) if changed else "edited details"
    )


def close(world: World, project: ProjectRec, skip_open: bool, user: CurrentUser) -> dict:
    today = world.today
    if project.closed:
        raise HTTPException(status.HTTP_409_CONFLICT, "This launch is already closed")
    if project.start is None or project.start > today:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You can close a launch once Day 1 has passed"
        )
    open_tasks = [t for t in world.tasks_by_project.get(project.id, []) if logic.is_open(t.status)]
    if skip_open and open_tasks:
        client.update_records(
            Work.TABLE, [{"id": t.id, "fields": {Work.STATUS: "Skipped"}} for t in open_tasks]
        )
        ids = {t.id for t in open_tasks}
        client.update_records(
            Reminders.TABLE,
            [
                {"id": r.id, "fields": {Reminders.STATUS: "Cancelled"}}
                for r in safe(load_reminders)
                if r.work_id in ids and r.kind == "Custom" and r.status == "Scheduled"
            ],
        )
    client.update_record(
        Session.TABLE,
        project.id,
        {Session.STATUS: SESSION_COMPLETE, Session.CLOSED_DATE: today.isoformat()},
        typecast=True,
    )
    note = ""
    if open_tasks:
        note = (
            f", marking {logic.plural(len(open_tasks), 'open task')} skipped"
            if skip_open
            else f" with {logic.plural(len(open_tasks), 'open task')} left as they were"
        )
    history.log_event(project.id, None, user.id, "Project Closed", f"closed this launch{note}")
    return {"closed": True, "skipped": len(open_tasks) if skip_open else 0}


def reopen(project: ProjectRec, user: CurrentUser) -> None:
    if not project.closed:
        raise HTTPException(status.HTTP_409_CONFLICT, "This launch is not closed")
    client.update_record(
        Session.TABLE,
        project.id,
        {Session.STATUS: SESSION_IN_PROGRESS, Session.CLOSED_DATE: None},
        typecast=True,
    )
    history.log_event(project.id, None, user.id, "Project Closed", "reopened this launch", "Complete", "In progress")


def delete(world: World, project: ProjectRec, user: CurrentUser) -> dict:
    """Delete a launch and every row that only exists for it.

    That is its tasks, its team, its history and notes, its links, and every
    reminder on its tasks. Nothing is left pointing at a launch that is gone,
    because the app hides such rows everywhere, so they could never be seen or
    cleaned up from here. To keep a launch for the record, close it instead.

    The launch itself goes last. If Airtable fails part way, the launch is still
    there with some of its rows, and deleting it again finishes the job.
    """
    task_ids = {t.id for t in world.tasks_by_project.get(project.id, [])}
    reminder_ids = [r.id for r in safe(load_reminders) if r.work_id in task_ids]
    link_ids = [
        link.id for link in world.links if link.session_id == project.id or link.work_id in task_ids
    ]
    log_ids = [
        row.id for row in world.log if row.session_id == project.id or row.work_id in task_ids
    ]
    team_ids = [t.id for t in world.team_for(project.id)]

    client.delete_records(Reminders.TABLE, reminder_ids)
    client.delete_records(Links.TABLE, link_ids)
    client.delete_records(ActivityLog.TABLE, log_ids)
    client.delete_records(SessionTeam.TABLE, team_ids)
    client.delete_records(Work.TABLE, sorted(task_ids))
    client.delete_records(Session.TABLE, [project.id])

    name = world.site_name(project)
    if project.start:
        name = f"{name} (Day 1 {logic.fmt_date(project.start, world.today)})"
    history.log_event(
        None,
        None,
        user.id,
        "System",
        f"deleted the launch {name} and its {logic.plural(len(task_ids), 'task')}",
    )
    return {"deleted": True, "tasks": len(task_ids)}


def season_stats(world: World) -> dict:
    """Three numbers for the public home page. Nothing else is shared."""
    today = world.today
    year = today.year
    this_year = [p for p in world.projects.values() if p.start and p.start.year == year]
    to_launch = [p for p in this_year if p.status in (SESSION_IN_PROGRESS, SESSION_NOT_STARTED, SESSION_COMPLETE)]
    launched = [p for p in this_year if p.start < today]
    week_start = today - timedelta(days=today.weekday())
    done = [t for t in world.tasks if t.status == "Done" and t.completed and week_start <= t.completed <= today]
    return {
        "year": year,
        "sites_to_launch": len(to_launch),
        "sites_launched": len(launched),
        "tasks_done_this_week": len(done),
    }
