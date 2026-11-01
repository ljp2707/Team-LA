"""The signed in user, and looking people up in the Airtable Users table."""

from typing import Any

from pydantic import BaseModel

from app.airtable import client
from app.airtable.schema import Roles, Users
from app.permissions import Actor, View


class SessionUser(BaseModel):
    """What is kept in the signed session cookie."""

    airtable_record_id: str
    email: str
    first_name: str = ""
    last_name: str = ""
    access_level: str | None = None
    roles: list[str] = []


class CurrentUser(SessionUser):
    """A SessionUser plus the view they are in for this request."""

    view: View

    @property
    def actor(self) -> Actor:
        return Actor(access_level=self.access_level, view=self.view)


def _role_names(role_ids: list[str]) -> list[str]:
    if not role_ids:
        return []
    names = {
        record["id"]: record["fields"].get(Roles.NAME, "")
        for record in client.all_records(Roles.TABLE)
    }
    return [names[role_id] for role_id in role_ids if names.get(role_id)]


def _to_session_user(record: dict[str, Any]) -> SessionUser:
    fields = record["fields"]
    return SessionUser(
        airtable_record_id=record["id"],
        email=fields.get(Users.EMAIL, ""),
        first_name=fields.get(Users.FIRST_NAME, ""),
        last_name=fields.get(Users.LAST_NAME, ""),
        access_level=fields.get(Users.ACCESS_LEVEL),
        roles=_role_names(fields.get(Users.ROLES, [])),
    )


def find_active_user_by_email(email: str) -> SessionUser | None:
    """Find an Active user, ignoring upper and lower case in the email.

    The (cached) table is searched here rather than with an Airtable formula, so
    text from outside the app is never built into a formula.
    """
    wanted = email.strip().lower()
    for record in client.all_records(Users.TABLE):
        fields = record["fields"]
        if (
            fields.get(Users.EMAIL, "").strip().lower() == wanted
            and fields.get(Users.STATUS) == "Active"
        ):
            return _to_session_user(record)
    return None


def find_active_user_by_id(record_id: str) -> SessionUser | None:
    """Find an Active user by Airtable record ID."""
    for record in client.all_records(Users.TABLE):
        if record["id"] == record_id and record["fields"].get(Users.STATUS) == "Active":
            return _to_session_user(record)
    return None
