"""Making a project's tasks, starting from a past launch, and moving Day 1."""

from datetime import date

import pytest
from fastapi import HTTPException

from app.airtable.schema import ActivityLog, Reminders, Session, SessionTeam, Work
from app.services import timeline
from app.services.records import load_tasks
from tests.builders import (
    add_project,
    add_reminder,
    add_site,
    add_step,
    add_task,
    add_template,
    standard_project,
)


def make_template(fake):
    add_site(fake)
    add_template(fake, live_version=3)
    add_step(fake, "recS1", "Confirm head coach", 42, role="recRole", order=0)
    add_step(fake, "recS2", "Ship equipment", 21, role="recRoleOps", depends=["recS1"], order=1)
    add_step(fake, "recS3", "Send survey", -7, role="recRoleOps", anchor="End", order=2)
    add_step(fake, "recOld", "Retired step", 10, order=3, retired_in=2)


def tasks_by_name(project="recNewProj"):
    return {t.name: t for t in load_tasks() if t.session_id == project}


def test_generate_timeline_assigns_by_role_with_override_and_dependencies(fake):
    make_template(fake)
    add_project(fake, "recNewProj", start=date(2026, 12, 6), duration=5, status="Not started")
    planned = timeline.generate_timeline(
        "recNewProj",
        assignments={"recRole": "recAdmin", "recRoleOps": "recStaff"},
        one_off_tasks=[timeline.OneOff("Collect CDC docs", date(2026, 11, 29), "recRole", None, ["recS1"])],
        overrides={"recS3": "recLead"},
        actor_id="recAdmin",
    )
    assert len(planned) == 4  # 3 live steps + 1 one-off; the retired step is left out
    tasks = tasks_by_name()
    coach, ship, survey, cdc = (
        tasks["Confirm head coach"],
        tasks["Ship equipment"],
        tasks["Send survey"],
        tasks["Collect CDC docs"],
    )
    assert coach.due == date(2026, 10, 25) and coach.assigned_to == "recAdmin"
    assert ship.assigned_to == "recStaff" and ship.depends_on == [coach.id]
    # End anchor: the program ends Dec 10, and -7 means a week after.
    assert survey.due == date(2026, 12, 17)
    assert survey.assigned_to == "recLead"  # the per-task override wins
    assert cdc.one_off and cdc.depends_on == [coach.id] and cdc.due == date(2026, 11, 29)
    assert all(t.status == "Not Started" for t in tasks.values())
    assert ship.step_id == "recS2" and ship.role_id == "recRoleOps"

    session = fake.find(Session.TABLE, "recNewProj")["fields"]
    assert session[Session.TEMPLATE_VERSION] == 3
    assert session[Session.STATUS] == "In progress"
    assert session.get(Session.TIMELINE_GENERATED_AT)
    assert any(r["fields"][ActivityLog.TYPE] == "Project Created" for r in fake.rows(ActivityLog.TABLE))


def test_role_with_nobody_leaves_tasks_unassigned(fake):
    make_template(fake)
    add_project(fake, "recNewProj", start=date(2026, 12, 6))
    timeline.generate_timeline("recNewProj", assignments={"recRole": "recAdmin"})
    assert tasks_by_name()["Ship equipment"].assigned_to is None


def test_create_launch_through_the_api_saves_the_team(client, sign_in, fake):
    make_template(fake)
    sign_in("admin@example.org")
    body = {
        "template_id": "recTpl",
        "name": "Rainier Beach Swim Safely Winter 2027",
        "site_id": "recSite",
        "day_one": "2027-01-10",
        "end_date": "2027-01-14",
        "assignments": {"recRole": "recAdmin", "recRoleOps": "recStaff"},
        "one_offs": [{"name": "Collect CDC docs", "due_date": "2027-01-03", "role_id": "recRole"}],
        "partner_name": "Dana",
        "partner_email": "dana@example.org",
        "drive_folder": "https://drive.google.com/drive/folders/abc",
    }
    response = client.post("/api/projects", json=body)
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    assert len([t for t in load_tasks() if t.session_id == project_id]) == 4
    team = [r["fields"] for r in fake.rows(SessionTeam.TABLE)]
    assert {(f[SessionTeam.ROLE][0], f[SessionTeam.USER][0]) for f in team} == {
        ("recRole", "recAdmin"),
        ("recRoleOps", "recStaff"),
    }
    session = fake.find(Session.TABLE, project_id)["fields"]
    assert session[Session.DURATION_DAYS] == 5
    # The site profile gets the partner details back.
    site = fake.find("Site", "recSite")["fields"]
    assert site["Partner Contact Name"] == "Dana"


def test_drive_folder_must_be_a_drive_link(client, sign_in, fake):
    make_template(fake)
    sign_in("admin@example.org")
    response = client.post(
        "/api/projects",
        json={
            "template_id": "recTpl",
            "name": "X",
            "site_id": "recSite",
            "day_one": "2027-01-10",
            "drive_folder": "https://example.com/folder",
        },
    )
    assert response.status_code == 422


def test_preview_writes_nothing_and_auto_picks_the_only_person(client, sign_in, fake):
    make_template(fake)
    sign_in("admin@example.org")
    before = len(fake.writes)
    body = client.post(
        "/api/projects/preview", json={"template_id": "recTpl", "day_one": "2026-12-06"}
    ).json()
    assert len(fake.writes) == before
    assert body["count"] == 3
    roles = {r["role_id"]: r for r in body["roles"]}
    # Several people hold Program Manager in the fake base, so it is not auto-picked.
    assert roles["recRole"]["user_id"] is None
    assert body["tasks"][0]["group"] == "6 WEEKS OUT"


