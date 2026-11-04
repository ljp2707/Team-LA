"""Plain Python views of Airtable rows, and the loaders that build them.

Everything else in services/ works on these dataclasses, so the rules can be unit
tested without Airtable. Reads go through the cached `client.all_records`, and all
filtering happens here in Python, never in an Airtable formula.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from requests import HTTPError

from app.airtable import client
from app.airtable.schema import (
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
from app.services.clock import parse_date, parse_datetime


def _first(value) -> str | None:
    if isinstance(value, list):
        return value[0] if value else None
    return value or None


def _int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _created(record: dict[str, Any], field_name: str | None = None) -> datetime | None:
    if field_name and record["fields"].get(field_name):
        return parse_datetime(record["fields"][field_name])
    return parse_datetime(record.get("createdTime"))


# --- People -----------------------------------------------------------------


@dataclass
class UserRec:
    id: str
    email: str
    first_name: str = ""
    last_name: str = ""
    status: str | None = None
    access_level: str | None = None
    role_ids: list[str] = field(default_factory=list)
    welcome_sent: str | None = None

    @property
    def name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or self.email

    @property
    def short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]

    @property
    def active(self) -> bool:
        return self.status == "Active"


def load_users() -> list[UserRec]:
    out = []
    for r in client.all_records(Users.TABLE):
        f = r["fields"]
        out.append(
            UserRec(
                id=r["id"],
                email=(f.get(Users.EMAIL) or "").strip(),
                first_name=f.get(Users.FIRST_NAME, "") or "",
                last_name=f.get(Users.LAST_NAME, "") or "",
                status=f.get(Users.STATUS),
                access_level=f.get(Users.ACCESS_LEVEL),
                role_ids=list(f.get(Users.ROLES, []) or []),
                welcome_sent=f.get(Users.WELCOME_EMAIL_SENT),
            )
        )
    return out


@dataclass
class RoleRec:
    id: str
    name: str
    status: str | None = None

    @property
    def active(self) -> bool:
        return self.status not in ("In Active", "Inactive")


def load_roles() -> list[RoleRec]:
    return [
        RoleRec(
            id=r["id"],
            name=r["fields"].get(Roles.NAME, "") or "",
            status=r["fields"].get(Roles.STATUS),
        )
        for r in client.all_records(Roles.TABLE)
    ]


# --- Places -----------------------------------------------------------------


@dataclass
class RegionRec:
    id: str
    name: str


def load_regions() -> list[RegionRec]:
    return [
        RegionRec(id=r["id"], name=r["fields"].get(Region.NAME, "") or "")
        for r in client.all_records(Region.TABLE)
    ]


@dataclass
class SiteRec:
    id: str
    name: str
    location: str = ""
    region_id: str | None = None
    site_type: str | None = None
    partner_name: str = ""
    partner_email: str = ""
    partner_phone: str = ""
    shipping_address: str = ""
    last_head_coach: str = ""
    drive_folder: str = ""
    instructor_ids: list[str] = field(default_factory=list)


def load_sites() -> list[SiteRec]:
    out = []
    for r in client.all_records(Site.TABLE):
        f = r["fields"]
        out.append(
            SiteRec(
                id=r["id"],
                name=f.get(Site.PROGRAM_NAME) or f.get(Site.REGION_SITE) or "Unnamed site",
                location=f.get(Site.PROGRAM_LOCATION, "") or "",
                region_id=_first(f.get(Site.REGION)),
                site_type=f.get(Site.SITE_TYPE),
                partner_name=f.get(Site.PARTNER_CONTACT_NAME, "") or "",
                partner_email=f.get(Site.PARTNER_CONTACT_EMAIL, "") or "",
                partner_phone=f.get(Site.PARTNER_CONTACT_PHONE, "") or "",
                shipping_address=f.get(Site.SHIPPING_ADDRESS, "") or "",
                last_head_coach=f.get(Site.LAST_HEAD_COACH, "") or "",
                drive_folder=f.get(Site.DRIVE_FOLDER, "") or "",
                instructor_ids=list(f.get(Site.INSTRUCTORS, []) or []),
            )
        )
    return out


@dataclass
class InstructorRec:
    id: str
    name: str
    email: str = ""
    site_ids: list[str] = field(default_factory=list)


def load_instructors() -> list[InstructorRec]:
    return [
        InstructorRec(
            id=r["id"],
            name=r["fields"].get(Instructors.NAME, "") or "",
            email=r["fields"].get(Instructors.EMAIL, "") or "",
            site_ids=list(r["fields"].get(Instructors.SITE, []) or []),
        )
        for r in client.all_records(Instructors.TABLE)
    ]


# --- Templates --------------------------------------------------------------


@dataclass
class TemplateRec:
    id: str
    name: str
    status: str | None = None
    live_version: int | None = None
    description: str = ""

    @property
    def active(self) -> bool:
        return self.status != "Inactive"

    @property
    def version(self) -> int:
        """Templates made before versions existed count as v1."""
        return self.live_version or 1


def load_templates() -> list[TemplateRec]:
    return [
        TemplateRec(
            id=r["id"],
            name=r["fields"].get(TemplateList.NAME, "") or "",
            status=r["fields"].get(TemplateList.STATUS),
            live_version=_int(r["fields"].get(TemplateList.LIVE_VERSION)),
            description=r["fields"].get(TemplateList.DESCRIPTION, "") or "",
        )
        for r in client.all_records(TemplateList.TABLE)
    ]


@dataclass
class StepRec:
    id: str
    name: str
    template_id: str | None
    description: str = ""
    days_before: int = 0
    anchor: str = "Start"
    role_ids: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    sort_order: float | None = None
    added_in: int | None = None
    retired_in: int | None = None
    retired_flag: bool = False
    auto_id: int | None = None

    @property
    def live(self) -> bool:
        return self.retired_in is None and not self.retired_flag

    @property
    def role_id(self) -> str | None:
        return self.role_ids[0] if self.role_ids else None


def load_steps() -> list[StepRec]:
    out = []
    for r in client.all_records(Steps.TABLE):
        f = r["fields"]
        out.append(
            StepRec(
                id=r["id"],
                name=f.get(Steps.SHORT_DESCRIPTION, "") or "",
                template_id=_first(f.get(Steps.TEMPLATE)),
                description=f.get(Steps.LONG_DESCRIPTION, "") or "",
                days_before=_int(f.get(Steps.DAYS_BEFORE_ANCHOR)) or 0,
                anchor=f.get(Steps.ANCHOR) or "Start",
                role_ids=list(f.get(Steps.ROLES, []) or []),
                depends_on=list(f.get(Steps.DEPENDS_ON, []) or []),
                sort_order=_float(f.get(Steps.SORT_ORDER)),
                added_in=_int(f.get(Steps.ADDED_IN_VERSION)),
                retired_in=_int(f.get(Steps.RETIRED_IN_VERSION)),
                retired_flag=bool(f.get(Steps.RETIRED)),
                auto_id=_int(f.get(Steps.ID)),
            )
        )
    return out


def step_sort_key(step: StepRec):
    """Sort Order first, then earliest due (furthest before Day 1), then age."""
    anchor_rank = 1 if step.anchor == "End" else 0
    return (
        step.sort_order if step.sort_order is not None else float("inf"),
        anchor_rank,
        -step.days_before,
        step.auto_id or 0,
    )


def live_steps(template_id: str, steps: list[StepRec] | None = None) -> list[StepRec]:
    steps = load_steps() if steps is None else steps
    return sorted(
        (s for s in steps if s.template_id == template_id and s.live), key=step_sort_key
    )


@dataclass
class VersionRec:
    id: str
    name: str
    template_id: str | None
    version: int
    status: str | None
    steps_json: str = ""
    change_note: str = ""
    published_at: str | None = None
    published_by: str | None = None
    created: datetime | None = None


def load_versions() -> list[VersionRec]:
    out = []
    for r in client.all_records(TemplateVersions.TABLE):
        f = r["fields"]
        out.append(
            VersionRec(
                id=r["id"],
                name=f.get(TemplateVersions.NAME, "") or "",
                template_id=_first(f.get(TemplateVersions.TEMPLATE)),
                version=_int(f.get(TemplateVersions.VERSION)) or 1,
                status=f.get(TemplateVersions.STATUS),
                steps_json=f.get(TemplateVersions.STEPS_JSON, "") or "",
                change_note=f.get(TemplateVersions.CHANGE_NOTE, "") or "",
                published_at=f.get(TemplateVersions.PUBLISHED_AT),
                published_by=_first(f.get(TemplateVersions.PUBLISHED_BY)),
                created=_created(r),
            )
        )
    return out


# --- Projects and tasks -----------------------------------------------------


@dataclass
class ProjectRec:
    id: str
    name: str
    site_id: str | None = None
    start: date | None = None
    duration_days: int | None = None
    end: date | None = None
    status: str | None = None
    template_id: str | None = None
    template_version: int | None = None
    hours: str = ""
    instructor_ids: list[str] = field(default_factory=list)
    lead_ids: list[str] = field(default_factory=list)
    site_type: str | None = None
    location: str = ""
    partner_name: str = ""
    partner_email: str = ""
    partner_phone: str = ""
    shipping_address: str = ""
    drive_folder: str = ""
    closed_date: date | None = None
    partner_ids: list[str] = field(default_factory=list)
    created_from: str | None = None
    timeline_generated_at: str | None = None
    session_name: str = ""

    @property
    def closed(self) -> bool:
        return self.status == "Complete"


def end_date_for(start: date | None, duration_days: int | None) -> date | None:
    """Matches the base's End Date formula: Start Date + Duration - 1."""
    if start is None or not duration_days:
        return None
    return start + timedelta(days=duration_days - 1)


