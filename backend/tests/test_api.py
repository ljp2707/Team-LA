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


def test_one_off_in_between_warns_but_moves_nothing(client, sign_in, project):
    sign_in("admin@example.org")
    before = fields(project, Work.TABLE, "recT3")[Work.DUE_DATE_OVERRIDE]
    response = client.post(
        "/api/projects/recProj/tasks",
        json={"name": "Print flyers", "due_date": "2026-11-10", "needs_first": ["recT2"], "comes_before": ["recT3"]},
    )
    assert response.status_code == 201
    new_id = response.json()["id"]
    assert response.json()["warnings"] == [
        "Community outreach (Nov 6) is due before Print flyers, which it now waits on."
    ]
    later = fields(project, Work.TABLE, "recT3")
    assert later[Work.DEPENDS_ON] == ["recT2", new_id]
    assert later[Work.DUE_DATE_OVERRIDE] == before  # Nothing moved

    row = client.get("/api/tasks/recT3").json()
    assert row["date_warning"] == "Due before Print flyers (Nov 10), which it needs first"
    assert row["date_warnings"] == ["Due before Print flyers (Nov 10), which it needs first."]
    assert client.get(f"/api/tasks/{new_id}").json()["date_warnings"] == [
        "Due after Community outreach (Nov 6), which waits on it."
    ]


def test_one_off_in_between_refuses_a_circle(client, sign_in, project):
    sign_in("admin@example.org")
    response = client.post(
        "/api/projects/recProj/tasks",
        json={"name": "Loop", "due_date": "2026-11-10", "needs_first": ["recT3"], "comes_before": ["recT2"]},
    )
    assert response.status_code == 422


def test_changing_a_due_date_only_warns(client, sign_in, project):
    sign_in("admin@example.org")
    assert client.get("/api/tasks/recT3").json()["date_warning"] is None
    client.patch("/api/tasks/recT2", json={"due_date": "2026-11-20"})
    assert fields(project, Work.TABLE, "recT3")[Work.DUE_DATE_OVERRIDE] == "2026-11-06"
    assert client.get("/api/tasks/recT3").json()["date_warning"] == (
        "Due before Design flyer (Nov 20), which it needs first"
    )


