"""The API end to end, through the fake base: who can do what, and what each page gets."""

from datetime import date

import pytest

from app import permissions as p
from app.airtable.schema import ActivityLog, Links, Session, SessionTeam, Steps, TemplateList, TemplateVersions, Users, Work
from app.permissions import Actor
from tests.builders import (
    add_note,
    add_project,
    add_step,
    add_task,
    add_team,
    add_template,
    standard_project,
)


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


def fields(fake, table, record_id):
    return fake.find(table, record_id)["fields"]


# --- Permission rules ---------------------------------------------------------


def test_partner_rules():
    partner = Actor("Partner", "partner")
    assert p.can_update_own_tasks(partner)
    assert not p.can_view_all_projects(partner)
    assert p.can_view_project(partner, "u1", ["u1"])
    assert not p.can_view_project(partner, "u1", ["u2"])
    assert not p.can_see_internal_notes(partner)
    assert not p.can_see_history(partner)
    assert not p.can_see_archive(partner)
    assert not p.can_assign_tasks(partner)
    assert not p.can_share_notes(partner)
    assert p.default_note_visibility(partner) == "Shared"
    assert p.base_view("Partner") == "partner"


def test_edit_task_rules():
    staff = Actor("Staff", "staff")
    assert p.can_edit_task(staff, "me", "me")
    assert not p.can_edit_task(staff, "me", "someone")
    assert not p.can_edit_task(staff, "me", None)
    assert not p.can_edit_task(Actor("Viewer", "staff"), "me", "me")
    assert p.can_edit_task(Actor("Admin", "admin"), "me", "someone")
    assert not p.can_edit_task_details(staff)


def test_note_delete_window():
    staff = Actor("Staff", "staff")
    assert p.can_delete_note(staff, True, 10)
    assert not p.can_delete_note(staff, True, 16)
    assert not p.can_delete_note(staff, False, 1)
    assert p.can_delete_note(Actor("Admin", "admin"), False, 1000)


# --- Projects -----------------------------------------------------------------


def test_dashboard_cards_have_computed_fields(client, sign_in, project):
    sign_in("admin@example.org")
    body = client.get("/api/projects").json()
    card = body["projects"][0]
    assert card["site"] == "Rainier Beach"
    assert card["overdue"] == 2  # Design flyer and Ship equipment
    assert card["complete"] == 16  # 1 of 6
    assert card["next_milestone"]["name"] == "Design flyer"
    assert card["needs_owner"] == 1
    assert body["summary"]["active"] == 1
    assert body["summary"]["next_day_one"]["site"] == "Rainier Beach"


