"""Add the fields and tables the app needs to the Airtable base.

Run from the backend folder:

    python -m jobs.migrate_airtable            Dry run: prints what it would add
    python -m jobs.migrate_airtable --apply    Adds what is missing

It only ever adds. It never deletes, renames or changes an existing field, table or
record, so it is safe to run any number of times. The token needs the
schema.bases:write scope.

Two kinds of change cannot be made through Airtable's metadata API, which does not
allow adding options to an existing select field:

- The "Partner" Access Level on Users
- The new Activity Log Types (Link, Task Added, Handoff, Project Created, Project
  Closed)

The app writes those with typecast, which makes Airtable add the option the first
time it is used. Admins can also add them by hand in Airtable.
"""

import argparse
import sys

from app.airtable.client import get_base, is_configured
from app.airtable.schema import (
    SITE_TYPES,
    ActivityLog,
    Links,
    Reminders,
    Session,
    Site,
    Steps,
    TemplateList,
    TemplateVersions,
    Users,
    Work,
)
from app.config import get_settings


def text():
    return ("singleLineText", None)


def long_text():
    return ("multilineText", None)


def number(precision: int = 0):
    return ("number", {"precision": precision})


def date_field():
    return ("date", {"dateFormat": {"name": "iso"}})


def date_time():
    return (
        "dateTime",
        {
            "dateFormat": {"name": "iso"},
            "timeFormat": {"name": "24hour"},
            "timeZone": get_settings().APP_TIMEZONE,
        },
    )


def checkbox():
    return ("checkbox", {"icon": "check", "color": "greenBright"})


def select(*choices: str):
    return ("singleSelect", {"choices": [{"name": c} for c in choices]})


def link(table_name: str):
    # Filled in with the real table ID once the base's schema is read.
    return ("multipleRecordLinks", {"linkedTableName": table_name})


# Fields to add to tables that already exist: {table: [(field, (type, options))]}
NEW_FIELDS = {
    Site.TABLE: [
        (Site.SITE_TYPE, select(*SITE_TYPES)),
        (Site.PARTNER_CONTACT_NAME, text()),
        (Site.PARTNER_CONTACT_EMAIL, ("email", None)),
        (Site.PARTNER_CONTACT_PHONE, ("phoneNumber", None)),
        (Site.SHIPPING_ADDRESS, long_text()),
        (Site.LAST_HEAD_COACH, text()),
        (Site.DRIVE_FOLDER, ("url", None)),
    ],
    Session.TABLE: [
        (Session.PROGRAM_NAME, text()),
        (Session.SITE_TYPE, select(*SITE_TYPES)),
        (Session.LOCATION, text()),
        (Session.PARTNER_CONTACT_NAME, text()),
        (Session.PARTNER_CONTACT_EMAIL, ("email", None)),
        (Session.PARTNER_CONTACT_PHONE, ("phoneNumber", None)),
        (Session.SHIPPING_ADDRESS, long_text()),
        (Session.DRIVE_FOLDER, ("url", None)),
        (Session.TEMPLATE_VERSION, number()),
        (Session.CREATED_FROM, link(Session.TABLE)),
        (Session.CLOSED_DATE, date_field()),
        (Session.PARTNERS, link(Users.TABLE)),
    ],
    Work.TABLE: [
        (Work.ROLE, link("Roles")),
        (Work.DEPENDS_ON, link(Work.TABLE)),
        (Work.ONE_OFF, checkbox()),
        (Work.SORT_ORDER, number(1)),
        (Work.COMPLETED_BY, link(Users.TABLE)),
        (Work.TASK_NAME, text()),
        (Work.ANCHOR, text()),
        (Work.DAYS_BEFORE_ANCHOR, number()),
        (Work.DUE_DATE_OVERRIDE, date_field()),
        # Written only by the Google Calendar automations. "Calendar Last Synced"
        # is a Last modified time field, which the API cannot create: add it by hand.
        (Work.CALENDAR_EVENT_ID, text()),
        (Work.CALENDAR_SYNCED_KEY, long_text()),
    ],
    Steps.TABLE: [
        (Steps.SORT_ORDER, number(1)),
        (Steps.ADDED_IN_VERSION, number()),
        (Steps.RETIRED_IN_VERSION, number()),
    ],
    TemplateList.TABLE: [
        (TemplateList.LIVE_VERSION, number()),
        (TemplateList.DESCRIPTION, text()),
    ],
    ActivityLog.TABLE: [
        (ActivityLog.VISIBILITY, select("Internal", "Shared")),
        (ActivityLog.BATCH, text()),
    ],
    Users.TABLE: [
        (Users.WELCOME_EMAIL_SENT, date_time()),
        (Users.CALENDAR_FEED_TOKEN, text()),
    ],
}

