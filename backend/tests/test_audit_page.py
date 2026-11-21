"""F35: the read-only Audit page, GET /api/audit."""

import pytest

from app.airtable.schema import AuditLog
from app.routers import audit_log
from tests.builders import standard_project


def _row(fake, when, action="PATCH /api/users/{user_id}", actor="recAdmin", target="user_id=recStaff"):
    fake.add(AuditLog.TABLE, {AuditLog.ACTION: action, AuditLog.WHEN: when, AuditLog.ACTOR: actor,
                              AuditLog.TARGET: target, AuditLog.STATUS: 200, AuditLog.REQUEST_ID: "abc"})


def test_newest_first_with_names(client, sign_in, fake):
    _row(fake, "2026-11-01T10:00:00+00:00")
    _row(fake, "2026-11-03T10:00:00+00:00", action="POST /api/roles", target="")
    sign_in("admin@example.org")
    body = client.get("/api/audit").json()
    assert [e["label"] for e in body["entries"]] == ["Added a role", "Changed a person"]
    first = body["entries"][1]
    assert first["actor_name"] == "Ada"  # Seeded with a first name only
    assert first["target"] == "Sam"
    assert first["action"] == "PATCH /api/users/{user_id}" and first["request_id"] == "abc"
    assert body["actors"] == [{"id": "recAdmin", "name": first["actor_name"]}]


def test_task_and_program_names(client, sign_in, fake):
    standard_project(fake)
    _row(fake, "2026-11-03T10:00:00+00:00", action="DELETE /api/tasks/{task_id}", target="task_id=recT2")
    _row(fake, "2026-11-03T11:00:00+00:00", action="POST /api/projects/{project_id}/archive", target="project_id=recGone")
    sign_in("admin@example.org")
    targets = [e["target"] for e in client.get("/api/audit").json()["entries"]]
    assert targets == ["recGone", "Design flyer"]  # A deleted record keeps its ID


def test_days_filter(client, sign_in, fake):
    _row(fake, "2026-10-01T10:00:00+00:00")  # 34 days before the test clock
    _row(fake, "2026-11-03T10:00:00+00:00")
    sign_in("admin@example.org")
    assert len(client.get("/api/audit").json()["entries"]) == 1
    assert len(client.get("/api/audit?days=60").json()["entries"]) == 2


def test_actor_filter(client, sign_in, fake):
    _row(fake, "2026-11-03T10:00:00+00:00", actor="recAdmin")
    _row(fake, "2026-11-03T11:00:00+00:00", actor="recAdmin2")
    sign_in("admin@example.org")
    entries = client.get("/api/audit?actor=recAdmin2").json()["entries"]
    assert [e["actor_id"] for e in entries] == ["recAdmin2"]


@pytest.mark.parametrize("query", ["actor=not-an-id", "actor=rec1%27%2B1", "days=0", "days=99999"])
def test_bad_filters_are_refused(client, sign_in, query):
    sign_in("admin@example.org")
    assert client.get(f"/api/audit?{query}").status_code == 422


def test_erased_person_shows_as_former_team_member(client, sign_in, fake):
    _row(fake, "2026-11-03T10:00:00+00:00", actor="recGone", target="")
    sign_in("admin@example.org")
    assert client.post("/api/users/recGone/erase").status_code == 200
    entries = client.get("/api/audit").json()["entries"]
    old = next(e for e in entries if e["actor_id"] == "recGone")
    assert old["actor_name"].startswith("Former")


def test_bad_rows_are_skipped(client, sign_in, fake):
    fake.add(AuditLog.TABLE, {AuditLog.ACTION: "POST /api/roles"})  # No time
    fake.add(AuditLog.TABLE, {AuditLog.ACTION: "POST /api/roles", AuditLog.WHEN: "yesterday"})
    sign_in("admin@example.org")
    assert client.get("/api/audit").json()["entries"] == []


def test_long_history_is_cut_and_flagged(client, sign_in, fake, monkeypatch):
    monkeypatch.setattr(audit_log, "MAX_ENTRIES", 3)
    for hour in range(5):
        _row(fake, f"2026-11-03T1{hour}:00:00+00:00")
    sign_in("admin@example.org")
    body = client.get("/api/audit").json()
    assert len(body["entries"]) == 3 and body["more"] is True
    assert body["entries"][0]["when"].startswith("2026-11-03T14")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_there_is_no_way_to_change_it(client, sign_in, method):
    sign_in("admin@example.org")
    assert client.request(method, "/api/audit").status_code == 405


def test_reading_it_is_not_audited(client, sign_in, fake):
    sign_in("admin@example.org")
    client.get("/api/audit")
    assert fake.rows(AuditLog.TABLE) == []
