"""Production safety settings: findings F2, F4 and F12 in docs/security/findings.md."""

import pytest
from pydantic import ValidationError

from app.config import PLACEHOLDER_SECRET, Settings

STRONG_SECRET = "s" * 40


def make(**values) -> Settings:
    """Build settings from these values only, never from a local .env file."""
    return Settings(_env_file=None, **values)


# --- F12: production mode cannot be switched off by a missing ENV ---------------


def test_localhost_default_is_not_production():
    assert make().is_production is False


def test_https_app_url_counts_as_production_even_without_env():
    assert make(APP_URL="https://launches.example.org", SESSION_SECRET=STRONG_SECRET).is_production


def test_https_app_url_refuses_the_placeholder_secret():
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        make(APP_URL="https://launches.example.org", SESSION_SECRET=PLACEHOLDER_SECRET)


def test_https_app_url_refuses_a_short_secret():
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        make(APP_URL="https://launches.example.org", SESSION_SECRET="short")


# --- F4: the dev view switch is refused in production -----------------------------


def test_view_switch_is_refused_in_production():
    with pytest.raises(ValidationError, match="DEV_ALLOW_VIEW_SWITCH"):
        make(ENV="production", SESSION_SECRET=STRONG_SECRET, DEV_ALLOW_VIEW_SWITCH=True)


def test_view_switch_is_refused_on_an_https_app_url():
    with pytest.raises(ValidationError, match="DEV_ALLOW_VIEW_SWITCH"):
        make(APP_URL="https://launches.example.org", SESSION_SECRET=STRONG_SECRET, DEV_ALLOW_VIEW_SWITCH=True)


def test_view_switch_still_works_on_localhost():
    assert make(DEV_ALLOW_VIEW_SWITCH=True).DEV_ALLOW_VIEW_SWITCH is True


def test_production_starts_with_the_view_switch_off():
    assert make(ENV="production", SESSION_SECRET=STRONG_SECRET).is_production


# --- F2: no API docs in production ------------------------------------------------


def test_api_docs_are_off_in_production():
    from app.main import api_docs_urls

    urls = api_docs_urls(make(ENV="production", SESSION_SECRET=STRONG_SECRET))
    assert urls == {"docs_url": None, "redoc_url": None, "openapi_url": None}


def test_api_docs_stay_on_localhost(client):
    from app.main import api_docs_urls

    assert api_docs_urls(make())["docs_url"] == "/docs"
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
