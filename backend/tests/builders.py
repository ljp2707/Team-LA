"""Helpers that put rows in the fake Airtable base for a test."""

from datetime import date

from app.airtable.schema import (
    ActivityLog,
    Reminders,
    Session,
    SessionTeam,
    Site,
    Steps,
    TemplateList,
    Work,
)


def add_site(fake, record_id="recSite", name="Rainier Beach", **extra):
    fields = {Site.PROGRAM_NAME: name, Site.PROGRAM_LOCATION: "Seattle, WA"}
    fields.update(extra)
    return fake.add(Site.TABLE, fields, record_id)


def add_template(fake, record_id="recTpl", name="Swim Safely", live_version=None, status="Active"):
    fields = {TemplateList.NAME: name, TemplateList.STATUS: status}
    if live_version:
        fields[TemplateList.LIVE_VERSION] = live_version
    return fake.add(TemplateList.TABLE, fields, record_id)


def add_step(
    fake,
    record_id,
    name,
    days,
    role="recRole",
    template="recTpl",
    anchor="Start",
    depends=(),
    order=None,
    retired_in=None,
):
    fields = {
        Steps.SHORT_DESCRIPTION: name,
        Steps.DAYS_BEFORE_ANCHOR: days,
        Steps.ANCHOR: anchor,
        Steps.TEMPLATE: [template],
        Steps.ROLES: [role] if role else [],
        Steps.DEPENDS_ON: list(depends),
    }
    if order is not None:
        fields[Steps.SORT_ORDER] = order
    if retired_in is not None:
        fields[Steps.RETIRED_IN_VERSION] = retired_in
    return fake.add(Steps.TABLE, fields, record_id)


def add_project(
    fake,
    record_id="recProj",
    name="Rainier Beach Swim Safely 2026",
    start=date(2026, 11, 22),
    duration=5,
    template="recTpl",
    site="recSite",
    status="In progress",
    partners=(),
    **extra,
):
    fields = {
        Session.PROGRAM_NAME: name,
        Session.START_DATE: start.isoformat() if start else None,
        Session.DURATION_DAYS: duration,
        Session.TEMPLATE: [template] if template else [],
        Session.SITE: [site] if site else [],
        Session.STATUS: status,
        Session.PARTNERS: list(partners),
    }
    fields.update(extra)
    return fake.add(Session.TABLE, fields, record_id)


def add_task(
    fake,
    record_id,
    name,
    due,
    project="recProj",
    status="Not Started",
    assigned=None,
    role="recRole",
    depends=(),
    one_off=False,
    completed=None,
    step=None,
    anchor="Start",
    days_before=None,
):
    fields = {
        Work.TASK_NAME: name,
        Work.SESSION: [project],
        Work.STATUS: status,
        Work.DUE_DATE_OVERRIDE: due.isoformat() if due else None,
        Work.ROLE: [role] if role else [],
        Work.DEPENDS_ON: list(depends),
        Work.ANCHOR: anchor,
    }
    if days_before is not None:
        fields[Work.DAYS_BEFORE_ANCHOR] = days_before
    if assigned:
        fields[Work.ASSIGNED_TO] = [assigned]
    if one_off:
        fields[Work.ONE_OFF] = True
    if completed:
        fields[Work.COMPLETED_DATE] = completed.isoformat()
    if step:
        fields[Work.STEPS] = [step]
    return fake.add(Work.TABLE, fields, record_id)


def add_team(fake, project, role, user):
    return fake.add(
        SessionTeam.TABLE,
        {SessionTeam.SESSION: [project], SessionTeam.ROLE: [role], SessionTeam.USER: [user]},
    )


def add_note(fake, record_id, task, author, text="A note", visibility="Internal", project="recProj"):
    return fake.add(
        ActivityLog.TABLE,
        {
            ActivityLog.SESSION: [project],
            ActivityLog.WORK: [task],
            ActivityLog.AUTHOR: [author],
            ActivityLog.TYPE: "Note",
            ActivityLog.TEXT: text,
            ActivityLog.VISIBILITY: visibility,
        },
        record_id,
    )


def add_reminder(fake, record_id, task, recipient, send_on, kind="Custom", status="Scheduled", note=""):
    return fake.add(
        Reminders.TABLE,
        {
            Reminders.NAME: f"{kind} reminder",
            Reminders.WORK: [task] if task else [],
            Reminders.RECIPIENT: [recipient] if recipient else [],
            Reminders.CREATED_BY: [recipient] if recipient else [],
            Reminders.KIND: kind,
            Reminders.SEND_ON: send_on.isoformat(),
            Reminders.STATUS: status,
            Reminders.NOTE: note,
        },
        record_id,
    )


def standard_project(fake):
    """A template with 4 steps and a project made from it, with tasks in each state.

    Today is Wed Nov 4, 2026. Day 1 is Sun Nov 22.
    """
    add_site(fake)
    add_template(fake)
    add_project(fake)
    add_task(fake, "recT1", "Confirm head coach", date(2026, 10, 11), status="Done",
             assigned="recAdmin", completed=date(2026, 10, 10))
    add_task(fake, "recT2", "Design flyer", date(2026, 10, 30), assigned="recStaff")
    add_task(fake, "recT3", "Community outreach", date(2026, 11, 6), assigned="recStaff",
             depends=["recT2"])
    add_task(fake, "recT4", "Ship equipment to site", date(2026, 11, 1), status="In Progress",
             assigned="recStaff", role="recRoleOps", depends=["recT1"])
    add_task(fake, "recT5", "Day 1 check-in", date(2026, 11, 22), assigned="recAdmin",
             depends=["recT4"])
    add_task(fake, "recT6", "Send participant survey", date(2026, 12, 3), assigned=None,
             anchor="End", days_before=-7)
