"""F31: a new session at sign in and at every change of view."""

import base64
import json

from app.auth.session import SESSION_ID_KEY, regenerate_session


def _session(client) -> dict:
    """What the signed cookie holds. The data before the first dot is plain base64 JSON."""
    value = client.cookies.get("nmu_session")
    return json.loads(base64.b64decode(value.split(".")[0]))


class _Request:
    def __init__(self, session):
        self.session = session


def test_regenerate_keeps_only_who_the_person_is():
    request = _Request({"user": {"airtable_record_id": "recA"}, "view": "staff", "signed_in_at": 1.0,
                        "seen_at": 2.0, "sid": "old", "_state_google_x": {"data": 1}, "denied_email": "x"})
    regenerate_session(request)
    assert set(request.session) == {"user", "view", "signed_in_at", "seen_at", SESSION_ID_KEY}
    assert request.session[SESSION_ID_KEY] != "old" and len(request.session[SESSION_ID_KEY]) >= 20
    assert request.session["user"] == {"airtable_record_id": "recA"}


def test_each_sign_in_gets_a_new_session_id(client, sign_in):
    sign_in("admin@example.org")
    first = _session(client)[SESSION_ID_KEY]
    sign_in("admin@example.org")
    assert _session(client)[SESSION_ID_KEY] != first


def test_view_switch_gets_a_new_session(client, sign_in, settings):
    settings(DEV_ALLOW_VIEW_SWITCH=True)
    sign_in("admin@example.org")
    before_cookie, before = client.cookies.get("nmu_session"), _session(client)
    assert client.post("/api/me/view", json={"view": "staff"}).json()["view"] == "staff"
    after = _session(client)
    assert client.cookies.get("nmu_session") != before_cookie
    assert after[SESSION_ID_KEY] != before[SESSION_ID_KEY]
    assert after["view"] == "staff" and after["user"]["airtable_record_id"] == "recAdmin"
    assert after["signed_in_at"] == before["signed_in_at"]  # The 7-day limit still counts from sign in
    assert client.get("/api/me").status_code == 200


def test_refused_view_switch_keeps_the_session(client, sign_in, settings):
    settings(DEV_ALLOW_VIEW_SWITCH=True)
    sign_in("partner@example.org")
    before = _session(client)[SESSION_ID_KEY]
    assert client.post("/api/me/view", json={"view": "admin"}).status_code == 403
    assert _session(client)[SESSION_ID_KEY] == before


def test_session_id_is_not_shown_to_the_page(client, sign_in):
    sign_in("admin@example.org")
    assert "sid" not in client.get("/api/me").text