def test_staff_see_projects_but_not_closed_ones(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/projects?status=closed").status_code == 403


def test_project_detail_groups_and_flags(client, sign_in, project):
    sign_in("admin@example.org")
    body = client.get("/api/projects/recProj").json()
    phases = {g["phase"]: [t["name"] for t in g["tasks"]] for g in body["groups"]}
    assert phases["Before the program"][0] == "Confirm head coach"
    assert phases["Program week"] == ["Day 1 check-in"]
    assert phases["After the program"] == ["Send participant survey"]
    rows = {t["name"]: t for g in body["groups"] for t in g["tasks"]}
    assert rows["Design flyer"]["dependents"] == 1
    assert rows["Community outreach"]["display_status"] == "Blocked"
    assert rows["Community outreach"]["waiting_text"] == "Waiting on Design flyer"
    assert rows["Community outreach"]["at_risk"]
    assert body["can_close"] is False  # Day 1 has not passed


def test_staff_cannot_change_anyone_elses_task_or_assign(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.patch("/api/tasks/recT5", json={"status": "Done"}).status_code == 403
    assert client.post("/api/tasks/recT2/assign", json={"user_id": "recStaff"}).status_code == 403
    assert client.patch("/api/tasks/recT2", json={"due_date": "2026-12-01"}).status_code == 403
    assert client.patch("/api/tasks/recT2", json={"status": "Skipped"}).status_code == 403
    assert client.post("/api/projects/recProj/tasks", json={"name": "x", "due_date": "2026-12-01"}).status_code == 403


def test_no_route_lets_staff_view_assign(client, sign_in, project):
    """Every assignment route needs admin view, even for an admin in staff view."""
    sign_in("admin@example.org")
    client.post("/api/me/view", json={"view": "staff"})
    assert client.post("/api/tasks/recT2/assign", json={"user_id": "recAdmin"}).status_code == 403
    assert client.post("/api/users/hand-off", json={"from_user": "recStaff", "to_user": "recAdmin"}).status_code == 403


def test_staff_marks_own_task_done_and_it_is_logged(client, sign_in, project):
    sign_in("staff@example.org")
    response = client.patch("/api/tasks/recT2", json={"status": "Done"})
    assert response.status_code == 200
    task = fields(project, Work.TABLE, "recT2")
    assert task[Work.STATUS] == "Done"
    assert task[Work.COMPLETED_DATE] == "2026-11-04"
    assert task[Work.COMPLETED_BY] == ["recStaff"]
    log = [r["fields"] for r in project.rows(ActivityLog.TABLE)]
    assert log[-1][ActivityLog.TYPE] == "Status Change"
    assert (log[-1][ActivityLog.FROM], log[-1][ActivityLog.TO]) == ("Not Started", "Done")


def test_viewers_cannot_write_anything(client, sign_in, project):
    sign_in("viewer@example.org")
    for method, path, body in [
        ("patch", "/api/tasks/recT2", {"status": "Done"}),
        ("post", "/api/tasks/recT2/notes", {"text": "hi"}),
        ("post", "/api/tasks/recT2/links", {"title": "x", "url": "https://example.org"}),
        ("post", "/api/tasks/recT2/reminders", {"send_on": "2026-11-10"}),
        ("delete", "/api/notes/recN", None),
    ]:
        assert client.request(method, path, json=body).status_code == 403, path


def test_admin_reassigns_and_due_date_change_is_logged(client, sign_in, project):
    sign_in("admin@example.org")
    assert client.post("/api/tasks/recT2/assign", json={"user_id": "recLead"}).status_code == 200
    assert fields(project, Work.TABLE, "recT2")[Work.ASSIGNED_TO] == ["recLead"]
    assert client.patch("/api/tasks/recT2", json={"due_date": "2026-11-12"}).status_code == 200
    types = [r["fields"][ActivityLog.TYPE] for r in project.rows(ActivityLog.TABLE)]
    assert types[-2:] == ["Reassignment", "Date Change"]


def test_dependency_cycles_are_refused(client, sign_in, project):
    sign_in("admin@example.org")
    response = client.patch("/api/tasks/recT2", json={"depends_on": ["recT3"]})
    assert response.status_code == 422


def test_one_off_task_and_close_and_reopen(client, sign_in, project, fixed_clock):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    sign_in("admin@example.org")
    response = client.post(
        "/api/projects/recProj/tasks",
        json={"name": "Collect CDC docs", "due_date": "2026-11-15", "role_id": "recRole", "needs_first": ["recT1"]},
    )
    assert response.status_code == 201
    new = fields(project, Work.TABLE, response.json()["id"])
    assert new[Work.ONE_OFF] is True and new[Work.DEPENDS_ON] == ["recT1"]

    assert client.post("/api/projects/recProj/close", json={}).status_code == 409  # before Day 1
    fixed_clock(datetime(2026, 11, 30, 9, tzinfo=ZoneInfo("America/Los_Angeles")))
    assert client.post("/api/projects/recProj/close", json={"skip_open": True}).status_code == 200
    session = fields(project, Session.TABLE, "recProj")
    assert session[Session.STATUS] == "Complete" and session[Session.CLOSED_DATE] == "2026-11-30"
    assert fields(project, Work.TABLE, "recT2")[Work.STATUS] == "Skipped"
    assert fields(project, Work.TABLE, "recT1")[Work.STATUS] == "Done"
    assert client.get("/api/projects").json()["projects"] == []
    assert client.post("/api/projects/recProj/reopen").status_code == 200
    assert fields(project, Session.TABLE, "recProj")[Session.STATUS] == "In progress"


# --- My Tasks and task detail ----------------------------------------------------


def test_my_tasks_groups_and_do_this_first(client, sign_in, project):
    sign_in("staff@example.org")
    body = client.get("/api/tasks/mine").json()
    groups = {k: [t["name"] for t in v] for k, v in body["groups"].items()}
    assert groups["overdue"] == ["Design flyer", "Ship equipment to site"]
    assert groups["this_week"] == ["Community outreach"]
    assert body["counts"] == {"overdue": 2, "this_week": 1, "open": 3}
    assert body["do_this_first"]["name"] == "Design flyer"
    assert body["do_this_first"]["reason"] == "Rainier Beach is waiting on it. 1 task depends on this one."
    week = client.get("/api/tasks/mine?filter=week").json()["groups"]
    assert [t["name"] for t in week["this_week"]] == ["Community outreach"] and not week["overdue"]


def test_task_detail_order_of_work(client, sign_in, project):
    sign_in("staff@example.org")
    body = client.get("/api/tasks/recT4").json()
    assert body["needs_first"][0]["name"] == "Confirm head coach"
    assert body["waiting_on_this"][0]["name"] == "Day 1 check-in"
    assert body["risk_note"].startswith("Day 1 check-in is waiting on this task.")
    assert body["calendar_url"].startswith("https://calendar.google.com/calendar/render?action=TEMPLATE")
    assert "20261101%2F20261102" in body["calendar_url"]
    assert body["timing"] == "No set timing" or "Day 1" in body["timing"]


def test_notes_and_links_on_own_task(client, sign_in, project):
    sign_in("staff@example.org")
    notes = client.post("/api/tasks/recT2/notes", json={"text": "Logo is in."}).json()["notes"]
    assert notes[-1]["text"] == "Logo is in." and notes[-1]["visibility"] == "Internal"
    assert client.post("/api/tasks/recT5/notes", json={"text": "not mine"}).status_code == 403
    assert client.post("/api/tasks/recT2/notes", json={"text": "x" * 2001}).status_code == 422

    link = client.post("/api/tasks/recT2/links", json={"title": "Flyer", "url": "https://www.canva.com/design/1"})
    assert link.json()["kind"] == "Canva"
    drive = client.post("/api/tasks/recT2/links", json={"title": "Doc", "url": "https://docs.google.com/d/1"})
    assert drive.json()["kind"] == "Google Drive"
    assert client.post("/api/tasks/recT2/links", json={"title": "x", "url": "http://insecure.org"}).status_code == 422
    assert client.delete(f"/api/links/{link.json()['id']}").status_code == 200
    assert not any(r["id"] == link.json()["id"] for r in project.rows(Links.TABLE))


def test_note_delete_window_through_the_api(client, sign_in, project, advance):
    sign_in("staff@example.org")
    note = client.post("/api/tasks/recT2/notes", json={"text": "oops"}).json()["notes"][-1]
    advance(minutes=20)
    assert client.delete(f"/api/notes/{note['id']}").status_code == 403
    sign_in("admin@example.org")
    assert client.delete(f"/api/notes/{note['id']}").status_code == 200
    assert project.rows(ActivityLog.TABLE)[-1]["fields"][ActivityLog.TYPE] == "System"


def test_reminder_date_cannot_be_in_the_past(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.post("/api/tasks/recT3/reminders", json={"send_on": "2026-11-03"}).status_code == 422
    panel = client.post("/api/tasks/recT3/reminders", json={"send_on": "2026-11-05", "note": "check"}).json()
    assert panel["custom"][0]["date_text"] == "Thu, Nov 5"
    reminder_id = panel["custom"][0]["id"]
    assert client.delete(f"/api/reminders/{reminder_id}").status_code == 200


# --- Partners ---------------------------------------------------------------------


@pytest.fixture
def partner_setup(project):
    fields(project, Session.TABLE, "recProj")[Session.PARTNERS] = ["recPartner"]
    add_project(project, "recOther", name="Kent YMCA Learn to Swim", start=date(2026, 12, 6))
    add_task(project, "recOtherTask", "Other task", date(2026, 11, 20), project="recOther", assigned="recPartner")
    add_task(project, "recPartnerTask", "Pool access", date(2026, 11, 10), assigned="recPartner")
    add_note(project, "recInternal", "recPartnerTask", "recAdmin", "Internal only", "Internal")
    add_note(project, "recShared", "recPartnerTask", "recAdmin", "Hello partner", "Shared")
    return project


def test_partner_cannot_read_another_project(client, sign_in, partner_setup):
    sign_in("partner@example.org")
    assert client.get("/api/projects/recOther").status_code == 404
    assert client.get("/api/tasks/recOtherTask").status_code == 404
    listed = [p["id"] for p in client.get("/api/projects").json()["projects"]]
    assert listed == ["recProj"]
    mine = client.get("/api/tasks/mine").json()
    names = [t["name"] for g in mine["groups"].values() for t in g]
    assert names == ["Pool access"]


def test_partner_cannot_read_the_archive_or_admin_pages(client, sign_in, partner_setup):
    sign_in("partner@example.org")
    for path in ("/api/archive", "/api/templates", "/api/users", "/api/roles", "/api/sites", "/api/projects/recProj/history"):
        assert client.get(path).status_code == 403, path


def test_partner_never_sees_internal_notes_or_history(client, sign_in, partner_setup):
    sign_in("partner@example.org")
    task = client.get("/api/tasks/recPartnerTask").json()
    assert [n["text"] for n in task["notes"]] == ["Hello partner"]
    assert client.patch("/api/notes/recInternal", json={"visibility": "Shared"}).status_code == 404
    project = client.get("/api/projects/recProj").json()
    assert project["history"] == [] and project["can_see_history"] is False
    # Their own notes are shared, and they can update their own task.
    notes = client.post("/api/tasks/recPartnerTask/notes", json={"text": "Gate code is 1234"}).json()["notes"]
    assert notes[-1]["visibility"] == "Shared"
    assert client.patch("/api/tasks/recPartnerTask", json={"status": "Done"}).status_code == 200


def test_staff_can_share_a_note_on_their_task(client, sign_in, partner_setup):
    add_note(partner_setup, "recStaffNote", "recT2", "recStaff", "for the partner")
    sign_in("staff@example.org")
    assert client.patch("/api/notes/recStaffNote", json={"visibility": "Shared"}).json()["visibility"] == "Shared"


def test_only_partner_users_can_be_partners(client, sign_in, partner_setup):
    sign_in("admin@example.org")
    assert client.patch("/api/projects/recProj", json={"partner_ids": ["recStaff"]}).status_code == 422
    assert client.patch("/api/projects/recProj", json={"partner_ids": ["recPartner"]}).status_code == 200


# --- Users and roles -------------------------------------------------------------


def test_add_person_refuses_duplicate_email(client, sign_in, fake):
    sign_in("admin@example.org")
    duplicate = {"first_name": "A", "email": "ADMIN@example.org", "access_level": "Staff"}
    assert client.post("/api/users", json=duplicate).status_code == 409
    new = {"first_name": "Mary", "email": "Mary@Example.org", "access_level": "Staff", "role_ids": ["recRole"]}
    response = client.post("/api/users", json=new)
    assert response.status_code == 201
    row = fake.find(Users.TABLE, response.json()["id"])["fields"]
    assert row[Users.EMAIL] == "mary@example.org" and row[Users.STATUS] == "Active"


def test_last_admin_cannot_be_removed(client, sign_in, fake):
    sign_in("admin@example.org")
    # Ada cannot demote or deactivate herself.
    assert client.patch("/api/users/recAdmin", json={"access_level": "Staff"}).status_code == 409
    assert client.patch("/api/users/recAdmin", json={"status": "Inactive"}).status_code == 409
    # With a second admin, Ada can remove the other one, but not leave zero.
    fake.find(Users.TABLE, "recLead")["fields"][Users.ACCESS_LEVEL] = "Admin"
    assert client.patch("/api/users/recLead", json={"status": "Inactive"}).status_code == 200


def test_rule_refuses_zero_admins():
    from app.models.people import UserUpdateIn
    from app.routers.users import check_admin_rules
    from app.services.records import UserRec
    from fastapi import HTTPException

    only = UserRec("a", "a@x.org", status="Active", access_level="Admin")
    me = UserRec("me", "me@x.org", status="Active", access_level="Staff")
    with pytest.raises(HTTPException):
        check_admin_rules([only, me], only, UserUpdateIn(access_level="Staff"), "me")


def test_hand_off_moves_only_open_tasks(client, sign_in, project):
    add_team(project, "recProj", "recRoleOps", "recStaff")
    add_task(project, "recDoneStaff", "Old work", date(2026, 10, 1), status="Done", assigned="recStaff")
    sign_in("admin@example.org")
    preview = client.post("/api/users/hand-off", json={"from_user": "recStaff", "to_user": "recLead", "preview": True}).json()
    assert preview["count"] == 3
    assert preview["button"] == "Move 3 tasks to Lee"
    before = len(project.writes)
    assert len(project.writes) == before
    result = client.post(
        "/api/users/hand-off",
        json={"from_user": "recStaff", "to_user": "recLead", "replace_on_teams": True},
    ).json()
    assert result["moved"] == 3
    for task_id in ("recT2", "recT3", "recT4"):
        assert fields(project, Work.TABLE, task_id)[Work.ASSIGNED_TO] == ["recLead"]
    assert fields(project, Work.TABLE, "recDoneStaff")[Work.ASSIGNED_TO] == ["recStaff"]
    assert project.rows(SessionTeam.TABLE)[0]["fields"][SessionTeam.USER] == ["recLead"]
    reassignments = [r for r in project.rows(ActivityLog.TABLE) if r["fields"][ActivityLog.TYPE] == "Reassignment"]
    assert len(reassignments) == 3


# --- Templates --------------------------------------------------------------------


@pytest.fixture
def template(fake):
    add_template(fake, live_version=3)
    add_step(fake, "recS1", "Confirm head coach", 42, order=0)
    add_step(fake, "recS2", "Design flyer", 35, order=1)
    add_step(fake, "recS3", "Order swim caps", 30, order=2)
    add_project(fake, "recRunning", start=date(2026, 12, 6), **{Session.TEMPLATE_VERSION: 3})
    add_task(fake, "recRun1", "Order swim caps", date(2026, 11, 6), project="recRunning", step="recS3")
    return fake


def test_publish_retires_steps_without_deleting_and_moves_live_version(client, sign_in, template):
    sign_in("admin@example.org")
    body = client.get("/api/templates/recTpl").json()
    steps = [
        {"key": s["key"], "name": s["name"], "anchor": s["anchor"], "days_before": s["days_before"],
         "role_id": s["role_id"], "depends_on": s["depends_on"]}
        for s in body["steps"]
    ]
    steps = [s for s in steps if s["name"] != "Order swim caps"]
    steps[1]["days_before"] = 28
    steps[1]["depends_on"] = ["recS1"]
    steps.append({"key": "new-1", "name": "Collect CDC docs", "anchor": "Start", "days_before": 7, "role_id": "recRole", "depends_on": ["recS1"]})
    draft = client.put("/api/templates/recTpl/draft", json={"steps": steps}).json()
    assert draft["draft"]["version"] == 4
    assert draft["projects_on_live"][0]["id"] == "recRunning"
    notes = {s["name"]: s["note"] for s in draft["draft"]["steps"]}
    assert notes["Design flyer"] == "Moved from 5 weeks before in this draft · needs Confirm head coach first"
    assert draft["draft"]["removed"] == ["Order swim caps"]

    published = client.post("/api/templates/recTpl/publish", json={"change_note": "Caps come from the partner"})
    assert published.status_code == 200
    assert not template.writes_to(Steps.TABLE, "delete")
    caps = fields(template, Steps.TABLE, "recS3")
    assert caps[Steps.RETIRED_IN_VERSION] == 4
    new = [r for r in template.rows(Steps.TABLE) if r["fields"][Steps.SHORT_DESCRIPTION] == "Collect CDC docs"][0]
    assert new["fields"][Steps.ADDED_IN_VERSION] == 4 and new["fields"][Steps.DEPENDS_ON] == ["recS1"]
    assert fields(template, Steps.TABLE, "recS2")[Steps.DAYS_BEFORE_ANCHOR] == 28
    assert fields(template, TemplateList.TABLE, "recTpl")[TemplateList.LIVE_VERSION] == 4
    statuses = sorted(r["fields"][TemplateVersions.STATUS] for r in template.rows(TemplateVersions.TABLE))
    assert statuses == ["Live", "Retired"]
    # The running project keeps its own copy of the task.
    assert fields(template, Work.TABLE, "recRun1")[Work.TASK_NAME] == "Order swim caps"
    versions = client.get("/api/templates/recTpl/versions").json()["versions"]
    assert [v["version"] for v in versions] == [4, 3]


def test_draft_with_a_cycle_is_refused(client, sign_in, template):
    sign_in("admin@example.org")
    steps = [
        {"key": "recS1", "name": "A", "days_before": 1, "depends_on": ["recS2"]},
        {"key": "recS2", "name": "B", "days_before": 2, "depends_on": ["recS1"]},
    ]
    assert client.put("/api/templates/recTpl/draft", json={"steps": steps}).status_code == 422


def test_duplicate_and_save_project_as_template(client, sign_in, template):
    sign_in("admin@example.org")
    copy_id = client.post("/api/templates/recTpl/duplicate", json={}).json()["id"]
    assert fields(template, TemplateList.TABLE, copy_id)[TemplateList.NAME] == "Swim Safely copy"
    copies = [r for r in template.rows(Steps.TABLE) if r["fields"][Steps.TEMPLATE] == [copy_id]]
    assert len(copies) == 3
    saved = client.post("/api/templates/from-project", json={"project_id": "recRunning", "name": "From Kent"})
    assert saved.status_code == 201
    steps = [r["fields"] for r in template.rows(Steps.TABLE) if r["fields"][Steps.TEMPLATE] == [saved.json()["id"]]]
    assert steps[0][Steps.DAYS_BEFORE_ANCHOR] == 30


def test_insights_from_past_launches(fake):
    from app.services.templates import insights

    add_template(fake)
    add_step(fake, "recOut", "Community outreach", 28)
    add_step(fake, "recCaps", "Order swim caps", 30)
    for i in range(3):
        pid = f"recClosed{i}"
        add_project(fake, pid, start=date(2025, 7, 6), status="Complete")
        add_task(fake, f"o{i}", "Community outreach", date(2025, 6, 8), project=pid, status="Done",
                 completed=date(2025, 6, 8 + 6 + i), step="recOut")
        add_task(fake, f"c{i}", "Order swim caps", date(2025, 6, 6), project=pid, status="Skipped", step="recCaps")
        add_task(fake, f"x{i}", "Collect CDC docs", date(2025, 6, 29 - i), project=pid, status="Done",
                 one_off=True, completed=date(2025, 6, 28))
    result = insights("recTpl")
    assert result["launches"] == 3
    assert result["often_late"][0]["text"] == "Late in 3 of 3, by 7 days on average"
    assert result["often_skipped"][0]["text"] == "Skipped in 3 of 3"
    added = result["often_added"][0]
    assert added["name"] == "Collect CDC docs" and added["days_before"] == 8


# --- Archive and public stats ------------------------------------------------------


def test_archive_lists_closed_launches_with_on_time_percent(client, sign_in, fake):
    add_template(fake)
    add_project(fake, "recAuburn", name="Auburn Swim Safely Summer 2026", start=date(2026, 7, 12),
                status="Complete", **{Session.CLOSED_DATE: "2026-08-02"})
    add_task(fake, "a1", "On time", date(2026, 6, 1), project="recAuburn", status="Done", completed=date(2026, 5, 30))
    add_task(fake, "a2", "Late", date(2026, 6, 16), project="recAuburn", status="Done", completed=date(2026, 6, 24))
    add_task(fake, "a3", "Skipped", date(2026, 6, 23), project="recAuburn", status="Skipped")
    add_task(fake, "a4", "Added", date(2026, 7, 1), project="recAuburn", status="Done", completed=date(2026, 7, 1), one_off=True)
    sign_in("admin@example.org")
    launches = client.get("/api/archive?site=aub&from=2026-01&to=2026-10").json()["launches"]
    assert launches[0]["on_time"] == 67
    assert client.get("/api/archive?from=2026-08").json()["launches"] == []
    detail = client.get("/api/archive/recAuburn").json()
    assert detail["counts"] == {"tasks": 4, "late": 1, "skipped": 1, "added": 1}
    labels = {t["name"]: t["label"] for t in detail["tasks"]}
    assert labels == {"On time": "On time", "Late": "8 days late", "Skipped": "Skipped", "Added": "Added"}
    assert "closed Aug 2" in detail["subtitle"]


def test_public_season_stats_need_no_sign_in(client, project):
    body = client.get("/api/public/season-stats").json()
    assert set(body) == {"year", "sites_to_launch", "sites_launched", "tasks_done_this_week"}
    assert body["sites_to_launch"] == 1 and body["sites_launched"] == 0
