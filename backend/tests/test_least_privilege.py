"""F37: each credential has only the access it needs."""

import pytest
from pydantic import ValidationError
from requests import HTTPError, Response

from app.airtable import client
from app.config import Settings
from jobs import authorize_gmail, dump_schema, migrate_airtable

SITE = "https://team.example.org"


@pytest.fixture
def airtable_set_up(settings):
    settings(AIRTABLE_TOKEN="patAppToken.123", AIRTABLE_BASE_ID="appBase")


# --- The schema scripts need their own token -----------------------------------------------


@pytest.mark.parametrize("job", [migrate_airtable, dump_schema])
def test_scripts_refuse_without_a_migration_token(job, airtable_set_up, capsys):
    result = job.main([]) if job is migrate_airtable else job.main()
    assert result == 1
    assert "Set AIRTABLE_MIGRATION_TOKEN" in capsys.readouterr().out


@pytest.mark.parametrize("job", [migrate_airtable, dump_schema])
def test_scripts_refuse_the_apps_own_token(job, airtable_set_up, settings, capsys):
    settings(AIRTABLE_MIGRATION_TOKEN=" patAppToken.123 ")
    result = job.main([]) if job is migrate_airtable else job.main()
    assert result == 1
    assert "is the app's own token" in capsys.readouterr().out


def test_migration_base_uses_the_migration_token(airtable_set_up, settings):
    settings(AIRTABLE_MIGRATION_TOKEN="patMigration.456")
    base = client.migration_base()
    assert base.api.api_key == "patMigration.456" and base.id == "appBase"


def test_migration_token_is_refused_in_production():
    with pytest.raises(ValidationError, match="AIRTABLE_MIGRATION_TOKEN must not be set in production"):
        Settings(_env_file=None, ENV="production", APP_URL=SITE, FRONTEND_URL=SITE, SESSION_SECRET="s" * 40,
                 AIRTABLE_MIGRATION_TOKEN="patMigration.456")


def test_migration_token_is_fine_on_a_laptop():
    assert Settings(_env_file=None, AIRTABLE_MIGRATION_TOKEN="patMigration.456").AIRTABLE_MIGRATION_TOKEN


# --- Production startup notices a token with schema access ---------------------------------


class _Base:
    def __init__(self, outcome):
        self.outcome = outcome

    def schema(self, force=False):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return "schema"


def _http_error(status: int) -> HTTPError:
    response = Response()
    response.status_code = status
    return HTTPError(response=response)


@pytest.mark.parametrize(
    "outcome, expected",
    [("ok", True), (_http_error(403), False), (_http_error(401), False), (_http_error(500), None), (ConnectionError(), None)],
)
def test_token_can_read_schema(monkeypatch, outcome, expected):
    monkeypatch.setattr(client, "get_base", lambda: _Base(outcome))
    assert client.token_can_read_schema() is expected


def test_warns_when_the_token_is_too_broad(monkeypatch, airtable_set_up, caplog):
    monkeypatch.setattr(client, "get_base", lambda: _Base("ok"))
    with caplog.at_level("WARNING", logger="app.security.events"):
        client.warn_if_token_too_broad()
    assert any(getattr(r, "event", "") == "airtable_token_too_broad" for r in caplog.records)
    assert "patAppToken" not in caplog.text


def test_quiet_when_the_token_is_narrow(monkeypatch, airtable_set_up, caplog):
    monkeypatch.setattr(client, "get_base", lambda: _Base(_http_error(403)))
    with caplog.at_level("WARNING", logger="app.security.events"):
        client.warn_if_token_too_broad()
    assert caplog.records == []


# --- Gmail: send only ----------------------------------------------------------------------


def test_gmail_asks_only_to_send():
    """Not read, not modify: a leaked refresh token can send mail but never read the inbox."""
    assert authorize_gmail.SCOPES == ["https://www.googleapis.com/auth/gmail.send"]
