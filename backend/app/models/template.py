"""A launch template and its steps (the Template List and Steps tables).

Not used yet. The fields will grow when Templates is built.
"""

from typing import Literal

from pydantic import BaseModel


class TemplateStep(BaseModel):
    id: str
    short_description: str
    days_before_anchor: int = 0
    anchor: Literal["Start", "End"] = "Start"


class Template(BaseModel):
    id: str
    name: str
    status: str | None = None