def load_projects() -> list[ProjectRec]:
    out = []
    for r in client.all_records(Session.TABLE):
        f = r["fields"]
        start = parse_date(f.get(Session.START_DATE))
        duration = _int(f.get(Session.DURATION_DAYS))
        out.append(
            ProjectRec(
                id=r["id"],
                name=(f.get(Session.PROGRAM_NAME) or f.get(Session.NAME) or "Untitled launch"),
                session_name=f.get(Session.NAME, "") or "",
                site_id=_first(f.get(Session.SITE)),
                start=start,
                duration_days=duration,
                end=parse_date(f.get(Session.END_DATE)) or end_date_for(start, duration),
                status=f.get(Session.STATUS),
                template_id=_first(f.get(Session.TEMPLATE)),
                template_version=_int(f.get(Session.TEMPLATE_VERSION)),
                hours=f.get(Session.PROGRAM_HOURS, "") or "",
                instructor_ids=list(f.get(Session.INSTRUCTORS, []) or []),
                lead_ids=list(f.get(Session.PROJECT_LEAD, []) or []),
                site_type=f.get(Session.SITE_TYPE),
                location=f.get(Session.LOCATION, "") or "",
                partner_name=f.get(Session.PARTNER_CONTACT_NAME, "") or "",
                partner_email=f.get(Session.PARTNER_CONTACT_EMAIL, "") or "",
                partner_phone=f.get(Session.PARTNER_CONTACT_PHONE, "") or "",
                shipping_address=f.get(Session.SHIPPING_ADDRESS, "") or "",
                drive_folder=f.get(Session.DRIVE_FOLDER, "") or "",
                closed_date=parse_date(f.get(Session.CLOSED_DATE)),
                partner_ids=list(f.get(Session.PARTNERS, []) or []),
                created_from=_first(f.get(Session.CREATED_FROM)),
                timeline_generated_at=f.get(Session.TIMELINE_GENERATED_AT),
            )
        )
    return out


