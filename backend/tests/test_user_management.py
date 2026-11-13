"""User management, batch reassignment, archive schedule and the matching permission
rules, merged from the user management prototype (landerstuff/)."""

from datetime import date

import pytest

from app import permissions as p
from app.airtable.schema import ActivityLog, Session, Users, Work
from app.permissions import Actor
from tests.builders import add_project, add_task, add_template, standard_project


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


def fields(fake, table, record_id):
    return fake.find(table, record_id)["fields"]


# --- Permission rules ---------------------------------------------------------


def test_merged_permission_rules():
    admin, staff, partner = Actor("Admin", "admin"), Actor("Staff", "staff"), Actor("Partner", "partner")
    assert p.can_reassign_tasks(admin) and not p.can_reassign_tasks(staff)
    assert p.can_remove_access(admin) and not p.can_remove_access(staff)
    assert p.can_see_directory(staff) and not p.can_see_directory(partner)
    assert p.program_access("Admin") == "All programs"
    assert p.program_access(None) == p.program_access("Viewer")
    assert p.is_admin_level("Project Lead") and not p.is_admin_level("Staff")


# --- Users ----------------------------------------------------------------------


def test_people_list_has_program_access_and_filters_by_level(client, sign_in, project):
    sign_in("admin@example.org")
    people = client.get("/api/users?access_level=Staff").json()["people"]
    assert [x["id"] for x in people] == ["recStaff"]
    assert people[0]["program_access"].startswith("Program Assistants")
    assert people[0]["is_admin"] is False


def test_directory_is_for_any_nmu_person_but_not_partners(client, sign_in, project):
    sign_in("viewer@example.org")
    names = {x["id"] for x in client.get("/api/users/directory").json()}
    assert {"recAdmin", "recStaff", "recGone"} <= names
    assert client.get("/api/users").status_code == 403  # the full list stays admin only
    sign_in("partner@example.org")
    assert client.get("/api/users/directory").status_code == 403


def test_remove_access_is_refused_while_open_tasks_remain(client, sign_in, project):
    sign_in("admin@example.org")
    response = client.delete("/api/users/recStaff")
    assert response.status_code == 409
    assert "3 open tasks" in response.json()["detail"]
    assert fields(project, Users.TABLE, "recStaff")[Users.STATUS] == "Active"


def test_remove_access_sets_inactive_and_keeps_the_row(client, sign_in, project):
    sign_in("admin@example.org")
    assert client.delete("/api/users/recViewer").status_code == 204
    assert fields(project, Users.TABLE, "recViewer")[Users.STATUS] == "Inactive"
    assert any("removed" in r["fields"][ActivityLog.TEXT] for r in project.rows(ActivityLog.TABLE))


def test_cannot_remove_own_access_and_staff_cannot_remove_anyone(client, sign_in, project):
    sign_in("admin@example.org")
    assert client.delete("/api/users/recAdmin").status_code == 409
    assert client.delete("/api/users/nope").status_code == 404
    sign_in("staff@example.org")
    assert client.delete("/api/users/recViewer").status_code == 403


# --- Batch reassignment -----------------------------------------------------------


def test_reassign_moves_chosen_open_tasks(client, sign_in, project):
    sign_in("admin@example.org")
    result = client.post("/api/tasks/reassign", json={"task_ids": ["recT2", "recT3"], "to_user": "recLead"})
    assert result.status_code == 200, result.text
    assert result.json()["moved"] == 2
    assert fields(project, Work.TABLE, "recT2")[Work.ASSIGNED_TO] == ["recLead"]
    assert fields(project, Work.TABLE, "recT4")[Work.ASSIGNED_TO] == ["recStaff"]  # not chosen


def test_reassign_with_from_user_keeps_others_on_the_task(client, sign_in, project):
    sign_in("admin@example.org")
    client.post("/api/tasks/recT3/assign", json={"user_ids": ["recStaff", "recAdmin"]})
    client.post("/api/tasks/reassign", json={"task_ids": ["recT3"], "to_user": "recLead", "from_user": "recStaff"})
    assert fields(project, Work.TABLE, "recT3")[Work.ASSIGNED_TO] == ["recLead", "recAdmin"]


def test_reassign_rules(client, sign_in, project):
    sign_in("admin@example.org")
    # Done tasks cannot move, and nothing moves if one task is not allowed.
    assert client.post("/api/tasks/reassign", json={"task_ids": ["recT2", "recT1"], "to_user": "recLead"}).status_code == 409
    assert fields(project, Work.TABLE, "recT2")[Work.ASSIGNED_TO] == ["recStaff"]
    # Never to an inactive person.
    assert client.post("/api/tasks/reassign", json={"task_ids": ["recT2"], "to_user": "recGone"}).status_code == 422
    assert client.post("/api/tasks/reassign", json={"task_ids": ["nope"], "to_user": "recLead"}).status_code == 404
    sign_in("staff@example.org")
    assert client.post("/api/tasks/reassign", json={"task_ids": ["recT2"], "to_user": "recLead"}).status_code == 403