def test_one_off_on_a_closed_launch_sends_no_email(client, sign_in, project, fixed_clock, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.services import reminders

    sent = []
    monkeypatch.setattr(reminders, "send_assignment_emails", lambda *a, **k: sent.append(a))
    sign_in("admin@example.org")
    fixed_clock(datetime(2026, 11, 30, 9, tzinfo=ZoneInfo("America/Los_Angeles")))
    assert client.post("/api/projects/recProj/close", json={}).status_code == 200
    response = client.post(
        "/api/projects/recProj/tasks",
        json={"name": "Return the lane ropes", "due_date": "2026-11-25", "user_id": "recStaff"},
    )
    assert response.status_code == 201
    assert sent == []


def test_a_task_can_have_several_people(client, sign_in, project, monkeypatch):
    from app.services import reminders

    sent = []
    monkeypatch.setattr(reminders, "send_assignment_emails", lambda by_user, *a: sent.append(by_user))
    sign_in("admin@example.org")
    response = client.post("/api/tasks/recT3/assign", json={"user_ids": ["recStaff", "recAdmin"]})
    assert response.status_code == 200
    assert [a["id"] for a in response.json()["assignees"]] == ["recStaff", "recAdmin"]
    assert fields(project, Work.TABLE, "recT3")[Work.ASSIGNED_TO] == ["recStaff", "recAdmin"]
    assert sent == []  # recStaff was already on it, and admins are not emailed about their own changes

    # Both people see it in My Tasks and can update it
    assert "Community outreach" in [t["name"] for t in client.get("/api/tasks/mine").json()["groups"]["this_week"]]
    sign_in("staff@example.org")
    assert "Community outreach" in [t["name"] for t in client.get("/api/tasks/mine").json()["groups"]["this_week"]]
    assert client.get("/api/tasks/recT3").json()["can_edit"] is True

    # Taking one person off keeps the other
    sign_in("admin@example.org")
    client.post("/api/tasks/recT3/assign", json={"user_ids": ["recAdmin"]})
    assert fields(project, Work.TABLE, "recT3")[Work.ASSIGNED_TO] == ["recAdmin"]
    sign_in("staff@example.org")
    assert client.get("/api/tasks/recT3").json()["can_edit"] is False


def test_adding_a_person_emails_only_the_new_person(client, sign_in, project, monkeypatch):
    from app.services import reminders

    sent = []
    monkeypatch.setattr(reminders, "send_assignment_emails", lambda by_user, *a: sent.append(by_user))
    sign_in("admin@example.org")
    client.post("/api/tasks/recT1/assign", json={"user_ids": []})
    client.post("/api/tasks/recT3/assign", json={"user_ids": ["recAdmin"]})
    sent.clear()
    client.post("/api/tasks/recT3/assign", json={"user_ids": ["recAdmin", "recStaff"]})
    assert sent == [{"recStaff": ["recT3"]}]


def test_reminders_go_to_everyone_on_a_task(project):
    from datetime import date

    from app.services.records import TaskRec
    from app.services.reminders import Context

    ctx = Context.load(date(2026, 11, 4))
    task = TaskRec(id="x", name="X", session_id="recProj", assignees=["recStaff", "recAdmin"])
    assert [u.id for u in ctx.recipients(task)] == ["recStaff", "recAdmin"]
    assert task.assigned_to == "recStaff" and task.is_assigned("recAdmin")


def test_hand_off_keeps_the_other_people_on_a_task(client, sign_in, project):
    sign_in("admin@example.org")
    client.post("/api/tasks/recT3/assign", json={"user_ids": ["recStaff", "recAdmin"]})
    response = client.post(
        "/api/users/hand-off",
        json={"from_user": "recAdmin", "to_user": "recStaff", "replace_on_teams": False},
    )
    assert response.status_code == 200, response.text
    assert fields(project, Work.TABLE, "recT3")[Work.ASSIGNED_TO] == ["recStaff"]


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


def test_adding_a_person_sends_them_a_welcome_email(client, sign_in, fake, settings, monkeypatch):
    from app.airtable.schema import Reminders
    from app.email import gmail

    settings(REMINDERS_DRY_RUN=False)
    sent = []
    monkeypatch.setattr(gmail, "send_email", lambda to, subject, text, html: sent.append((to, subject)))
    sign_in("admin@example.org")
    new = {"first_name": "Mary", "email": "mary@example.org", "access_level": "Staff", "role_ids": ["recRole"]}
    response = client.post("/api/users", json=new)
    assert response.status_code == 201
    assert sent == [("mary@example.org", "You've been added to NMU Launches")]
    row = fake.find(Users.TABLE, response.json()["id"])["fields"]
    assert row[Users.WELCOME_EMAIL_SENT]
    logged = [r["fields"] for r in fake.rows(Reminders.TABLE)]
    assert [(r[Reminders.KIND], r[Reminders.STATUS]) for r in logged] == [("Welcome", "Sent")]


def test_a_failed_welcome_email_is_logged_as_failed(client, sign_in, fake, settings, monkeypatch):
    from app.airtable.schema import Reminders
    from app.email import gmail

    settings(REMINDERS_DRY_RUN=False)

    def fail(*args):
        raise gmail.EmailError("Gmail refused the email: test")

    monkeypatch.setattr(gmail, "send_email", fail)
    sign_in("admin@example.org")
    new = {"first_name": "Mary", "email": "mary@example.org", "access_level": "Staff"}
    assert client.post("/api/users", json=new).status_code == 201
    logged = [r["fields"] for r in fake.rows(Reminders.TABLE)]
    assert [(r[Reminders.STATUS], r[Reminders.ERROR]) for r in logged] == [("Failed", "Gmail refused the email: test")]


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


def test_template_used_by_a_launch_cannot_be_deleted(client, sign_in, template):
    sign_in("admin@example.org")
    response = client.delete("/api/templates/recTpl")
    assert response.status_code == 409
    assert "inactive" in response.json()["detail"]
    assert template.writes_to(TemplateList.TABLE, "delete") == []
    assert template.writes_to(Steps.TABLE, "delete") == []


def test_unused_template_is_deleted_with_its_steps_and_versions(client, sign_in, template):
    sign_in("admin@example.org")
    copy_id = client.post("/api/templates/recTpl/duplicate", json={}).json()["id"]
    copy_steps = {r["id"] for r in template.rows(Steps.TABLE) if r["fields"][Steps.TEMPLATE] == [copy_id]}
    assert len(copy_steps) == 3
    assert client.delete(f"/api/templates/{copy_id}").status_code == 204
    assert copy_id not in {r["id"] for r in template.rows(TemplateList.TABLE)}
    assert not copy_steps & {r["id"] for r in template.rows(Steps.TABLE)}
    assert not [r for r in template.rows(TemplateVersions.TABLE) if r["fields"].get(TemplateVersions.TEMPLATE) == [copy_id]]
    assert len([r for r in template.rows(Steps.TABLE) if r["fields"][Steps.TEMPLATE] == ["recTpl"]]) == 3
    assert client.get(f"/api/templates/{copy_id}").status_code == 404


def test_only_admins_can_delete_templates(client, sign_in, template):
    sign_in("staff@example.org")
    assert client.delete("/api/templates/recTpl").status_code == 403


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


def test_erase_removes_a_former_persons_details(client, sign_in, project):
    gone = fields(project, Users.TABLE, "recGone")
    full = f"{gone[Users.FIRST_NAME]} {gone.get(Users.LAST_NAME, '')}".strip()
    project.add(ActivityLog.TABLE, {ActivityLog.TYPE: "Reassignment", ActivityLog.TEXT: f"gave Flyer to {full}", ActivityLog.TO: full})
    project.add(ActivityLog.TABLE, {ActivityLog.TYPE: "System", ActivityLog.TEXT: "wrote to gone@example.org"})
    sign_in("admin@example.org")

    assert client.post("/api/users/recStaff/erase").status_code == 409  # still active
    response = client.post("/api/users/recGone/erase")
    assert response.status_code == 200 and response.json()["history_rows"] == 2

    row = fields(project, Users.TABLE, "recGone")
    assert (row[Users.FIRST_NAME], row[Users.LAST_NAME]) == ("Former", "team member")
    assert row[Users.EMAIL].endswith("@example.invalid")
    texts = " ".join(
        f"{r['fields'].get(ActivityLog.TEXT, '')} {r['fields'].get(ActivityLog.TO, '')}" for r in project.rows(ActivityLog.TABLE)
    )
    assert full not in texts and "gone@example.org" not in texts
    assert "gave Flyer to Former team member" in texts


# --- Deleting a launch ----------------------------------------------------------


def test_only_admin_view_can_delete_a_launch(client, sign_in, project):
    assert p.can_delete_projects(Actor("Admin", "admin"))
    assert not p.can_delete_projects(Actor("Admin", "staff"))
    assert not p.can_delete_projects(Actor("Staff", "staff"))
    for email in ("staff@example.org", "viewer@example.org", "partner@example.org"):
        sign_in(email)
        assert client.delete("/api/projects/recProj").status_code == 403
    sign_in("admin@example.org")
    client.post("/api/me/view", json={"view": "staff"})
    assert client.get("/api/projects/recProj").json()["can_delete"] is False
    assert client.delete("/api/projects/recProj").status_code == 403
    assert project.writes_to(Session.TABLE, "delete") == []
    assert project.writes_to(Work.TABLE, "delete") == []


def test_deleting_a_launch_deletes_everything_on_it(client, sign_in, project):
    from tests.builders import add_reminder

    add_team(project, "recProj", "recRole", "recStaff")
    add_note(project, "recN1", "recT2", "recStaff")
    add_reminder(project, "recR1", "recT2", "recStaff", date(2026, 11, 20))
    project.add(Links.TABLE, {Links.TITLE: "Flyer", Links.URL: "https://canva.com/x", Links.SESSION: ["recProj"]}, "recL1")
    # Another launch's rows must be left alone.
    add_project(project, "recOther", name="Kent")
    add_task(project, "recOtherT", "Other task", date(2026, 12, 1), project="recOther", assigned="recStaff")
    add_team(project, "recOther", "recRole", "recStaff")
    add_note(project, "recN2", "recOtherT", "recStaff", project="recOther")
    add_reminder(project, "recR2", "recOtherT", "recStaff", date(2026, 11, 25))

    sign_in("admin@example.org")
    assert client.get("/api/projects/recProj").json()["can_delete"] is True
    response = client.delete("/api/projects/recProj")
    assert response.status_code == 200
    assert response.json() == {"deleted": True, "tasks": 6}

    assert [r["id"] for r in project.rows(Session.TABLE)] == ["recOther"]
    assert [r["id"] for r in project.rows(Work.TABLE)] == ["recOtherT"]
    assert [r["fields"][SessionTeam.SESSION] for r in project.rows(SessionTeam.TABLE)] == [["recOther"]]
    assert project.rows(Links.TABLE) == []
    from app.airtable.schema import Reminders
    assert [r["id"] for r in project.rows(Reminders.TABLE)] == ["recR2"]
    log = project.rows(ActivityLog.TABLE)
    assert "recN1" not in {r["id"] for r in log} and "recN2" in {r["id"] for r in log}
    # The launch goes last, so a failure part way never leaves rows without a launch.
    assert [w[1] for w in project.writes if w[0] == "delete"][-1] == Session.TABLE
    # One history row, not tied to any launch, records who deleted it.
    deleted = [r for r in log if "deleted the launch" in r["fields"].get(ActivityLog.TEXT, "")]
    assert len(deleted) == 1
    assert ActivityLog.SESSION not in deleted[0]["fields"]
    assert deleted[0]["fields"][ActivityLog.AUTHOR] == ["recAdmin"]
    assert "Rainier Beach" in deleted[0]["fields"][ActivityLog.TEXT]

    assert client.get("/api/projects/recProj").status_code == 404
    assert client.delete("/api/projects/recProj").status_code == 404
    assert "recProj" not in {c["id"] for c in client.get("/api/projects").json()["projects"]}
    sign_in("staff@example.org")
    assert {t["id"] for g in client.get("/api/tasks/mine").json()["groups"].values() for t in g} == {"recOtherT"}
