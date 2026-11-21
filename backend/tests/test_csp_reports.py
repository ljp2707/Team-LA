"""F25: the endpoint browsers send Content-Security-Policy violation reports to."""

import json

import pytest

from app import rate_limit

URL = "/api/security/csp-report"

# The older report-uri format, as Firefox and Safari send it.
REPORT_URI_BODY = {
    "csp-report": {
        "document-uri": "https://nmu.example/tasks/recT2?email=mary@example.org#notes",
        "violated-directive": "script-src-elem",
        "effective-directive": "script-src-elem",
        "blocked-uri": "https://evil.example/steal.js?token=secret123",
        "script-sample": "alert('mary@example.org')",
        "original-policy": "default-src 'self'",
    }
}

# The Reporting API format, as Chrome sends it: a list, camelCase keys.
REPORTING_API_BODY = [
    {
        "type": "csp-violation",
        "url": "https://nmu.example/projects/recProj",
        "body": {
            "documentURL": "https://nmu.example/projects/recProj?q=private",
            "effectiveDirective": "style-src-attr",
            "blockedURL": "inline",
            "sample": "color: red",
        },
    },
    {
        "type": "csp-violation",
        "body": {
            "documentURL": "https://nmu.example/calendar/" + "A" * 43 + ".ics",
            "effectiveDirective": "img-src",
            "blockedURL": "data",
        },
    },
    {"type": "deprecation", "body": {"id": "something"}},  # Not a CSP report: ignored
]


def _post(client, body, content_type="application/csp-report", **headers):
    return client.post(URL, content=json.dumps(body), headers={"Content-Type": content_type, **headers})


@pytest.fixture
def csp_log(caplog):
    caplog.set_level("WARNING", logger="app.security.csp")
    return caplog


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "app.security.csp"]


def test_report_uri_format_logs_only_directive_site_and_path(client, csp_log):
    assert _post(client, REPORT_URI_BODY).status_code == 204
    assert _lines(csp_log) == [
        "CSP violation: directive=script-src-elem blocked=https://evil.example page=/tasks/recT2"
    ]


def test_reporting_api_format(client, csp_log):
    assert _post(client, REPORTING_API_BODY, "application/reports+json").status_code == 204
    assert _lines(csp_log) == [
        "CSP violation: directive=style-src-attr blocked=inline page=/projects/recProj",
        "CSP violation: directive=img-src blocked=data page=/calendar/[redacted].ics",
    ]


def test_no_personal_data_reaches_the_log(client, csp_log):
    _post(client, REPORT_URI_BODY)
    _post(client, REPORTING_API_BODY, "application/reports+json")
    text = csp_log.text
    for secret in ("mary@example.org", "secret123", "token=", "steal.js", "alert(", "private", "color: red", "A" * 43):
        assert secret not in text


def test_odd_values_are_replaced_not_logged(client, csp_log):
    body = {"csp-report": {"effective-directive": "script-src\nFAKE LOG LINE", "blocked-uri": "javascript:alert(1)",
                           "document-uri": "not a url \x1b[31m"}}
    assert _post(client, body).status_code == 204
    line = _lines(csp_log)[0]
    assert "\n" not in line and "\x1b" not in line and "FAKE" not in line
    assert line.startswith("CSP violation: directive=unknown blocked=other page=")


def test_signed_out_and_without_origin_is_accepted(client, csp_log):
    """Browsers send these on their own, sometimes without an Origin header."""
    client.headers.pop("Origin", None)
    assert _post(client, REPORT_URI_BODY).status_code == 204
    assert _post(client, REPORT_URI_BODY, Origin="https://other.example").status_code == 204


def test_other_routes_still_need_a_trusted_origin(client, sign_in, fake):
    sign_in("admin@example.org")
    response = client.post("/api/me/view", json={"view": "staff"}, headers={"Origin": "https://other.example"})
    assert response.status_code == 403


@pytest.mark.parametrize(
    "body, content_type",
    [
        ("not json", "application/csp-report"),
        ('{"something": "else"}', "application/csp-report"),
        ('"just a string"', "application/json"),
        (json.dumps(REPORT_URI_BODY), "text/plain"),
    ],
)
def test_anything_else_is_refused(client, csp_log, body, content_type):
    assert client.post(URL, content=body, headers={"Content-Type": content_type}).status_code == 400
    assert _lines(csp_log) == []


def test_body_over_64_kb_is_refused(client, csp_log):
    big = {"csp-report": {"effective-directive": "img-src", "padding": "x" * 70_000}}
    assert _post(client, big).status_code == 413
    assert _lines(csp_log) == []


def test_only_20_reports_per_request_are_logged(client, csp_log):
    many = [REPORTING_API_BODY[0]] * 50
    assert _post(client, many, "application/reports+json").status_code == 204
    assert len(_lines(csp_log)) == 20


def test_rate_limited(client):
    for _ in range(30):
        assert _post(client, REPORT_URI_BODY).status_code == 204
    assert _post(client, REPORT_URI_BODY).status_code == 429
    rate_limit.reset()


def test_writes_nothing_to_airtable(client, fake):
    before = len(fake.writes)
    _post(client, REPORT_URI_BODY)
    _post(client, REPORTING_API_BODY, "application/reports+json")
    assert len(fake.writes) == before


@pytest.mark.parametrize("mode, header", [("report-only", "Content-Security-Policy-Report-Only"),
                                          ("enforce", "Content-Security-Policy")])
def test_policy_points_browsers_at_the_endpoint(client, settings, mode, header):
    settings(CSP_MODE=mode)
    response = client.get("/api/health")
    policy = response.headers[header]
    assert "report-uri /api/security/csp-report" in policy
    assert "report-to csp-endpoint" in policy
    assert response.headers["Reporting-Endpoints"] == 'csp-endpoint="/api/security/csp-report"'


def test_no_reporting_endpoint_when_csp_is_off(client, settings):
    settings(CSP_MODE="off")
    assert "Reporting-Endpoints" not in client.get("/api/health").headers
