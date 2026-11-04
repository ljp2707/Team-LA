"""The daily reminder job: what it picks, and that it never sends twice."""

from datetime import date

import pytest

from app.airtable.schema import Reminders
from app.email import gmail
from app.services import reminders
from tests.builders import add_project, add_reminder, add_site, add_task, add_team, add_template

MONDAY = date(2026, 11, 9)


@pytest.fixture
def outbox():
    sent = []

    def send(to, subject, text, html):
        sent.append((to, subject))

    send.sent = sent
    return send


@pytest.fixture
def base(fake):
    add_site(fake)
    add_template(fake)
    add_project(fake, start=date(2026, 12, 6))
    add_task(fake, "recSeven", "Ship equipment to site", date(2026, 11, 16), assigned="recStaff")
    add_task(fake, "recToday", "Confirm pool schedule", MONDAY, assigned="recStaff")
    add_task(fake, "recDone", "Design flyer", MONDAY, status="Done", assigned="recStaff")
    add_task(fake, "recLater", "Day 1 check-in", date(2026, 12, 6), assigned="recAdmin")
    add_task(fake, "recLate", "Order caps", date(2026, 11, 2), assigned="recAdmin")
    return fake


def rows(fake):
    return [r["fields"] for r in fake.rows(Reminders.TABLE)]


def test_seven_day_and_due_date_emails_go_to_the_assignee(base, outbox):
    result = reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=outbox)
    subjects = {s for _, s in outbox.sent}
    assert subjects == {
        "Due in 7 days: Ship equipment to site (Rainier Beach)",
        "Due today: Confirm pool schedule (Rainier Beach)",
    }
    assert all(to == "staff@example.org" for to, _ in outbox.sent)
    assert len(result.sent) == 2
    assert {f[Reminders.STATUS] for f in rows(base)} == {"Sent"}


def test_rerunning_sends_nothing_new(base, outbox):
    reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=outbox)
    again = reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=outbox)
    assert len(outbox.sent) == 2
    assert len(again.already) == 2 and not again.sent
    assert len(rows(base)) == 2


def test_done_tasks_get_no_email(base, outbox):
    reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=outbox)
    assert not any("Design flyer" in s for _, s in outbox.sent)


def test_closed_projects_get_no_email(base, outbox):
    base.find("Session", "recProj")["fields"]["Status"] = "Complete"
    reminders.run_daily(day=MONDAY, dry_run=False, send=outbox)
    assert outbox.sent == []


def test_unassigned_task_falls_back_to_the_team_then_skips(base, outbox):
    base.find("Work", "recToday")["fields"].pop("Assigned To")
    add_team(base, "recProj", "recRole", "recLead")
    reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=outbox)
    assert ("lead@example.org", "Due today: Confirm pool schedule (Rainier Beach)") in outbox.sent

    base.tables["Session Team"] = []
    base.find("Work", "recSeven")["fields"].pop("Assigned To")
    result = reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=outbox)
    skipped = [f for f in rows(base) if f[Reminders.STATUS] == "Skipped"]
    assert skipped and skipped[0][Reminders.ERROR] == "No one assigned"
    assert result.skipped


def test_weekly_digest_only_on_mondays(base, outbox):
    reminders.run_daily(day=date(2026, 11, 10), only="weekly", dry_run=False, send=outbox)
    assert outbox.sent == []
    reminders.run_daily(day=MONDAY, only="weekly", dry_run=False, send=outbox)
    assert sorted(to.lower() for to, _ in outbox.sent) == ["admin@example.org", "staff@example.org"]
    assert all(s == "Your NMU tasks for the week of Nov 9" for _, s in outbox.sent)


def test_digest_lists_overdue_first(base):
    ctx = reminders.Context.load(MONDAY)
    overdue, upcoming = reminders.digest_tasks(ctx, MONDAY)["recAdmin"]
    assert [t.name for t in overdue] == ["Order caps"]
    assert upcoming == []  # Day 1 check-in is more than 7 days away


def test_dry_run_sends_and_writes_nothing(base, outbox):
    before = len(base.writes)
    result = reminders.run_daily(day=MONDAY, dry_run=True, send=outbox)
    assert outbox.sent == []
    assert len(base.writes) == before
    assert result.planned


def test_gmail_failure_is_logged_as_failed_then_retried(base):
    def broken(to, subject, text, html):
        raise gmail.EmailError("Gmail refused the email: quota")

    result = reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=broken)
    assert len(result.failed) == 2
    failed = [f for f in rows(base) if f[Reminders.STATUS] == "Failed"]
    assert len(failed) == 2 and "quota" in failed[0][Reminders.ERROR]

    sent = []
    reminders.run_daily(day=MONDAY, only="auto", dry_run=False, send=lambda *a: sent.append(a))
    assert len(sent) == 2
    assert len(rows(base)) == 2  # the Failed rows were updated, not duplicated
    assert {f[Reminders.STATUS] for f in rows(base)} == {"Sent"}


def test_custom_reminders_go_out_once(base, outbox):
    add_reminder(base, "recCustom", "recLater", "recStaff", MONDAY, note="Bring the roster")
    reminders.run_daily(day=MONDAY, only="custom", dry_run=False, send=outbox)
    reminders.run_daily(day=MONDAY, only="custom", dry_run=False, send=outbox)
    assert outbox.sent == [("staff@example.org", "Reminder: Day 1 check-in (Rainier Beach)")]
    assert base.find(Reminders.TABLE, "recCustom")["fields"][Reminders.STATUS] == "Sent"


def test_finishing_a_task_cancels_its_custom_reminders(base, client, sign_in):
    add_reminder(base, "recCustom", "recSeven", "recStaff", date(2026, 11, 12))
    sign_in("staff@example.org")
    assert client.patch("/api/tasks/recSeven", json={"status": "Done"}).status_code == 200
    assert base.find(Reminders.TABLE, "recCustom")["fields"][Reminders.STATUS] == "Cancelled"


def test_job_exits_non_zero_when_an_email_fails(base, monkeypatch, capsys):
    from jobs import send_reminders

    def broken(*args):
        raise gmail.EmailError("nope")

    monkeypatch.setattr(gmail, "send_email", broken)
    monkeypatch.setattr(reminders.gmail, "send_email", broken)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "REMINDERS_DRY_RUN", False)
    assert send_reminders.main(["--date", "2026-11-09", "--only", "auto"]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_task_panel_shows_sent_scheduled_and_custom(base):
    from app.services.records import load_tasks

    add_reminder(base, "r1", "recLater", "recAdmin", date(2026, 11, 29), kind="7 Days Before", status="Sent")
    add_reminder(base, "r2", "recLater", "recAdmin", date(2026, 11, 20))
    task = next(t for t in load_tasks() if t.id == "recLater")
    panel = reminders.task_panel(task, "recAdmin", date(2026, 11, 4))
    assert panel["automatic"][0]["status"].startswith("Sent")
    assert panel["automatic"][1]["status"] == "Scheduled Dec 6"
    assert panel["custom"][0]["date_text"] == "Fri, Nov 20"
