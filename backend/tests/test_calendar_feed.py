"""The private calendar feed (.ics): turning it on and off, who sees what, and escaping."""

from datetime import date

import pytest

from app.airtable.schema import Users, Work
from app.services import calendar_feed
from tests.builders import add_project, add_task, standard_project


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


def _turn_on(client, sign_in, email):
    sign_in(email)
    response = client.post("/api/me/calendar-feed")
    assert response.status_code == 200, response.text
    body = response.json()
    return body, body["feed_url"].rsplit("/", 1)[1].removesuffix(".ics")


def _events(text):
    """Unfold the feed and return {UID: {property: value}} for each event."""
    unfolded = text.replace("\r\n ", "")
    events, current = {}, None
    for line in unfolded.split("\r\n"):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            events[current["UID"]] = current
            current = None
        elif current is not None and ":" in line:
            name, value = line.split(":", 1)
            current[name] = value
    return events


def _feed(client, token):
    client.cookies.clear()  # Google fetches the feed without signing in
    return client.get(f"/calendar/{token}.ics")


def test_turning_on_gives_a_private_link_and_google_subscribe_link(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.get("/api/me/calendar-feed").json() == {
        "enabled": False, "can_turn_on": True, "feed_url": None, "google_url": None,
    }
    body, token = _turn_on(client, sign_in, "staff@example.org")
    assert body["enabled"] is True
    assert body["feed_url"] == f"http://localhost:8000/calendar/{token}.ics"
    assert len(token) >= 40
    assert body["google_url"].startswith("https://calendar.google.com/calendar/render?cid=webcal%3A%2F%2F")
    assert project.find(Users.TABLE, "recStaff")["fields"][Users.CALENDAR_FEED_TOKEN] == token
    assert client.get("/api/me/calendar-feed").json()["feed_url"] == body["feed_url"]


def test_feed_has_only_that_persons_open_dated_tasks(client, sign_in, project):
    # Someone else's task, a finished one, one with no date, and one on a closed launch.
    add_task(project, "recOther", "Admin only", date(2026, 11, 20), assigned="recAdmin")
    add_task(project, "recDone", "Finished", date(2026, 11, 21), status="Done", assigned="recStaff")
    add_task(project, "recNoDate", "Someday", None, assigned="recStaff")
    add_project(project, "recClosed", name="Old launch", status="Complete", start=date(2026, 6, 1))
    add_task(project, "recClosedT", "Leftover", date(2026, 11, 25), project="recClosed", assigned="recStaff")
    _, token = _turn_on(client, sign_in, "staff@example.org")

    response = _feed(client, token)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    text = response.text
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and text.endswith("END:VCALENDAR\r\n")
    events = _events(text)
    assert set(events) == {"recT2@nmu-launches", "recT3@nmu-launches", "recT4@nmu-launches"}
    flyer = events["recT2@nmu-launches"]
    assert flyer["SUMMARY"] == "[Rainier Beach Swim Safely 2026] Design flyer"
    assert flyer["DTSTART;VALUE=DATE"] == "20261030"
    assert flyer["DTEND;VALUE=DATE"] == "20261031"  # All day: ends the next day
    assert "Status: Not Started" in flyer["DESCRIPTION"]
    assert "Launch: Rainier Beach Swim Safely 2026" in flyer["DESCRIPTION"]
    assert flyer["URL"].endswith("/tasks/recT2")
    assert "Status: Blocked" in events["recT3@nmu-launches"]["DESCRIPTION"]  # As the app shows it
    for hidden in ("Admin only", "Finished", "Someday", "Leftover"):
        assert hidden not in text


def test_changing_a_task_keeps_its_event_uid(client, sign_in, project):
    _, token = _turn_on(client, sign_in, "staff@example.org")
    before = _events(_feed(client, token).text)["recT2@nmu-launches"]
    project.find(Work.TABLE, "recT2")["fields"][Work.TASK_NAME] = "Design the flyer"
    project.find(Work.TABLE, "recT2")["fields"][Work.DUE_DATE_OVERRIDE] = "2026-11-12"
    after = _events(_feed(client, token).text)["recT2@nmu-launches"]
    assert after["SUMMARY"].endswith("Design the flyer") and after["DTSTART;VALUE=DATE"] == "20261112"
    assert before["SUMMARY"] != after["SUMMARY"]


def test_unknown_turned_off_and_reset_links_answer_404(client, sign_in, project):
    _, token = _turn_on(client, sign_in, "staff@example.org")
    assert _feed(client, "x" * 43).status_code == 404  # Well formed but unknown
    assert _feed(client, "not-a-token").status_code == 404  # Malformed
    assert _feed(client, "").status_code == 404

    # Reset: the old link stops at once, the new one works.
    _, new_token = _turn_on(client, sign_in, "staff@example.org")
    assert new_token != token
    assert _feed(client, token).status_code == 404
    assert _feed(client, new_token).status_code == 200

    # Turn off: the link stops and the token is gone from Airtable.
    sign_in("staff@example.org")
    assert client.delete("/api/me/calendar-feed").json()["enabled"] is False
    assert Users.CALENDAR_FEED_TOKEN not in project.find(Users.TABLE, "recStaff")["fields"]
    assert _feed(client, new_token).status_code == 404


def test_losing_access_stops_the_feed(client, sign_in, project):
    _, token = _turn_on(client, sign_in, "staff@example.org")
    sign_in("admin@example.org")
    assert client.patch("/api/users/recStaff", json={"status": "Inactive"}).status_code == 200
    assert Users.CALENDAR_FEED_TOKEN not in project.find(Users.TABLE, "recStaff")["fields"]
    assert _feed(client, token).status_code == 404
    # Even a token left on an inactive person's row never works.
    project.find(Users.TABLE, "recStaff")["fields"][Users.CALENDAR_FEED_TOKEN] = token
    assert _feed(client, token).status_code == 404


def test_viewers_cannot_turn_it_on_and_partners_only_get_their_launches(client, sign_in, project):
    sign_in("viewer@example.org")
    assert client.get("/api/me/calendar-feed").json()["can_turn_on"] is False
    assert client.post("/api/me/calendar-feed").status_code == 403

    add_project(project, "recTheirs", name="Partner launch", partners=["recPartner"])
    add_task(project, "recPT", "Book the pool", date(2026, 11, 30), project="recTheirs", assigned="recPartner")
    add_task(project, "recPHidden", "Not their launch", date(2026, 11, 30), assigned="recPartner")
    _, token = _turn_on(client, sign_in, "partner@example.org")
    assert set(_events(_feed(client, token).text)) == {"recPT@nmu-launches"}


def test_signed_out_people_cannot_change_the_setting(client, project):
    assert client.get("/api/me/calendar-feed").status_code == 401
    assert client.post("/api/me/calendar-feed").status_code == 401


def test_task_page_says_when_a_task_is_already_in_the_feed(client, sign_in, project):
    sign_in("staff@example.org")
    assert client.get("/api/tasks/recT2").json()["in_calendar_feed"] is False
    _turn_on(client, sign_in, "staff@example.org")
    detail = client.get("/api/tasks/recT2").json()
    assert detail["in_calendar_feed"] is True
    assert detail["calendar_url"]  # The per-task button is still offered
    sign_in("admin@example.org")
    assert client.get("/api/tasks/recT2").json()["in_calendar_feed"] is False  # Not the admin's feed


def test_special_characters_are_escaped_and_long_lines_folded(client, sign_in, project):
    tricky = 'Buy caps, goggles; "kick boards"\nfor the deep end \\ shallow end — ✅ ready'
    add_task(project, "recX", tricky, date(2026, 12, 1), assigned="recStaff")
    _, token = _turn_on(client, sign_in, "staff@example.org")
    text = _feed(client, token).text
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75  # Folded by bytes, never mid-character
    summary = _events(text)["recX@nmu-launches"]["SUMMARY"]
    assert summary == (
        "[Rainier Beach Swim Safely 2026] "
        'Buy caps\\, goggles\\; "kick boards"\\nfor the deep end \\\\ shallow end — ✅ ready'
    )


def test_escape_and_fold_rules():
    assert calendar_feed.escape_text("a,b;c\\d\r\ne\nf") == "a\\,b\\;c\\\\d\\ne\\nf"
    folded = calendar_feed.fold("SUMMARY:" + "é" * 80)
    parts = folded.split("\r\n")
    assert all(len(p.encode("utf-8")) <= 75 for p in parts)
    assert all(p.startswith(" ") for p in parts[1:])
    assert "".join(p[1:] if i else p for i, p in enumerate(parts)) == "SUMMARY:" + "é" * 80
