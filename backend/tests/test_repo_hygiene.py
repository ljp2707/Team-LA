"""F38: nothing personal or secret in the files everyone copies, and no stray files in git."""

import re
import shutil
import subprocess

import pytest

from app.config import REPO_ROOT

EXAMPLE = REPO_ROOT / ".env.example"
# Settings that hold a secret, an address or a person: always blank in the example.
MUST_BE_BLANK = {
    "SESSION_SECRET", "AIRTABLE_TOKEN", "AIRTABLE_BASE_ID", "AIRTABLE_MIGRATION_TOKEN",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET",
    "GMAIL_REFRESH_TOKEN", "GMAIL_SENDER", "BOOTSTRAP_ADMIN_EMAILS", "DEV_LOGIN_EMAIL",
    "CONTACT_EMAIL", "ORG_ADDRESS",
}


def _example_values() -> dict[str, str]:
    values = {}
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


@pytest.mark.parametrize("name", sorted(MUST_BE_BLANK))
def test_example_leaves_secrets_and_people_blank(name):
    values = _example_values()
    if name in values:
        assert values[name] == "", f"{name} must be blank in .env.example"


def test_example_has_no_real_email_addresses():
    """A copied example must never make a former developer an admin or an email sender."""
    for address in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", EXAMPLE.read_text(encoding="utf-8")):
        assert address.lower().endswith(("@example.org", "@example.com")), address


def _tracked_files() -> list[str]:
    if not shutil.which("git") or not (REPO_ROOT / ".git").exists():
        pytest.skip("Not a git checkout")
    result = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return result.stdout.splitlines()


def test_no_stray_or_secret_files_in_git():
    bad = [
        path
        for path in _tracked_files()
        if path.endswith((".DS_Store", ".tsbuildinfo", ".pem", ".key", ".p12"))
        or path.split("/")[-1] in {".env", "credentials.json", "token.json", "launch.json", "settings.local.json"}
        or (path.split("/")[-1].startswith(".env.") and path != ".env.example")
    ]
    assert bad == []
