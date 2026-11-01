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


def email_allowed(email: str) -> bool:
    """Check the email against ALLOWED_EMAIL_DOMAIN, if that is set."""
    domain = get_settings().ALLOWED_EMAIL_DOMAIN.strip().lower()
    return not domain or email.lower().endswith(f"@{domain}")
