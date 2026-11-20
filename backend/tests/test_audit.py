"""F34: the audit trail of admin actions (Audit Log table)."""

import logging

import pytest

from app import audit
from app.airtable import client as airtable
from app.airtable.schema import AuditLog
from app.email import gmail
from tests.builders import standard_project


def _audit_rows(fake):
    return [r["fields"] for r in fake.rows(AuditLog.TABLE)]


def test_admin_change_writes_one_row(client, sign_in, fake):
    sign_in("admin@example.org")
    response = client.patch("/api/users/recStaff", json={"first_name": "Samuel"})
    assert response.status_code == 200
    [row] = _audit_rows(fake)
    assert row[AuditLog.ACTION] == "PATCH /api/users/{user_id}"
    assert row[AuditLog.ACTOR] == "recAdmin"
    assert row[AuditLog.TARGET] == "user_id=recStaff"
    assert row[AuditLog.STATUS] == 200
    assert row[AuditLog.REQUEST_ID] == response.headers["X-Request-ID"]
    assert row[AuditLog.WHEN] == "2026-11-04T17:00:00+00:00"


def test_no_body_names_or_emails_in_the_row(client, sign_in, fake):
    sign_in("admin@example.org")
    client.post("/api/users", json={"first_name": "Secret", "last_name": "Person", "email": "secret.person@example.org",
                                    "access_level": "Staff", "role_ids": []})
    [row] = _audit_rows(fake)
    text = " ".join(str(v) for v in row.values())
    assert "Secret" not in text and "secret.person" not in text and "@" not in text


def test_reads_are_not_audited(client, sign_in, fake):
    sign_in("admin@example.org")
    assert client.get("/api/users").status_code == 200
    assert _audit_rows(fake) == []


def test_refused_and_failed_changes_are_not_audited(client, sign_in, fake):
    sign_in("admin@example.org")
    assert client.patch("/api/users/recNobody", json={"first_name": "X"}).status_code == 404
    assert client.delete("/api/users/recAdmin").status_code == 409  # Own access
    assert _audit_rows(fake) == []


def test_staff_changes_are_not_audited(client, sign_in, fake):
    """Only admin actions: everyday task updates are in the project history instead."""
    standard_project(fake)
    sign_in("staff@example.org")
    assert client.patch("/api/tasks/recT2", json={"status": "In Progress"}).status_code == 200
    assert _audit_rows(fake) == []


def test_real_nudge_is_audited(client, sign_in, fake, settings, monkeypatch):
    settings(REMINDERS_DRY_RUN=False)
    monkeypatch.setattr(gmail, "send_email", lambda *args: None)
    standard_project(fake)
    sign_in("admin@example.org")
    assert client.post("/api/tasks/recT2/nudge", json={"message": ""}).status_code == 200
    assert [r[AuditLog.ACTION] for r in _audit_rows(fake)] == ["POST /api/tasks/{task_id}/nudge"]


def test_real_day_one_move_is_audited(client, sign_in, fake):
    standard_project(fake)
    sign_in("admin@example.org")
    response = client.post("/api/projects/recProj/move-day-one", json={"new_day_one": "2026-11-29"})
    assert response.status_code == 200
    assert [r[AuditLog.ACTION] for r in _audit_rows(fake)] == ["POST /api/projects/{project_id}/move-day-one"]


def test_failed_audit_write_keeps_the_action_and_logs_it(client, sign_in, fake, monkeypatch, caplog):
    real_create = fake.create_records

    def no_audit(name, rows, typecast=False):
        if name == AuditLog.TABLE:
            raise ConnectionError("Airtable down")
        return real_create(name, rows, typecast)

    monkeypatch.setattr(airtable, "create_records", no_audit)
    sign_in("admin@example.org")
    with caplog.at_level(logging.ERROR, logger="app.security.events"):
        assert client.patch("/api/users/recStaff", json={"first_name": "Samuel"}).status_code == 200
    assert "audit_write_failed" in caplog.text and "PATCH /api/users/{user_id}" in caplog.text
    assert "recAdmin" in caplog.text


# --- Append only ---------------------------------------------------------------------------


def test_audit_rows_cannot_be_edited(fake):
    row = fake.add(AuditLog.TABLE, {AuditLog.ACTION: "POST /api/roles"})
    with pytest.raises(ValueError, match="append only"):
        airtable.update_records(AuditLog.TABLE, [{"id": row["id"], "fields": {AuditLog.ACTION: "nothing"}}])


def test_audit_rows_cannot_be_deleted(fake):
    row = fake.add(AuditLog.TABLE, {AuditLog.ACTION: "POST /api/roles"})
    with pytest.raises(ValueError, match="append only"):
        airtable.delete_records(AuditLog.TABLE, [row["id"]])


def test_real_client_refuses_too():
    """The guard is in the real client, before any request to Airtable."""
    from importlib import reload

    import app.airtable.client as real

    fresh = reload(real)  # The real functions, not the test fakes
    try:
        with pytest.raises(ValueError, match="append only"):
            fresh.update_records(AuditLog.TABLE, [{"id": "recA", "fields": {}}])
        with pytest.raises(ValueError, match="append only"):
            fresh.delete_records(AuditLog.TABLE, ["recA"])
    finally:
        reload(real)


def test_erasing_someone_does_not_touch_the_audit_log(client, sign_in, fake):
    sign_in("admin@example.org")
    assert client.post("/api/users/recGone/erase").status_code == 200
    assert not fake.writes_to(AuditLog.TABLE, "update") and not fake.writes_to(AuditLog.TABLE, "delete")


def test_labels():
    assert audit.label("PATCH /api/users/{user_id}") == "Changed a person"
    assert audit.label("POST /api/something/new") == "POST /api/something/new"
