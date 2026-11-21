"""Request limits, headers, log redaction and safe links: findings F1, F3, F6, F7."""

import logging

import pytest
from pydantic import ValidationError

from app.airtable.schema import Links, Session, Work
from app.config import Settings
from tests.builders import standard_project

STRONG_SECRET = "s" * 40


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


def _upload(client, path, size, name="photo.png"):
    return client.post(path, files={"file": (name, b"\x89PNG\r\n\x1a\n" + b"x" * (size - 8), "image/png")})


# --- F6: request size limits, checked before sign-in and form parsing ---------------


def test_oversized_upload_is_refused_when_signed_out(client):
    response = _upload(client, "/api/tasks/recT2/files", 7 * 1024 * 1024)
    assert response.status_code == 413


def test_oversized_upload_is_refused_when_signed_in(client, sign_in, project):
    sign_in("staff@example.org")
    response = _upload(client, "/api/tasks/recT2/files", 7 * 1024 * 1024)
    assert response.status_code == 413
    assert "too large" in response.json()["detail"]


def test_normal_upload_still_works(client, sign_in, project):
    sign_in("staff@example.org")
    assert _upload(client, "/api/tasks/recT2/files", 1024 * 1024).status_code == 201


def test_large_json_body_is_refused(client, sign_in, project):
    sign_in("staff@example.org")
    response = client.post("/api/tasks/recT2/notes", json={"text": "x" * (3 * 1024 * 1024)})
    assert response.status_code == 413


def test_body_without_content_length_is_counted_as_it_streams(client):
    def chunks():
        for _ in range(4):
            yield b"x" * (1024 * 1024)

    response = client.post(
        "/api/tasks/recT2/notes", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


# --- F3: calendar tokens and sign-in codes are kept out of the access log -----------


def _access_record(path: str) -> logging.LogRecord:
    """A record shaped like the ones uvicorn's access logger writes."""
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0,
        '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5", "GET", path, "1.1", 200), None,
    )


def test_calendar_token_is_removed_from_access_log():
    from app.log_redaction import RedactSecretsFilter

    record = _access_record("/calendar/AbCdEf0123456789_-AbCdEf0123456789_-abcdefg.ics")
    assert RedactSecretsFilter().filter(record)
    assert "AbCdEf" not in record.getMessage()
    assert "/calendar/[redacted].ics" in record.getMessage()


def test_sign_in_code_is_removed_from_access_log():
    from app.log_redaction import RedactSecretsFilter

    record = _access_record("/auth/callback?state=abc&code=4/secret-code&scope=email")
    RedactSecretsFilter().filter(record)
    assert "secret-code" not in record.getMessage() and "state=abc" not in record.getMessage()
    assert "/auth/callback" in record.getMessage()


def test_other_paths_are_logged_unchanged():
    from app.log_redaction import RedactSecretsFilter

    record = _access_record("/api/projects?status=active")
    RedactSecretsFilter().filter(record)
    assert '"GET /api/projects?status=active HTTP/1.1" 200' in record.getMessage()


def test_redaction_filter_is_on_the_uvicorn_access_logger():
    import app.main  # noqa: F401 - attaching the filter happens on import
    from app.log_redaction import RedactSecretsFilter

    access = logging.getLogger("uvicorn.access")
    assert any(isinstance(f, RedactSecretsFilter) for f in access.filters)


# --- F1: HSTS in production, CSP behind a setting -----------------------------------


def test_no_hsts_on_localhost(client):
    assert "strict-transport-security" not in client.get("/api/health").headers


def test_hsts_in_production(client, settings):
    settings(ENV="production")
    assert client.get("/api/health").headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_csp_is_enforced_by_default(client):
    """F28: enforce is the default now the browser test shows every page works under it."""
    headers = client.get("/api/health").headers
    assert "content-security-policy-report-only" not in headers
    policy = headers["content-security-policy"]
    assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy


def test_csp_default_setting_is_enforce():
    from app.config import Settings

    assert Settings.model_fields["CSP_MODE"].default == "enforce"


def test_csp_report_only_is_still_an_option(client, settings):
    settings(CSP_MODE="report-only")
    headers = client.get("/api/health").headers
    assert "content-security-policy" not in headers
    assert "script-src 'self'" in headers["content-security-policy-report-only"]


def test_csp_can_be_enforced(client, settings):
    settings(CSP_MODE="enforce")
    headers = client.get("/api/health").headers
    assert "script-src 'self'" in headers["content-security-policy"]
    assert "content-security-policy-report-only" not in headers


def test_csp_can_be_turned_off(client, settings):
    settings(CSP_MODE="off")
    headers = client.get("/api/health").headers
    assert "content-security-policy" not in headers
    assert "content-security-policy-report-only" not in headers


def test_unknown_csp_mode_refuses_to_start():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CSP_MODE="sometimes")


# --- F7: only https links reach the page ---------------------------------------------


def test_javascript_link_typed_into_airtable_is_not_returned(client, sign_in, project):
    project.add(Links.TABLE, {Links.TITLE: "Evil", Links.URL: "javascript:alert(1)", Links.WORK: ["recT2"]}, "recLBad")
    project.add(Links.TABLE, {Links.TITLE: "Good", Links.URL: "https://canva.com/x", Links.WORK: ["recT2"]}, "recLGood")
    sign_in("staff@example.org")
    links = {l["id"]: l for l in client.get("/api/tasks/recT2").json()["links"] if l["id"]}
    assert links["recLBad"]["url"] is None
    assert links["recLGood"]["url"] == "https://canva.com/x"


def test_javascript_resource_link_is_dropped(client, sign_in, project):
    project.find(Work.TABLE, "recT2")["fields"][Work.RESOURCE_LINK] = "javascript:alert(1)"
    sign_in("staff@example.org")
    links = client.get("/api/tasks/recT2").json()["links"]
    assert not any(l["title"] == "Resource from the template" for l in links)


def test_https_resource_link_is_kept(client, sign_in, project):
    project.find(Work.TABLE, "recT2")["fields"][Work.RESOURCE_LINK] = "https://docs.google.com/d/1"
    sign_in("staff@example.org")
    links = client.get("/api/tasks/recT2").json()["links"]
    assert any(l["url"] == "https://docs.google.com/d/1" for l in links)


def test_non_https_drive_folder_is_not_returned(client, sign_in, project):
    project.find(Session.TABLE, "recProj")["fields"][Session.DRIVE_FOLDER] = "javascript:alert(1)"
    sign_in("admin@example.org")
    body = client.get("/api/projects/recProj").json()
    assert body["drive_folder"] is None
    assert body["edit"]["drive_folder"] == ""


def test_launch_without_drive_folder_gives_the_edit_form_text(client, sign_in, project):
    """The edit form calls .trim() on it: null blanked the whole launch page."""
    project.find(Session.TABLE, "recProj")["fields"].pop(Session.DRIVE_FOLDER, None)
    sign_in("admin@example.org")
    assert client.get("/api/projects/recProj").json()["edit"]["drive_folder"] == ""
