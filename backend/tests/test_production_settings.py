"""F33: production refuses settings that would quietly weaken it, and warns about a leftover bootstrap list."""

import logging

import pytest
from pydantic import ValidationError
from requests import ConnectionError as RequestsConnectionError

from app.airtable.schema import Users
from app.config import Settings
from app.routers import auth

SITE = "https://team.example.org"
GMAIL = dict(GMAIL_SENDER="programs@example.org", GMAIL_REFRESH_TOKEN="refresh",
             GOOGLE_CLIENT_ID="id.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="secret")


def make(**values) -> Settings:
    base = dict(ENV="production", APP_URL=SITE, FRONTEND_URL=SITE, SESSION_SECRET="s" * 40)
    return Settings(_env_file=None, **{**base, **values})


def test_a_correct_production_config_starts():
    assert make().is_production
    assert make(REMINDERS_DRY_RUN=False, **GMAIL).is_production


# --- https only --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["APP_URL", "FRONTEND_URL"])
def test_production_refuses_http_addresses(name):
    with pytest.raises(ValidationError, match=f"{name} must start with https://"):
        make(**{name: "http://team.example.org"})


def test_localhost_keeps_http():
    local = Settings(_env_file=None)
    assert local.APP_URL.startswith("http://") and not local.is_production


# --- CSP_MODE must be a known value ------------------------------------------------------


@pytest.mark.parametrize("mode", ["enforced", "on", "", "report_only"])
def test_unknown_csp_mode_is_refused(mode):
    with pytest.raises(ValidationError, match="CSP_MODE"):
        make(CSP_MODE=mode)


# --- Real email needs every Gmail setting -------------------------------------------------


@pytest.mark.parametrize("missing", ["GMAIL_SENDER", "GMAIL_REFRESH_TOKEN", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"])
def test_real_email_without_gmail_settings_is_refused(missing):
    values = {**GMAIL, missing: ""}
    with pytest.raises(ValidationError, match="REMINDERS_DRY_RUN=false needs"):
        make(REMINDERS_DRY_RUN=False, **values)


def test_separate_gmail_client_counts():
    assert make(REMINDERS_DRY_RUN=False, GMAIL_SENDER="a@example.org", GMAIL_REFRESH_TOKEN="r",
                GMAIL_CLIENT_ID="gid", GMAIL_CLIENT_SECRET="gsecret").is_production


def test_dry_run_needs_no_gmail_settings():
    assert make(REMINDERS_DRY_RUN=True).is_production


def test_local_real_email_is_not_checked():
    assert not Settings(_env_file=None, REMINDERS_DRY_RUN=False).is_production


# --- BOOTSTRAP_ADMIN_EMAILS ---------------------------------------------------------------


def test_bootstrap_outside_the_domain_is_refused():
    with pytest.raises(ValidationError, match="BOOTSTRAP_ADMIN_EMAILS"):
        make(ALLOWED_EMAIL_DOMAIN="example.org", BOOTSTRAP_ADMIN_EMAILS="boss@example.org, typo@exmaple.org")


def test_bootstrap_outside_the_domain_is_refused_locally_too():
    with pytest.raises(ValidationError, match="BOOTSTRAP_ADMIN_EMAILS"):
        Settings(_env_file=None, ALLOWED_EMAIL_DOMAIN="example.org", BOOTSTRAP_ADMIN_EMAILS="a@gmail.com")


def test_bootstrap_inside_the_domain_or_without_one_is_fine():
    assert make(ALLOWED_EMAIL_DOMAIN="example.org", BOOTSTRAP_ADMIN_EMAILS="Boss@Example.org")
    assert make(BOOTSTRAP_ADMIN_EMAILS="someone@gmail.com")


def test_warns_when_an_active_admin_already_exists(settings, caplog):
    settings(BOOTSTRAP_ADMIN_EMAILS="admin@example.org")
    with caplog.at_level(logging.WARNING, logger="app.routers.auth"):
        assert auth.warn_if_bootstrap_not_needed() is True
    assert "Remove BOOTSTRAP_ADMIN_EMAILS" in caplog.text
    assert "admin@example.org" not in caplog.text  # No emails in the logs


def test_no_warning_before_the_first_admin(settings, fake, caplog):
    settings(BOOTSTRAP_ADMIN_EMAILS="new@example.org")
    for row in fake.rows(Users.TABLE):
        if row["fields"].get(Users.ACCESS_LEVEL) == "Admin":
            row["fields"][Users.STATUS] = "Inactive"
    with caplog.at_level(logging.WARNING):
        assert auth.warn_if_bootstrap_not_needed() is False
    assert "BOOTSTRAP" not in caplog.text


def test_no_warning_when_the_list_is_empty(caplog):
    assert auth.warn_if_bootstrap_not_needed() is False


def test_airtable_down_does_not_stop_startup(settings, monkeypatch, caplog):
    settings(BOOTSTRAP_ADMIN_EMAILS="admin@example.org")

    def down(*args, **kwargs):
        raise RequestsConnectionError("down")

    monkeypatch.setattr(auth.client, "all_records", down)
    with caplog.at_level(logging.WARNING):
        assert auth.warn_if_bootstrap_not_needed() is False
    assert "Could not check" in caplog.text
