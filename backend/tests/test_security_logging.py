"""F36: one-line JSON logs in production, request IDs on every line, and security events."""

import json
import logging

import pytest

from app import logging_setup
from app.airtable.schema import Users
from app.auth.google import oauth
from app.logging_setup import JsonFormatter, TextFormatter, request_id_var
from app.security_events import clean, security_event


def _record(message="hello %s", args=("world",), **extra):
    record = logging.LogRecord("app.test", logging.WARNING, __file__, 1, message, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _events(caplog, name=None):
    found = [r for r in caplog.records if getattr(r, "event", None)]
    return [r for r in found if name is None or r.event == name]


# --- The format --------------------------------------------------------------------------


def test_json_line_has_the_basic_fields():
    line = JsonFormatter().format(_record())
    assert "\n" not in line
    data = json.loads(line)
    assert data["level"] == "WARNING" and data["logger"] == "app.test" and data["message"] == "hello world"
    assert data["time"].endswith("Z")


def test_line_breaks_cannot_fake_a_second_log_line():
    line = JsonFormatter().format(_record("bad %s", ("one\n{\"level\": \"INFO\"}",)))
    assert "\n" not in line and json.loads(line)["message"].startswith("bad one\n")


def test_request_id_is_added_while_a_request_runs():
    token = request_id_var.set("abc123")
    try:
        assert json.loads(JsonFormatter().format(_record()))["request_id"] == "abc123"
        assert TextFormatter().format(_record()).endswith("[request abc123]")
    finally:
        request_id_var.reset(token)
    assert "request_id" not in json.loads(JsonFormatter().format(_record()))


def test_event_fields_become_json_fields():
    data = json.loads(JsonFormatter().format(_record(event="sign_in", event_fields={"user": "rec1", "message": "x"})))
    assert data["event"] == "sign_in" and data["user"] == "rec1"
    assert data["message"] == "hello world"  # A field never replaces the basic ones


def test_exceptions_stay_on_one_line():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record(exc_info=sys.exc_info())
    line = JsonFormatter().format(record)
    assert "\n" not in line and "ValueError: boom" in json.loads(line)["exception"]


def test_install_sends_uvicorn_lines_through_the_same_handler():
    root = logging.getLogger()
    saved = (root.handlers[:], {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).propagate) for n in logging_setup.UVICORN_LOGGERS})
    try:
        logging_setup.install(json_lines=True)
        assert len(root.handlers) == 1 and isinstance(root.handlers[0].formatter, JsonFormatter)
        for name in logging_setup.UVICORN_LOGGERS:
            assert logging.getLogger(name).handlers == [] and logging.getLogger(name).propagate
        # The access log still hides calendar tokens (F3): its filter is on the logger.
        from app.log_redaction import RedactSecretsFilter

        assert any(isinstance(f, RedactSecretsFilter) for f in logging.getLogger("uvicorn.access").filters)
    finally:
        root.handlers = saved[0]
        for name, (handlers, propagate) in saved[1].items():
            logging.getLogger(name).handlers = handlers
            logging.getLogger(name).propagate = propagate


def test_clean_keeps_values_short_and_on_one_line():
    assert clean("a\nb\rc\x00d") == "a b c d"
    assert len(clean("x" * 1000)) == 200
    assert clean(403) == 403 and clean(None) is None and clean(True) is True


def test_security_event_record(caplog):
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        security_event("thing_happened", user="rec1", note="two\nlines")
    [record] = _events(caplog, "thing_happened")
    assert record.event_fields == {"user": "rec1", "note": "two lines"}
    assert "\n" not in record.getMessage()


# --- Request IDs reach the lines written during a request --------------------------------


def test_lines_logged_in_a_sync_route_carry_the_request_id(client, sign_in, caplog, monkeypatch):
    """Sync routes run on a worker thread; the request ID must follow them there."""
    seen = []
    real = request_id_var.get
    sign_in("admin@example.org")
    from app.routers import me

    original = me._describe

    def spy(user):
        seen.append(real())
        return original(user)

    monkeypatch.setattr(me, "_describe", spy)
    response = client.get("/api/me")
    assert seen == [response.headers["X-Request-ID"]]
    assert request_id_var.get() == ""  # Cleared after the request


# --- Events ------------------------------------------------------------------------------


def _google(monkeypatch, client, **userinfo):
    async def fake_token(request):
        return {"userinfo": {"email_verified": True, **userinfo}}

    monkeypatch.setattr(oauth.google, "authorize_access_token", fake_token)
    return client.get("/auth/callback")


