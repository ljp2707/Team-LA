"""A project: one program launch at one site (the Airtable Session table).

Not used yet. The fields will grow when the Dashboard and project pages are built.
"""

from datetime import date

from pydantic import BaseModel


class Project(BaseModel):
    id: str
    name: str
    day_one: date | None = None
    status: str | None = None
