"""A generated task (the Airtable Work table).

Not used yet. The fields will grow when My Tasks and Task detail are built.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

TaskStatus = Literal["Not Started", "In Progress", "Blocked", "Done", "Skipped"]


class Task(BaseModel):
    id: str
    name: str
    due_date: date | None = None
    status: TaskStatus = "Not Started"
