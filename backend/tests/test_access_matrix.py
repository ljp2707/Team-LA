"""Who may call each route: one row per route, one expected status per role.

Why this file exists: so a new route cannot ship without someone deciding who may use
it. test_every_route_is_in_the_table fails until the new route has a row here.

The rules themselves live in app/permissions.py. This file only checks them from the
outside. See docs/security/threat-model.md, section 4, for the same routes in prose.

Roles:
  admin           Access Level Admin, in admin view
  admin_as_staff  the same Admin after switching to staff view: must get staff results
  staff           Access Level Staff. Assigned to recT2. recT7 belongs to someone else
  viewer          Access Level Viewer: reads everything, changes nothing
  lead            Access Level "Project Lead". No longer a level, but Airtable may still
                  hold it. Unknown levels must be read only, like Viewer
  partner         Access Level Partner. On launch recProj only, not on recOther
  anon            signed out

Statuses: 401 signed out, 403 not allowed, 404 hidden (partners are told a launch they
are not on does not exist). Any 2xx means allowed.
"""

from dataclasses import dataclass, field
from datetime import date

import pytest

from app.airtable.schema import Links, Session
from app.main import app
from tests.builders import add_note, add_project, add_reminder, add_task, standard_project
from tests.conftest import person

ROLES = ["admin", "admin_as_staff", "staff", "viewer", "lead", "partner", "anon"]
SIGNED_IN = [r for r in ROLES if r != "anon"]
EMAILS = {
    "admin": "admin@example.org",
    "admin_as_staff": "admin@example.org",
    "staff": "staff@example.org",
    "viewer": "viewer@example.org",
    "lead": "lead-legacy@example.org",
    "partner": "partner@example.org",
}
USER_IDS = {
    "admin": "recAdmin",
    "admin_as_staff": "recAdmin",
    "staff": "recStaff",
    "viewer": "recViewer",
    "lead": "recPL",
    "partner": "recPartner",
}

PNG = b"\x89PNG\r\n\x1a\n access matrix"


# --- Expectation helpers: who gets what -------------------------------------------


def everyone(ok: int) -> dict[str, int]:
    """Public: signed in or not."""
    return {r: ok for r in ROLES}


def signed_in(ok: int) -> dict[str, int]:
    """Any signed-in person."""
    return {**{r: ok for r in SIGNED_IN}, "anon": 401}


def internal(ok: int) -> dict[str, int]:
    """NMU people only: partners are refused."""
    return {**signed_in(ok), "partner": 403}


def can_write(ok: int) -> dict[str, int]:
    """Anyone who may change things: not Viewer, not an unknown level."""
    return {**signed_in(ok), "viewer": 403, "lead": 403}


def admin_only(ok: int) -> dict[str, int]:
    """Admin view only. An Admin in staff view is refused like Staff."""
    return {**{r: 403 for r in SIGNED_IN}, "admin": ok, "anon": 401}


def assignee_or_admin(ok: int, partner: int = 403) -> dict[str, int]:
    """Changing recT2, which is assigned to staff only."""
    return {**{r: 403 for r in SIGNED_IN}, "admin": ok, "staff": ok, "partner": partner, "anon": 401}


@dataclass
class Row:
    method: str
    route: str  # The path as FastAPI declares it, for the completeness check
    expect: dict[str, int]
    url: str = ""  # The concrete path to call; defaults to route
    json: dict | None = None
    upload: bool = False
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def target(self) -> str:
        return self.url or self.route


# --- The table: every route in the app ---------------------------------------------

