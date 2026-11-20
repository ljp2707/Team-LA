"""Rate limits, hosts, logout, log masking, file checks, notes and sessions.

Findings F5, F8, F10, F11, F13, F14, F15 and F16 in docs/security/findings.md.
"""

import io
import logging
from datetime import date
from pathlib import Path

import pytest

from app.airtable.schema import ActivityLog, Users
from app.email import gmail
from app.services import reminders
from app.services.links import read_upload
from tests.builders import add_note, add_project, add_site, add_task, add_template, standard_project

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


# --- F14: proxy headers and allowed hosts --------------------------------------------


def test_unknown_host_is_refused(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_app_and_railway_health_check_hosts_are_allowed(client):
    for host in ("localhost:8000", "127.0.0.1", "healthcheck.railway.app", "testserver"):
        assert client.get("/api/health", headers={"host": host}).status_code == 200, host


def test_docker_image_trusts_railways_proxy_headers():
    command = (REPO_ROOT / "Dockerfile").read_text()
    assert "--proxy-headers" in command and "--forwarded-allow-ips" in command


# --- F5: rate limits -------------------------------------------------------------------


def test_sign_in_is_rate_limited_per_address(client):
    codes = [client.get("/auth/login", follow_redirects=False).status_code for _ in range(11)]
    assert 429 not in codes[:10]
    assert codes[10] == 429


def test_rate_limited_answer_says_when_to_retry(client):
    for _ in range(10):
        client.get("/auth/login", follow_redirects=False)
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


def test_limits_reset_after_the_window(client, advance):
    for _ in range(10):
        client.get("/auth/login", follow_redirects=False)
    assert client.get("/auth/login", follow_redirects=False).status_code == 429
    advance(seconds=61)
    assert client.get("/auth/login", follow_redirects=False).status_code != 429


def test_calendar_feed_is_rate_limited(client):
    codes = [client.get("/calendar/" + "a" * 43 + ".ics").status_code for _ in range(61)]
    assert codes[:60] == [404] * 60 and codes[60] == 429


def test_writes_are_rate_limited_per_person(client, sign_in, project):
    sign_in("staff@example.org")
    body = {"send_on": "2026-11-20"}
    codes = [client.post("/api/tasks/recT2/reminders", json=body).status_code for _ in range(61)]
    assert 429 not in codes[:60] and codes[60] == 429
    # Someone else is not held up by Staff's limit.
    sign_in("admin@example.org")
    assert client.post("/api/tasks/recT2/reminders", json=body).status_code == 201


# --- F8: logout needs a POST -------------------------------------------------------------


def test_get_logout_no_longer_signs_you_out(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.get("/auth/logout", follow_redirects=False).status_code in (302, 303)
    assert client.get("/api/me").status_code == 200


def test_post_logout_signs_you_out(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.post("/auth/logout", follow_redirects=False).status_code == 303
    assert client.get("/api/me").status_code == 401


# --- F13: no full email addresses in logs ------------------------------------------------


def test_dry_run_email_log_masks_the_address(caplog, settings):
    settings(REMINDERS_DRY_RUN=True)
    with caplog.at_level(logging.INFO):
        gmail.send_email("mary.smith@example.org", "Subject", "text", "<p>html</p>")
    assert "mary.smith@example.org" not in caplog.text
    assert "m***@example.org" in caplog.text


def test_reminder_job_labels_mask_addresses(fake):
    add_site(fake)
    add_template(fake)
    add_project(fake, start=date(2026, 12, 6))
    add_task(fake, "recToday", "Confirm pool schedule", date(2026, 11, 9), assigned="recStaff")
    result = reminders.run_daily(day=date(2026, 11, 9), only="auto", dry_run=True)
    assert result.planned
    assert not any("staff@example.org" in label for label in result.planned)
    assert any("s***@example.org" in label for label in result.planned)


# --- F10: file content must match its extension -------------------------------------------


class _Upload:
    """Just enough of FastAPI's UploadFile for read_upload."""

    def __init__(self, name, content):
        self.filename = name
        self.file = io.BytesIO(content)


@pytest.mark.parametrize(
    "name,content",
    [
        ("photo.png", b"\x89PNG\r\n\x1a\n" + b"x" * 20),
        ("photo.jpg", b"\xff\xd8\xff\xe0" + b"x" * 20),
        ("anim.gif", b"GIF89a" + b"x" * 20),
        ("pic.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"x" * 20),
        ("pic.heic", b"\x00\x00\x00\x18ftypheic" + b"x" * 20),
        ("doc.pdf", b"%PDF-1.7\n" + b"x" * 20),
        ("doc.docx", b"PK\x03\x04" + b"x" * 20),
        ("old.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"x" * 20),
        ("notes.txt", "Café, déjà vu".encode("cp1252")),
        ("list.csv", b"name,email\nMary,m@example.org\n"),
    ],
)
def test_real_files_are_accepted(name, content):
    assert read_upload(_Upload(name, content))[0] == name


@pytest.mark.parametrize(
    "name,content",
    [
        ("report.pdf", b"MZ\x90\x00\x03\x00\x00\x00" + b"x" * 20),  # A Windows program
        ("photo.png", b"%PDF-1.7\n"),
        ("sheet.xlsx", b"\x7fELF\x02\x01\x01\x00" + b"x" * 20),
        ("notes.txt", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00"),  # Binary, not text
    ],
)
def test_files_whose_content_does_not_match_are_refused(name, content):
    with pytest.raises(ValueError, match="does not look like"):
        read_upload(_Upload(name, content))


# --- F11: only the author or an admin shares an Internal note ------------------------------


def test_staff_cannot_share_someone_elses_note(client, sign_in, project):
    add_note(project, "recAdminNote", "recT2", "recAdmin", "staff only")
    sign_in("staff@example.org")
    notes = client.get("/api/tasks/recT2").json()["notes"]
    note = next(n for n in notes if n["id"] == "recAdminNote")
    assert note["can_share"] is False
    assert client.patch("/api/notes/recAdminNote", json={"visibility": "Shared"}).status_code == 403


def test_author_can_share_their_own_note(client, sign_in, project):
    add_note(project, "recStaffNote", "recT2", "recStaff", "for the partner")
    sign_in("staff@example.org")
    notes = client.get("/api/tasks/recT2").json()["notes"]
    note = next(n for n in notes if n["id"] == "recStaffNote")
    assert note["can_share"] is True
    assert client.patch("/api/notes/recStaffNote", json={"visibility": "Shared"}).status_code == 200


def test_admin_can_share_anyones_note(client, sign_in, project):
    add_note(project, "recStaffNote", "recT2", "recStaff", "for the partner")
    sign_in("admin@example.org")
    assert client.patch("/api/notes/recStaffNote", json={"visibility": "Shared"}).status_code == 200


# --- F16: a note with no launch is hidden from partners -------------------------------------


def test_partner_cannot_touch_a_note_without_a_launch(client, sign_in, project):
    project.add(
        Users.TABLE,
        {Users.EMAIL: "p2@example.org", Users.STATUS: "Active", Users.ACCESS_LEVEL: "Partner", Users.FIRST_NAME: "Pat"},
        "recP2",
    )
    project.add(
        ActivityLog.TABLE,
        {ActivityLog.TYPE: "Note", ActivityLog.TEXT: "loose", ActivityLog.VISIBILITY: "Shared", ActivityLog.AUTHOR: ["recP2"]},
        "recLoose",
    )
    sign_in("p2@example.org")
    assert client.delete("/api/notes/recLoose").status_code == 404
    assert client.patch("/api/notes/recLoose", json={"visibility": "Internal"}).status_code == 404


# --- F15: sessions expire when idle, and after a week at most ------------------------------


def test_session_ends_after_a_day_idle(client, sign_in, project, advance):
    sign_in("staff@example.org")
    advance(hours=25)
    assert client.get("/api/me").status_code == 401


def test_activity_keeps_the_session_alive(client, sign_in, project, advance):
    sign_in("staff@example.org")
    for _ in range(3):
        advance(hours=20)
        assert client.get("/api/me").status_code == 200


def test_session_ends_a_week_after_sign_in_even_when_active(client, sign_in, project, advance):
    sign_in("staff@example.org")
    for _ in range(7):
        advance(hours=23)
        assert client.get("/api/me").status_code == 200
    advance(hours=23)  # 8 x 23 hours is more than 7 days since sign in
    assert client.get("/api/me").status_code == 401


def test_idle_timeout_is_a_setting(client, sign_in, project, advance, settings):
    settings(SESSION_IDLE_HOURS=2)
    sign_in("staff@example.org")
    advance(hours=3)
    assert client.get("/api/me").status_code == 401
