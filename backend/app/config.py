"""App settings, read from environment variables (or a local .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_SECRET = "replace-with-a-long-random-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        extra="ignore",
    )

    ENV: str = "development"
    APP_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    SESSION_SECRET: str = PLACEHOLDER_SECRET

    AIRTABLE_TOKEN: str = ""
    AIRTABLE_BASE_ID: str = ""

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    ALLOWED_EMAIL_DOMAIN: str = ""
    # Comma separated. These people get an Admin row on first sign in if they have none.
    BOOTSTRAP_ADMIN_EMAILS: str = ""

    APP_TIMEZONE: str = "America/Los_Angeles"

    DEV_ALLOW_VIEW_SWITCH: bool = False
    DEV_LOGIN_EMAIL: str = ""

    GMAIL_SENDER: str = ""
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    REMINDERS_DRY_RUN: bool = True

    # Shown on the Privacy and Terms pages and at the bottom of every email.
    ORG_NAME: str = "No More Under"
    CONTACT_EMAIL: str = ""  # Where privacy questions, data requests and "stop emailing me" go
    ORG_ADDRESS: str = ""  # Mailing address, one line

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def bootstrap_admins(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.BOOTSTRAP_ADMIN_EMAILS.split(",")
            if email.strip()
        }

    @property
    def google_configured(self) -> bool:
        """False while the client ID is empty or still the .env.example placeholder."""
        client_id = self.GOOGLE_CLIENT_ID.strip()
        return bool(client_id) and not client_id.endswith(
            "replace-me.apps.googleusercontent.com"
        )

    @property
    def gmail_client_id(self) -> str:
        return self.GMAIL_CLIENT_ID or self.GOOGLE_CLIENT_ID

    @property
    def gmail_client_secret(self) -> str:
        return self.GMAIL_CLIENT_SECRET or self.GOOGLE_CLIENT_SECRET

    @model_validator(mode="after")
    def refuse_weak_secret_in_production(self):
        # Anyone who knows this secret could forge a signed-in admin session.
        if self.is_production and (
            self.SESSION_SECRET == PLACEHOLDER_SECRET or len(self.SESSION_SECRET) < 32
        ):
            raise ValueError("SESSION_SECRET must be a random string of 32+ characters")
        # A blank secret (as in .env.example) is fine on a laptop: use the dev placeholder.
        if not self.SESSION_SECRET:
            self.SESSION_SECRET = PLACEHOLDER_SECRET
        # This skips Google entirely, so it must only ever run on a developer's computer.
        if self.DEV_LOGIN_EMAIL and (
            self.is_production or not self.APP_URL.startswith("http://localhost")
        ):
            raise ValueError("DEV_LOGIN_EMAIL only works on localhost, never in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
