"""Task timelines. Stub: no logic yet."""


def generate_timeline(session_id: str) -> None:
    """Create Work records from the template's Steps.

    Uses Days Before Anchor and Anchor (Start or End) for each due date, assigns
    owners from Session Team by role, then sets Timeline Generated At.
    """
    raise NotImplementedError


def shift_day_one(session_id: str, new_start_date: str) -> None:
    """Move Day 1. Moves open tasks only, and keeps finished tasks' dates."""
    raise NotImplementedError


def find_blocked_tasks(session_id: str) -> list[dict]:
    """Return tasks that cannot start, using Depends On."""
    raise NotImplementedError


def find_at_risk_tasks(session_id: str) -> list[dict]:
    """Return tasks at risk because something they depend on is late."""
    raise NotImplementedError
