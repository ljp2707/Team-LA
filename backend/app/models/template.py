"""Request bodies for templates (the Template List, Steps and Template Versions tables)."""

from typing import Literal

from pydantic import BaseModel, Field


class StepIn(BaseModel):
    key: str | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    anchor: Literal["Start", "End"] = "Start"
    days_before: int = Field(default=0, ge=-365, le=365)
    role_id: str | None = None
    depends_on: list[str] = []


class DraftIn(BaseModel):
    steps: list[StepIn] = Field(max_length=200)


class PublishIn(BaseModel):
    change_note: str = Field(default="", max_length=1000)


class NewTemplateIn(BaseModel):
    copy_from: str
    name: str = Field(min_length=1, max_length=200)


class DuplicateIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)


class FromProjectIn(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=200)


class TemplateStatusIn(BaseModel):
    status: Literal["Active", "Inactive"]
