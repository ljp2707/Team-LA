"""Sending email through Gmail. Stub: no logic yet."""


def send_email(to: str, subject: str, body: str) -> None:
    """Send one email from GMAIL_SENDER.

    TODO: Gmail API setup.
    1. In Google Cloud Console, enable the Gmail API on the same project as sign in.
    2. Create an OAuth client and authorize the sender account once, with the
       https://www.googleapis.com/auth/gmail.send scope, to get a refresh token.
    3. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN.
    4. Call users.messages.send with a base64url encoded message.
    """
    raise NotImplementedError