def test_start_from_past_launch_keeps_offsets_and_skips_skipped(fake):
    add_site(fake)
    add_template(fake)
    add_project(fake, "recPast", start=date(2026, 6, 7), status="Complete", **{Session.TEMPLATE_VERSION: 2})
    add_task(fake, "recP1", "Confirm head coach", date(2026, 4, 26), project="recPast", status="Done")
    add_task(fake, "recP2", "Order caps", date(2026, 5, 1), project="recPast", status="Skipped")
    add_task(fake, "recP3", "Ship", date(2026, 5, 17), project="recPast", status="Done",
             role="recRoleOps", depends=["recP1", "recP2"])
    add_task(fake, "recP4", "Collect CDC docs", date(2026, 5, 31), project="recPast", status="Done", one_off=True)
    add_project(fake, "recNewProj", start=date(2027, 6, 6), template=None)
    timeline.start_from_past_launch("recPast", "recNewProj", {"recRoleOps": "recStaff"})
    tasks = tasks_by_name()
    assert set(tasks) == {"Confirm head coach", "Ship", "Collect CDC docs"}
    assert tasks["Confirm head coach"].due == date(2027, 4, 25)  # 6 weeks before
    assert tasks["Ship"].depends_on == [tasks["Confirm head coach"].id]
    assert tasks["Ship"].assigned_to == "recStaff"
    assert tasks["Collect CDC docs"].one_off
    assert fake.find(Session.TABLE, "recNewProj")["fields"][Session.CREATED_FROM] == ["recPast"]


def test_shift_day_one_moves_open_tasks_and_custom_reminders_only(fake):
    standard_project(fake)
    add_reminder(fake, "recRem", "recT3", "recStaff", date(2026, 11, 5))
    add_reminder(fake, "recRemDone", "recT1", "recAdmin", date(2026, 11, 5))
    result = timeline.shift_day_one("recProj", date(2026, 11, 29), "recAdmin")
    assert result["moved_tasks"] == 5 and result["kept_tasks"] == 1
    assert result["moved_reminders"] == 1
    assert result["message"].startswith("Day 1 moved from Nov 22 to Nov 29. 5 open tasks")
    assert "a week later" in result["message"]
    tasks = {t.id: t for t in load_tasks()}
    assert tasks["recT1"].due == date(2026, 10, 11)  # Done: kept
    assert tasks["recT2"].due == date(2026, 11, 6)  # open: moved a week
    reminder = fake.find(Reminders.TABLE, "recRem")["fields"]
    assert reminder[Reminders.SEND_ON] == "2026-11-12"
    assert fake.find(Reminders.TABLE, "recRemDone")["fields"][Reminders.SEND_ON] == "2026-11-05"
    assert fake.find(Session.TABLE, "recProj")["fields"][Session.START_DATE] == "2026-11-29"


def test_undo_shift_puts_everything_back(fake):
    standard_project(fake)
    add_reminder(fake, "recRem", "recT3", "recStaff", date(2026, 11, 5))
    batch = timeline.shift_day_one("recProj", date(2026, 11, 29), "recAdmin")["batch"]
    timeline.undo_shift("recProj", batch, "recAdmin")
    tasks = {t.id: t for t in load_tasks()}
    assert tasks["recT2"].due == date(2026, 10, 30)
    assert fake.find(Reminders.TABLE, "recRem")["fields"][Reminders.SEND_ON] == "2026-11-05"
    assert fake.find(Session.TABLE, "recProj")["fields"][Session.START_DATE] == "2026-11-22"
    # Undo cannot be repeated, because it is no longer the latest move.
    with pytest.raises(HTTPException) as error:
        timeline.undo_shift("recProj", batch, "recAdmin")
    assert error.value.status_code == 409


def test_undo_refused_after_24_hours(fake, advance):
    standard_project(fake)
    batch = timeline.shift_day_one("recProj", date(2026, 11, 29), "recAdmin")["batch"]
    advance(hours=25)
    with pytest.raises(HTTPException) as error:
        timeline.undo_shift("recProj", batch, "recAdmin")
    assert error.value.status_code == 409
    assert "24 hours" in error.value.detail


def test_undo_refused_when_not_the_latest_move(fake, advance):
    standard_project(fake)
    first = timeline.shift_day_one("recProj", date(2026, 11, 29), "recAdmin")["batch"]
    advance(minutes=5)
    timeline.shift_day_one("recProj", date(2026, 12, 6), "recAdmin")
    with pytest.raises(HTTPException) as error:
        timeline.undo_shift("recProj", first, "recAdmin")
    assert error.value.status_code == 409


def test_move_day_one_preview_writes_nothing(client, sign_in, fake):
    standard_project(fake)
    sign_in("admin@example.org")
    before = len(fake.writes)
    body = client.post(
        "/api/projects/recProj/move-day-one", json={"new_day_one": "2026-11-29", "preview": True}
    ).json()
    assert len(fake.writes) == before
    assert body["message"] == (
        "5 open tasks and their reminders will move 1 week later. 1 finished task keeps its date."
    )


def test_finished_tasks_without_a_stored_date_get_one_before_day_1_moves(fake):
    """Older tasks follow Day 1 through a formula, so they are pinned first."""
    standard_project(fake)
    record = fake.find(Work.TABLE, "recT1")
    record["fields"].pop(Work.DUE_DATE_OVERRIDE)
    record["fields"][Work.DUE_DATE] = "2026-10-11T00:00:00.000Z"
    timeline.shift_day_one("recProj", date(2026, 11, 29), "recAdmin")
    assert fake.find(Work.TABLE, "recT1")["fields"][Work.DUE_DATE_OVERRIDE] == "2026-10-11"


def test_find_cycle():
    assert timeline.find_cycle({"a": ["b"], "b": ["a"]})
    assert not timeline.find_cycle({"a": ["b"], "b": []})
