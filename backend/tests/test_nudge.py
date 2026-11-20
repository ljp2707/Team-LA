"""The admin Nudge button: one reminder email now, on top of the automatic ones.

Standard project: Design flyer (recT2) is open and assigned to Sam (recStaff).
Today is Wed Nov 4, 2026, 9 AM Pacific.
"""

import pytest

from app.airtable.schema import ActivityLog, Reminders, Session, Users, Work
from app.email import gmail
from app.rate_limit import NUDGES_PER_HOUR
from tests.builders import add_task, standard_project


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


@pytest.fixture
def outbox(monkeypatch, settings):
    """Real sending (not dry run), into a list instead of Gmail."""
    settings(REMINDERS_DRY_RUN=False)
    sent = []
    monkeypatch.setattr(gmail, "send_email", lambda to, subject, text, html: sent.append((to, subject, text, html)))
    return sent


def _nudge(client, task="recT2", message=""):
    return client.post(f"/api/tasks/{task}/nudge", json={"message": message})


def _nudge_rows(fake):
    return [r["fields"] for r in fake.rows(Reminders.TABLE) if r["fields"].get(Reminders.KIND) == "Nudge"]


# --- Who may nudge ---------------------------------------------------------------------


def test_admin_can_nudge(client, sign_in, project, outbox):
    sign_in("admin@example.org")
    response = _nudge(client)
    assert response.status_code == 200
    assert response.json()["message"] == "Reminder sent to Sam."
    assert [(to, subject) for to, subject, *_ in outbox] == [
        ("staff@example.org", "Reminder from Ada: Design flyer (Rainier Beach)")
    ]


@pytest.mark.parametrize("email", ["staff@example.org", "viewer@example.org", "partner@example.org"])
def test_every_other_role_gets_403(client, sign_in, project, outbox, email):
    sign_in(email)
    assert _nudge(client).status_code == 403
    assert outbox == []


def test_admin_in_staff_view_gets_403(client, sign_in, project, outbox):
    sign_in("admin@example.org")
    client.post("/api/me/view", json={"view": "staff"})
    assert _nudge(client).status_code == 403


def test_signed_out_gets_401(client, project):
    assert _nudge(client).status_code == 401


# --- Which tasks -----------------------------------------------------------------------


@pytest.mark.parametrize("status", ["Done", "Skipped"])
def test_finished_tasks_are_refused(client, sign_in, project, outbox, status):
    project.find(Work.TABLE, "recT2")["fields"][Work.STATUS] = status
    sign_in("admin@example.org")
    assert _nudge(client).status_code == 409
    assert outbox == []


def test_task_with_nobody_active_is_refused(client, sign_in, project, outbox, fake):
    fake.find(Users.TABLE, "recStaff")["fields"][Users.STATUS] = "Inactive"
    sign_in("admin@example.org")
    assert _nudge(client).status_code == 409
    assert _nudge(client, "recT6").status_code == 409  # nobody assigned at all


def test_closed_program_is_refused(client, sign_in, project, outbox):
    project.find(Session.TABLE, "recProj")["fields"][Session.STATUS] = "Complete"
    sign_in("admin@example.org")
    assert _nudge(client).status_code == 409


def test_task_page_shows_the_button_only_when_it_would_work(client, sign_in, project):
    sign_in("admin@example.org")
    assert client.get("/api/tasks/recT2").json()["can_nudge"] is True
    assert client.get("/api/tasks/recT1").json()["can_nudge"] is False  # Done
    assert client.get("/api/tasks/recT6").json()["can_nudge"] is False  # nobody on it
    sign_in("staff@example.org")
    assert client.get("/api/tasks/recT2").json()["can_nudge"] is False


# --- Limits ----------------------------------------------------------------------------


def test_same_person_once_per_task_per_day(client, sign_in, project, outbox, advance):
    sign_in("admin@example.org")
    assert _nudge(client).status_code == 200
    again = _nudge(client)
    assert again.status_code == 429
    assert again.json()["detail"] == (
        "Sam was already nudged about this task in the last day. You can nudge again after 9:00 AM on Nov 5."
    )
    assert len(outbox) == 1
    advance(hours=24, minutes=1)
    sign_in("admin@example.org")  # A day idle ends the session, so sign in again
    assert _nudge(client).status_code == 200
    assert len(outbox) == 2


def test_limit_is_per_person(client, sign_in, project, outbox, fake):
    sign_in("admin@example.org")
    assert _nudge(client).status_code == 200
    fake.find(Work.TABLE, "recT2")["fields"][Work.ASSIGNED_TO] = ["recStaff", "recAdmin"]
    response = _nudge(client)
    assert response.status_code == 200
    assert response.json()["sent"] == ["Ada"] and response.json()["skipped"] == ["Sam"]
    assert [to for to, *_ in outbox] == ["staff@example.org", "Admin@Example.org"]


def test_limit_is_per_task(client, sign_in, project, outbox):
    sign_in("admin@example.org")
    assert _nudge(client, "recT2").status_code == 200
    assert _nudge(client, "recT3").status_code == 200