@dataclass
class TaskRec:
    id: str
    name: str
    session_id: str | None
    status: str = "Not Started"
    due: date | None = None
    completed: date | None = None
    assigned_to: str | None = None  # The first person, kept for places that show one name
    role_id: str | None = None
    anchor: str = "Start"
    days_before: int | None = None
    depends_on: list[str] = field(default_factory=list)
    one_off: bool = False
    sort_order: float | None = None
    completed_by: str | None = None
    step_id: str | None = None
    description: str = ""
    resource_link: str = ""
    has_override: bool = False
    assignees: list[str] = field(default_factory=list)  # Everyone on the task, in order

    def __post_init__(self) -> None:
        if not self.assignees and self.assigned_to:
            self.assignees = [self.assigned_to]
        self.assignees = list(dict.fromkeys(self.assignees))
        self.assigned_to = self.assignees[0] if self.assignees else None

    def is_assigned(self, user_id: str | None) -> bool:
        return bool(user_id) and user_id in self.assignees


def load_tasks(steps: list[StepRec] | None = None) -> list[TaskRec]:
    """Every task. Fills a missing name or role from the task's step."""
    steps_by_id = {s.id: s for s in (load_steps() if steps is None else steps)}
    out = []
    for r in client.all_records(Work.TABLE):
        f = r["fields"]
        step = steps_by_id.get(_first(f.get(Work.STEPS)) or "")
        override = parse_date(f.get(Work.DUE_DATE_OVERRIDE))
        due = override or parse_date(f.get(Work.DUE_DATE)) or parse_date(
            f.get(Work.CALCULATED_DUE_DATE)
        )
        out.append(
            TaskRec(
                id=r["id"],
                name=f.get(Work.TASK_NAME) or (step.name if step else "") or "Untitled task",
                session_id=_first(f.get(Work.SESSION)),
                status=f.get(Work.STATUS) or "Not Started",
                due=due,
                completed=parse_date(f.get(Work.COMPLETED_DATE)),
                assignees=list(f.get(Work.ASSIGNED_TO) or []),
                role_id=_first(f.get(Work.ROLE)) or (step.role_id if step else None),
                anchor=f.get(Work.ANCHOR) or (step.anchor if step else "Start"),
                days_before=_int(f.get(Work.DAYS_BEFORE_ANCHOR))
                if f.get(Work.DAYS_BEFORE_ANCHOR) is not None
                else (step.days_before if step else None),
                depends_on=list(f.get(Work.DEPENDS_ON, []) or []),
                one_off=bool(f.get(Work.ONE_OFF)),
                sort_order=_float(f.get(Work.SORT_ORDER)),
                completed_by=_first(f.get(Work.COMPLETED_BY)),
                step_id=step.id if step else _first(f.get(Work.STEPS)),
                description=step.description if step else "",
                resource_link=f.get(Work.RESOURCE_LINK, "") or "",
                has_override=override is not None,
            )
        )
    return out


