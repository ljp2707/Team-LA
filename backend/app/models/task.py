"""Request bodies for tasks (the Airtable Work table), notes, links and reminders."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TaskStatus = Literal["Not Started", "In Progress", "Blocked", "Done", "Skipped"]

NOTE_MAX = 2000


class TaskUpdateIn(BaseModel):
    """Staff may only send status. Admins may also send the rest."""

    status: TaskStatus | None = None
    due_date: date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    depends_on: list[str] | None = None


class AssignIn(BaseModel):
    user_id: str | None = None
    user_ids: list[str] | None = None  # Everyone on the task. Takes priority over user_id.


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=NOTE_MAX)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Write something first")
        return value.strip()


class NoteVisibilityIn(BaseModel):
    visibility: Literal["Internal", "Shared"]


class LinkIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=9, max_length=2000)

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("https://") or " " in value:
            raise ValueError("Links must start with https://")
        return value


class ReminderIn(BaseModel):
    send_on: date
    note: str = Field(default="", max_length=500)


class OneOffTaskIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    due_date: date
    role_id: str | None = None
    user_id: str | None = None
    user_ids: list[str] = []  # More people besides user_id
    needs_first: list[str] = []
    comes_before: list[str] = []