def test_admin_hourly_cap(client, sign_in, project, outbox):
    for n in range(NUDGES_PER_HOUR):
        add_task(project, f"recN{n}", f"Task {n}", None, assigned="recStaff")
    sign_in("admin@example.org")
    for n in range(NUDGES_PER_HOUR):
        assert _nudge(client, f"recN{n}").status_code == 200
    capped = _nudge(client, "recT3")
    assert capped.status_code == 429
    assert capped.json()["detail"] == "You have sent a lot of nudges this hour. Please try again later."


def test_limit_survives_a_restart(client, sign_in, project, outbox):
    """The daily limit is read from Airtable, not from memory."""
    from app import rate_limit

    sign_in("admin@example.org")
    assert _nudge(client).status_code == 200
    rate_limit.reset()
    assert _nudge(client).status_code == 429


# --- The email ---------------------------------------------------------------------------


def test_email_has_task_program_due_date_link_and_message(client, sign_in, project, outbox):
    sign_in("admin@example.org")
    _nudge(client, message="Please send it to the printer today.")
    _, subject, text, html = outbox[0]
    assert "Design flyer at Rainier Beach" in text
    assert "5 days late" in text or "Due Oct 30" in text or "Oct 30" in text
    assert "http://localhost:8000/tasks/recT2" in text and "http://localhost:8000/tasks/recT2" in html
    assert "Ada wrote: Please send it to the printer today." in text


def test_message_is_escaped(client, sign_in, project, outbox):
    sign_in("admin@example.org")
    _nudge(client, message='<script>alert(1)</script><a href="https://evil.example">x</a>')
    html = outbox[0][3]
    assert "<script>" not in html and '<a href="https://evil.example">' not in html
    assert "&lt;script&gt;" in html


def test_message_over_500_characters_is_refused(client, sign_in, project, outbox):
    sign_in("admin@example.org")
    assert _nudge(client, message="x" * 501).status_code == 422
    assert outbox == []


def test_dry_run_sends_and_writes_nothing(client, sign_in, project, monkeypatch, fake):
    sent = []
    monkeypatch.setattr(gmail, "send_email", lambda *args: sent.append(args))
    sign_in("admin@example.org")
    before = len(fake.writes)
    response = _nudge(client)
    assert response.status_code == 200
    assert response.json()["message"] == "Email is in dry run mode, so nothing was sent."
    assert sent == [] and len(fake.writes) == before


def test_failed_email_is_reported_and_logged(client, sign_in, project, monkeypatch, settings, fake):
    settings(REMINDERS_DRY_RUN=False)

    def broken(*args):
        raise gmail.EmailError("Gmail refused the email: test")

    monkeypatch.setattr(gmail, "send_email", broken)
    sign_in("admin@example.org")
    response = _nudge(client)
    assert response.status_code == 502
    assert response.json()["detail"] == "The reminder was not sent. Gmail refused the email: test"
    assert [(r[Reminders.STATUS], r[Reminders.ERROR]) for r in _nudge_rows(fake)] == [
        ("Failed", "Gmail refused the email: test")
    ]
    assert not [r for r in fake.rows(ActivityLog.TABLE) if r["fields"].get(ActivityLog.TYPE) == "Nudge"]


def test_message_and_address_never_reach_the_log(client, sign_in, project, outbox, caplog):
    sign_in("admin@example.org")
    with caplog.at_level("DEBUG"):
        _nudge(client, message="secret plan for the pool")
    assert "secret plan" not in caplog.text and "staff@example.org" not in caplog.text


# --- History ---------------------------------------------------------------------------


def test_history_entry_and_last_nudged(client, sign_in, project, outbox, fake):
    sign_in("admin@example.org")
    assert client.get("/api/tasks/recT2").json()["last_nudge"] is None
    _nudge(client, message="secret plan for the pool")
    row = next(r["fields"] for r in fake.rows(ActivityLog.TABLE) if r["fields"].get(ActivityLog.TYPE) == "Nudge")
    assert row[ActivityLog.TEXT] == "nudged Sam about Design flyer"
    assert row[ActivityLog.WORK] == ["recT2"] and row[ActivityLog.AUTHOR] == ["recAdmin"]
    assert "secret plan" not in str(row)  # the message is not stored
    assert client.get("/api/tasks/recT2").json()["last_nudge"] == {"by": "Ada", "date_text": "Nov 4"}
    history = client.get("/api/projects/recProj/history").json()["entries"]
    assert any(e["text"] == "nudged Sam about Design flyer" for e in history)
    sent = _nudge_rows(fake)
    assert [(r[Reminders.STATUS], r[Reminders.RECIPIENT]) for r in sent] == [("Sent", ["recStaff"])]


def test_partners_do_not_see_last_nudged(client, sign_in, project, outbox, fake):
    fake.find(Session.TABLE, "recProj")["fields"][Session.PARTNERS] = ["recPartner"]
    fake.find(Work.TABLE, "recT2")["fields"][Work.ASSIGNED_TO] = ["recPartner"]
    sign_in("admin@example.org")
    _nudge(client)
    sign_in("partner@example.org")
    assert client.get("/api/tasks/recT2").json()["last_nudge"] is None