@dataclass
class TeamRec:
    id: str
    session_id: str | None
    role_id: str | None
    user_id: str | None


def load_team() -> list[TeamRec]:
    return [
        TeamRec(
            id=r["id"],
            session_id=_first(r["fields"].get(SessionTeam.SESSION)),
            role_id=_first(r["fields"].get(SessionTeam.ROLE)),
            user_id=_first(r["fields"].get(SessionTeam.USER)),
        )
        for r in client.all_records(SessionTeam.TABLE)
    ]


@dataclass
class LogRec:
    id: str
    session_id: str | None
    work_id: str | None
    author_id: str | None
    type: str
    text: str = ""
    from_value: str = ""
    to_value: str = ""
    created: datetime | None = None
    visibility: str = "Internal"
    batch: str = ""


def load_log() -> list[LogRec]:
    out = []
    for r in client.all_records(ActivityLog.TABLE):
        f = r["fields"]
        out.append(
            LogRec(
                id=r["id"],
                session_id=_first(f.get(ActivityLog.SESSION)),
                work_id=_first(f.get(ActivityLog.WORK)),
                author_id=_first(f.get(ActivityLog.AUTHOR)),
                type=f.get(ActivityLog.TYPE) or "System",
                text=f.get(ActivityLog.TEXT, "") or "",
                from_value=f.get(ActivityLog.FROM, "") or "",
                to_value=f.get(ActivityLog.TO, "") or "",
                created=_created(r, ActivityLog.CREATED),
                visibility=f.get(ActivityLog.VISIBILITY) or "Internal",
                batch=f.get(ActivityLog.BATCH, "") or "",
            )
        )
    return out


@dataclass
class LinkRec:
    id: str
    title: str
    url: str
    kind: str = "Other"
    work_id: str | None = None
    session_id: str | None = None
    added_by: str | None = None
    created: datetime | None = None


def load_links() -> list[LinkRec]:
    return [
        LinkRec(
            id=r["id"],
            title=r["fields"].get(Links.TITLE, "") or "",
            url=r["fields"].get(Links.URL, "") or "",
            kind=r["fields"].get(Links.KIND) or "Other",
            work_id=_first(r["fields"].get(Links.WORK)),
            session_id=_first(r["fields"].get(Links.SESSION)),
            added_by=_first(r["fields"].get(Links.ADDED_BY)),
            created=_created(r),
        )
        for r in client.all_records(Links.TABLE)
    ]


@dataclass
class ReminderRec:
    id: str
    name: str
    work_id: str | None
    recipient_id: str | None
    kind: str
    send_on: date | None
    status: str | None
    sent_at: str | None = None
    error: str = ""
    created_by: str | None = None
    note: str = ""


def load_reminders() -> list[ReminderRec]:
    out = []
    for r in client.all_records(Reminders.TABLE):
        f = r["fields"]
        out.append(
            ReminderRec(
                id=r["id"],
                name=f.get(Reminders.NAME, "") or "",
                work_id=_first(f.get(Reminders.WORK)),
                recipient_id=_first(f.get(Reminders.RECIPIENT)),
                kind=f.get(Reminders.KIND) or "",
                send_on=parse_date(f.get(Reminders.SEND_ON)),
                status=f.get(Reminders.STATUS),
                sent_at=f.get(Reminders.SENT_AT),
                error=f.get(Reminders.ERROR, "") or "",
                created_by=_first(f.get(Reminders.CREATED_BY)),
                note=f.get(Reminders.NOTE, "") or "",
            )
        )
    return out


def safe(loader):
    """Run a loader for a table that may not exist yet (before the migration)."""
    try:
        return loader()
    except HTTPError:
        return []
