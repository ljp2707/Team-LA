"""Fill a TEST Airtable base with the sample data from the wireframes.

Run from the backend folder:

    python -m jobs.seed_demo --yes-this-is-a-test-base

It refuses to run when ENV=production, and refuses to run twice (it stops if
catalina@example.org is already in Users). It only ever creates new rows. It never
changes or deletes a row that was already there, although linking a new row to an
existing role makes that link show up on the role too. Roles that already exist
(matched by name) are reused, so there are no duplicates.

Every email is @example.org, so nobody real gets mail. Dates are worked out from
today, so the overdue, this week and later groups always have something in them.
The bootstrap admin from BOOTSTRAP_ADMIN_EMAILS is left alone.
"""

import argparse
import json
import sys
from datetime import date, timedelta

from app.airtable import client
from app.airtable.schema import (
    ACTIVE,
    ActivityLog,
    Instructors,
    Links,
    Region,
    Reminders,
    Roles,
    Session,
    SessionTeam,
    Site,
    Steps,
    TemplateList,
    TemplateVersions,
    Users,
    Work,
)
from app.config import get_settings
from app.services import clock
from app.services.records import load_roles, load_users
from app.services.timeline import OneOff, items_from_one_offs, items_from_steps, plan_tasks
from app.services.records import StepRec

MARKER_EMAIL = "catalina@example.org"

# (name, days before anchor, role, needs first, anchor)
SWIM_SAFELY = [
    ("Confirm head coach", 42, "Program Manager", [], "Start"),
    ("Confirm pool schedule", 42, "Operations", [], "Start"),
    ("Sign partner agreement", 40, "Program Manager", [], "Start"),
    ("Design flyer", 35, "Marketing", ["Confirm pool schedule"], "Start"),
    ("Order swim caps", 30, "Operations", [], "Start"),
    ("Community outreach", 28, "Marketing", ["Design flyer"], "Start"),
    ("Open registration", 28, "Program Assistant", ["Confirm pool schedule"], "Start"),
    ("Lifeguard roster", 21, "Operations", ["Confirm head coach"], "Start"),
    ("Ship equipment to site", 21, "Operations", ["Confirm head coach"], "Start"),
    ("Collect instructor certifications", 14, "Program Manager", ["Confirm head coach"], "Start"),
    ("Send attendance list template", 10, "Program Assistant", [], "Start"),
    ("Registration closes", 7, "Program Assistant", ["Open registration"], "Start"),
    ("Send welcome email to families", 5, "Program Assistant", ["Registration closes"], "Start"),
    ("Instructor orientation", 3, "Program Manager", ["Collect instructor certifications"], "Start"),
    ("Day 1 check-in", 0, "Program Assistant", ["Ship equipment to site", "Instructor orientation"], "Start"),
    ("Send participant survey", -7, "Program Assistant", [], "End"),
    ("Return equipment", -10, "Operations", [], "End"),
    ("Report numbers for grants", -14, "Development", ["Send participant survey"], "End"),
]
REGISTRATION = {"Open registration", "Registration closes", "Send welcome email to families"}
YMCA = [s for s in SWIM_SAFELY if s[0] not in REGISTRATION]
CITY = [
    ("Book city facility permit", 49, "Operations", [], "Start"),
    ("Confirm city insurance certificate", 35, "Program Manager", ["Book city facility permit"], "Start"),
] + SWIM_SAFELY

TEMPLATES = [
    ("Swim Safely", SWIM_SAFELY, 3, ""),
    ("Learn to Swim with YMCA", YMCA, 2, "No registration steps"),
    ("Learn to Swim with City", CITY, 1, ""),
]

ROLE_NAMES = [
    "Program Manager",
    "Marketing",
    "Operations",
    "Program Assistant",
    "Development",
    "Grants",
    "Executive Director",
]

