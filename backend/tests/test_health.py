"""Health checks, sign in, /api/me and frontend serving."""

import subprocess
import sys
from pathlib import Path

import pytest

from app import main
from app.airtable import client as airtable
from app.airtable.schema import ALL_TABLES, Users
from app.auth.google import oauth
from app.config import Settings

# Saved here because conftest.py swaps this function for a fake during tests.
REAL_ALL_RECORDS = airtable.all_records


def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_airtable_health_lists_every_table(client, sign_in):
    sign_in("admin@example.org")
    body = client.get("/api/health/airtable").json()
    assert body["connected"] is True
    assert [t["table"] for t in body["tables"]] == [t.TABLE for t in ALL_TABLES]
    assert body["tables"][0]["count"] == 6


def test_airtable_health_reports_a_failing_table(client, sign_in, monkeypatch):
    sign_in("admin@example.org")
    real_all_records = airtable.all_records

    def fails_on_counts(name, fields=None):
        if fields:  # Only the count requests ask for specific fields
            raise RuntimeError("secret detail")
        return real_all_records(name)

    monkeypatch.setattr(airtable, "all_records", fails_on_counts)
    response = client.get("/api/health/airtable")
    assert response.json()["connected"] is False
    assert "secret detail" not in response.text


def test_admin_signs_in_to_dashboard_ignoring_email_case(client, sign_in):
    response = sign_in("ADMIN@example.org")
    assert response.status_code == 302
    assert response.headers["location"].endswith("/dashboard")

    me = client.get("/api/me").json()
    assert me["view"] == "admin"
    assert me["access_level"] == "Admin"
    assert me["user"]["roles"] == ["Program Manager"]
    assert me["can_switch_view"] is True


def test_staff_signs_in_to_my_tasks(client, sign_in):
    assert sign_in("staff@example.org").headers["location"].endswith("/my-tasks")
    assert client.get("/api/me").json()["can_switch_view"] is False


def test_unknown_and_inactive_people_are_rejected(client, sign_in):
    for email in ("nobody@example.org", "gone@example.org"):
        assert sign_in(email).headers["location"].endswith("/not-authorized")
        assert client.get("/api/me").status_code == 401


def test_unverified_google_email_is_rejected(client, sign_in):
    response = sign_in("admin@example.org", verified=False)
    assert "/not-authorized" in response.headers["location"]
    assert client.get("/api/me").status_code == 401


def test_allowed_domain_is_enforced(client, sign_in, settings):
    settings(ALLOWED_EMAIL_DOMAIN="nomoreunder.org")
    response = sign_in("admin@example.org")
    assert response.headers["location"].endswith("/not-authorized?reason=domain")


def test_logout_clears_the_session(client, sign_in):
    sign_in("admin@example.org")
    response = client.get("/auth/logout")
    assert response.status_code == 302
    assert client.get("/api/me").status_code == 401


def test_deactivating_someone_ends_their_session(client, sign_in, users):
    sign_in("admin@example.org")
    users[0]["fields"][Users.STATUS] = "Inactive"
    assert client.get("/api/me").status_code == 401


def test_demoted_admin_loses_admin_view(client, sign_in, users):
    sign_in("admin@example.org")
    users[0]["fields"][Users.ACCESS_LEVEL] = "Staff"
    assert client.get("/api/me").json()["view"] == "staff"
    assert client.get("/api/archive").status_code == 403


def test_staff_cannot_choose_admin_view(client, sign_in):
    sign_in("staff@example.org")
    assert client.post("/api/me/view", json={"view": "admin"}).status_code == 403
    assert client.post("/api/me/view", json={"view": "owner"}).status_code == 422


def test_dev_switch_lets_staff_use_admin_view(client, sign_in, settings):
    settings(DEV_ALLOW_VIEW_SWITCH=True)
    sign_in("staff@example.org")
    me = client.post("/api/me/view", json={"view": "admin"}).json()
    assert me["view"] == "admin"
    assert me["dev_mode"] is True
    assert client.get("/api/archive").status_code == 200


def test_frontend_fallback_serves_index_but_not_api_paths(
    client, monkeypatch, tmp_path
):
    (tmp_path / "index.html").write_text("<h1>app</h1>")
    (tmp_path / "logo.svg").write_text("<svg></svg>")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret")
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)

    assert "app" in client.get("/my-tasks").text
    assert "svg" in client.get("/logo.svg").text
    assert client.get("/api/nope").status_code == 404
    assert "secret" not in client.get("/..%2Fsecret.txt").text


def test_reminder_job_runs_as_a_dry_run(capsys):
    from jobs import send_reminders

    assert send_reminders.main([]) == 0
    assert "Dry run" in capsys.readouterr().out


def test_reminder_job_module_starts():
    """The cron command itself can start (it prints help without touching Airtable)."""
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "jobs.send_reminders", "--help"],
        cwd=backend,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout


def test_google_callback_without_matching_state_is_rejected(client):
    """Protects against forged sign in links. Uses the real authlib check."""
    response = client.get("/auth/callback?code=forged&state=forged")
    assert response.headers["location"].endswith("/not-authorized?reason=google")
    assert client.get("/api/me").status_code == 401


def test_login_sends_people_to_google_with_our_callback(client, monkeypatch):
    async def fake_metadata():
        return {"authorization_endpoint": "https://accounts.google.com/o/oauth2/auth"}

    monkeypatch.setattr(oauth.google, "load_server_metadata", fake_metadata)
    location = client.get("/auth/login").headers["location"]
    assert location.startswith("https://accounts.google.com/")
    assert "auth%2Fcallback" in location


