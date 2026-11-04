"""Request bodies for projects (the Airtable Session table)."""

from datetime import date

from pydantic import BaseModel, Field, field_validator

DRIVE_PREFIX = "https://drive.google.com/"


class OneOffIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    due_date: date
    role_id: str | None = None
    user_id: str | None = None
    needs_first: list[str] = []


class ProjectDetailsIn(BaseModel):
    """Every field from the New Project form except the task choices."""

    name: str | None = Field(default=None, max_length=200)
    site_id: str | None = None
    site_type: str | None = None
    day_one: date | None = None
    end_date: date | None = None
    program_hours: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    instructor_ids: list[str] | None = None
    partner_name: str | None = Field(default=None, max_length=200)
    partner_email: str | None = Field(default=None, max_length=200)
    partner_phone: str | None = Field(default=None, max_length=50)
    shipping_address: str | None = Field(default=None, max_length=1000)
    drive_folder: str | None = Field(default=None, max_length=1000)
    partner_ids: list[str] | None = None

    @field_validator("drive_folder")
    @classmethod
    def drive_link(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if value and not value.startswith(DRIVE_PREFIX):
            raise ValueError("The Google Drive folder must start with https://drive.google.com/")
        return value or None

    @field_validator("partner_email")
    @classmethod
    def email_shape(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if value and ("@" not in value or " " in value):
            raise ValueError("The partner email does not look right")
        return value or None


class ProjectPreviewIn(BaseModel):
    template_id: str | None = None
    from_project_id: str | None = None
    day_one: date | None = None
    end_date: date | None = None
    assignments: dict[str, str | None] = {}
    overrides: dict[str, str | None] = {}
    one_offs: list[OneOffIn] = []


class ProjectCreateIn(ProjectDetailsIn, ProjectPreviewIn):
    name: str = Field(min_length=1, max_length=200)
    site_id: str
    day_one: date
    update_site_profile: bool = True


class MoveDayOneIn(BaseModel):
    new_day_one: date
    preview: bool = False


class UndoIn(BaseModel):
    batch: str = Field(min_length=1, max_length=40)


class CloseIn(BaseModel):
    skip_open: bool = False
