"""Write docs/data-model.md from app/airtable/schema.py.

Run from backend:  python -m jobs.data_model

Every table and field comes from schema.py, so the doc cannot list a field the app
does not use. The descriptions below explain what each one is for. If you add a
field to schema.py, add a line for it here and run this again.
"""

import re
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "app" / "airtable" / "schema.py"
OUT = Path(__file__).resolve().parents[2] / "docs" / "data-model.md"

TABLES: dict[str, tuple[str, str]] = {
    # class name: (what the table holds, which features use it)
    "Users": ("One row per person who can sign in. The Status and Access Level decide who gets in and what they can do.", "Sign in, Users and roles, every assignment"),
    "TemplateList": ("One row per template (kind of launch), for example Swim Safely.", "Templates, Start a launch"),
    "Roles": ("Jobs such as Operations or Marketing. Template steps and launch teams point at roles, not people.", "Users and roles, Templates, Start a launch"),
    "Steps": ("The tasks inside a template, with their timing and default role.", "Templates, Start a launch"),
    "Region": ("Groups of sites.", "Dashboard region filter"),
    "Site": ("A place where programs run, with its partner contact and shipping details (the site profile).", "Start a launch, Archive search"),
    "Session": ("One launch: one program at one site with a Day 1. The app calls this a project.", "Dashboard, Projects, Project page, Archive"),
    "Instructors": ("Lead instructors, linked to sites and launches.", "Start a launch, project cards"),
    "Work": ("One task in one launch, made from a template step or added as a one-off.", "My Tasks, Task page, Project page, reminders"),
    "SessionTeam": ("Who fills each role on one launch.", "Start a launch, hand-off, reminders when a task has no assignee"),
    "ActivityLog": ("Every change and every note. Notes are rows with Type Note.", "Project history, notes, Move Day 1 undo, Archive"),
    "Links": ("Google Drive, Canva and other links on tasks and launches.", "Task page, Project page"),
    "Reminders": ("Custom reminders people set, and a log of every reminder email sent, failed or skipped.", "Reminders panel, the daily job"),
    "TemplateVersions": ("A frozen copy of a template's steps for each published version, plus the current draft.", "Templates: drafts, publishing, version history"),
}

FIELDS: dict[tuple[str, str], str] = {
    ("Users", "EMAIL"): "The Google email they sign in with.",
    ("Users", "STATUS"): "Active can sign in. Inactive cannot.",
    ("Users", "ACCESS_LEVEL"): "Admin, Project Lead, Staff, Viewer or Partner. Sets their view and permissions.",
    ("Users", "ROLES"): "The roles this person holds. One person can hold several.",
    ("Users", "WELCOME_EMAIL_SENT"): "Set when the welcome email goes out, so it is sent once.",
    ("TemplateList", "STATUS"): "Inactive templates are hidden on Start a launch.",
    ("TemplateList", "LIVE_VERSION"): "The version new launches use.",
    ("Roles", "STATUS"): "Active, On Hold or In Active. Only active roles can be picked.",
    ("Steps", "DAYS_BEFORE_ANCHOR"): "How many days before the anchor the task is due. Negative means after.",
    ("Steps", "ANCHOR"): "Start (Day 1) or End (the last day).",
    ("Steps", "DEPENDS_ON"): "Steps that must be done first.",
    ("Steps", "RETIRED"): "Removed from the template. Kept so old launches still make sense.",
    ("Steps", "SORT_ORDER"): "The order on the Templates page.",
    ("Steps", "ADDED_IN_VERSION"): "The template version that added this step.",
    ("Steps", "RETIRED_IN_VERSION"): "The template version that removed this step.",
    ("Site", "PROGRAM_NAME"): "The site's own name, for example Rainier Beach.",
    ("Site", "SITE_TYPE"): "City pool, YMCA pool, Community pool and so on.",
    ("Site", "LAST_HEAD_COACH"): "Shown on Start a launch as a reminder of who coached last season.",
    ("Session", "NAME"): "A formula in Airtable. The app shows Program Name instead.",
    ("Session", "START_DATE"): "Day 1. Every due date is worked out from it.",
    ("Session", "DURATION_DAYS"): "How long the program runs. End Date is worked out from it.",
    ("Session", "END_DATE"): "A formula: Start Date plus Duration, minus 1.",
    ("Session", "STATUS"): "Not started, In progress or Complete. Complete means closed and in the Archive.",
    ("Session", "PROGRAM_NAME"): "The launch's name, for example Swim Safely Winter 2027.",
    ("Session", "TEMPLATE_VERSION"): "The template version this launch was made from. Publishing a new version never changes it.",
    ("Session", "CREATED_FROM"): "The past launch it was copied from, if any.",
    ("Session", "CLOSED_DATE"): "When an admin closed it.",
    ("Session", "PARTNERS"): "Partner users who can see this launch.",
    ("Work", "DUE_DATE"): "A formula: the override if there is one, otherwise the calculated date.",
    ("Work", "DUE_DATE_OVERRIDE"): "The due date the app writes. Moving Day 1 and changing a due date both write here.",
    ("Work", "ASSIGNEE"): "A lookup of the step's roles, not a person. The app does not use it for assignment.",
    ("Work", "ASSIGNED_TO"): "The people doing the task. Usually one, but can be several; each gets the reminders.",
    ("Work", "STATUS"): "Not Started, In Progress, Blocked, Done or Skipped.",
    ("Work", "COMPLETED_DATE"): "Set when the task is marked Done.",
    ("Work", "COMPLETED_BY"): "Who marked it Done.",
    ("Work", "DEPENDS_ON"): "Tasks that must be done first. An open task waiting on an open task shows as Blocked.",
    ("Work", "NOTES"): "A notes field from the original base. The app keeps notes in the Activity Log instead.",
    ("Work", "RESOURCE_LINK"): "A single link field from the original base. New links go in the Links table.",
    ("Site", "PROGRAM_LOCATION"): "The city, for example Seattle, WA. Fills in Location on a new launch.",
    ("Work", "ROLE"): "The role responsible for the task.",
    ("Work", "ONE_OFF"): "Added to this launch only, not from the template.",
    ("ActivityLog", "TYPE"): "What happened: Status Change, Date Change, Note, Reassignment and so on.",
    ("ActivityLog", "VISIBILITY"): "Internal or Shared. Partners only see Shared notes.",
    ("ActivityLog", "BATCH"): "Groups the rows of one Day 1 move, so it can be undone.",
    ("Links", "KIND"): "Google Drive, Canva or Other, worked out from the address.",
    ("Reminders", "KIND"): "7 Days Before, Due Date, Custom, Weekly Digest, Assignment or Welcome.",
    ("Reminders", "STATUS"): "Scheduled, Sent, Failed, Skipped or Cancelled. A Sent row stops the same email going out twice.",
    ("TemplateVersions", "STATUS"): "Draft, Live or Retired.",
    ("TemplateVersions", "STEPS_JSON"): "Every step in that version, saved as JSON.",
}


