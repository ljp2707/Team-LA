"""Users and roles, /users (admin): people, roles and handing off tasks.

Nobody is ever deleted. Deactivating sets Status to Inactive. The server refuses
any change that would leave no Active Admin, and admins cannot deactivate
themselves or remove their own Admin level.

DELETE /api/users/{id} ("remove access") also sets Status to Inactive, so history
keeps the person's name, but is stricter than Deactivate: it is refused while
the person still has open tasks. Reassign or hand them off first.
GET /api/users/directory gives every signed-in NMU person teammates' names.
"""

from collections import defaultdict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app import permissions
from app.airtable import client
from app.airtable.schema import ACTIVE, INACTIVE, Roles, SessionTeam, Users, Work
from app.auth.deps import current_user, require_admin
from app.models.people import HandOffIn, RoleIn, RoleUpdateIn, UserIn, UserUpdateIn
from app.models.user import CurrentUser
from app.services import history, logic, reminders
from app.services.records import UserRec
from app.services.views import World, task_row

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])
roles_router = APIRouter(prefix="/api/roles", tags=["roles"], dependencies=[Depends(require_admin)])
# Not admin only, so it lives on its own router.
directory_router = APIRouter(prefix="/api/users", tags=["users"])


def _open_counts(world: World) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for t in world.tasks:
        project = world.projects.get(t.session_id or "")
        if logic.is_open(t.status) and project and not project.closed:
            for uid in t.assignees:
                counts[uid] += 1
    return counts


def _person(world: World, u: UserRec, counts: dict[str, int]) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "email": u.email,
        "access_level": u.access_level,
        "status": u.status,
        "active": u.active,
        "roles": [
            {"id": r, "name": world.role_name(r)} for r in u.role_ids if world.role_name(r)
        ],
        "open_tasks": counts.get(u.id, 0),
        "program_access": permissions.program_access(u.access_level),
        "is_admin": permissions.is_admin_level(u.access_level),
    }


def active_admins(users: list[UserRec]) -> set[str]:
    return {
        u.id for u in users if u.active and u.access_level in permissions.ADMIN_ACCESS_LEVELS
    }


def check_admin_rules(users: list[UserRec], target: UserRec, body: UserUpdateIn, actor_id: str) -> None:
    """Refuse changes that lock everyone out, or that an admin makes to themselves."""
    new_level = body.access_level or target.access_level
    new_status = body.status or target.status
    if target.id == actor_id:
        if new_status != ACTIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, "You cannot deactivate yourself.")
        if target.access_level in permissions.ADMIN_ACCESS_LEVELS and new_level not in permissions.ADMIN_ACCESS_LEVELS:
            raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove your own Admin level.")
    remaining = active_admins(users) - {target.id}
    if new_status == ACTIVE and new_level in permissions.ADMIN_ACCESS_LEVELS:
        remaining.add(target.id)
    if not remaining:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "There must always be at least one Active Admin. Make someone else an Admin first.",
        )


