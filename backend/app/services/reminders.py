"""Task reminders. Stub: no logic yet."""


def tasks_due_in(days: int) -> list[dict]:
    """Return open tasks due exactly this many days from today.

    TODO: read the Work table. Returns nothing for now, so the job can run safely.
    """
    return []


def build_reminder_email(task: dict) -> tuple[str, str]:
    """Return the (subject, body) of the reminder email for a task."""
    raise NotImplementedError