def parse_schema() -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """Each schema class as (class name, table name, [(constant, field, comment)])."""
    tables = []
    current = None
    for line in SCHEMA.read_text(encoding="utf-8").splitlines():
        cls = re.match(r"^class (\w+):", line)
        if cls:
            current = [cls.group(1), "", []]
            tables.append(current)
            continue
        field = re.match(r'^    ([A-Z_]+) = "([^"]+)"\s*(?:#\s*(.*))?$', line)
        if current and field:
            const, name, comment = field.group(1), field.group(2), (field.group(3) or "").strip()
            if const == "TABLE":
                current[1] = name
            else:
                current[2].append((const, name, comment))
    return [(c, t, f) for c, t, f in tables if t]


LINK_NAMES = {
    "Roles": "Roles", "Role": "Roles", "Session": "Session", "Work": "Work", "Steps": "Steps",
    "Template": "Template List", "Templates": "Template List", "Site": "Site", "Region": "Region",
    "Instructors": "Instructors", "Users": "Users", "User": "Users", "Session Team": "Session Team",
    "Activity Log": "Activity Log", "Author": "Users", "Recipient": "Users", "Added By": "Users",
    "Created By": "Users", "Published By": "Users", "Project Lead": "Users", "Blocks": "Work",
}


def default_note(name: str, comment: str) -> str:
    """A plain description for fields without one of their own."""
    if comment:
        return comment
    if name in LINK_NAMES:
        return f"Link to the {LINK_NAMES[name]} table."
    if name in ("Created",):
        return "When the row was made."
    if name in ("Unique", "ID") or "(from" in name:
        return "Worked out by Airtable. The app only reads it."
    if "Name" in name or name in ("Title",):
        return "Shown in the app."
    return "Read and written by the app."


def build() -> str:
    out = [
        "# Data model",
        "",
        "Every Airtable table and field NMU Launches uses, and what it is for. "
        "Generated from `backend/app/airtable/schema.py` by `python -m jobs.data_model`. "
        "Fields marked *added* were added by `python -m jobs.migrate_airtable`. "
        "For the full live base, including fields the app does not use, see `airtable-schema.md`.",
        "",
    ]
    for cls, table, fields in parse_schema():
        what, used_by = TABLES.get(cls, ("", ""))
        out += [f"## {table}", ""]
        if what:
            out += [what, ""]
        if used_by:
            out += [f"Used by: {used_by}.", ""]
        out += ["| Field | What it is for |", "|---|---|"]
        for const, name, comment in fields:
            added = "added by migrate_airtable" in comment
            note = FIELDS.get((cls, const)) or default_note(
                name, re.sub(r"added by migrate_airtable:?\s*", "", comment).strip()
            )
            label = f"{name} *(added)*" if added else name
            out.append(f"| {label} | {note.replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
