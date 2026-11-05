"""Sending email through the Gmail API, over HTTPS.

Why not SMTP: Railway blocks outbound SMTP below its Pro plan, and NMU asked for no
extra email service. The Gmail API works on any plan.

Setup (see the README section "Set up email"):
1. Enable the Gmail API on the same Google Cloud project as sign in.
2. Run `python -m jobs.authorize_gmail` once, signed in as the sender account.
3. Put the printed token in GMAIL_REFRESH_TOKEN and set GMAIL_SENDER.

GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET default to the Google sign in client, so one
OAuth client can do both jobs.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
FROM_NAME = "NMU Launches"
TIMEOUT_SECONDS = 20

EXPIRED_MESSAGE = (
    "The Gmail authorization has expired or been revoked. "
    "Re-run python -m jobs.authorize_gmail."
)


class EmailError(Exception):
    """Sending failed. The message is safe to show to an admin."""


_token_lock = threading.Lock()
_token: dict[str, float | str] = {}


def _clear_token() -> None:
    with _token_lock:
        _token.clear()


def get_access_token() -> str:
    """Swap the refresh token for an access token, cached until 60 seconds before expiry."""
    with _token_lock:
        if _token and float(_token["expires_at"]) > time.time():
            return str(_token["value"])

    settings = get_settings()
    if not settings.GMAIL_REFRESH_TOKEN:
        raise EmailError(
            "Email is not set up yet. Run python -m jobs.authorize_gmail and set "
            "GMAIL_REFRESH_TOKEN."
        )
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        raise EmailError("Email is not set up: the Google client ID or secret is missing.")
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.gmail_client_id,
                "client_secret": settings.gmail_client_secret,
                "refresh_token": settings.GMAIL_REFRESH_TOKEN,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        raise EmailError(f"Could not reach Google to get a Gmail token ({type(error).__name__}).") from error
    if response.status_code != 200:
        body = _safe_json(response)
        if body.get("error") == "invalid_grant":
            raise EmailError(EXPIRED_MESSAGE)
        raise EmailError(
            f"Google refused the Gmail token request: {body.get('error_description') or body.get('error') or response.status_code}"
        )
    body = response.json()
    with _token_lock:
        _token["value"] = body["access_token"]
        _token["expires_at"] = time.time() + int(body.get("expires_in", 3600)) - 60
    return body["access_token"]


def _safe_json(response: httpx.Response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def build_message(to: str, subject: str, text: str, html: str) -> EmailMessage:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = formataddr((FROM_NAME, settings.GMAIL_SENDER))
    message["To"] = to
    message["Subject"] = subject
    # Lets mail apps show their own "Unsubscribe" button. It opens an email to NMU.
    contact = settings.CONTACT_EMAIL or settings.GMAIL_SENDER
    if contact:
        message["List-Unsubscribe"] = f"<mailto:{contact}?subject=Stop%20NMU%20Launches%20emails>"
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


def send_email(to: str, subject: str, text: str, html: str) -> str | None:
    """Send one email from GMAIL_SENDER. Returns the Gmail message ID.

    With REMINDERS_DRY_RUN=true this only logs the recipient and subject.
    Retries once on a 5xx answer or a timeout. Raises EmailError on failure.
    """
    settings = get_settings()
    if settings.REMINDERS_DRY_RUN:
        logger.info("Dry run email to %s: %s", to, subject)
        return None
    if not settings.GMAIL_SENDER:
        raise EmailError("Email is not set up: GMAIL_SENDER is empty.")

    raw = base64.urlsafe_b64encode(build_message(to, subject, text, html).as_bytes()).decode()
    last_error = ""
    for attempt in range(2):
        token = get_access_token()
        try:
            response = httpx.post(
                SEND_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": raw},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            last_error = "Gmail did not answer in time."
            continue
        except httpx.HTTPError as error:
            raise EmailError(f"Could not reach Gmail ({type(error).__name__}).") from error
        if response.status_code < 300:
            return _safe_json(response).get("id")
        body = _safe_json(response)
        error = body.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        if response.status_code == 401:
            # The cached access token went bad. Get a new one and try once more.
            _clear_token()
            last_error = message or "Gmail said the token is not valid."
            if attempt == 0:
                continue
        if error == "invalid_grant" or (message and "invalid_grant" in str(message)):
            raise EmailError(EXPIRED_MESSAGE)
        if response.status_code >= 500 and attempt == 0:
            last_error = message or f"Gmail error {response.status_code}"
            continue
        raise EmailError(f"Gmail refused the email: {message or response.status_code}")
    raise EmailError(last_error or "Gmail did not accept the email.")
