"""Project history. Stub: no logic yet."""


def log_event(
    session_id: str,
    work_id: str | None,
    author_id: str | None,
    type: str,
    text: str,
    from_value: str | None = None,
    to_value: str | None = None,
) -> None:
    """Write one Activity Log entry.

    Type is one of: Note, Status Change, Date Change, Reassignment, System.
    """
    raise NotImplementedError