def test_airtable_reads_every_page_then_uses_the_cache(monkeypatch):
    calls = []

    class FakeTable:
        def iterate(self, fields):
            calls.append(fields)
            yield [{"id": "rec1"}]
            yield [{"id": "rec2"}]

    class FakeBase:
        def table(self, name):
            return FakeTable()

    airtable.clear_cache()
    monkeypatch.setattr(airtable, "get_base", FakeBase)
    assert len(REAL_ALL_RECORDS("Users")) == 2
    assert len(REAL_ALL_RECORDS("Users")) == 2
    assert len(calls) == 1
    airtable.clear_cache()


class _CountingBase:
    """Stands in for get_base: counts downloads, and can hold one open."""

    def __init__(self):
        import threading

        self.calls = 0
        self.release = threading.Event()
        self.release.set()
        self.value = "old"

    def __call__(self):
        return self

    def table(self, name):
        return self

    def iterate(self, fields):
        self.calls += 1
        self.release.wait(5)
        yield [{"id": "rec1", "fields": {"v": self.value}}]


def test_airtable_cache_serves_stale_copy_and_refreshes_in_background(monkeypatch):
    import time

    base = _CountingBase()
    airtable.clear_cache()
    monkeypatch.setattr(airtable, "get_base", base)
    assert REAL_ALL_RECORDS("Users")[0]["fields"]["v"] == "old"
    base.value = "new"
    # Make the copy look 60 seconds old: past fresh, inside stale.
    key = ("Users", ())
    at, records = airtable._cache[key]
    airtable._cache[key] = (at - 60, records)
    assert REAL_ALL_RECORDS("Users")[0]["fields"]["v"] == "old"  # Answered at once
    for _ in range(100):
        if not airtable._in_flight:
            break
        time.sleep(0.01)
    assert REAL_ALL_RECORDS("Users")[0]["fields"]["v"] == "new"
    assert base.calls == 2
    airtable.clear_cache()


def test_airtable_cache_downloads_a_table_once_for_many_readers(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    base = _CountingBase()
    base.release.clear()
    airtable.clear_cache()
    monkeypatch.setattr(airtable, "get_base", base)
    with ThreadPoolExecutor(5) as pool:
        futures = [pool.submit(REAL_ALL_RECORDS, "Users") for _ in range(5)]
        base.release.set()
        results = [f.result() for f in futures]
    assert all(len(r) == 1 for r in results)
    assert base.calls == 1
    airtable.clear_cache()


def test_airtable_write_drops_copies_and_downloads_started_before_it(monkeypatch):
    import threading

    base = _CountingBase()
    airtable.clear_cache()
    monkeypatch.setattr(airtable, "get_base", base)
    REAL_ALL_RECORDS("Users")
    base.release.clear()
    key = ("Users", ())
    at, records = airtable._cache[key]
    airtable._cache[key] = (at - 60, records)
    REAL_ALL_RECORDS("Users")  # Starts a background refresh, held open
    base.value = "after write"
    airtable.clear_cache()  # A write lands while that refresh is still running
    reader = threading.Thread(target=lambda: results.append(REAL_ALL_RECORDS("Users")))
    results = []
    reader.start()
    base.release.set()
    reader.join(5)
    assert results[0][0]["fields"]["v"] == "after write"
    assert airtable._cache[key][1][0]["fields"]["v"] == "after write"
    airtable.clear_cache()


def test_dev_login_signs_in_without_google(client, settings):
    settings(DEV_LOGIN_EMAIL="staff@example.org")
    assert client.get("/auth/login").headers["location"].endswith("/my-tasks")
    assert client.get("/api/me").json()["access_level"] == "Staff"


def test_dev_login_still_requires_an_active_airtable_user(client, settings):
    settings(DEV_LOGIN_EMAIL="gone@example.org")
    assert client.get("/auth/login").headers["location"].endswith("/not-authorized")
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "values",
    [
        {"ENV": "production", "SESSION_SECRET": "x" * 40},
        {"APP_URL": "https://nmu.up.railway.app"},
    ],
)
def test_dev_login_refuses_to_run_outside_localhost(values):
    with pytest.raises(ValueError):
        Settings(_env_file=None, DEV_LOGIN_EMAIL="a@example.org", **values)


def test_every_response_has_security_headers(client):
    response = client.get("/api/public/about")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_airtable_write_patches_its_table_and_drops_tables_that_follow_it(monkeypatch):
    base = _CountingBase()
    airtable.clear_cache()
    monkeypatch.setattr(airtable, "get_base", base)
    for name in ("Session", "Work", "Steps"):
        REAL_ALL_RECORDS(name)
    airtable._cache[("Session", ())] = (airtable._cache[("Session", ())][0], [
        {"id": "recA", "fields": {"v": "a"}},
        {"id": "recB", "fields": {"v": "b"}},
    ])
    airtable._after_write("Session", changed=[{"id": "recB", "fields": {"v": "b2"}}, {"id": "recC", "fields": {"v": "c"}}])
    assert [r["fields"]["v"] for r in REAL_ALL_RECORDS("Session")] == ["a", "b2", "c"]
    assert ("Work", ()) not in airtable._cache  # Due dates follow the Session's Day 1
    assert ("Steps", ()) in airtable._cache  # Not affected, kept
    airtable._after_write("Session", deleted_ids=["recA"])
    assert [r["id"] for r in REAL_ALL_RECORDS("Session")] == ["recB", "recC"]
    airtable._after_write("Session")  # A write that failed part way
    assert ("Session", ()) not in airtable._cache
    airtable.clear_cache()
