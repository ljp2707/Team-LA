"""Email templates and the Gmail sender."""

import base64
import email

import httpx
import pytest

from app.email import gmail, templates
from app.email.templates import TaskLine


def line(name="Ship <b>equipment</b> & more", site="Rainier \"Beach\""):
    return TaskLine(name=name, site=site, due_text="Due Nov 16", url="http://localhost:8000/tasks/rec1")


def test_values_are_html_escaped():
    subject, text, html = templates.due_in_seven(line())
    assert "<b>equipment</b>" not in html
    assert "Ship &lt;b&gt;equipment&lt;/b&gt; &amp; more" in html
    assert "Rainier &quot;Beach&quot;" in html
    # The plain text part keeps the original words.
    assert "Ship <b>equipment</b> & more" in text
    assert subject == 'Due in 7 days: Ship <b>equipment</b> & more (Rainier "Beach")'


def test_every_email_has_the_footer_and_one_button():
    for subject, text, html in (
        templates.due_today(line()),
        templates.custom_reminder(line(), note="<script>x</script>"),
        templates.weekly_digest("Nov 9", "Tash", [line()], [line("Other")]),
        templates.assignment([line(), line("Other")], "Catalina"),
        templates.welcome("Mary", "mary@example.org"),
    ):
        assert templates.FOOTER in text and templates.FOOTER in html
        assert html.count('style="display:inline-block;padding:12px 24px') == 1
        assert "<script>" not in html
        assert "<img" not in html


def test_subjects_match_the_spec():
    assert templates.due_today(line("Confirm pool schedule", "Kent YMCA"))[0] == (
        "Due today: Confirm pool schedule (Kent YMCA)"
    )
    assert templates.assignment([line("A", "Rainier Beach")] * 3, "C")[0] == (
        "3 new tasks for you at Rainier Beach"
    )
    assert templates.assignment([line("Design flyer")], "C")[0] == "New task for you: Design flyer"
    assert templates.welcome("M", "m@example.org")[0] == "You've been added to NMU Launches"
    assert templates.weekly_digest("Nov 3", "T", [], [])[0] == "Your NMU tasks for the week of Nov 3"


def test_dry_run_sends_nothing(settings, monkeypatch):
    settings(REMINDERS_DRY_RUN=True)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("should not call Google"))
    assert gmail.send_email("a@example.org", "S", "t", "<p>h</p>") is None


class Answer:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def live(settings):
    settings(REMINDERS_DRY_RUN=False, GMAIL_REFRESH_TOKEN="refresh", GMAIL_SENDER="nmu@example.org")
    gmail._clear_token()
    yield
    gmail._clear_token()


def test_sends_a_base64url_message_from_nmu_launches(live, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if url == gmail.TOKEN_URL:
            # One client serves sign in and Gmail when the GMAIL_ ones are empty.
            assert kwargs["data"]["client_id"] == "test-client.apps.googleusercontent.com"
            return Answer(200, {"access_token": "tok", "expires_in": 3600})
        return Answer(200, {"id": "msg1"})

    monkeypatch.setattr(httpx, "post", post)
    assert gmail.send_email("a@example.org", "Hello", "text", "<p>html</p>") == "msg1"
    raw = calls[1][1]["json"]["raw"]
    message = email.message_from_bytes(base64.urlsafe_b64decode(raw))
    assert message["From"] == "NMU Launches <nmu@example.org>"
    assert message.is_multipart()
    # The access token is cached.
    gmail.send_email("b@example.org", "Again", "t", "<p>h</p>")
    assert [c[0] for c in calls].count(gmail.TOKEN_URL) == 1


def test_retries_once_on_a_server_error(live, monkeypatch):
    answers = iter([Answer(503, {"error": {"message": "busy"}}), Answer(200, {"id": "ok"})])

    def post(url, **kwargs):
        if url == gmail.TOKEN_URL:
            return Answer(200, {"access_token": "tok", "expires_in": 3600})
        return next(answers)

    monkeypatch.setattr(httpx, "post", post)
    assert gmail.send_email("a@example.org", "S", "t", "h") == "ok"


def test_expired_authorization_has_a_clear_message(live, monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda url, **k: Answer(400, {"error": "invalid_grant"})
    )
    with pytest.raises(gmail.EmailError) as error:
        gmail.send_email("a@example.org", "S", "t", "h")
    assert "Re-run python -m jobs.authorize_gmail" in str(error.value)


def test_test_email_endpoint_shows_the_error(client, sign_in, live, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **k: Answer(400, {"error": "invalid_grant"}))
    sign_in("admin@example.org")
    body = client.post("/api/admin/test-email").json()
    assert body["sent"] is False and "authorize_gmail" in body["error"]
    sign_in("staff@example.org")
    assert client.post("/api/admin/test-email").status_code == 403
