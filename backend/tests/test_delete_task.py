"""Deleting a task from a program that is not closed (admins only).

Standard project: Design flyer (recT2, staff, due Oct 30, overdue) has Community
outreach (recT3) waiting on it. Today is Wed Nov 4, 2026.
"""

from datetime import date

import pytest

from app.airtable.schema import ActivityLog, Links, Reminders, Session, Work
from tests.builders import add_note, add_reminder, standard_project


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


def _ids(fake, table):
    return {r["id"] for r in fake.rows(table)}


@pytest.mark.parametrize("email", ["staff@example.org", "viewer@example.org", "partner@example.org"])
def test_only_admins_can_delete(client, sign_in, project, email):
    sign_in(email)
    assert client.delete("/api/tasks/recT2").status_code == 403
    assert "recT2" in _ids(project, Work.TABLE)


def test_admin_in_staff_view_cannot_delete(client, sign_in, project):
    sign_in("admin@example.org")
    client.post("/api/me/view", json={"view": "staff"})
    assert client.delete("/api/tasks/recT2").status_code == 403


def test_signed_out_cannot_delete(client, project):
    assert client.delete("/api/tasks/recT2").status_code == 401


def test_admin_deletes_and_dependencies_are_cleared(client, sign_in, project):
    sign_in("admin@example.org")
    response = client.delete("/api/tasks/recT2")
    assert response.status_code == 200
    assert response.json()["no_longer_waiting"] == ["Community outreach"]
    assert "recT2" not in _ids(project, Work.TABLE)
    assert project.find(Work.TABLE, "recT3")["fields"].get(Work.DEPENDS_ON, []) == []
    # Community outreach is no longer blocked waiting on a task that is gone.
    assert client.get("/api/tasks/recT3").json()["display_status"] == "Not Started"


def test_history_keeps_name_due_date_and_people(client, sign_in, project):
    sign_in("admin@example.org")
    client.delete("/api/tasks/recT2")
    row = next(r for r in project.rows(ActivityLog.TABLE) if "deleted the task" in r["fields"][ActivityLog.TEXT])
    assert row["fields"][ActivityLog.TEXT] == "deleted the task Design flyer (due Oct 30, assigned to Sam)"
    assert row["fields"][ActivityLog.SESSION] == ["recProj"]
    assert row["fields"][ActivityLog.AUTHOR] == ["recAdmin"]
    history = client.get("/api/projects/recProj/history").json()["entries"]
    assert any("deleted the task Design flyer" in e["text"] for e in history)


def test_history_is_written_before_the_task_goes(client, sign_in, project):
    sign_in("admin@example.org")
    client.delete("/api/tasks/recT2")
    kinds = [(w[0], w[1]) for w in project.writes]
    assert kinds.index(("create", ActivityLog.TABLE)) < kinds.index(("delete", Work.TABLE))


def test_scheduled_reminders_are_cancelled(client, sign_in, project):
    add_reminder(project, "recRem", "recT2", "recStaff", date(2026, 11, 10))
    sign_in("admin@example.org")
    client.delete("/api/tasks/recT2")
    assert project.find(Reminders.TABLE, "recRem")["fields"][Reminders.STATUS] == "Cancelled"


def test_links_move_to_the_program_and_notes_stay(client, sign_in, project):
    project.add(Links.TABLE, {Links.TITLE: "Flyer draft", Links.URL: "https://www.canva.com/design/x",
                              Links.WORK: ["recT2"], Links.SESSION: ["recProj"]}, "recLFlyer")
    add_note(project, "recNote", "recT2", "recStaff", text="Private detail about the flyer")
    sign_in("admin@example.org")
    client.delete("/api/tasks/recT2")
    body = client.get("/api/projects/recProj").json()
    assert "recLFlyer" in {link["id"] for link in body["links"]}
    assert "recNote" in _ids(project, ActivityLog.TABLE)
    history = client.get("/api/projects/recProj/history").json()["entries"]
    texts = [e["text"] for e in history]
    assert "Private detail about the flyer" not in texts
    assert "added a note to a task that was later deleted" in texts


def test_closed_programs_are_refused(client, sign_in, project):
    project.find(Session.TABLE, "recProj")["fields"][Session.STATUS] = "Complete"
    sign_in("admin@example.org")
    response = client.delete("/api/tasks/recT2")
    assert response.status_code == 409
    assert "recT2" in _ids(project, Work.TABLE)


def test_unknown_task_is_not_found(client, sign_in, project):
    sign_in("admin@example.org")
    assert client.delete("/api/tasks/recNope").status_code == 404


def test_totals_update_everywhere(client, sign_in, project, settings):
    sign_in("admin@example.org")
    card = next(c for c in client.get("/api/projects").json()["projects"] if c["id"] == "recProj")
    assert (card["task_count"], card["overdue"]) == (6, 2)
    client.delete("/api/tasks/recT2")

    card = next(c for c in client.get("/api/projects").json()["projects"] if c["id"] == "recProj")
    assert (card["task_count"], card["overdue"]) == (5, 1)
    detail = client.get("/api/projects/recProj").json()
    assert detail["complete"] == card["complete"] == 20  # 1 of 5 done
    assert "Design flyer" not in client.get("/api/projects/recProj/export.csv").text

    sign_in("staff@example.org")
    mine = client.get("/api/tasks/mine").json()
    assert "recT2" not in {t["id"] for g in mine["groups"].values() for t in g}
    assert mine["counts"]["overdue"] == 1

    turned_on = client.post("/api/me/calendar-feed").json()
    feed = client.get("/calendar/" + turned_on["feed_url"].rsplit("/", 1)[1])
    assert "Design flyer" not in feed.text and "Community outreach" in feed.text


def test_task_page_offers_delete_to_admins_on_open_programs_only(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.get("/api/tasks/recT2").json()["can_delete"] is False
    sign_in("admin@example.org")
    assert client.get("/api/tasks/recT2").json()["can_delete"] is True
    project.find(Session.TABLE, "recProj")["fields"][Session.STATUS] = "Complete"
    assert client.get("/api/tasks/recT2").json()["can_delete"] is False


# --- Skip is unchanged -----------------------------------------------------------------


def test_skip_still_works_for_admins(client, sign_in, project):
    sign_in("admin@example.org")
    assert client.patch("/api/tasks/recT2", json={"status": "Skipped"}).status_code == 200
    assert project.find(Work.TABLE, "recT2")["fields"][Work.STATUS] == "Skipped"
    assert "recT2" in _ids(project, Work.TABLE)


def test_staff_still_cannot_skip(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.patch("/api/tasks/recT2", json={"status": "Skipped"}).status_code == 403