PEOPLE = [
    # (first, last, email, access level, roles)
    ("Catalina", "", "catalina@example.org", "Admin", ["Program Manager"]),
    ("Mary", "", "mary@example.org", "Staff", ["Marketing"]),
    ("Tash", "", "tash@example.org", "Staff", ["Operations", "Program Assistant"]),
    ("Erin", "Placeholder", "erin@example.org", "Staff", ["Executive Director", "Development"]),
    ("Gabe", "Placeholder", "gabe@example.org", "Staff", ["Grants"]),
    ("Pat", "Partner", "pat.partner@example.org", "Partner", []),
    ("Vic", "Viewer", "vic.viewer@example.org", "Viewer", []),
]

SITES = [
    # (name, type, location, partner, phone, address, head coach)
    ("Rainier Beach", "Community pool", "Seattle, WA", "Dana Ortiz", "206-555-0101", "8825 Rainier Ave S, Seattle, WA 98118", "Lee Park"),
    ("Kent YMCA", "YMCA pool", "Kent, WA", "Ray Chen", "253-555-0102", "17850 SE 256th St, Covington, WA 98042", "Sam Rivera"),
    ("Federal Way", "City pool", "Federal Way, WA", "Kim Nguyen", "253-555-0103", "33325 8th Ave S, Federal Way, WA 98003", "Alex Kim"),
    ("Tukwila", "City pool", "Tukwila, WA", "Jo Martin", "206-555-0104", "4414 S 144th St, Tukwila, WA 98168", "Morgan Lee"),
    ("Auburn", "City pool", "Auburn, WA", "Chris Patel", "253-555-0105", "516 4th St NE, Auburn, WA 98002", "Taylor Brooks"),
    ("Renton YMCA", "YMCA pool", "Renton, WA", "Pat Gomez", "425-555-0106", "1150 N 10th St, Renton, WA 98057", "Jamie Fox"),
    ("SeaTac", "Community pool", "SeaTac, WA", "Lou Diaz", "206-555-0107", "13735 24th Ave S, SeaTac, WA 98168", "Casey Wu"),
    ("Burien", "City pool", "Burien, WA", "Ari Cole", "206-555-0108", "12000 4th Ave SW, Burien, WA 98146", "Drew Hall"),
    ("White Center", "Community pool", "Seattle, WA", "Sky Reyes", "206-555-0109", "10601 8th Ave SW, Seattle, WA 98146", "Robin Ash"),
]


def next_sunday(day: date) -> date:
    return day + timedelta(days=(6 - day.weekday()) or 7)


