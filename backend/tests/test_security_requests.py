"""CSRF origin check, headers on every response, request IDs, safe errors and hosts.

The controls live in backend/app/security.py and app/config.py.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.security import CONTENT_SECURITY_POLICY, ERROR_MESSAGE
from tests.builders import standard_project

STRONG_SECRET = "s" * 40
FRONTEND = "http://localhost:5173"


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


@pytest.fixture
def bare_client():
    """A client that sends no Origin header, unlike the usual one."""
    return TestClient(app, follow_redirects=False)


def _post_note(client, **headers):
    return client.post("/api/tasks/recT2/notes", json={"text": "hello"}, headers=headers)


# --- CSRF: changes must come from our own site --------------------------------------


def test_change_from_another_website_is_refused(client, sign_in, project):
    sign_in("staff@example.org")
    before = len(project.writes)
    response = _post_note(client, Origin="https://evil.example")
    assert response.status_code == 403
    assert "another website" in response.json()["detail"]
    assert len(project.writes) == before


def test_change_from_the_frontend_is_allowed(client, sign_in, project):
    sign_in("staff@example.org")
    assert _post_note(client, Origin=FRONTEND).status_code == 201


def test_change_from_the_app_url_is_allowed(client, sign_in, project):
    sign_in("staff@example.org")
    assert _post_note(client, Origin="http://localhost:8000").status_code == 201


def test_referer_is_used_when_origin_is_missing(bare_client, project):
    _sign_in_bare(bare_client)
    assert _post_note(bare_client, Referer=f"{FRONTEND}/tasks/recT2").status_code == 201
    assert _post_note(bare_client, Referer="https://evil.example/page").status_code == 403


def test_change_with_no_origin_or_referer_is_refused(bare_client, project):
    _sign_in_bare(bare_client)
    assert _post_note(bare_client).status_code == 403


def test_null_origin_is_refused(client, sign_in, project):
    """Sandboxed frames and some redirects send "null"."""
    sign_in("staff@example.org")
    assert _post_note(client, Origin="null").status_code == 403


def test_lookalike_origin_is_refused(client, sign_in, project):
    sign_in("staff@example.org")
    assert _post_note(client, Origin="http://localhost:5173.evil.example").status_code == 403
    assert _post_note(client, Origin="https://localhost:5173").status_code == 403


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_every_changing_method_is_checked(client, sign_in, project, method):
    sign_in("admin@example.org")
    response = client.request(method, "/api/tasks/recT2", json={}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_sign_out_from_another_website_is_refused(client, sign_in):
    sign_in("staff@example.org")
    assert client.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/me").status_code == 200  # Still signed in


def test_sign_out_goes_home_on_the_same_site(client, sign_in):
    """A redirect to another address would be blocked by the CSP's form-action 'self'."""
    sign_in("staff@example.org")
    response = client.post("/auth/logout")
    assert response.status_code == 303 and response.headers["location"] == "/"


def test_reading_is_not_checked(client, sign_in, project):
    """GET never changes anything, and other sites cannot read the answer anyway."""
    sign_in("staff@example.org")
    assert client.get("/api/tasks/recT2", headers={"Origin": "https://evil.example"}).status_code == 200


def _sign_in_bare(bare_client):
    """Sign in with a client that has no default Origin. Sign-in itself is a GET."""
    from app.auth.google import oauth

    async def fake_token(request):
        return {"userinfo": {"email": "staff@example.org", "email_verified": True}}

    original = oauth.google.authorize_access_token
    oauth.google.authorize_access_token = fake_token
    try:
        assert bare_client.get("/auth/callback").status_code in (302, 303)
    finally:
        oauth.google.authorize_access_token = original


# --- Headers on every response, errors included ---------------------------------------


def _assert_security_headers(response):
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in response.headers  # Enforced by default (F28)
    assert len(response.headers["x-request-id"]) == 32


def test_headers_on_a_refused_host(client):
    _assert_security_headers(client.get("/api/health", headers={"host": "evil.example"}))


def test_headers_on_an_oversized_request(client):
    response = client.post("/api/tasks/recT2/notes", content=b"x" * (3 * 1024 * 1024),
                           headers={"content-type": "application/json"})
    assert response.status_code == 413
    _assert_security_headers(response)


def test_headers_on_not_found_and_not_signed_in(client):
    _assert_security_headers(client.get("/api/nothing-here"))
    _assert_security_headers(client.get("/api/me"))


def test_headers_on_a_csrf_refusal(client):
    _assert_security_headers(client.post("/auth/logout", headers={"Origin": "https://evil.example"}))