ROWS: list[Row] = [
    # Sign-in, session and public (threat model 4.1)
    Row("GET", "/auth/login", everyone(302)),
    Row("GET", "/auth/callback", {**{r: 302 for r in SIGNED_IN}, "anon": 302}),
    Row("GET", "/auth/denied", everyone(200)),
    Row("POST", "/auth/logout", everyone(303)),
    Row("GET", "/auth/logout", everyone(302)),
    Row("GET", "/api/health", everyone(200)),
    Row("GET", "/api/health/airtable", admin_only(200)),
    Row("GET", "/api/health/auth", admin_only(200)),
    Row("GET", "/api/public/season-stats", everyone(200)),
    Row("GET", "/api/public/about", everyone(200)),
    Row("POST", "/api/security/csp-report", everyone(204),
        json={"csp-report": {"effective-directive": "img-src", "blocked-uri": "data"}},
        note="Browsers send CSP reports on their own; it only logs (F25)"),
    Row("GET", "/calendar/{token}.ics", everyone(404), url="/calendar/" + "A" * 43 + ".ics"),
    # The signed-in person (4.2)
    Row("GET", "/api/me", signed_in(200)),
    Row("POST", "/api/me/view", {**signed_in(200), "partner": 403}, json={"view": "staff"}),
    Row("GET", "/api/me/calendar-feed", signed_in(200)),
    Row("POST", "/api/me/calendar-feed", can_write(200)),
    Row("DELETE", "/api/me/calendar-feed", can_write(200)),
    Row("GET", "/api/users/directory", internal(200)),
    # Launches (4.3). recProj has partner on it.
    Row("GET", "/api/projects", signed_in(200)),
    Row("GET", "/api/projects/{project_id}", signed_in(200), url="/api/projects/recProj"),
    Row("GET", "/api/projects/{project_id}/history", internal(200), url="/api/projects/recProj/history"),
    Row("POST", "/api/projects/preview", admin_only(200), json={"template_id": "recTpl", "day_one": "2026-12-20"}),
    Row("POST", "/api/projects", admin_only(201),
        json={"name": "New launch", "site_id": "recSite", "day_one": "2026-12-20", "template_id": "recTpl"}),
    Row("PATCH", "/api/projects/{project_id}", admin_only(200), url="/api/projects/recProj",
        json={"program_hours": "9 to 5"}),
    Row("DELETE", "/api/projects/{project_id}", admin_only(200), url="/api/projects/recProj"),
    Row("POST", "/api/projects/{project_id}/move-day-one", admin_only(200),
        url="/api/projects/recProj/move-day-one", json={"new_day_one": "2026-11-29", "preview": True}),
    # 409: the admin got past the permission check to "this move can no longer be undone".
    Row("POST", "/api/projects/{project_id}/move-day-one/undo", admin_only(409),
        url="/api/projects/recProj/move-day-one/undo", json={"batch": "no-such-batch"}),
    Row("POST", "/api/projects/{project_id}/tasks", admin_only(201), url="/api/projects/recProj/tasks",
        json={"name": "Extra task", "due_date": "2026-11-15"}),
    Row("POST", "/api/projects/{project_id}/close", admin_only(200), url="/api/projects/recPast/close",
        json={"skip_open": True}),
    Row("POST", "/api/projects/{project_id}/reopen", admin_only(200), url="/api/projects/recClosed/reopen"),
    Row("POST", "/api/projects/{project_id}/links", admin_only(201), url="/api/projects/recProj/links",
        json={"title": "Folder", "url": "https://drive.google.com/drive/folders/x"}),
    Row("POST", "/api/projects/{project_id}/files", admin_only(201), url="/api/projects/recProj/files", upload=True),
    Row("GET", "/api/projects/{project_id}/export.csv", admin_only(200), url="/api/projects/recProj/export.csv"),
    # Tasks, notes, links, files, reminders (4.4). recT2 is assigned to staff only.
    Row("GET", "/api/tasks/mine", signed_in(200)),
    Row("GET", "/api/tasks/{task_id}", signed_in(200), url="/api/tasks/recT2"),
    Row("PATCH", "/api/tasks/{task_id}", assignee_or_admin(200), url="/api/tasks/recT2",
        json={"status": "In Progress"}),
    Row("DELETE", "/api/tasks/{task_id}", admin_only(200), url="/api/tasks/recT2"),
    Row("POST", "/api/tasks/{task_id}/nudge", admin_only(200), url="/api/tasks/recT2/nudge",
        json={"message": "Can you finish this today?"}, note="Dry run in tests, so nothing is sent"),
    Row("POST", "/api/tasks/reassign", admin_only(200), json={"task_ids": ["recT2"], "to_user": "recLead"}),
    Row("POST", "/api/tasks/{task_id}/assign", admin_only(200), url="/api/tasks/recT6/assign",
        json={"user_id": "recLead"}),
    Row("POST", "/api/tasks/{task_id}/notes", assignee_or_admin(201), url="/api/tasks/recT2/notes",
        json={"text": "Called the pool"}),
    Row("POST", "/api/tasks/{task_id}/links", assignee_or_admin(201), url="/api/tasks/recT2/links",
        json={"title": "Flyer", "url": "https://www.canva.com/design/x"}),
    Row("POST", "/api/tasks/{task_id}/files", assignee_or_admin(201), url="/api/tasks/recT2/files", upload=True),
    Row("POST", "/api/tasks/{task_id}/reminders", can_write(201), url="/api/tasks/recT2/reminders",
        json={"send_on": "2026-11-10"}, note="A reminder for yourself on any task you can see"),
    Row("GET", "/api/links/{link_id}/file", signed_in(302), url="/api/links/recLFile/file"),
    Row("DELETE", "/api/links/{link_id}", assignee_or_admin(200), url="/api/links/recLTask"),
    # recN1 is staff's own Internal note on recT2, posted just now. Partners cannot see it.
    Row("DELETE", "/api/notes/{note_id}", assignee_or_admin(200, partner=404), url="/api/notes/recN1"),
    Row("PATCH", "/api/notes/{note_id}", assignee_or_admin(200, partner=404), url="/api/notes/recN1",
        json={"visibility": "Shared"}),
    Row("GET", "/api/reminders/mine", signed_in(200)),
    # recR1 is staff's own reminder. Anyone else is told it does not exist.
    Row("DELETE", "/api/reminders/{reminder_id}", {**can_write(404), "staff": 200}, url="/api/reminders/recR1"),
    # Admin setup (4.5)
    Row("GET", "/api/templates", admin_only(200)),
    Row("POST", "/api/templates", admin_only(201), json={"copy_from": "recTpl", "name": "Copy"}),
    Row("GET", "/api/templates/{template_id}", admin_only(200), url="/api/templates/recTpl"),
    Row("PUT", "/api/templates/{template_id}/draft", admin_only(200), url="/api/templates/recTpl/draft",
        json={"steps": [{"name": "Book the pool"}]}),
    # 404 and 409: the admin got past the permission check to "there is no draft".
    Row("DELETE", "/api/templates/{template_id}/draft", admin_only(404), url="/api/templates/recTpl/draft"),
    Row("POST", "/api/templates/{template_id}/publish", admin_only(409), url="/api/templates/recTpl/publish",
        json={"change_note": "First"}),
    Row("GET", "/api/templates/{template_id}/versions", admin_only(200), url="/api/templates/recTpl/versions"),
    Row("GET", "/api/templates/{template_id}/insights", admin_only(200), url="/api/templates/recTpl/insights"),
    Row("PATCH", "/api/templates/{template_id}", admin_only(200), url="/api/templates/recTpl",
        json={"status": "Inactive"}),
    Row("DELETE", "/api/templates/{template_id}", admin_only(204), url="/api/templates/recTplUnused"),
    Row("POST", "/api/templates/{template_id}/duplicate", admin_only(201), url="/api/templates/recTpl/duplicate",
        json={}),
    Row("POST", "/api/templates/from-project", admin_only(201), json={"project_id": "recProj", "name": "From"}),
    Row("GET", "/api/users", admin_only(200)),
    Row("GET", "/api/users/{user_id}/work", admin_only(200), url="/api/users/recStaff/work"),
    Row("POST", "/api/users", admin_only(201), json={"first_name": "New", "email": "new@example.org"}),
    Row("PATCH", "/api/users/{user_id}", admin_only(200), url="/api/users/recViewer", json={"first_name": "Vee"}),
    Row("DELETE", "/api/users/{user_id}", admin_only(204), url="/api/users/recViewer"),
    Row("POST", "/api/users/hand-off", admin_only(200),
        json={"from_user": "recStaff", "to_user": "recLead", "preview": True}),
    Row("POST", "/api/users/{user_id}/erase", admin_only(200), url="/api/users/recGone/erase"),
    Row("GET", "/api/roles", admin_only(200)),
    Row("POST", "/api/roles", admin_only(201), json={"name": "Coach"}),
    Row("PATCH", "/api/roles/{role_id}", admin_only(200), url="/api/roles/recRoleOps", json={"name": "Ops"}),
    Row("GET", "/api/archive", admin_only(200)),
    Row("GET", "/api/archive/{project_id}", admin_only(200), url="/api/archive/recClosed"),
    Row("GET", "/api/sites", admin_only(200)),
    Row("POST", "/api/sites", admin_only(201), json={"name": "Medgar Evers Pool"}),
    Row("GET", "/api/sites/{site_id}", admin_only(200), url="/api/sites/recSite"),
    Row("GET", "/api/instructors", admin_only(200)),
    Row("POST", "/api/admin/test-email", admin_only(200)),
]


