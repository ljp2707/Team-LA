"""Security events: one log line per thing worth watching (findings F34, F36).

Every event goes to the "app.security.events" logger with an event name and a few
fields, for example:

    security_event("sign_in_denied", reason="not_in_users")

docs/security/monitoring.md lists every event and what to alert on.

Fields must never hold secrets, tokens, cookies, sign-in codes, request bodies, note text
or full email addresses. Use record IDs, and log_redaction.mask_email for an address.
Values are cut to one short line so nobody can forge extra log lines.
"""

import logging

logger = logging.getLogger("app.security.events")

MAX_VALUE_LENGTH = 200


def clean(value) -> str | int | float | bool | None:
    """A value safe for one log line: numbers and booleans as they are, text on one line."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = "".join(ch if ch.isprintable() else " " for ch in str(value))
    return text[:MAX_VALUE_LENGTH]


def security_event(name: str, level: int = logging.INFO, **fields) -> None:
    cleaned = {key: clean(value) for key, value in fields.items()}
    details = " ".join(f"{key}={value}" for key, value in cleaned.items())
    logger.log(level, "security_event %s %s", name, details, extra={"event": name, "event_fields": cleaned})
