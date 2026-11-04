"""Authorize the account that sends NMU Launches email. Run once, on a laptop.

    python -m jobs.authorize_gmail

Before running:
1. Enable the Gmail API in the Google Cloud project (APIs and Services > Library).
2. Add http://localhost:8765/ (with the slash) to the OAuth client's redirect URIs.
3. Put GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env (or GMAIL_CLIENT_ID and
   GMAIL_CLIENT_SECRET to use a separate client).

A browser opens. Sign in as the sender, click Advanced, then Go to NMU Launches on
the "Google hasn't verified this app" screen, and allow sending email. The refresh
token is printed here: put it in GMAIL_REFRESH_TOKEN, and set GMAIL_SENDER to the
same address you signed in with.
"""

import sys

from app.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
PORT = 8765


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Run pip install -r requirements.txt first (needs google-auth-oauthlib).")
        return 1

    settings = get_settings()
    client_id, client_secret = settings.gmail_client_id, settings.gmail_client_secret
    if not client_id or not client_secret or not settings.google_configured:
        print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first.")
        return 1

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [f"http://localhost:{PORT}/"],
        }
    }
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    credentials = flow.run_local_server(
        port=PORT,
        access_type="offline",
        prompt="consent",
        open_browser=True,
        success_message="NMU Launches can now send email. You can close this tab.",
    )
    if not credentials.refresh_token:
        print("Google did not return a refresh token. Run this again.")
        return 1
    print("\nGMAIL_REFRESH_TOKEN=" + credentials.refresh_token)
    print("\nPut that line in .env (and on both Railway services when deployed),")
    print("set GMAIL_SENDER to the address you just signed in with, and set")
    print("REMINDERS_DRY_RUN=false once the test email on the Users page works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
