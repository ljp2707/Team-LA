"""Every Airtable table and field name used by the app.

If someone renames a table or field in Airtable, this is the only file to change.
In development, the app compares this file to the real base on startup and logs a
warning for anything missing (see `find_schema_problems` in airtable/client.py).
"""


class Users:
    TABLE = "Users"
    EMAIL = "Email Address"
    FIRST_NAME = "First Name"
    LAST_NAME = "Last Name"
    STATUS = "Status"
    CREATED = "Created"
    ROLES = "Roles"
    SESSION = "Session"
    ACCESS_LEVEL = "Access Level"
    WORK = "Work"
    SESSION_TEAM = "Session Team"
    ACTIVITY_LOG = "Activity Log"


class TemplateList:
    TABLE = "Template List"
    NAME = "List Name (Unique)"
    STATUS = "Status"
    CREATED = "Created"
    STEPS = "Steps"
    SESSION = "Session"


class Roles:
    TABLE = "Roles"
    NAME = "Role Name"
    STATUS = "Status"
    USERS = "Users"
    STEPS = "Steps"
    TEMPLATES = "Templates"
    SESSION_TEAM = "Session Team"


class Steps:
    TABLE = "Steps"
    UNIQUE = "Unique"
    SHORT_DESCRIPTION = "Short Description"
    LONG_DESCRIPTION = "Long Description"
    DAYS_BEFORE_ANCHOR = "Days Before Anchor"
    TEMPLATE = "Template"
    ROLES = "Roles"
    DEPENDS_ON = "Depends On"
    BLOCKS = "Blocks"
    ID = "ID"
    WORK = "Work"
    ANCHOR = "Anchor"


class Region:
    TABLE = "Region"
    NAME = "Name"
    SITE = "Site"


class Site:
    TABLE = "Site"
    REGION_SITE = "Region Site"
    PROGRAM_NAME = "Program Name"
    PROGRAM_LOCATION = "Program Location"
    REGION = "Region"
    SESSION = "Session"
    INSTRUCTORS = "Instructors"
    WORK = "Work"


class Session:
    """A project: one program launch at one site."""

    TABLE = "Session"
    NAME = "Session Name"
    START_DATE = "Start Date"  # This is Day 1
    DURATION_DAYS = "Duration (Days)"
    END_DATE = "End Date"
    SITE = "Site"
    REGION_SITE_SESSION = "Region Site Session"
    STATUS = "Status"
    PROGRAM_HOURS = "Program Hours"
    INSTRUCTORS = "Instructors"
    WORK = "Work"
    TEMPLATE = "Template"
    PROJECT_LEAD = "Project Lead"
    TIMELINE_GENERATED_AT = "Timeline Generated At"
    SESSION_TEAM = "Session Team"
    ACTIVITY_LOG = "Activity Log"


class Instructors:
    TABLE = "Instructors"
    NAME = "Instructor Name"
    SITE = "Site"
    EMAIL = "Email"
    SESSION = "Session"


class Work:
    """A generated task."""

    TABLE = "Work"
    UNIQUE = "Unique"
    STEPS = "Steps"
    SESSION = "Session"
    START_DATE_FROM_SESSION = "Start Date (from Session)"
    DAYS_FROM_STEPS = "Days (from Steps)"
    DUE_DATE = "Due Date"
    COMPLETED_DATE = "Completed Date"
    STATUS_OLD = "Status (old)"
    ASSIGNEE = "Assignee"
    NOTES = "Notes"
    ASSIGNED_TO = "Assigned To"
    TASK_NAME = "Task Name"
    ANCHOR = "Anchor"
    DAYS_BEFORE_ANCHOR = "Days Before Anchor"
    STATUS = "Status"
    END_DATE_FROM_SESSION = "End Date (from Session)"
    ACTIVITY_LOG = "Activity Log"


class SessionTeam:
    """Who fills each role on a project."""

    TABLE = "Session Team"
    ID = "ID"
    SESSION = "Session"
    ROLE = "Role"
    USER = "User"
    ASSIGNMENT = "Assignment"


class ActivityLog:
    """Project history."""

    TABLE = "Activity Log"
    ID = "ID"
    SESSION = "Session"
    WORK = "Work"
    AUTHOR = "Author"
    TYPE = "Type"
    TEXT = "Text"
    FROM = "From"
    TO = "To"
    CREATED = "Created"


ALL_TABLES = [
    Users,
    TemplateList,
    Roles,
    Steps,
    Region,
    Site,
    Session,
    Instructors,
    Work,
    SessionTeam,
    ActivityLog,
]


def field_names(table) -> list[str]:
    """Return every field name declared on one of the classes above."""
    return [
        value
        for name, value in vars(table).items()
        if name.isupper() and name != "TABLE"
    ]
