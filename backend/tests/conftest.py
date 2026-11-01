"""Shared test setup: a fake Airtable Users table and real sign in through the callback."""

import os

# Tests must never read a developer's .env values or reach the real Airtable base.
os.environ.update(
    ENV="test",
    SESSION_SECRET="test-secret",
    AIRTABLE_TOKEN="",
    AIRTABLE_BASE_ID="",
    ALLOWED_EMAIL_DOMAIN="",
    DEV_ALLOW_VIEW_SWITCH="false",
    DEV_LOGIN_EMAIL="",
)

import pytest
from fastapi.testclient import TestClient

from app.airtable import client as airtable
from app.airtable.schema import Roles, Users
from app.auth.google import oauth
from app.config import get_settings
from app.main import app


def person(record_id, email, access_level, status="Active"):
    return {
        "id": record_id,
        "fields": {
            Users.EMAIL: email,
            Users.FIRST_NAME: "Test",
            Users.STATUS: status,
            Users.ACCESS_LEVEL: access_level,
            Users.ROLES: ["recRole"],
        },
    }


@pytest.fixture
def users():
    """The fake Users table. Tests may change it to simulate edits in Airtable."""
    return [
        person("recAdmin", "Admin@Example.org", "Admin"),
        person("recLead", "lead@example.org", "Project Lead"),
        person("recStaff", "staff@example.org", "Staff"),
        person("recViewer", "viewer@example.org", "Viewer"),
        person("recGone", "gone@example.org", "Admin", status="Inactive"),
    ]


@pytest.fixture(autouse=True)
def fake_airtable(monkeypatch, users):
    tables = {
        Users.TABLE: users,
        Roles.TABLE: [{"id": "recRole", "fields": {Roles.NAME: "Program Manager"}}],
    }
    monkeypatch.setattr(
        airtable, "all_records", lambda name, fields=None: tables.get(name, [])
    )


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def sign_in(client, monkeypatch):
    """Sign in by running the real callback with a faked answer from Google."""

    def _sign_in(email, verified=True):
        async def fake_token(request):
            return {"userinfo": {"email": email, "email_verified": verified}}

        monkeypatch.setattr(oauth.google, "authorize_access_token", fake_token)
        return client.get("/auth/callback")

    return _sign_in


@pytest.fixture
def settings(monkeypatch):
    """Lets a test change a setting and have it undone afterward."""
    current = get_settings()

    def _set(**values):
        for name, value in values.items():
            monkeypatch.setattr(current, name, value)

    return _set
