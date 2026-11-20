"""Serve the built app on a local port for the browser test (findings F28).

    python tests/e2e_server.py --email admin@example.org --port 8301

The data is the same in-memory fake Airtable the backend tests use, so the browser test
never reaches the real Airtable base, Google or Gmail, and it works in CI. Sign-in is the
DEV_LOGIN_EMAIL shortcut, so each server is signed in as one person. The policy is
CSP_MODE=enforce, so anything it blocks breaks the page and fails the test.

Not part of the app: it lives in tests/ and is not copied into the Docker image.
"""

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Importing conftest sets the test environment (no real Airtable, Google or Gmail) before
# the app is imported, and gives us the same fake base and people the tests use.
from tests.conftest import FakeAirtable, person  # noqa: E402

import uvicorn  # noqa: E402

from app import main  # noqa: E402
from app.airtable import client as airtable  # noqa: E402
from app.airtable.schema import AuditLog, Roles, Session, Site, Users, Work  # noqa: E402
from app.config import get_settings  # noqa: E402
from tests.builders import add_project, add_site, add_task, standard_project  # noqa: E402

FRONTEND_DIST = BACKEND.parent / "frontend" / "dist"


def seeded_base() -> FakeAirtable:
    """Admin Ada, staff Sam, partner Pat; one running program and one archived one."""
    fake = FakeAirtable(
        {
            Users.TABLE: [
                person("recAdmin", "Admin@Example.org", "Admin", first="Ada"),
                person("recStaff", "staff@example.org", "Staff", first="Sam"),
                person("recPartner", "partner@example.org", "Partner", roles=(), first="Pat"),
            ],
            Roles.TABLE: [{"id": "recRole", "fields": {Roles.NAME: "Program Manager", Roles.STATUS: "Active"}}],
        }
    )
    standard_project(fake)
    # City and State, so the My Tasks location filters appear
    site = fake.find(Site.TABLE, "recSite")["fields"]
    site[Site.CITY], site[Site.STATE] = "Seattle", "WA"
    # The partner is on the program and has one task, so their pages have something to show
    fake.find(Session.TABLE, "recProj")["fields"][Session.PARTNERS] = ["recPartner"]
    fake.find(Work.TABLE, "recT6")["fields"][Work.ASSIGNED_TO] = ["recPartner"]
    # An archived program for the Archive page
    add_site(fake, "recSiteOld", "Kent Pool")
    add_project(fake, "recOld", "Kent Swim Safely 2025", start=date(2025, 6, 1), site="recSiteOld", status="Complete")
    add_task(fake, "recOld1", "Order caps", date(2025, 5, 20), project="recOld", status="Done", assigned="recStaff")
    # One admin action for the Audit page
    fake.add(AuditLog.TABLE, {AuditLog.ACTION: "PATCH /api/users/{user_id}", AuditLog.ACTOR: "recAdmin",
                              AuditLog.WHEN: datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              AuditLog.TARGET: "user_id=recStaff", AuditLog.STATUS: 200, AuditLog.REQUEST_ID: "e2e"})
    return fake


def main_() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="who DEV_LOGIN_EMAIL signs in as")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not (FRONTEND_DIST / "index.html").is_file():
        sys.exit("Build the frontend first: cd frontend && npm run build")

    fake = seeded_base()
    airtable.all_records = fake.all_records
    airtable.create_records = fake.create_records
    airtable.update_records = fake.update_records
    airtable.delete_records = fake.delete_records
    airtable.upload_attachment = fake.upload_attachment
    main.STATIC_DIR = FRONTEND_DIST

    # These are read on every request, so changing them after import takes effect.
    origin = f"http://127.0.0.1:{args.port}"
    settings = get_settings()
    settings.CSP_MODE = "enforce"
    settings.DEV_LOGIN_EMAIL = args.email
    settings.APP_URL = origin
    settings.FRONTEND_URL = origin

    # As in the Dockerfile: no Server header. No lifespan: it would warm the real cache.
    uvicorn.run(main.app, host="127.0.0.1", port=args.port, lifespan="off", server_header=False, log_level="warning")


if __name__ == "__main__":
    main_()