def test_hsts_includes_subdomains_in_production(client, settings):
    settings(ENV="production")
    assert client.get("/api/health").headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_csp_allows_only_what_the_app_loads():
    assert "'unsafe-inline'" not in CONTENT_SECURITY_POLICY
    assert "'unsafe-eval'" not in CONTENT_SECURITY_POLICY
    for directive in ("default-src 'self'", "script-src 'self'", "connect-src 'self'", "object-src 'none'",
                      "frame-ancestors 'none'", "base-uri 'self'",
                      "form-action 'self' https://accounts.google.com"):
        assert directive in CONTENT_SECURITY_POLICY


# --- Cache-Control: personal data is never cached -------------------------------------


@pytest.mark.parametrize("path", ["/api/me", "/api/projects", "/api/tasks/mine", "/api/users"])
def test_personal_api_answers_are_not_cached(client, sign_in, project, path):
    sign_in("admin@example.org")
    assert client.get(path).headers["cache-control"] == "no-store"


def test_sign_in_answers_are_not_cached(client):
    assert client.get("/auth/denied").headers["cache-control"] == "no-store"


def test_errors_are_not_cached(client):
    assert client.get("/api/me").headers["cache-control"] == "no-store"  # 401


@pytest.mark.parametrize("path", ["/api/health", "/api/public/about"])
def test_public_answers_may_be_cached(client, path):
    assert "cache-control" not in client.get(path).headers


# --- Request IDs and unexpected errors ------------------------------------------------


def test_every_response_has_its_own_request_id(client):
    first = client.get("/api/health").headers["x-request-id"]
    second = client.get("/api/health").headers["x-request-id"]
    assert first != second


def test_request_id_cannot_be_chosen_by_the_caller(client):
    response = client.get("/api/health", headers={"X-Request-ID": "attacker-chosen-id"})
    assert response.headers["x-request-id"] != "attacker-chosen-id"


@pytest.fixture
def crash(monkeypatch):
    """Make the home page stats crash with a message that must never reach the browser."""

    def boom(world):
        raise RuntimeError("secret-detail-from-airtable")

    monkeypatch.setattr("app.routers.public.season_stats", boom)


def test_crash_returns_a_plain_message_and_request_id(client, crash, caplog):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = client.get("/api/public/season-stats")
    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": ERROR_MESSAGE, "request_id": response.headers["x-request-id"]}
    assert "secret-detail" not in response.text and "Traceback" not in response.text
    # The log has the details and the same ID, so the team can find it.
    assert body["request_id"] in caplog.text
    assert "secret-detail-from-airtable" in caplog.text


def test_crash_response_still_has_security_headers(client, crash):
    _assert_security_headers(client.get("/api/public/season-stats"))


def test_crash_is_plain_in_production_too(client, crash, settings):
    settings(ENV="production")
    response = client.get("/api/public/season-stats")
    assert response.status_code == 500 and response.json()["detail"] == ERROR_MESSAGE


def test_crash_log_hides_calendar_tokens(client, monkeypatch, caplog):
    def boom(world, token):
        raise RuntimeError("feed failed")

    monkeypatch.setattr("app.services.calendar_feed.user_for_token", boom)
    token = "A" * 43
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        assert client.get(f"/calendar/{token}.ics").status_code == 500
    assert "/calendar/[redacted].ics" in caplog.text
    assert token not in caplog.text


# --- Hosts -----------------------------------------------------------------------------


def _production(**values) -> Settings:
    return Settings(_env_file=None, ENV="production", APP_URL="https://team.example.org",
                    FRONTEND_URL="https://team.example.org", SESSION_SECRET=STRONG_SECRET, **values)


def test_production_answers_only_its_own_hosts():
    hosts = _production().allowed_hosts
    assert hosts == ["healthcheck.railway.app", "team.example.org"]


def test_extra_hosts_can_be_added_for_a_custom_domain():
    hosts = _production(ALLOWED_HOSTS="launches.nomoreunder.org, www.launches.nomoreunder.org").allowed_hosts
    assert "launches.nomoreunder.org" in hosts and "www.launches.nomoreunder.org" in hosts


def test_localhost_is_allowed_in_development():
    hosts = Settings(_env_file=None).allowed_hosts
    assert {"localhost", "127.0.0.1", "testserver"} <= set(hosts)


def test_docker_image_reads_forwarded_allow_ips():
    from pathlib import Path

    command = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    assert "--proxy-headers" in command
    assert '--forwarded-allow-ips=\\"${FORWARDED_ALLOW_IPS:-*}\\"' in command
