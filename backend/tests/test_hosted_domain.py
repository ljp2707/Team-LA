"""F32: with ALLOWED_EMAIL_DOMAIN set, Google's "hd" claim must match it too."""

import pytest
from fastapi.responses import RedirectResponse

from app.airtable.schema import Users
from app.auth.google import email_allowed, oauth

DOMAIN = "example.org"


@pytest.fixture
def google_says(client, monkeypatch):
    """Run the real callback with Google answering this userinfo."""

    def _google_says(**userinfo):
        async def fake_token(request):
            return {"userinfo": {"email_verified": True, **userinfo}}

        monkeypatch.setattr(oauth.google, "authorize_access_token", fake_token)
        return client.get("/auth/callback")

    return _google_says


def test_workspace_account_gets_in(client, settings, google_says):
    settings(ALLOWED_EMAIL_DOMAIN=DOMAIN)
    response = google_says(email="staff@example.org", hd=DOMAIN)
    assert response.status_code == 302 and "not-authorized" not in response.headers["location"]
    assert client.get("/api/me").status_code == 200


def test_personal_account_with_a_work_address_is_refused(client, settings, google_says):
    """A personal Google account made with a work email has no "hd" claim."""
    settings(ALLOWED_EMAIL_DOMAIN=DOMAIN)
    response = google_says(email="staff@example.org")
    assert response.headers["location"].endswith("/not-authorized?reason=domain")
    assert client.get("/api/me").status_code == 401


def test_other_workspace_is_refused(client, settings, google_says):
    settings(ALLOWED_EMAIL_DOMAIN=DOMAIN)
    response = google_says(email="staff@example.org", hd="evil.example")
    assert response.headers["location"].endswith("/not-authorized?reason=domain")


def test_wrong_email_domain_is_refused_even_with_the_right_hd(settings, google_says):
    settings(ALLOWED_EMAIL_DOMAIN=DOMAIN)
    response = google_says(email="someone@gmail.com", hd=DOMAIN)
    assert response.headers["location"].endswith("/not-authorized?reason=domain")


def test_no_domain_setting_allows_personal_accounts(client, google_says, fake):
    fake.find(Users.TABLE, "recStaff")["fields"][Users.EMAIL] = "sam@gmail.com"
    response = google_says(email="sam@gmail.com")
    assert "not-authorized" not in response.headers["location"]


@pytest.mark.parametrize(
    "email, hd, ok",
    [
        ("a@example.org", "example.org", True),
        ("A@Example.org", "EXAMPLE.ORG", True),
        ("a@example.org", None, False),
        ("a@example.org", "", False),
        ("a@example.org", "sub.example.org", False),
        ("a@evil-example.org", "example.org", False),
    ],
)
def test_email_allowed(settings, email, hd, ok):
    settings(ALLOWED_EMAIL_DOMAIN=DOMAIN)
    assert email_allowed(email, hd) is ok


def test_sign_in_page_hints_the_domain_to_google(client, settings, monkeypatch):
    settings(ALLOWED_EMAIL_DOMAIN=DOMAIN, GOOGLE_CLIENT_ID="id", GOOGLE_CLIENT_SECRET="secret")
    seen = {}

    async def fake_redirect(request, redirect_uri, **kwargs):
        seen.update(kwargs)
        return RedirectResponse("https://accounts.google.com/o/oauth2/auth")

    monkeypatch.setattr(oauth.google, "authorize_redirect", fake_redirect)
    assert client.get("/auth/login").status_code in (302, 307)
    assert seen == {"prompt": "select_account", "hd": DOMAIN}


def test_dev_login_still_works_with_a_domain(client, settings):
    settings(ALLOWED_EMAIL_DOMAIN=DOMAIN, DEV_LOGIN_EMAIL="admin@example.org")
    response = client.get("/auth/login")
    assert "not-authorized" not in response.headers["location"]
    assert client.get("/api/me").status_code == 200
