"""Refuses oversized requests before anything else reads them (findings F6).

FastAPI reads a whole upload before it checks who is signed in, and nothing else
caps the size, so without this a stranger could fill the server's disk.
"""

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MB = 1024 * 1024
# A 5 MB file (the Airtable limit in services/links.py) plus the form around it.
UPLOAD_LIMIT_BYTES = 6 * MB
# Everything else. The largest real request, a 200-step template draft, is about 1.1 MB.
DEFAULT_LIMIT_BYTES = 2 * MB
# CSP violation reports (F25): a page sends a few small ones, so anything bigger is junk.
CSP_REPORT_LIMIT_BYTES = 64 * 1024


def limit_for(method: str, path: str) -> int:
    """The most bytes this request may send."""
    if method == "POST" and path.endswith("/files"):
        return UPLOAD_LIMIT_BYTES
    if path == "/api/security/csp-report":
        return CSP_REPORT_LIMIT_BYTES
    return DEFAULT_LIMIT_BYTES


def _message(limit: int) -> str:
    if limit == UPLOAD_LIMIT_BYTES:
        return "That file is too large. Files can be up to 5 MB."
    return "That request is too large."


class RequestSizeLimit:
    """Answers 413 when a request body is bigger than its limit.

    Checks the Content-Length header first, then counts the bytes as they arrive,
    in case the header is missing or wrong.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = limit_for(scope["method"], scope["path"])
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": _message(limit)}, status_code=413)(scope, receive, send)
            return

        received = 0

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # An HTTPException, so FastAPI turns it into a 413 answer
                    # instead of a generic "error parsing the body".
                    raise HTTPException(413, _message(limit))
            return message

        await self.app(scope, counted_receive, send)