def test_sign_in_event(client, monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        _google(monkeypatch, client, email="staff@example.org")
    [event] = _events(caplog, "sign_in")
    assert event.event_fields == {"user": "recStaff", "access_level": "Staff"}
    assert "staff@example.org" not in caplog.text


@pytest.mark.parametrize(
    "userinfo, reason",
    [
        ({"email": "stranger@example.org"}, "not_an_active_user"),
        ({"email": "staff@example.org", "email_verified": False}, "email_not_verified"),
    ],
)
def test_denied_sign_in_events_mask_the_email(client, monkeypatch, caplog, userinfo, reason):
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        _google(monkeypatch, client, **userinfo)
    [event] = _events(caplog, "sign_in_denied")
    assert event.event_fields["reason"] == reason
    assert event.event_fields["email"] == userinfo["email"][0] + "***@example.org"
    assert userinfo["email"] not in caplog.text


def test_wrong_domain_event(client, monkeypatch, caplog, settings):
    settings(ALLOWED_EMAIL_DOMAIN="example.org")
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        _google(monkeypatch, client, email="someone@gmail.com")
    assert _events(caplog, "sign_in_denied")[0].event_fields["reason"] == "wrong_domain"


def test_sign_out_events(client, sign_in, caplog):
    sign_in("staff@example.org")
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        client.post("/auth/logout")
    assert _events(caplog, "sign_out")[0].event_fields == {"user": "recStaff"}
    sign_in("staff@example.org")
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        client.post("/auth/logout-everywhere")
    assert _events(caplog, "sign_out_everywhere")[0].event_fields == {"user": "recStaff"}


def test_revoked_session_event(client, sign_in, fake, caplog):
    sign_in("staff@example.org")
    fake.find(Users.TABLE, "recStaff")["fields"][Users.SESSION_VERSION] = 5
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        assert client.get("/api/me").status_code == 401
    assert _events(caplog, "session_revoked")[0].event_fields == {"user": "recStaff"}


def test_deactivated_while_signed_in_event(client, sign_in, fake, caplog):
    sign_in("staff@example.org")
    fake.find(Users.TABLE, "recStaff")["fields"][Users.STATUS] = "Inactive"
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        client.get("/api/me")
    assert _events(caplog, "session_ended_inactive_user")


def test_access_denied_event_names_the_route_and_user(client, sign_in, caplog):
    sign_in("staff@example.org")
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        assert client.get("/api/users").status_code == 403
    [event] = _events(caplog, "access_denied")
    fields = event.event_fields
    assert fields["route"] == "/api/users" and fields["user"] == "recStaff" and fields["status"] == 403
    assert fields["method"] == "GET"


def test_request_from_another_site_is_an_access_denied_event(client, sign_in, caplog):
    sign_in("admin@example.org")
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        client.post("/api/roles", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert _events(caplog, "access_denied")


def test_rate_limited_event(client, sign_in, caplog):
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        for _ in range(40):
            if client.post("/api/security/csp-report", content=b"{}", headers={"Content-Type": "application/csp-report"}).status_code == 429:
                break
    assert _events(caplog, "rate_limited")[0].event_fields["route"] == "/api/security/csp-report"


def test_signed_out_401s_are_not_events(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        assert client.get("/api/me").status_code == 401
    assert _events(caplog) == []


def test_csp_violation_event(client, caplog):
    report = {"csp-report": {"violated-directive": "script-src", "blocked-uri": "https://evil.example/x.js",
                             "document-uri": "http://localhost:8000/dashboard?token=secret"}}
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        client.post("/api/security/csp-report", json=report, headers={"Content-Type": "application/csp-report"})
    [event] = _events(caplog, "csp_violation")
    assert event.event_fields["blocked"] == "https://evil.example"
    assert "secret" not in caplog.text


def test_unexpected_error_event(client, sign_in, caplog, monkeypatch):
    from app.routers import me

    def broken(user):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr(me, "_describe", broken)
    sign_in("admin@example.org")
    with caplog.at_level(logging.INFO, logger="app.security.events"):
        assert client.get("/api/me").status_code == 500
    [event] = _events(caplog, "unexpected_error")
    assert event.event_fields == {"method": "GET", "route": "/api/me"}


def test_events_never_carry_cookies_or_codes(client, sign_in, caplog):
    with caplog.at_level(logging.DEBUG):
        sign_in("staff@example.org")
        cookie = client.cookies.get("nmu_session")
        client.get("/api/users")
        client.post("/auth/logout")
    assert cookie and cookie not in caplog.text