# --- The world every case runs in ---------------------------------------------------


@pytest.fixture
def users(users):
    """The usual people, plus someone whose Access Level is the retired "Project Lead"."""
    return [*users, person("recPL", "lead-legacy@example.org", "Project Lead", first="Lou")]


@pytest.fixture
def world(fake):
    standard_project(fake)
    fake.find(Session.TABLE, "recProj")["fields"][Session.PARTNERS] = ["recPartner"]
    # Another program's launch: the partner is not on it.
    add_project(fake, "recOther", name="Other program 2026", start=date(2026, 12, 1))
    add_task(fake, "recOT1", "Other program task", date(2026, 11, 20), project="recOther", assigned="recPartner")
    add_note(fake, "recNOther", "recOT1", "recPartner", visibility="Shared", project="recOther")
    fake.add(Links.TABLE, {Links.TITLE: "Other file", Links.KIND: "File", Links.WORK: ["recOT1"],
                           Links.FILE: [{"url": "https://v5.airtableusercontent.com/o.png"}]}, "recLOther")
    # A launch that has finished, and one already closed.
    add_project(fake, "recPast", name="Past launch 2026", start=date(2026, 9, 1))
    add_project(fake, "recClosed", name="Closed launch 2026", start=date(2026, 8, 1), status="Complete")
    # A template no launch uses, so it can be deleted.
    fake.add("Template List", {"Template Name": "Unused", "Status": "Inactive"}, "recTplUnused")
    # A task that belongs to neither staff nor admin.
    add_task(fake, "recT7", "Order caps", date(2026, 11, 12), assigned="recLead")
    # Things on recT2 (staff's task) and recT7 (someone else's).
    add_note(fake, "recN1", "recT2", "recStaff")
    fake.add(Links.TABLE, {Links.TITLE: "Flyer draft", Links.URL: "https://www.canva.com/design/a",
                           Links.KIND: "Canva", Links.WORK: ["recT2"]}, "recLTask")
    fake.add(Links.TABLE, {Links.TITLE: "Coach list", Links.URL: "https://docs.google.com/d/1",
                           Links.KIND: "Google Drive", Links.WORK: ["recT7"]}, "recLOthersTask")
    fake.add(Links.TABLE, {Links.TITLE: "Flyer", Links.KIND: "File", Links.WORK: ["recT2"],
                           Links.FILE: [{"url": "https://v5.airtableusercontent.com/f.png"}]}, "recLFile")
    add_reminder(fake, "recR1", "recT2", "recStaff", date(2026, 11, 10))
    return fake


