"""Google sign in with OAuth 2.0, using authlib."""

from authlib.integrations.starlette_client import OAuth

from app.config import get_settings

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

oauth = OAuth()
oauth.register(
    name="google",
    client_id=get_settings().GOOGLE_CLIENT_ID,
    client_secret=get_settings().GOOGLE_CLIENT_SECRET,
    server_metadata_url=GOOGLE_DISCOVERY_URL,
    client_kwargs={"scope": "openid email profile"},
)


def callback_url() -> str:
    """Must exactly match a redirect URL on the Google OAuth client."""
    return f"{get_settings().APP_URL.rstrip('/')}/auth/callback"


def allowed_domain() -> str:
    return get_settings().ALLOWED_EMAIL_DOMAIN.strip().lower()


def email_allowed(email: str, hosted_domain: str | None) -> bool:
    """Check the account against ALLOWED_EMAIL_DOMAIN, if that is set.

    Both must match: the email's domain, and Google's "hd" (hosted domain) claim (findings
    F32). Google only sends "hd" for accounts that the organisation's Google Workspace
    manages. Without that check, a personal Google account made with a work address (for
    example by a former employee before their mailbox closed) would also get in.
    """
    domain = allowed_domain()
    if not domain:
        return True
    return email.strip().lower().endswith(f"@{domain}") and (hosted_domain or "").strip().lower() == domain
