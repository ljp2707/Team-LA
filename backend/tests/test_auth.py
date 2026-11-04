"""Google sign in: bootstrap admin, account picker, not set up, and the denied email."""

from app.airtable.schema import Users
from app.auth.google import oauth


def test_bootstrap_admin_row_is_created_when_missing(client, sign_in, settings, fake):
    settings(BOOTSTRAP_ADMIN_EMAILS="avanthi.arun@gmail.com, other@example.org")
    response = sign_in("Avanthi.Arun@gmail.com", given_name="Avanthi", family_name="Arun")
    assert response.headers["location"].endswith("/dashboard")
    row = next(r for r in fake.rows(Users.TABLE) if r["fields"][Users.EMAIL] == "avanthi.arun@gmail.com")
    assert row["fields"][Users.ACCESS_LEVEL] == "Admin"
    assert row["fields"][Users.STATUS] == "Active"
    assert row["fields"][Users.FIRST_NAME] == "Avanthi"
    assert row["fields"][Users.LAST_NAME] == "Arun"
    assert client.get("/api/me").json()["view"] == "admin"


def test_existing_bootstrap_row_is_never_changed(client, sign_in, settings, fake, caplog):
    settings(BOOTSTRAP_ADMIN_EMAILS="staff@example.org,gone@example.org")
    assert sign_in("staff@example.org").headers["location"].endswith("/my-tasks")
    assert sign_in("gone@example.org").headers["location"].endswith("/not-authorized")
    assert not fake.writes_to(Users.TABLE)
    assert "not an Active Admin" in caplog.text


def test_email_not_on_the_list_is_refused_and_shown(client, sign_in, settings, fake):
    settings(BOOTSTRAP_ADMIN_EMAILS="avanthi.arun@gmail.com")
    response = sign_in("stranger@gmail.com")
    assert response.headers["location"].endswith("/not-authorized")
    assert not fake.writes_to(Users.TABLE)
    assert client.get("/auth/denied").json() == {"email": "stranger@gmail.com"}
    # It is shown once, then cleared.
    assert client.get("/auth/denied").json() == {"email": None}


def test_login_asks_google_for_the_account_picker(client, monkeypatch):
    async def fake_metadata():
        return {"authorization_endpoint": "https://accounts.google.com/o/oauth2/auth"}

    monkeypatch.setattr(oauth.google, "load_server_metadata", fake_metadata)
    location = client.get("/auth/login").headers["location"]
    assert "prompt=select_account" in location


def test_login_without_a_client_id_explains_instead_of_going_to_google(client, settings):
    for placeholder in ("", "replace-me.apps.googleusercontent.com"):
        settings(GOOGLE_CLIENT_ID=placeholder)
        location = client.get("/auth/login").headers["location"]
        assert location.endswith("/not-authorized?reason=not-configured")


def test_dev_login_still_works_without_a_client_id(client, settings):
    settings(GOOGLE_CLIENT_ID="", DEV_LOGIN_EMAIL="staff@example.org")
    assert client.get("/auth/login").headers["location"].endswith("/my-tasks")


def test_auth_health_is_admin_only_and_never_shows_secrets(client, sign_in):
    sign_in("staff@example.org")
    assert client.get("/api/health/auth").status_code == 403
    sign_in("admin@example.org")
    body = client.get("/api/health/auth").json()
    assert body["client_id_set"] is True
    assert body["callback_url"] == "http://localhost:8000/auth/callback"
    assert body["dev_login"] is False
    assert "test-client" not in str(body) and "test-secret" not in str(body)


def test_partner_signs_in_to_partner_view(client, sign_in):
    assert sign_in("partner@example.org").headers["location"].endswith("/my-tasks")
    me = client.get("/api/me").json()
    assert me["view"] == "partner"
    assert me["can_switch_view"] is False
    assert client.post("/api/me/view", json={"view": "staff"}).status_code == 403
    assert client.post("/api/me/view", json={"view": "admin"}).status_code == 403