@pytest.fixture
def as_role(client, sign_in):
    """Sign in as one of ROLES (or stay signed out for anon)."""

    def _as(role: str):
        if role == "anon":
            return
        response = sign_in(EMAILS[role])
        assert response.status_code in (302, 303), f"{role} could not sign in"
        if role == "admin_as_staff":
            assert client.post("/api/me/view", json={"view": "staff"}).json()["view"] == "staff"

    return _as


def call(client, method: str, url: str, json=None, upload=False):
    if upload:
        return client.post(url, files={"file": ("flyer.png", PNG, "image/png")})
    return client.request(method, url, json=json)


# --- The checks ---------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"{r.method} {r.target}")
def test_route_answers_each_role_as_expected(client, world, as_role, row, role):
    as_role(role)
    response = call(client, row.method, row.target, row.json, row.upload)
    assert response.status_code == row.expect[role], (
        f"{row.method} {row.target} as {role}: got {response.status_code}, "
        f"expected {row.expect[role]}. {response.text[:200]}"
    )


def _declared_routes() -> set[tuple[str, str]]:
    """Every (method, path) the app serves, including routes inside included routers."""

    def walk(routes):
        for route in routes:
            if hasattr(route, "effective_candidates"):  # An included APIRouter
                yield from walk(route.effective_candidates())
            else:
                yield route

    found = set()
    for route in walk(app.routes):
        inner = getattr(route, "route", route)
        path = getattr(route, "path", None) or getattr(inner, "path", "")
        methods = getattr(route, "methods", None) or getattr(inner, "methods", None) or set()
        for method in set(methods) - {"HEAD"}:
            found.add((method, path))
    return found


def test_every_route_is_in_the_table():
    declared = _declared_routes()
    in_table = {(r.method, r.route) for r in ROWS}
    must_be_listed = {(m, p) for m, p in declared if p.startswith(("/api/", "/auth/", "/calendar/"))}
    missing = sorted(must_be_listed - in_table)
    assert not missing, "Add a row to ROWS deciding who may call: " + ", ".join(f"{m} {p}" for m, p in missing)
    stale = sorted(in_table - declared)
    assert not stale, "These rows no longer match a route: " + ", ".join(f"{m} {p}" for m, p in stale)
    assert len(must_be_listed) > 70  # The walker found the routes, not an empty list


def test_every_row_covers_every_role():
    for row in ROWS:
        assert set(row.expect) == set(ROLES), f"{row.method} {row.route} is missing roles"


# --- Object level: the right role, the wrong object ---------------------------------