# --- Archive schedule -------------------------------------------------------------


def _closed(fake, record_id, start, name):
    add_project(fake, record_id, name=name, start=start, status="Complete", **{Session.CLOSED_DATE: "2026-08-30"})


def _moved_day_one(fake, project, old, new):
    fake.add(
        ActivityLog.TABLE,
        {
            ActivityLog.SESSION: [project],
            ActivityLog.TYPE: "Date Change",
            ActivityLog.TEXT: f"moved Day 1 to {new}",
            ActivityLog.FROM: old,
            ActivityLog.TO: new,
        },
    )


def test_archive_schedule_compares_planned_and_actual_day_one(client, sign_in, fake):
    add_template(fake)
    _closed(fake, "recLate", date(2026, 7, 15), "Auburn Summer")
    _closed(fake, "recEarly", date(2026, 7, 8), "Kent Summer")
    _closed(fake, "recSame", date(2025, 7, 1), "Renton Summer")
    _moved_day_one(fake, "recLate", "2026-07-12", "2026-07-15")
    _moved_day_one(fake, "recEarly", "2026-07-10", "2026-07-08")
    sign_in("admin@example.org")
    rows = {r["id"]: r["schedule"] for r in client.get("/api/archive").json()["launches"]}
    assert rows["recLate"] == {"status": "Delayed", "days": 3, "planned_day_one": "2026-07-12"}
    assert rows["recEarly"]["status"] == "Completed Early" and rows["recEarly"]["days"] == 2
    assert rows["recSame"]["status"] == "On Schedule"
    assert [r["id"] for r in client.get("/api/archive?status=Delayed").json()["launches"]] == ["recLate"]
    assert [r["id"] for r in client.get("/api/archive?year=2025").json()["launches"]] == ["recSame"]
    assert [r["id"] for r in client.get("/api/archive?q=kent").json()["launches"]] == ["recEarly"]
    assert client.get("/api/archive?status=Bogus").status_code == 422
    assert client.get("/api/archive/recLate").json()["schedule"]["status"] == "Delayed"


# --- One person's launches and tasks --------------------------------------------


def test_only_admin_view_can_see_a_persons_work(client, sign_in, project):
    assert p.can_view_user_work(Actor("Admin", "admin"))
    assert not p.can_view_user_work(Actor("Admin", "staff"))
    for email in ("staff@example.org", "viewer@example.org", "partner@example.org"):
        sign_in(email)
        assert client.get("/api/users/recStaff/work").status_code == 403
    sign_in("admin@example.org")
    client.post("/api/me/view", json={"view": "staff"})
    assert client.get("/api/users/recStaff/work").status_code == 403


def test_a_persons_work_shows_active_launches_and_open_tasks(client, sign_in, project):
    from tests.builders import add_team

    # A closed launch is left out, even with an open task on it.
    add_project(project, "recClosed", name="Old", status="Complete", start=date(2026, 6, 1))
    add_task(project, "recClosedT", "Leftover", date(2026, 6, 1), project="recClosed", assigned="recStaff")
    # On a team with nothing assigned: still listed, with no tasks.
    add_project(project, "recTeamOnly", name="Kent", start=date(2027, 1, 10))
    add_team(project, "recTeamOnly", "recRoleOps", "recStaff")

    sign_in("admin@example.org")
    body = client.get("/api/users/recStaff/work").json()
    assert body["person"]["id"] == "recStaff"
    assert body["person"]["access_level"] == "Staff"
    launches = body["launches"]
    assert [launch["id"] for launch in launches] == ["recProj", "recTeamOnly"]  # By Day 1
    first = launches[0]
    assert [t["id"] for t in first["tasks"]] == ["recT2", "recT4", "recT3"]  # Open only, by due date
    assert all(t["status"] and t["due"] for t in first["tasks"])
    assert first["done"] == 0
    assert launches[1]["tasks"] == [] and launches[1]["roles"] == ["Operations"]

    admin = client.get("/api/users/recAdmin/work").json()["launches"]
    assert [t["id"] for t in admin[0]["tasks"]] == ["recT5"]
    assert admin[0]["done"] == 1  # Confirm head coach is done, so it is only counted

    assert client.get("/api/users/recPartner/work").json()["launches"] == []
    assert client.get("/api/users/recNobody/work").status_code == 404