# New tables: {table: [(field, (type, options))]}. The first field is the primary.
NEW_TABLES = {
    Links.TABLE: [
        (Links.TITLE, text()),
        (Links.URL, ("url", None)),
        (Links.KIND, select("Google Drive", "Canva", "Other", "File")),
        (Links.WORK, link(Work.TABLE)),
        (Links.SESSION, link(Session.TABLE)),
        (Links.ADDED_BY, link(Users.TABLE)),
        (Links.FILE, ("multipleAttachments", None)),
    ],
    Reminders.TABLE: [
        (Reminders.NAME, text()),
        (Reminders.WORK, link(Work.TABLE)),
        (Reminders.RECIPIENT, link(Users.TABLE)),
        (
            Reminders.KIND,
            select(
                "7 Days Before",
                "Due Date",
                "Custom",
                "Weekly Digest",
                "Assignment",
                "Welcome",
            ),
        ),
        (Reminders.SEND_ON, date_field()),
        (Reminders.STATUS, select("Scheduled", "Sent", "Failed", "Skipped", "Cancelled")),
        (Reminders.SENT_AT, date_time()),
        (Reminders.ERROR, long_text()),
        (Reminders.CREATED_BY, link(Users.TABLE)),
        (Reminders.NOTE, long_text()),
    ],
    TemplateVersions.TABLE: [
        (TemplateVersions.NAME, text()),
        (TemplateVersions.TEMPLATE, link(TemplateList.TABLE)),
        (TemplateVersions.VERSION, number()),
        (TemplateVersions.STATUS, select("Draft", "Live", "Retired")),
        (TemplateVersions.STEPS_JSON, long_text()),
        (TemplateVersions.CHANGE_NOTE, long_text()),
        (TemplateVersions.PUBLISHED_AT, date_time()),
        (TemplateVersions.PUBLISHED_BY, link(Users.TABLE)),
    ],
}


def resolve(options, table_ids: dict[str, str]):
    """Swap a link's table name for the real table ID."""
    if options and "linkedTableName" in options:
        return {"linkedTableId": table_ids[options["linkedTableName"]]}
    return options


def plan(base):
    """Return (tables_to_create, fields_to_create) compared to the real base."""
    schema = base.schema(force=True)
    existing = {t.name: {f.name for f in t.fields} for t in schema.tables}
    tables = [name for name in NEW_TABLES if name not in existing]
    fields = []
    for table, specs in NEW_FIELDS.items():
        if table not in existing:
            print(f"! Table {table} is missing from the base. Skipping its fields.")
            continue
        for name, spec in specs:
            if name not in existing[table]:
                fields.append((table, name, spec))
    # Fields missing from tables this script made on an earlier run.
    for table in NEW_TABLES:
        if table in existing:
            for name, spec in NEW_TABLES[table]:
                if name not in existing[table]:
                    fields.append((table, name, spec))
    return tables, fields


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="Make the changes")
    args = parser.parse_args(argv)

    if not is_configured():
        print("Airtable is not configured. Set AIRTABLE_TOKEN and AIRTABLE_BASE_ID.")
        return 1

    base = get_base()
    tables, fields = plan(base)
    if not tables and not fields:
        print("Nothing to add. The base already has every field and table.")
        return 0

    for name in tables:
        print(f"+ table {name} ({len(NEW_TABLES[name])} fields)")
    for table, name, (type_name, _) in fields:
        print(f"+ field {table} > {name} ({type_name})")

    if not args.apply:
        print("\nDry run. Nothing was changed. Run again with --apply to add these.")
        return 0

    table_ids = {t.name: t.id for t in base.schema(force=True).tables}
    for name in tables:
        specs = NEW_TABLES[name]
        # Create the table with its non-link fields, then add the links, so a
        # table that links to another new table still works.
        simple = [(n, s) for n, s in specs if s[0] != "multipleRecordLinks"]
        created = base.create_table(
            name,
            [
                {"name": n, "type": t, **({"options": o} if o else {})}
                for n, (t, o) in simple
            ],
        )
        table_ids[name] = created.id
        print(f"Created table {name}")
        for n, (t, o) in specs:
            if t == "multipleRecordLinks":
                base.table(created.id).create_field(n, t, options=resolve(o, table_ids))
                print(f"  added {name} > {n}")

    for table, name, (type_name, options) in fields:
        base.table(table_ids[table]).create_field(
            name, type_name, options=resolve(options, table_ids)
        )
        print(f"Added {table} > {name}")

    print("\nDone. Run python -m jobs.dump_schema to refresh docs/airtable-schema.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