STAFF_ON_SOMEONE_ELSES_TASK = [
    ("PATCH", "/api/tasks/recT7", {"status": "In Progress"}, False),
    ("POST", "/api/tasks/recT7/notes", {"text": "Not mine"}, False),
    ("POST", "/api/tasks/recT7/links", {"title": "x", "url": "https://docs.google.com/d/2"}, False),
    ("POST", "/api/tasks/recT7/files", None, True),
    ("DELETE", "/api/links/recLOthersTask", None, False),
]


@pytest.mark.parametrize("role", ["staff", "admin_as_staff", "partner"])
@pytest.mark.parametrize("method,url,json,upload", STAFF_ON_SOMEONE_ELSES_TASK)
def test_nobody_but_admin_changes_someone_elses_task(client, world, as_role, role, method, url, json, upload):
    as_role(role)
    assert call(client, method, url, json, upload).status_code == 403


def test_admin_view_can_change_someone_elses_task(client, world, as_role):
    as_role("admin")
    for method, url, json, upload in STAFF_ON_SOMEONE_ELSES_TASK:
        assert call(client, method, url, json, upload).status_code in (200, 201), f"{method} {url}"


PARTNER_ON_ANOTHER_PROGRAM = [
    ("GET", "/api/projects/recOther", None, False),
    ("GET", "/api/tasks/recOT1", None, False),
    ("PATCH", "/api/tasks/recOT1", {"status": "In Progress"}, False),
    ("POST", "/api/tasks/recOT1/notes", {"text": "hello"}, False),
    ("POST", "/api/tasks/recOT1/links", {"title": "x", "url": "https://docs.google.com/d/3"}, False),
    ("POST", "/api/tasks/recOT1/files", None, True),
    ("POST", "/api/tasks/recOT1/reminders", {"send_on": "2026-11-10"}, False),
    ("GET", "/api/links/recLOther/file", None, False),
    ("DELETE", "/api/links/recLOther", None, False),
    ("PATCH", "/api/notes/recNOther", {"visibility": "Internal"}, False),
    ("DELETE", "/api/notes/recNOther", None, False),
]


@pytest.mark.parametrize("method,url,json,upload", PARTNER_ON_ANOTHER_PROGRAM)
def test_partner_cannot_reach_another_programs_launch(client, world, as_role, method, url, json, upload):
    """Even a task assigned to them there: they are not on that launch. 404, so it stays hidden."""
    as_role("partner")
    assert call(client, method, url, json, upload).status_code == 404


def test_partner_lists_only_their_own_launches(client, world, as_role):
    as_role("partner")
    ids = {p["id"] for p in client.get("/api/projects").json()["projects"]}
    assert ids == {"recProj"}


def test_partner_cannot_read_another_programs_history(client, world, as_role):
    as_role("partner")
    assert client.get("/api/projects/recOther/history").status_code == 403


# The CSP report endpoint accepts anyone and writes nothing (test_csp_reports.py checks that).
VIEWER_WRITES = [
    r
    for r in ROWS
    if r.method != "GET" and not r.route.startswith(("/auth/", "/api/me/view", "/api/security/csp-report"))
]


@pytest.mark.parametrize("role", ["viewer", "lead"])
@pytest.mark.parametrize("row", VIEWER_WRITES, ids=lambda r: f"{r.method} {r.target}")
def test_read_only_people_change_nothing(client, world, as_role, row, role):
    as_role(role)
    before = len(world.writes)
    response = call(client, row.method, row.target, row.json, row.upload)
    assert response.status_code in (403, 404)
    assert len(world.writes) == before, "a refused request still wrote to Airtable"


@pytest.mark.parametrize("role", ["staff", "admin_as_staff", "viewer", "lead", "partner"])
@pytest.mark.parametrize("change", [{"access_level": "Admin"}, {"status": "Active"}, {"status": "Inactive"}])
def test_nobody_changes_their_own_access_level_or_status(client, world, as_role, role, change):
    as_role(role)
    response = client.patch(f"/api/users/{USER_IDS[role]}", json=change)
    assert response.status_code == 403


@pytest.mark.parametrize("change", [{"access_level": "Staff"}, {"access_level": "Viewer"}, {"status": "Inactive"}])
def test_admin_cannot_demote_or_deactivate_themselves(client, world, as_role, change):
    as_role("admin")
    before = len(world.writes)
    response = client.patch("/api/users/recAdmin", json=change)
    assert response.status_code in (400, 409)
    assert len(world.writes) == before


def test_admin_in_staff_view_gets_staff_results_everywhere():
    """The table must say so too: the admin_as_staff column never grants more than staff."""
    for row in ROWS:
        staff, as_staff = row.expect["staff"], row.expect["admin_as_staff"]
        if staff >= 400:
            assert as_staff >= 400, f"{row.method} {row.route}: admin in staff view is allowed, staff is not"