@directory_router.get("/directory")
def directory(user: CurrentUser = Depends(current_user)):
    """Names of everyone, for assignee labels. Any signed-in NMU person, not partners."""
    if not permissions.can_see_directory(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available to partners")
    world = World()
    return [
        {"id": u.id, "name": u.name, "access_level": u.access_level, "status": u.status, "active": u.active}
        for u in sorted(world.users.values(), key=lambda u: u.name.lower())
    ]


@router.get("")
def list_users(inactive: bool = False, access_level: str | None = None):
    world = World()
    counts = _open_counts(world)
    people = [
        _person(world, u, counts)
        for u in sorted(world.users.values(), key=lambda u: u.name.lower())
        if (inactive or u.active) and (not access_level or u.access_level == access_level)
    ]
    active_roles = [r for r in world.roles.values() if r.active]
    return {
        "people": people,
        "counts": {
            "people": sum(1 for u in world.users.values() if u.active),
            "roles": len(active_roles),
        },
        "roles": sorted(({"id": r.id, "name": r.name} for r in active_roles), key=lambda r: r["name"]),
        "access_levels": permissions.ACCESS_LEVELS,
    }


@router.get("/{user_id}/work")
def person_work(user_id: str, user: CurrentUser = Depends(require_admin)):
    """One person's active launches, with their open tasks on each. Admins only.

    A launch counts as theirs if they are on its team or have any task on it.
    Closed launches are left out, as on My Tasks. Finished tasks are only counted.
    """
    if not permissions.can_view_user_work(user.actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin view required")
    world = World()
    target = world.users.get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    roles_by_project: dict[str, list[str]] = defaultdict(list)
    for t in world.team:
        if t.user_id == target.id and t.session_id and world.role_name(t.role_id):
            roles_by_project[t.session_id].append(world.role_name(t.role_id) or "")
    tasks_by_project: dict[str, list] = defaultdict(list)
    for t in world.tasks:
        if t.session_id and t.is_assigned(target.id):
            tasks_by_project[t.session_id].append(t)
    active = [
        p
        for p in world.projects.values()
        if not p.closed and (p.id in roles_by_project or p.id in tasks_by_project)
    ]
    active.sort(key=lambda p: (p.start is None, p.start, world.site_name(p).lower()))
    launches = []
    for p in active:
        mine = tasks_by_project.get(p.id, [])
        open_tasks = sorted(
            (t for t in mine if logic.is_open(t.status)),
            key=lambda t: (t.due is None, t.due, t.sort_order or 0, t.name),
        )
        launches.append(
            {
                "id": p.id,
                "name": p.name,
                "site": world.site_name(p),
                "program_type": world.template_name(p),
                "day_one": p.start.isoformat() if p.start else None,
                "roles": sorted(set(roles_by_project.get(p.id, []))),
                "tasks": [task_row(world, t, user) for t in open_tasks],
                "done": len(mine) - len(open_tasks),
            }
        )
    return {"person": _person(world, target, _open_counts(world)), "launches": launches}


@router.post("", status_code=status.HTTP_201_CREATED)
def add_person(body: UserIn, background: BackgroundTasks, user: CurrentUser = Depends(require_admin)):
    world = World()
    if any(u.email.lower() == body.email for u in world.users.values()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Someone with that email is already in NMU Launches")
    role_ids = [r for r in body.role_ids if r in world.roles]
    created = client.create_record(
        Users.TABLE,
        {
            Users.EMAIL: body.email,
            Users.FIRST_NAME: body.first_name.strip(),
            Users.LAST_NAME: body.last_name.strip(),
            Users.STATUS: ACTIVE,
            Users.ACCESS_LEVEL: body.access_level,
            Users.ROLES: role_ids,
        },
        typecast=True,
    )
    history.log_event(
        None, None, user.id, "System", f"added {body.first_name.strip()} ({body.email}) as {body.access_level}"
    )
    background.add_task(reminders.send_welcome, created["id"])
    world = World()
    return _person(world, world.users[created["id"]], _open_counts(world))


@router.patch("/{user_id}")
def update_person(user_id: str, body: UserUpdateIn, user: CurrentUser = Depends(require_admin)):
    world = World()
    target = world.users.get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    check_admin_rules(list(world.users.values()), target, body, user.id)
    fields: dict = {}
    sent = body.model_fields_set
    if "first_name" in sent and body.first_name:
        fields[Users.FIRST_NAME] = body.first_name.strip()
    if "last_name" in sent and body.last_name is not None:
        fields[Users.LAST_NAME] = body.last_name.strip()
    if "access_level" in sent and body.access_level:
        fields[Users.ACCESS_LEVEL] = body.access_level
    if "role_ids" in sent and body.role_ids is not None:
        fields[Users.ROLES] = [r for r in body.role_ids if r in world.roles]
    if "status" in sent and body.status:
        fields[Users.STATUS] = body.status
    if fields:
        client.update_record(Users.TABLE, user_id, fields, typecast=True)
        what = []
        if body.access_level and body.access_level != target.access_level:
            what.append(f"access level to {body.access_level}")
        if body.status and body.status != target.status:
            what.append("status to " + body.status)
        if "role_ids" in sent:
            what.append("roles")
        if Users.FIRST_NAME in fields or Users.LAST_NAME in fields:
            what.append("name")
        history.log_event(
            None, None, user.id, "System", f"changed {target.name}'s " + (logic.name_list(what, 4) or "details")
        )
    world = World()
    return _person(world, world.users[user_id], _open_counts(world))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_access(user_id: str, user: CurrentUser = Depends(require_admin)):
    """Remove someone's access (Status Inactive). Refused while they have open tasks."""
    world = World()
    target = world.users.get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    if target.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove your own access.")
    if not target.active:
        return None
    open_count = _open_counts(world).get(target.id, 0)
    if open_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{target.short_name} still has {logic.plural(open_count, 'open task')}. "
            "Reassign them before removing access.",
        )
    check_admin_rules(list(world.users.values()), target, UserUpdateIn(status=INACTIVE), user.id)
    client.update_record(Users.TABLE, user_id, {Users.STATUS: INACTIVE}, typecast=True)
    history.log_event(None, None, user.id, "System", f"removed {target.name}'s access")
    return None


@router.post("/hand-off")
def hand_off(body: HandOffIn, background: BackgroundTasks, user: CurrentUser = Depends(require_admin)):
    world = World()
    giver = world.users.get(body.from_user)
    taker = world.users.get(body.to_user)
    if giver is None or taker is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick both people")
    if giver.id == taker.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick two different people")
    if not taker.active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The person taking over must be active")
    tasks = sorted(
        (
            t
            for t in world.tasks
            if t.is_assigned(giver.id)
            and logic.is_open(t.status)
            and t.session_id in world.projects
            and not world.projects[t.session_id].closed
        ),
        key=lambda t: (t.due is None, t.due),
    )
    teams = [
        t
        for t in world.team
        if t.user_id == giver.id and t.session_id in world.projects and not world.projects[t.session_id].closed
    ]
    names = [t.name for t in tasks]
    summary = {
        "count": len(tasks),
        "tasks": names,
        "preview": logic.name_list(names, 2),
        "team_rows": len(teams),
        "button": f"Move {logic.plural(len(tasks), 'task')} to {taker.short_name}",
    }
    if body.preview:
        return summary
    if not tasks and not (body.replace_on_teams and teams):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{giver.short_name} has no open tasks to hand off")
    client.update_records(
        Work.TABLE,
        [
            # Swap the giver for the taker and keep anyone else on the task.
            {"id": t.id, "fields": {Work.ASSIGNED_TO: list(dict.fromkeys(taker.id if a == giver.id else a for a in t.assignees))}}
            for t in tasks
        ],
    )
    events = [
        history.Event(
            t.session_id, t.id, user.id, "Reassignment", f"gave {t.name} to {taker.name}", giver.name, taker.name
        )
        for t in tasks
    ]
    by_project: dict[str, int] = defaultdict(int)
    for t in tasks:
        by_project[t.session_id] += 1
    events += [
        history.Event(
            pid,
            None,
            user.id,
            "Handoff",
            f"handed off {logic.plural(n, 'open task')} from {giver.name} to {taker.name}",
            giver.name,
            taker.name,
        )
        for pid, n in by_project.items()
    ]
    history.log_events(events)
    if body.replace_on_teams:
        client.update_records(
            SessionTeam.TABLE, [{"id": t.id, "fields": {SessionTeam.USER: [taker.id]}} for t in teams]
        )
    if tasks and taker.id != user.id:
        background.add_task(reminders.send_assignment_emails, {taker.id: [t.id for t in tasks]}, user.name)
    return {**summary, "moved": len(tasks), "teams_updated": len(teams) if body.replace_on_teams else 0}


# --- Roles -------------------------------------------------------------------


@roles_router.get("")
def list_roles():
    world = World()
    people = defaultdict(int)
    for u in world.users.values():
        if u.active:
            for r in u.role_ids:
                people[r] += 1
    steps = defaultdict(int)
    for s in world.steps:
        if s.live:
            for r in s.role_ids:
                steps[r] += 1
    return {
        "roles": [
            {
                "id": r.id,
                "name": r.name,
                "status": r.status or "Active",
                "active": r.active,
                "people": people[r.id],
                "steps": steps[r.id],
            }
            for r in sorted(world.roles.values(), key=lambda r: r.name.lower())
        ]
    }


@roles_router.post("", status_code=status.HTTP_201_CREATED)
def add_role(body: RoleIn, user: CurrentUser = Depends(require_admin)):
    name = body.name.strip()
    if any(r.name.strip().lower() == name.lower() for r in World().roles.values()):
        raise HTTPException(status.HTTP_409_CONFLICT, "A role with that name already exists")
    client.create_record(Roles.TABLE, {Roles.NAME: name, Roles.STATUS: "Active"}, typecast=True)
    history.log_event(None, None, user.id, "System", f"added the role {name}")
    return list_roles()


@roles_router.patch("/{role_id}")
def update_role(role_id: str, body: RoleUpdateIn, user: CurrentUser = Depends(require_admin)):
    world = World()
    role = world.roles.get(role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    fields = {}
    if body.name and body.name.strip() != role.name:
        if any(r.id != role_id and r.name.strip().lower() == body.name.strip().lower() for r in world.roles.values()):
            raise HTTPException(status.HTTP_409_CONFLICT, "A role with that name already exists")
        fields[Roles.NAME] = body.name.strip()
    if body.status:
        fields[Roles.STATUS] = body.status
    if fields:
        client.update_record(Roles.TABLE, role_id, fields, typecast=True)
        history.log_event(None, None, user.id, "System", f"changed the role {role.name}")
    return list_roles()


__all__ = ["router", "roles_router", "directory_router", "INACTIVE"]


FORMER_FIRST = "Former"
FORMER_LAST = "team member"


@router.post("/{user_id}/erase")
def erase_person(user_id: str, user: CurrentUser = Depends(require_admin)):
    """Remove a deactivated person's name and email everywhere, for a deletion request.

    The Users row stays so the work they did still links to someone, but it is
    renamed "Former team member" and its email is replaced with an address that
    cannot receive mail or sign in. Their name and email are also taken out of
    the history text, partner access and any partner contact fields that hold
    their email. Their scheduled reminders are cancelled.
    """
    world = World()
    target = world.users.get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    if target.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove your own details.")
    if target.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deactivate them first, then remove their details.")
    open_count = _open_counts(world).get(target.id, 0)
    if open_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{target.short_name} still has {logic.plural(open_count, 'open task')}. Hand them off first.",
        )
    if target.first_name == FORMER_FIRST and target.last_name == FORMER_LAST:
        return {"erased": True, "history_rows": 0}

    from app.airtable.schema import ActivityLog, Reminders, Session, Site
    from app.services.records import load_reminders, safe

    former = f"{FORMER_FIRST} {FORMER_LAST}"
    old_email = (target.email or "").strip()
    # Longest first, so "Catalina Lopez" is replaced before a shorter form of it could be.
    needles = sorted({n for n in (target.name, f"{target.first_name} {target.last_name}".strip(), old_email) if n and len(n) > 2}, key=len, reverse=True)

    def scrub(text: str) -> str:
        for needle in needles:
            text = text.replace(needle, former)
        return text

    log_updates = []
    for row in world.log:
        fields = {}
        for name, value in ((ActivityLog.TEXT, row.text), (ActivityLog.FROM, row.from_value), (ActivityLog.TO, row.to_value)):
            if value and scrub(value) != value:
                fields[name] = scrub(value)
        if fields:
            log_updates.append({"id": row.id, "fields": fields})
    client.update_records(ActivityLog.TABLE, log_updates)

    # Partner access, and partner contact fields that hold this person's email
    session_updates = []
    for project in world.projects.values():
        if target.id in project.partner_ids:
            session_updates.append(
                {"id": project.id, "fields": {Session.PARTNERS: [p for p in project.partner_ids if p != target.id]}}
            )
    client.update_records(Session.TABLE, session_updates)
    if old_email:
        for table, cls in ((Session.TABLE, Session), (Site.TABLE, Site)):
            contact_updates = [
                {
                    "id": r["id"],
                    "fields": {cls.PARTNER_CONTACT_NAME: "", cls.PARTNER_CONTACT_EMAIL: "", cls.PARTNER_CONTACT_PHONE: ""},
                }
                for r in client.all_records(table)
                if (r["fields"].get(cls.PARTNER_CONTACT_EMAIL) or "").strip().lower() == old_email.lower()
            ]
            client.update_records(table, contact_updates)

    scheduled = [
        r.id for r in safe(load_reminders) if r.recipient_id == target.id and r.status == reminders.SCHEDULED
    ]
    client.update_records(
        Reminders.TABLE, [{"id": i, "fields": {Reminders.STATUS: reminders.CANCELLED}} for i in scheduled]
    )

    client.update_record(
        Users.TABLE,
        target.id,
        {
            Users.FIRST_NAME: FORMER_FIRST,
            Users.LAST_NAME: FORMER_LAST,
            # .invalid can never receive mail, and no Google account can sign in with it.
            Users.EMAIL: f"removed-{target.id.lower()}@example.invalid",
            Users.ROLES: [],
        },
        typecast=True,
    )
    history.log_event(None, None, user.id, "System", "removed a former team member's personal details")
    return {"erased": True, "history_rows": len(log_updates)}
