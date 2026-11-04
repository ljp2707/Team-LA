"""Request bodies for users, roles, sites and the hand-off."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.airtable.schema import SITE_TYPES

AccessLevel = Literal["Admin", "Project Lead", "Staff", "Viewer", "Partner"]


class UserIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str = Field(min_length=3, max_length=200)
    access_level: AccessLevel = "Staff"
    role_ids: list[str] = []

    @field_validator("email")
    @classmethod
    def email_shape(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or " " in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("That email does not look right")
        return value


class UserUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    access_level: AccessLevel | None = None
    role_ids: list[str] | None = None
    status: Literal["Active", "Inactive"] | None = None


class HandOffIn(BaseModel):
    from_user: str
    to_user: str
    replace_on_teams: bool = False
    preview: bool = False


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["Active", "On Hold", "In Active"] | None = None


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    site_type: str | None = None
    location: str = Field(default="", max_length=200)
    region_id: str | None = None
    partner_name: str = Field(default="", max_length=200)
    partner_email: str = Field(default="", max_length=200)
    partner_phone: str = Field(default="", max_length=50)
    shipping_address: str = Field(default="", max_length=1000)

    @field_validator("site_type")
    @classmethod
    def known_type(cls, value: str | None) -> str | None:
        if value and value not in SITE_TYPES:
            raise ValueError("Pick a site type from the list")
        return value or None
