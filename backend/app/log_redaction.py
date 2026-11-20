"""Keeps secrets in URLs out of the server's access log (findings F3).

uvicorn logs the full path of every request. Two paths carry secrets:
- /calendar/<token>.ics: the token is the only key to someone's calendar feed.
- /auth/callback?code=...: Google's one-time sign-in code.
"""

import logging
import re

CALENDAR_TOKEN = re.compile(r"^/calendar/[^/?]+\.ics")


def redact_path(path: str) -> str:
    """The same path with any secret replaced, safe to write to a log."""
    if CALENDAR_TOKEN.match(path):
        return CALENDAR_TOKEN.sub("/calendar/[redacted].ics", path, count=1)
    if path.startswith("/auth/callback?"):
        return "/auth/callback?[redacted]"
    return path


def mask_email(address: str | None) -> str:
    """An address shortened for logs: mary.smith@example.org becomes m***@example.org (F13).

    Enough to tell people apart when debugging, without putting a list of everyone's
    address in the server logs.
    """
    local, at, domain = (address or "").strip().partition("@")
    if not at:
        return "***"
    return f"{local[:1]}***@{domain}"


class RedactSecretsFilter(logging.Filter):
    """Rewrites the path in uvicorn access log lines. Never drops a line."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn's access lines have args (client, method, path, http version, status).
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], redact_path(args[2]), *args[3:])
        return True


def install() -> None:
    """Attach the filter to uvicorn's access logger, once."""
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactSecretsFilter) for f in access.filters):
        access.addFilter(RedactSecretsFilter())
