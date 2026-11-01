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

    DEV_ALLOW_VIEW_SWITCH: bool = False
    DEV_LOGIN_EMAIL: str = ""

    GMAIL_SENDER: str = ""
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    REMINDERS_DRY_RUN: bool = True

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @model_validator(mode="after")
    def refuse_weak_secret_in_production(self):
        # Anyone who knows this secret could forge a signed-in admin session.
        if self.is_production and (
            self.SESSION_SECRET == PLACEHOLDER_SECRET or len(self.SESSION_SECRET) < 32
        ):
            raise ValueError("SESSION_SECRET must be a random string of 32+ characters")
        # This skips Google entirely, so it must only ever run on a developer's computer.
        if self.DEV_LOGIN_EMAIL and (
            self.is_production or not self.APP_URL.startswith("http://localhost")
        ):
            raise ValueError("DEV_LOGIN_EMAIL only works on localhost, never in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
