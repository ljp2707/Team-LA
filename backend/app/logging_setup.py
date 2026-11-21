"""How the app writes its logs (findings F36).

In production every line is one JSON object, so Railway's log search (and any tool it
forwards to) can filter on fields, for example `event:"sign_in_denied"` or a request ID:

    {"time": "2026-11-20T17:00:00.123Z", "level": "WARNING", "logger": "app.security.events",
     "message": "security_event access_denied ...", "request_id": "3f2a...",
     "event": "access_denied", "status": 403, "route": "/api/users", "user": "rec123"}

On a laptop the lines stay plain text, easier to read in a terminal.

Every line written while a request is handled carries that request's ID, the same one
sent back in the X-Request-ID header, so a person's error report leads straight to the
matching log lines. JSON keeps a message with line breaks on one line, so nothing in a
message can fake a separate log line.

What must never be logged: secrets, tokens, cookies, sign-in codes, request bodies, note
text, full email addresses (see security_events.py and log_redaction.py).
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# Set by security.RequestContext for the length of each request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# uvicorn's loggers. Their own handlers are swapped for ours so every line has one format.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            line["request_id"] = request_id
        event = getattr(record, "event", None)
        if event:
            line["event"] = event
            for key, value in (getattr(record, "event_fields", None) or {}).items():
                line.setdefault(key, value)
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(levelname)s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        request_id = request_id_var.get()
        return f"{text} [request {request_id}]" if request_id else text


def install(json_lines: bool) -> None:
    """Send every log line, the app's and uvicorn's, to stdout in one format."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_lines else TextFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []  # Their filters (log_redaction) stay on the logger
        uvicorn_logger.propagate = True
