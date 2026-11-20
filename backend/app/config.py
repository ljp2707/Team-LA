"""App settings, read from environment variables (or a local .env file)."""

from functools import lru_cache
from urllib.parse import urlparse
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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
    # Sign people out after this many hours without using the app (findings F15).
    SESSION_IDLE_HOURS: int = Field(default=24, ge=1)

    AIRTABLE_TOKEN: str = ""
    AIRTABLE_BASE_ID: str = ""

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    ALLOWED_EMAIL_DOMAIN: str = ""
    # Comma separated. These people get an Admin row on first sign in if they have none.
    BOOTSTRAP_ADMIN_EMAILS: str = ""

    APP_TIMEZONE: str = "America/Los_Angeles"

    # Content-Security-Policy (findings F1, F28): "enforce" blocks anything outside the
    # policy, "report-only" only reports it (useful for trying a policy change on the live
    # site first), "off" sends no policy. Enforced by default since the browser test
    # (frontend/e2e) showed every page works under it.
    CSP_MODE: Literal["off", "report-only", "enforce"] = "enforce"

    # Extra host names the app answers to, comma separated, such as a custom domain.
    # The hosts of APP_URL and FRONTEND_URL are always allowed; localhost only outside
    # production. Requests for any other host get 400.
    ALLOWED_HOSTS: str = ""
    # Which proxies uvicorn believes about the visitor's address and https (the
    # X-Forwarded-For and X-Forwarded-Proto headers). Read by uvicorn from the
    # environment in the Dockerfile. "*" is right on Railway: its proxy has no fixed
    # address, and the app can only be reached through it.
    FORWARDED_ALLOW_IPS: str = "*"

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
        # An https address means a real deployment, so a missing ENV can't turn off
        # the production checks below (findings F12).
        return self.ENV == "production" or self.APP_URL.strip().lower().startswith("https://")

    @property
    def allowed_hosts(self) -> list[str]:
        """Host names the app answers to. Others get 400 (findings F14)."""
        hosts = {urlparse(self.APP_URL).hostname, urlparse(self.FRONTEND_URL).hostname}
        hosts |= {h.strip().lower() for h in self.ALLOWED_HOSTS.split(",")}
        hosts.add("healthcheck.railway.app")  # Railway's deploy health check
        if not self.is_production:
            hosts |= {"localhost", "127.0.0.1", "testserver"}  # Laptops and pytest
        return sorted(h for h in hosts if h)

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
        # It lets any signed-in person use admin view with admin permissions (findings F4).
        if self.DEV_ALLOW_VIEW_SWITCH and self.is_production:
            raise ValueError("DEV_ALLOW_VIEW_SWITCH must be false in production")
        self._refuse_unsafe_production_settings()
        self._refuse_bootstrap_outside_domain()
        return self

    def _refuse_unsafe_production_settings(self) -> None:
        """Settings that would quietly weaken a live site (findings F33)."""
        if not self.is_production:
            return
        # Over http the session cookie (Secure, __Host-) and Google sign in would not work,
        # and nothing would be encrypted.
        for name in ("APP_URL", "FRONTEND_URL"):
            if not getattr(self, name).strip().lower().startswith("https://"):
                raise ValueError(f"{name} must start with https:// in production")
        # Real email on, but nothing to send it with: every reminder would fail.
        if not self.REMINDERS_DRY_RUN:
            missing = [
                name
                for name, value in (
                    ("GMAIL_SENDER", self.GMAIL_SENDER),
                    ("GMAIL_REFRESH_TOKEN", self.GMAIL_REFRESH_TOKEN),
                    ("GMAIL_CLIENT_ID or GOOGLE_CLIENT_ID", self.gmail_client_id),
                    ("GMAIL_CLIENT_SECRET or GOOGLE_CLIENT_SECRET", self.gmail_client_secret),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(
                    "REMINDERS_DRY_RUN=false needs these settings in production: " + ", ".join(missing)
                )

    def _refuse_bootstrap_outside_domain(self) -> None:
        """A bootstrap admin who could never sign in is a typo, or an address that should not
        be there (findings F33)."""
        domain = self.ALLOWED_EMAIL_DOMAIN.strip().lower()
        if domain and any(not email.endswith(f"@{domain}") for email in self.bootstrap_admins):
            raise ValueError("Every BOOTSTRAP_ADMIN_EMAILS address must be in ALLOWED_EMAIL_DOMAIN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
