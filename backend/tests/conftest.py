"""Shared test setup: a fake Airtable base, a fixed clock, and real sign in.

The fake keeps every table in memory. Reads go through `client.all_records` and
writes through `client.create_records`, `update_records` and `delete_records`, so
the app code runs unchanged. Every write is also recorded in `fake.writes`.
"""

import os

# Tests must never read a developer's .env values or reach the real Airtable base,
# Google or Gmail.
os.environ.update(
    ENV="test",
    SESSION_SECRET="test-secret",
    AIRTABLE_TOKEN="",
    AIRTABLE_BASE_ID="",
    ALLOWED_EMAIL_DOMAIN="",
    DEV_ALLOW_VIEW_SWITCH="false",
    DEV_LOGIN_EMAIL="",
    GOOGLE_CLIENT_ID="test-client.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="test-secret",
    BOOTSTRAP_ADMIN_EMAILS="",
    GMAIL_SENDER="sender@example.org",
    GMAIL_CLIENT_ID="",
    GMAIL_CLIENT_SECRET="",
    GMAIL_REFRESH_TOKEN="",
    REMINDERS_DRY_RUN="true",
    APP_URL="http://localhost:8000",
    FRONTEND_URL="http://localhost:5173",
    APP_TIMEZONE="America/Los_Angeles",
)

import itertools
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.airtable import client as airtable
from app.airtable.schema import Roles, Users
from app.auth.google import oauth
from app.config import get_settings
from app.main import app
from app.routers import public
from app.services import clock

TODAY = date(2026, 11, 4)  # A Wednesday
PACIFIC = ZoneInfo("America/Los_Angeles")


def person(record_id, email, access_level, status="Active", roles=("recRole",), first="Test"):
    return {
        "id": record_id,
        "createdTime": "2026-01-01T00:00:00.000Z",
        "fields": {
            Users.EMAIL: email,
            Users.FIRST_NAME: first,
            Users.STATUS: status,
            Users.ACCESS_LEVEL: access_level,
            Users.ROLES: list(roles),
        },
    }


class FakeAirtable:
    """An in-memory Airtable base."""

    def __init__(self, tables):
        self.tables = tables
        self.writes = []
        self._ids = itertools.count(1)
        self.now = None

    def rows(self, name):
        return self.tables.setdefault(name, [])

    def all_records(self, name, fields=None):
        return self.rows(name)

    def find(self, name, record_id):
        return next(r for r in self.rows(name) if r["id"] == record_id)

    def _created_time(self):
        now = self.now or clock.now()
        return now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def add(self, name, fields, record_id=None):
        record = {
            "id": record_id or f"recNew{next(self._ids)}",
            "createdTime": self._created_time(),
            "fields": {k: v for k, v in fields.items() if v is not None},
        }
        self.rows(name).append(record)
        return record

    def create_records(self, name, rows, typecast=False):
        # Same rule as the real client: the app never writes automation-owned fields.
        airtable._refuse_automation_fields(name, rows)
        created = [self.add(name, dict(fields)) for fields in rows]
        self.writes += [("create", name, r["id"], dict(r["fields"])) for r in created]
        return created

    def update_records(self, name, updates, typecast=False):
        airtable._refuse_automation_fields(name, [u["fields"] for u in updates])
        out = []
        for update in updates:
            record = self.find(name, update["id"])
            for key, value in update["fields"].items():
                if value is None or value == []:
                    record["fields"].pop(key, None)
                else:
                    record["fields"][key] = value
            self.writes.append(("update", name, update["id"], dict(update["fields"])))
            out.append(record)
        return out

    def upload_attachment(self, name, record, field, filename, content, content_type):
        stored = self.find(name, record["id"])
        attachment = {
            "id": f"att{next(self._ids)}",
            "url": f"https://v5.airtableusercontent.com/{filename}",
            "filename": filename,
            "size": len(content),
            "type": content_type,
        }
        stored["fields"][field] = [*stored["fields"].get(field, []), attachment]
        self.writes.append(("upload", name, record["id"], {field: filename}))
        return stored

    def delete_records(self, name, ids):
        self.tables[name] = [r for r in self.rows(name) if r["id"] not in ids]
        self.writes += [("delete", name, i, {}) for i in ids]

    def writes_to(self, name, kind=None):
        return [w for w in self.writes if w[1] == name and (kind is None or w[0] == kind)]


@pytest.fixture
def users():
    """The fake Users table. Tests may change it to simulate edits in Airtable."""
    return [
        person("recAdmin", "Admin@Example.org", "Admin", first="Ada"),
        person("recLead", "lead@example.org", "Project Lead", first="Lee"),
        person("recStaff", "staff@example.org", "Staff", first="Sam"),
        person("recViewer", "viewer@example.org", "Viewer", first="Vi"),
        person("recGone", "gone@example.org", "Admin", status="Inactive"),
        person("recPartner", "partner@example.org", "Partner", roles=(), first="Pat"),
    ]


@pytest.fixture
def fake(users):
    return FakeAirtable(
        {
            Users.TABLE: users,
            Roles.TABLE: [
                {"id": "recRole", "fields": {Roles.NAME: "Program Manager", Roles.STATUS: "Active"}},
                {"id": "recRoleOps", "fields": {Roles.NAME: "Operations", Roles.STATUS: "Active"}},
            ],
        }
    )


@pytest.fixture(autouse=True)
def fake_airtable(monkeypatch, fake):
    monkeypatch.setattr(airtable, "all_records", fake.all_records)
    monkeypatch.setattr(airtable, "create_records", fake.create_records)
    monkeypatch.setattr(airtable, "update_records", fake.update_records)
    monkeypatch.setattr(airtable, "delete_records", fake.delete_records)
    monkeypatch.setattr(airtable, "upload_attachment", fake.upload_attachment)
    public.clear()
    return fake


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """Today is always Wednesday, Nov 4, 2026 at 9 AM Pacific, unless a test moves it."""
    state = {"now": datetime(2026, 11, 4, 9, 0, tzinfo=PACIFIC)}

    def set_now(value: datetime):
        state["now"] = value

    monkeypatch.setattr(clock, "now", lambda: state["now"])
    monkeypatch.setattr(clock, "today", lambda: state["now"].date())
    return set_now


@pytest.fixture
def advance(fixed_clock):
    """Move the clock forward: advance(hours=25)."""

    def _advance(**kwargs):
        fixed_clock(clock.now() + timedelta(**kwargs))

    return _advance


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def sign_in(client, monkeypatch):
    """Sign in by running the real callback with a faked answer from Google."""

    def _sign_in(email, verified=True, given_name="", family_name=""):
        async def fake_token(request):
            return {
                "userinfo": {
                    "email": email,
                    "email_verified": verified,
                    "given_name": given_name,
                    "family_name": family_name,
                }
            }

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