def email_for(name: str) -> str:
    return name.lower().replace(" ", ".") + "@example.org"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add demo data to a test base")
    parser.add_argument("--yes-this-is-a-test-base", action="store_true", dest="confirmed")
    args = parser.parse_args(argv)
    if get_settings().is_production:
        print("Refusing to seed demo data with ENV=production.")
        return 1
    if not args.confirmed:
        print("This adds demo rows to the base in .env. Run again with --yes-this-is-a-test-base.")
        return 1
    if any(u.email.lower() == MARKER_EMAIL for u in load_users()):
        print("Demo data is already in this base (catalina@example.org exists). Nothing added.")
        return 0

    today = clock.today()
    print(f"Seeding demo data for today = {today}")

    # Roles: reuse by name, create the rest.
    roles = {r.name: r.id for r in load_roles()}
    missing = [n for n in ROLE_NAMES if n not in roles]
    for rec in client.create_records(
        Roles.TABLE, [{Roles.NAME: n, Roles.STATUS: "Active"} for n in missing], typecast=True
    ):
        roles[rec["fields"][Roles.NAME]] = rec["id"]
    print(f"Roles: created {len(missing)}, reused {len(ROLE_NAMES) - len(missing)}")

    # People
    created = client.create_records(
        Users.TABLE,
        [
            {
                Users.EMAIL: email,
                Users.FIRST_NAME: first,
                Users.LAST_NAME: last,
                Users.STATUS: ACTIVE,
                Users.ACCESS_LEVEL: level,
                Users.ROLES: [roles[r] for r in role_names],
            }
            for first, last, email, level, role_names in PEOPLE
        ],
        typecast=True,
    )
    people = {rec["fields"][Users.FIRST_NAME]: rec["id"] for rec in created}
    print(f"People: {len(people)}")

    # Region, sites and instructors
    region = client.create_record(Region.TABLE, {Region.NAME: "South King County WA (demo)"})
    site_recs = client.create_records(
        Site.TABLE,
        [
            {
                Site.PROGRAM_NAME: name,
                Site.SITE_TYPE: kind,
                Site.PROGRAM_LOCATION: location,
                Site.REGION: [region["id"]],
                Site.PARTNER_CONTACT_NAME: partner,
                Site.PARTNER_CONTACT_EMAIL: email_for(partner),
                Site.PARTNER_CONTACT_PHONE: phone,
                Site.SHIPPING_ADDRESS: address,
                Site.LAST_HEAD_COACH: coach,
                Site.DRIVE_FOLDER: "https://drive.google.com/drive/folders/demo-"
                + name.lower().replace(" ", "-"),
            }
            for name, kind, location, partner, phone, address, coach in SITES
        ],
        typecast=True,
    )
    sites = {rec["fields"][Site.PROGRAM_NAME]: rec["id"] for rec in site_recs}
    instructor_recs = client.create_records(
        Instructors.TABLE,
        [
            {
                Instructors.NAME: coach,
                Instructors.EMAIL: email_for(coach),
                Instructors.SITE: [sites[name]],
            }
            for name, _, _, _, _, _, coach in SITES
        ],
    )
    instructors = {
        rec["fields"][Instructors.SITE][0]: rec["id"] for rec in instructor_recs
    }
    print(f"Sites: {len(sites)}")

    # Templates and steps
    templates: dict[str, str] = {}
    template_steps: dict[str, list[StepRec]] = {}
    for name, rows, version, description in TEMPLATES:
        template = client.create_record(
            TemplateList.TABLE,
            {
                TemplateList.NAME: name,
                TemplateList.STATUS: "Active",
                TemplateList.LIVE_VERSION: version,
                TemplateList.DESCRIPTION: description,
            },
            typecast=True,
        )
        templates[name] = template["id"]
        step_recs = client.create_records(
            Steps.TABLE,
            [
                {
                    Steps.SHORT_DESCRIPTION: step_name,
                    Steps.LONG_DESCRIPTION: f"{step_name}. See the project page for site details.",
                    Steps.DAYS_BEFORE_ANCHOR: days,
                    Steps.ANCHOR: anchor,
                    Steps.TEMPLATE: [template["id"]],
                    Steps.ROLES: [roles[role]],
                    Steps.SORT_ORDER: i,
                    Steps.ADDED_IN_VERSION: 1,
                }
                for i, (step_name, days, role, _, anchor) in enumerate(rows)
            ],
            typecast=True,
        )
        ids = {rec["fields"][Steps.SHORT_DESCRIPTION]: rec["id"] for rec in step_recs}
        client.update_records(
            Steps.TABLE,
            [
                {"id": ids[step_name], "fields": {Steps.DEPENDS_ON: [ids[d] for d in deps]}}
                for step_name, _, _, deps, _ in rows
                if deps
            ],
        )
        template_steps[name] = [
            StepRec(
                id=ids[step_name],
                name=step_name,
                template_id=template["id"],
                days_before=days,
                anchor=anchor,
                role_ids=[roles[role]],
                depends_on=[ids[d] for d in deps],
                sort_order=float(i),
            )
            for i, (step_name, days, role, deps, anchor) in enumerate(rows)
        ]
        snapshot = [
            {
                "key": ids[step_name],
                "name": step_name,
                "description": "",
                "anchor": anchor,
                "days_before": days,
                "role_id": roles[role],
                "depends_on": [ids[d] for d in deps],
            }
            for step_name, days, role, deps, anchor in rows
        ]
        client.create_record(
            TemplateVersions.TABLE,
            {
                TemplateVersions.NAME: f"{name} v{version}",
                TemplateVersions.TEMPLATE: [template["id"]],
                TemplateVersions.VERSION: version,
                TemplateVersions.STATUS: "Live",
                TemplateVersions.STEPS_JSON: json.dumps(snapshot),
                TemplateVersions.CHANGE_NOTE: "Demo data",
                TemplateVersions.PUBLISHED_BY: [people["Catalina"]],
            },
            typecast=True,
        )
    print(f"Templates: {len(templates)}")

    team = {
        roles["Program Manager"]: people["Catalina"],
        roles["Marketing"]: people["Mary"],
        roles["Operations"]: people["Tash"],
        roles["Program Assistant"]: people["Tash"],
        roles["Development"]: people["Erin"],
        roles["Grants"]: people["Gabe"],
        roles["Executive Director"]: people["Erin"],
    }

    sunday = next_sunday(today)
    launches = [
        # (site, template, day one, duration, closed?)
        ("Federal Way", "Learn to Swim with City", sunday + timedelta(days=7), 5, False),
        ("Rainier Beach", "Swim Safely", sunday + timedelta(days=14), 5, False),
        ("Kent YMCA", "Learn to Swim with YMCA", sunday + timedelta(days=35), 5, False),
        ("Tukwila", "Swim Safely", sunday + timedelta(days=70), 5, False),
        ("Auburn", "Swim Safely", date(today.year, 7, 12), 5, True),
        ("Renton YMCA", "Learn to Swim with YMCA", date(today.year, 6, 7), 5, True),
        ("SeaTac", "Swim Safely", date(today.year - 1, 8, 17), 5, True),
        ("Burien", "Learn to Swim with City", date(today.year - 1, 7, 6), 5, True),
        ("White Center", "Swim Safely", date(today.year - 1, 6, 22), 5, True),
    ]
    site_types = {s[0]: s[1] for s in SITES}
    site_rows = {s[0]: s for s in SITES}
    season = lambda d: f"{'Summer' if d.month in (6, 7, 8) else 'Winter' if d.month in (12, 1, 2) else 'Fall' if d.month >= 9 else 'Spring'} {d.year}"  # noqa: E731
    session_recs = client.create_records(
        Session.TABLE,
        [
            {
                Session.PROGRAM_NAME: f"{site} {template} {season(day1)}",
                Session.START_DATE: day1.isoformat(),
                Session.DURATION_DAYS: duration,
                Session.SITE: [sites[site]],
                Session.STATUS: "Complete" if closed else "In progress",
                Session.PROGRAM_HOURS: "Sun 10:00 to 12:00",
                Session.INSTRUCTORS: [instructors[sites[site]]],
                Session.TEMPLATE: [templates[template]],
                Session.PROJECT_LEAD: [people["Catalina"]],
                Session.TIMELINE_GENERATED_AT: clock.utc_now_iso(),
                Session.SITE_TYPE: site_types[site],
                Session.LOCATION: site_rows[site][2],
                Session.PARTNER_CONTACT_NAME: site_rows[site][3],
                Session.PARTNER_CONTACT_EMAIL: email_for(site_rows[site][3]),
                Session.PARTNER_CONTACT_PHONE: site_rows[site][4],
                Session.SHIPPING_ADDRESS: site_rows[site][5],
                Session.DRIVE_FOLDER: "https://drive.google.com/drive/folders/demo-"
                + site.lower().replace(" ", "-"),
                Session.TEMPLATE_VERSION: {"Swim Safely": 3, "Learn to Swim with YMCA": 2}.get(
                    template, 1
                )
                - (1 if closed and template == "Swim Safely" else 0),
                **(
                    {Session.CLOSED_DATE: (day1 + timedelta(days=duration + 20)).isoformat()}
                    if closed
                    else {}
                ),
                **({Session.PARTNERS: [people["Pat"]]} if site == "Rainier Beach" else {}),
            }
            for site, template, day1, duration, closed in launches
        ],
        typecast=True,
    )
    sessions = {
        site: rec["id"] for (site, *_), rec in zip(launches, session_recs)
    }

    # Session Team: one row per role, plus Mary sharing Program Assistant at Kent.
    team_rows = []
    for site, *_ in launches:
        for role_id, user_id in team.items():
            team_rows.append(
                {SessionTeam.SESSION: [sessions[site]], SessionTeam.ROLE: [role_id], SessionTeam.USER: [user_id]}
            )
    team_rows.append(
        {
            SessionTeam.SESSION: [sessions["Kent YMCA"]],
            SessionTeam.ROLE: [roles["Program Assistant"]],
            SessionTeam.USER: [people["Mary"]],
        }
    )
    client.create_records(SessionTeam.TABLE, team_rows)

    # Tasks
    task_ids: dict[tuple[str, str], str] = {}
    logs = []
    for index, (site, template, day1, duration, closed) in enumerate(launches):
        end = day1 + timedelta(days=duration - 1)
        steps = template_steps[template]
        one_offs = []
        if template == "Swim Safely":
            one_offs.append(OneOff("Collect CDC training docs", day1 - timedelta(days=7), roles["Program Assistant"]))
        items = items_from_steps(steps) + items_from_one_offs(one_offs, len(steps))
        planned = plan_tasks(items, day1, end, team)
        rows = []
        for p in planned:
            fields = {
                Work.SESSION: [sessions[site]],
                Work.TASK_NAME: p.name,
                Work.ANCHOR: p.anchor,
                Work.DAYS_BEFORE_ANCHOR: p.days_before,
                Work.DUE_DATE_OVERRIDE: p.due.isoformat(),
                Work.SORT_ORDER: p.sort_order,
                Work.ROLE: [p.role_id],
            }
            if p.step_id:
                fields[Work.STEPS] = [p.step_id]
            if p.user_id:
                fields[Work.ASSIGNED_TO] = [p.user_id]
            if p.one_off:
                fields[Work.ONE_OFF] = True
            status, completed = "Not Started", None
            if closed:
                status, completed = "Done", p.due - timedelta(days=1)
                if p.name == "Order swim caps" and template == "Swim Safely":
                    status, completed = "Skipped", None
                elif p.name == "Community outreach":
                    completed = p.due + timedelta(days=6 + index)
                elif p.name == "Lifeguard roster" and index % 2:
                    completed = p.due + timedelta(days=3)
            elif p.due < today:
                status, completed = "Done", p.due
                if site == "Rainier Beach" and p.name in ("Design flyer", "Community outreach"):
                    status, completed = "Not Started", None
                if site == "Rainier Beach" and p.name == "Ship equipment to site":
                    status, completed = "In Progress", None
                if site == "Federal Way" and p.name == "Lifeguard roster":
                    status, completed = "Not Started", None
            elif p.due <= today + timedelta(days=3):
                status = "In Progress" if p.name.startswith("Confirm") else "Not Started"
            fields[Work.STATUS] = status
            if completed:
                fields[Work.COMPLETED_DATE] = completed.isoformat()
                if p.user_id:
                    fields[Work.COMPLETED_BY] = [p.user_id]
            rows.append(fields)
        recs = client.create_records(Work.TABLE, rows, typecast=True)
        key_to_id = {p.key: rec["id"] for p, rec in zip(planned, recs)}
        for p, rec in zip(planned, recs):
            task_ids[(site, p.name)] = rec["id"]
        client.update_records(
            Work.TABLE,
            [
                {"id": key_to_id[p.key], "fields": {Work.DEPENDS_ON: [key_to_id[k] for k in p.depends_on if k in key_to_id]}}
                for p in planned
                if any(k in key_to_id for k in p.depends_on)
            ],
        )
        logs.append(
            {
                ActivityLog.SESSION: [sessions[site]],
                ActivityLog.AUTHOR: [people["Catalina"]],
                ActivityLog.TYPE: "Project Created",
                ActivityLog.TEXT: f"created this launch with {len(planned)} tasks",
                ActivityLog.VISIBILITY: "Internal",
            }
        )
        if closed:
            logs.append(
                {
                    ActivityLog.SESSION: [sessions[site]],
                    ActivityLog.AUTHOR: [people["Catalina"]],
                    ActivityLog.TYPE: "Project Closed",
                    ActivityLog.TEXT: "closed this launch",
                    ActivityLog.VISIBILITY: "Internal",
                }
            )
        print(f"  {site}: {len(planned)} tasks")

    ship = task_ids[("Rainier Beach", "Ship equipment to site")]
    logs += [
        {
            ActivityLog.SESSION: [sessions["Rainier Beach"]],
            ActivityLog.WORK: [ship],
            ActivityLog.AUTHOR: [people["Tash"]],
            ActivityLog.TYPE: "Note",
            ActivityLog.TEXT: "Boxes are packed. Courier picks up Monday morning.",
            ActivityLog.VISIBILITY: "Shared",
        },
        {
            ActivityLog.SESSION: [sessions["Rainier Beach"]],
            ActivityLog.WORK: [ship],
            ActivityLog.AUTHOR: [people["Catalina"]],
            ActivityLog.TYPE: "Note",
            ActivityLog.TEXT: "The shipping address changed this year. Use the one on the project page.",
            ActivityLog.VISIBILITY: "Internal",
        },
        {
            ActivityLog.SESSION: [sessions["Rainier Beach"]],
            ActivityLog.WORK: [task_ids[("Rainier Beach", "Design flyer")]],
            ActivityLog.AUTHOR: [people["Mary"]],
            ActivityLog.TYPE: "Note",
            ActivityLog.TEXT: "Waiting on the partner's logo before this can go to print.",
            ActivityLog.VISIBILITY: "Internal",
        },
    ]
    client.create_records(ActivityLog.TABLE, logs, typecast=True)

    client.create_records(
        Links.TABLE,
        [
            {Links.TITLE: "Equipment packing list", Links.URL: "https://drive.google.com/file/d/demo-packing-list", Links.KIND: "Google Drive", Links.WORK: [ship], Links.ADDED_BY: [people["Tash"]]},
            {Links.TITLE: "Box shipping labels", Links.URL: "https://www.canva.com/design/demo-labels", Links.KIND: "Canva", Links.WORK: [ship], Links.ADDED_BY: [people["Tash"]]},
            {Links.TITLE: "Partner agreement", Links.URL: "https://docs.google.com/document/d/demo-agreement", Links.KIND: "Google Drive", Links.SESSION: [sessions["Rainier Beach"]], Links.ADDED_BY: [people["Catalina"]]},
        ],
        typecast=True,
    )
    attendance = task_ids[("Kent YMCA", "Send attendance list template")]
    client.create_record(
        Reminders.TABLE,
        {
            Reminders.NAME: "Custom: Send attendance list template",
            Reminders.WORK: [attendance],
            Reminders.RECIPIENT: [people["Tash"]],
            Reminders.CREATED_BY: [people["Tash"]],
            Reminders.KIND: "Custom",
            Reminders.SEND_ON: (today + timedelta(days=5)).isoformat(),
            Reminders.STATUS: "Scheduled",
            Reminders.NOTE: "Check Mary has the sign-in sheet.",
        },
        typecast=True,
    )
    print("Done. Sign in with DEV_LOGIN_EMAIL=catalina@example.org (admin) or tash@example.org (staff).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
