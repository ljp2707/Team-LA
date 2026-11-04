"""Shapes the API returns. The frontend does no business logic, so every computed
field (overdue, waiting on, complete %, next milestone and so on) is filled in here.

`World` loads each table once per request (Airtable reads are cached for 30
seconds anyway) and the functions below turn records into small dicts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property

from fastapi import HTTPException, status

from app import permissions
from app.models.user import CurrentUser
from app.services import clock, logic
from app.services.records import (
    InstructorRec,
    LinkRec,
    LogRec,
    ProjectRec,
    RegionRec,
    RoleRec,
    SiteRec,
    TaskRec,
    TeamRec,
    TemplateRec,
    UserRec,
    load_instructors,
    load_links,
    load_log,
    load_projects,
    load_regions,
    load_roles,
    load_sites,
    load_steps,
    load_tasks,
    load_team,
    load_templates,
    load_users,
    safe,
)


@dataclass
class World:
    today: date = field(default_factory=lambda: clock.today())

    @cached_property
    def users(self) -> dict[str, UserRec]:
        return {u.id: u for u in load_users()}

    @cached_property
    def roles(self) -> dict[str, RoleRec]:
        return {r.id: r for r in load_roles()}

    @cached_property
    def sites(self) -> dict[str, SiteRec]:
        return {s.id: s for s in load_sites()}

    @cached_property
    def regions(self) -> dict[str, RegionRec]:
        return {r.id: r for r in load_regions()}

    @cached_property
    def templates(self) -> dict[str, TemplateRec]:
        return {t.id: t for t in load_templates()}

    @cached_property
    def projects(self) -> dict[str, ProjectRec]:
        return {p.id: p for p in load_projects()}

    @cached_property
    def steps(self):
        return load_steps()

    @cached_property
    def tasks(self) -> list[TaskRec]:
        return load_tasks(self.steps)

    @cached_property
    def tasks_by_id(self) -> dict[str, TaskRec]:
        return {t.id: t for t in self.tasks}

    @cached_property
    def tasks_by_project(self) -> dict[str, list[TaskRec]]:
        out: dict[str, list[TaskRec]] = defaultdict(list)
        for t in self.tasks:
            if t.session_id:
                out[t.session_id].append(t)
        return out

    @cached_property
    def dependents(self) -> dict[str, list[TaskRec]]:
        return logic.dependents_map(self.tasks)

    @cached_property
    def team(self) -> list[TeamRec]:
        return load_team()

    @cached_property
    def instructors(self) -> dict[str, InstructorRec]:
        return {i.id: i for i in load_instructors()}

    @cached_property
    def log(self) -> list[LogRec]:
        return load_log()

    @cached_property
    def links(self) -> list[LinkRec]:
        return safe(load_links)

    # --- lookups -------------------------------------------------------------

    def user_name(self, user_id: str | None) -> str | None:
        user = self.users.get(user_id or "")
        return user.name if user else None

    def user_short(self, user_id: str | None) -> str | None:
        user = self.users.get(user_id or "")
        return user.short_name if user else None

    def role_name(self, role_id: str | None) -> str | None:
        role = self.roles.get(role_id or "")
        return role.name if role else None

    def site_name(self, project: ProjectRec) -> str:
        site = self.sites.get(project.site_id or "")
        return site.name if site else project.name

    def template_name(self, project: ProjectRec) -> str:
        template = self.templates.get(project.template_id or "")
        return template.name if template else "No template"

    def project(self, project_id: str) -> ProjectRec:
        project = self.projects.get(project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        return project

    def task(self, task_id: str) -> TaskRec:
        task = self.tasks_by_id.get(task_id)
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
        return task

    def team_for(self, project_id: str) -> list[TeamRec]:
        return [t for t in self.team if t.session_id == project_id]


# --- Access ------------------------------------------------------------------


def check_project_access(user: CurrentUser, project: ProjectRec) -> None:
    """Partners only see their own projects. Answer 404 so others stay hidden."""
    if not permissions.can_view_project(user.actor, user.id, project.partner_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def visible_projects(world: World, user: CurrentUser) -> list[ProjectRec]:
    return [
        p
        for p in world.projects.values()
        if permissions.can_view_project(user.actor, user.id, p.partner_ids)
    ]


# --- Tasks -------------------------------------------------------------------


def task_row(world: World, task: TaskRec, user: CurrentUser) -> dict:
    project = world.projects.get(task.session_id or "")
    waiting = logic.waiting_on(task, world.tasks_by_id)
    dependents = world.dependents.get(task.id, [])
    open_dependents = [d for d in dependents if logic.is_open(d.status)]
    shared = []
    if project and task.role_id:
        shared = [
            world.user_short(t.user_id)
            for t in world.team_for(project.id)
            if t.role_id == task.role_id and t.user_id and t.user_id != task.assigned_to
        ]
    today = world.today
    return {
        "id": task.id,
        "name": task.name,
        "project_id": task.session_id,
        "project_name": project.name if project else "",
        "site": world.site_name(project) if project else "",
        "program_type": world.template_name(project) if project else "",
        "status": task.status,
        "display_status": logic.display_status(task, waiting),
        "due": task.due.isoformat() if task.due else None,
        "due_text": logic.due_text(task, today),
        "due_short": logic.fmt_date(task.due, today) if task.due else "",
        "overdue": logic.is_overdue(task, today),
        "days_late": logic.days_late(task, today),
        "waiting_text": logic.waiting_text(waiting),
        "waiting_on": [
            {"id": w.id, "name": w.name, "assignee": world.user_short(w.assigned_to)}
            for w in waiting
        ],
        "at_risk": logic.is_at_risk(task, world.tasks_by_id, today),
        "dependents": len(open_dependents),
        "one_off": task.one_off,
        "role": world.role_name(task.role_id),
        "role_id": task.role_id,
        "assignee": (
            {"id": task.assigned_to, "name": world.user_short(task.assigned_to)}
            if task.assigned_to and task.assigned_to in world.users
            else None
        ),
        "shared_with": [s for s in shared if s],
        "can_edit": permissions.can_edit_task(user.actor, user.id, task.assigned_to),
        "phase": logic.phase_for(task.due, project.start if project else None, project.end if project else None),
        "completed": task.completed.isoformat() if task.completed else None,
    }


def note_dict(world: World, row: LogRec, user: CurrentUser) -> dict:
    author = world.users.get(row.author_id or "")
    minutes = 0.0
    if row.created:
        minutes = (clock.now() - row.created).total_seconds() / 60
    return {
        "id": row.id,
        "author": author.short_name if author else "Someone",
        "author_initial": (author.short_name if author else "?")[:1].upper(),
        "date_text": logic.fmt_date(row.created.astimezone(clock.tz()).date(), world.today)
        if row.created
        else "",
        "created": row.created.isoformat() if row.created else None,
        "text": row.text,
        "visibility": row.visibility,
        "can_delete": permissions.can_delete_note(
            user.actor, row.author_id == user.id, minutes
        ),
        "can_share": permissions.can_share_notes(user.actor),
    }


def link_dict(world: World, link: LinkRec, can_remove: bool) -> dict:
    return {
        "id": link.id,
        "title": link.title,
        "url": link.url,
        "kind": link.kind,
        "added_by": world.user_short(link.added_by),
        "can_remove": can_remove,
    }


def history_dict(world: World, row: LogRec) -> dict:
    author = world.user_short(row.author_id) or "NMU Launches"
    task = world.tasks_by_id.get(row.work_id or "")
    text = row.text
    if row.type == "Note" and task:
        text = f"added a note to {task.name}"
    elif row.type == "Status Change" and task and row.to_value:
        text = row.text or f"marked {task.name} {row.to_value.lower()}"
    return {
        "id": row.id,
        "author": author,
        "type": row.type,
        "text": text,
        "from": row.from_value,
        "to": row.to_value,
        "date_text": logic.fmt_date(row.created.astimezone(clock.tz()).date(), world.today)
        if row.created
        else "",
        "created": row.created.isoformat() if row.created else None,
    }


# --- Projects ----------------------------------------------------------------


def project_card(world: World, project: ProjectRec) -> dict:
    tasks = world.tasks_by_project.get(project.id, [])
    today = world.today
    overdue = [t for t in tasks if logic.is_overdue(t, today)]
    blocked = [
        t
        for t in tasks
        if logic.is_open(t.status)
        and logic.display_status(t, logic.waiting_on(t, world.tasks_by_id)) == logic.BLOCKED
    ]
    needs_owner = [t for t in tasks if logic.is_open(t.status) and not t.assigned_to]
    milestone = logic.next_milestone(tasks)
    site = world.sites.get(project.site_id or "")
    region = world.regions.get(site.region_id or "") if site else None
    instructors = [world.instructors[i].name for i in project.instructor_ids if i in world.instructors]
    return {
        "id": project.id,
        "name": project.name,
        "site": world.site_name(project),
        "site_id": project.site_id,
        "region": region.name if region else None,
        "region_id": region.id if region else None,
        "program_type": world.template_name(project),
        "template_id": project.template_id,
        "site_type": project.site_type or (site.site_type if site else None),
        "day_one": project.start.isoformat() if project.start else None,
        "day_one_text": logic.fmt_date(project.start, today, weekday=True) if project.start else "No Day 1",
        "end_date": project.end.isoformat() if project.end else None,
        "complete": logic.complete_percent(tasks),
        "task_count": len(tasks),
        "overdue": len(overdue),
        "blocked": len(blocked),
        "needs_owner": len(needs_owner),
        "next_milestone": (
            {"id": milestone.id, "name": milestone.name, "due_text": logic.fmt_date(milestone.due, today)}
            if milestone
            else None
        ),
        "lead_instructor": ", ".join(instructors) or None,
        "status": project.status,
        "closed": project.closed,
        "closed_date": project.closed_date.isoformat() if project.closed_date else None,
    }


def dashboard_summary(cards: list[dict], today: date) -> dict:
    upcoming = sorted(
        (c for c in cards if c["day_one"] and c["day_one"] >= today.isoformat()),
        key=lambda c: c["day_one"],
    )
    nxt = upcoming[0] if upcoming else None
    return {
        "active": len(cards),
        "overdue": sum(c["overdue"] for c in cards),
        "blocked": sum(c["blocked"] for c in cards),
        "needs_owner": sum(c["needs_owner"] for c in cards),
        "next_day_one": (
            {
                "date": nxt["day_one"],
                "text": logic.fmt_date(date.fromisoformat(nxt["day_one"]), today),
                "site": nxt["site"],
                "project_id": nxt["id"],
            }
            if nxt
            else None
        ),
    }


def sort_cards(cards: list[dict], sort: str | None) -> list[dict]:
    if sort == "overdue":
        return sorted(cards, key=lambda c: (-c["overdue"], c["day_one"] or "9999"))
    if sort == "type":
        return sorted(cards, key=lambda c: (c["program_type"], c["day_one"] or "9999"))
    return sorted(cards, key=lambda c: c["day_one"] or "9999")
