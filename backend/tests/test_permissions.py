"""One test per row of the permissions table, plus view rules and route enforcement."""

import pytest

from app import permissions as p
from app.permissions import ADMIN, STAFF, Actor

ADMIN_ACTOR = Actor("Admin", ADMIN)
LEAD_ACTOR = Actor("Project Lead", ADMIN)
STAFF_ACTOR = Actor("Staff", STAFF)
VIEWER_ACTOR = Actor("Viewer", STAFF)
ADMIN_IN_STAFF_VIEW = Actor("Admin", STAFF)
ADMIN_ONLY_RULES = [
    p.can_manage_projects,
    p.can_assign_tasks,
    p.can_edit_setup,
    p.can_see_archive,
]


def test_update_own_tasks():
    assert p.can_update_own_tasks(ADMIN_ACTOR)
    assert p.can_update_own_tasks(STAFF_ACTOR)
    assert not p.can_update_own_tasks(VIEWER_ACTOR)


def test_view_all_projects():
    assert p.can_view_all_projects(ADMIN_ACTOR)
    assert p.can_view_all_projects(STAFF_ACTOR)
    assert p.can_view_all_projects(VIEWER_ACTOR)


@pytest.mark.parametrize("rule", ADMIN_ONLY_RULES)
def test_admin_only_rules(rule):
    assert rule(ADMIN_ACTOR)
    assert not rule(STAFF_ACTOR)
    assert not rule(VIEWER_ACTOR)


@pytest.mark.parametrize("rule", ADMIN_ONLY_RULES)
def test_admin_in_staff_view_gets_staff_permissions(rule):
    assert not rule(ADMIN_IN_STAFF_VIEW)


def test_admin_in_staff_view_can_still_update_own_tasks():
    assert p.can_update_own_tasks(ADMIN_IN_STAFF_VIEW)


def test_project_lead_is_treated_as_admin_for_now():
    """Assumption still being decided. See BASE_VIEW_BY_ACCESS_LEVEL."""
    assert p.base_view("Project Lead") == ADMIN
    assert p.can_edit_setup(LEAD_ACTOR)


@pytest.mark.parametrize("level", [None, "", "Partner"])
def test_unknown_access_level_gets_least_access(level):
    assert p.base_view(level) == STAFF
    assert not p.can_update_own_tasks(Actor(level, STAFF))
    assert not p.can_choose_view(level, ADMIN, dev_switch=False)


def test_only_admin_base_view_may_choose_admin():
    assert p.can_choose_view("Admin", ADMIN, dev_switch=False)
    assert not p.can_choose_view("Staff", ADMIN, dev_switch=False)
    assert p.can_choose_view("Staff", ADMIN, dev_switch=True)
    assert p.can_choose_view("Viewer", STAFF, dev_switch=False)


def test_effective_view_drops_admin_after_demotion():
    assert p.effective_view("Staff", ADMIN, dev_switch=False) == STAFF
    assert p.effective_view("Admin", STAFF, dev_switch=False) == STAFF
    assert p.effective_view("Admin", None, dev_switch=False) == ADMIN
    assert p.effective_view("Admin", "nonsense", dev_switch=False) == ADMIN


ADMIN_ROUTES = [
    ("get", "/api/health/airtable"),
    ("post", "/api/projects"),
    ("post", "/api/projects/rec1/move-day-one"),
    ("post", "/api/tasks/rec1/assign"),
    ("get", "/api/templates"),
    ("get", "/api/users"),
    ("post", "/api/users/hand-off"),
    ("get", "/api/archive"),
]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_signed_out_gets_401(client, method, path):
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_staff_cannot_call_admin_routes(client, sign_in, method, path):
    sign_in("staff@example.org")
    assert client.request(method, path).status_code == 403


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_can_reach_admin_routes_until_switching_view(
    client, sign_in, method, path
):
    sign_in("admin@example.org")
    assert client.request(method, path).status_code in (200, 501)

    client.post("/api/me/view", json={"view": "staff"})
    assert client.request(method, path).status_code == 403

    client.post("/api/me/view", json={"view": "admin"})
    assert client.request(method, path).status_code in (200, 501)


def test_viewer_cannot_update_tasks_but_staff_reaches_the_stub(client, sign_in):
    sign_in("viewer@example.org")
    assert client.patch("/api/tasks/rec1").status_code == 403
    sign_in("staff@example.org")
    assert client.patch("/api/tasks/rec1").status_code == 501


def test_everyone_signed_in_can_reach_read_stubs(client, sign_in):
    sign_in("viewer@example.org")
    for path in ("/api/projects", "/api/projects/rec1", "/api/tasks/mine"):
        assert client.get(path).status_code == 501
