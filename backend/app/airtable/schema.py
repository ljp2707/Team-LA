"""Every Airtable table and field name used by the app.

If someone renames a table or field in Airtable, this is the only file to change.
In development, the app compares this file to the real base on startup and logs a
warning for anything missing (see `find_schema_problems` in airtable/client.py).

Fields marked "added by migrate_airtable" are created by `python -m jobs.migrate_airtable
--apply`. Their types live in `jobs/migrate_airtable.py`. See docs/airtable-schema.md for
the real base as it was dumped, and docs/decisions.md for why some choices were made.
"""


class Users:
    TABLE = "Users"
    EMAIL = "Email Address"  # Primary field
    FIRST_NAME = "First Name"
    LAST_NAME = "Last Name"
    STATUS = "Status"  # Active, Inactive
    CREATED = "Created"
    ROLES = "Roles"
    SESSION = "Session"
    ACCESS_LEVEL = "Access Level"  # Admin, Project Lead, Staff, Viewer, Partner
    WORK = "Work"
    SESSION_TEAM = "Session Team"
    ACTIVITY_LOG = "Activity Log"
    WELCOME_EMAIL_SENT = "Welcome Email Sent"  # added by migrate_airtable


ACTIVE = "Active"
INACTIVE = "Inactive"


class TemplateList:
    TABLE = "Template List"
    NAME = "List Name (Unique)"
    STATUS = "Status"  # Active, Inactive
    CREATED = "Created"
    STEPS = "Steps"
    SESSION = "Session"
    LIVE_VERSION = "Live Version"  # added by migrate_airtable
    DESCRIPTION = "Description"  # added by migrate_airtable


class Roles:
    TABLE = "Roles"
    NAME = "Role Name"
    STATUS = "Status"  # The real options are "Active", "On Hold" and "In Active"
    USERS = "Users"
    STEPS = "Steps"
    TEMPLATES = "Templates"
    SESSION_TEAM = "Session Team"


ROLE_ACTIVE = "Active"
ROLE_INACTIVE = "In Active"  # Spelled this way in the real base


class Steps:
    TABLE = "Steps"
    UNIQUE = "Unique"  # Formula
    SHORT_DESCRIPTION = "Short Description"
    LONG_DESCRIPTION = "Long Description"
    DAYS_BEFORE_ANCHOR = "Days Before Anchor"  # Negative means after the anchor
    TEMPLATE = "Template"
    ROLES = "Roles"
    DEPENDS_ON = "Depends On"
    BLOCKS = "Blocks"
    ID = "ID"
    WORK = "Work"
    ANCHOR = "Anchor"  # Single select: Start or End
    # An older checkbox already in the base. A step with it ticked is treated as
    # retired, the same as one with Retired In Version set.
    RETIRED = "Retired"
    SORT_ORDER = "Sort Order"  # added by migrate_airtable
    ADDED_IN_VERSION = "Added In Version"  # added by migrate_airtable
    RETIRED_IN_VERSION = "Retired In Version"  # added by migrate_airtable


class Region:
    TABLE = "Region"
    NAME = "Name"
    SITE = "Site"


class Site:
    TABLE = "Site"
    REGION_SITE = "Region Site"  # Formula: "Region - Program Name"
    # Despite its name, this is the site's own name (for example "Rainier Beach").
    PROGRAM_NAME = "Program Name"
    PROGRAM_LOCATION = "Program Location"
    REGION = "Region"
    SESSION = "Session"
    INSTRUCTORS = "Instructors"
    DRIVE_FOLDER = "Drive Folder"
    SITE_TYPE = "Site Type"  # added by migrate_airtable
    PARTNER_CONTACT_NAME = "Partner Contact Name"  # added by migrate_airtable
    PARTNER_CONTACT_EMAIL = "Partner Contact Email"  # added by migrate_airtable
    PARTNER_CONTACT_PHONE = "Partner Contact Phone"  # added by migrate_airtable
    SHIPPING_ADDRESS = "Shipping Address"  # added by migrate_airtable
    LAST_HEAD_COACH = "Last Head Coach"  # added by migrate_airtable


SITE_TYPES = ["City pool", "YMCA pool", "Community pool", "School pool", "Other"]


class Session:
    """A project: one program launch at one site."""

    TABLE = "Session"
    NAME = "Session Name"  # Formula: "MM/DD/YYYY - Region - Site". Not writable.
    START_DATE = "Start Date"  # This is Day 1
    # The base stores the length of the program. End Date is a formula from it.
    DURATION_DAYS = "Duration (Days)"
    END_DATE = "End Date"  # Formula: Start Date + Duration - 1
    SITE = "Site"
    REGION_SITE_SESSION = "Region Site Session"
    STATUS = "Status"  # Not started, In progress, Complete
    PROGRAM_HOURS = "Program Hours"
    INSTRUCTORS = "Instructors"  # Lead instructors
    WORK = "Work"
    TEMPLATE = "Template"
    PROJECT_LEAD = "Project Lead"
    TIMELINE_GENERATED_AT = "Timeline Generated At"
    SESSION_TEAM = "Session Team"
    ACTIVITY_LOG = "Activity Log"
    DRIVE_FOLDER = "Drive Folder"
    LESSONS_LEARNED = "Lessons Learned"
    # Session Name is a formula, so the name people type is kept here.
    PROGRAM_NAME = "Program Name"  # added by migrate_airtable
    SITE_TYPE = "Site Type"  # added by migrate_airtable
    LOCATION = "Location"  # added by migrate_airtable
    PARTNER_CONTACT_NAME = "Partner Contact Name"  # added by migrate_airtable
    PARTNER_CONTACT_EMAIL = "Partner Contact Email"  # added by migrate_airtable
    PARTNER_CONTACT_PHONE = "Partner Contact Phone"  # added by migrate_airtable
    SHIPPING_ADDRESS = "Shipping Address"  # added by migrate_airtable
    TEMPLATE_VERSION = "Template Version"  # added by migrate_airtable
    CREATED_FROM = "Created From"  # added by migrate_airtable
    CLOSED_DATE = "Closed Date"  # added by migrate_airtable
    PARTNERS = "Partners"  # added by migrate_airtable


SESSION_NOT_STARTED = "Not started"
SESSION_IN_PROGRESS = "In progress"
SESSION_COMPLETE = "Complete"


class Instructors:
    TABLE = "Instructors"
    NAME = "Instructor Name"
    SITE = "Site"
    EMAIL = "Email"
    SESSION = "Session"


class Work:
    """A generated task.

    The person: "Assigned To" links to Users. "Assignee" is a lookup through Steps
    (the step's default roles), so it is never used for the person.

    Dates: "Due Date" is a formula that uses "Due Date Override" when it is set, and
    otherwise "Calculated Due Date", which follows the Session's Start Date. The app
    always writes "Due Date Override", so a task's date never moves on its own when
    Day 1 changes, and finished tasks keep their dates.

    Task Name, Anchor and Days Before Anchor are real fields (not lookups), copied
    from the step when the task is made.
    """

    TABLE = "Work"
    UNIQUE = "Unique"  # Formula
    STEPS = "Steps"
    SESSION = "Session"
    START_DATE_FROM_SESSION = "Start Date (from Session)"
    CALCULATED_DUE_DATE = "Calculated Due Date"  # Formula
    DUE_DATE = "Due Date"  # Formula: override, else calculated
    DUE_DATE_OVERRIDE = "Due Date Override"  # What the app writes
    COMPLETED_DATE = "Completed Date"
    ASSIGNEE = "Assignee"  # Lookup of the step's roles. Not the person.
    NOTES = "Notes"
    ASSIGNED_TO = "Assigned To"  # Link to Users: the person
    TASK_NAME = "Task Name"
    ANCHOR = "Anchor"  # Text: Start or End
    DAYS_BEFORE_ANCHOR = "Days Before Anchor"
    STATUS = "Status"  # Not Started, In Progress, Blocked, Done, Skipped
    END_DATE_FROM_SESSION = "End Date (from Session)"
    ACTIVITY_LOG = "Activity Log"
    DEPENDS_ON = "Depends On"  # Link to Work, already in the base
    BLOCKS = "Blocks"  # The other side of Depends On
    RESOURCE_LINK = "Resource Link"
    ROLE = "Role"  # added by migrate_airtable
    ONE_OFF = "One-off"  # added by migrate_airtable
    SORT_ORDER = "Sort Order"  # added by migrate_airtable
    COMPLETED_BY = "Completed By"  # added by migrate_airtable


NOT_STARTED = "Not Started"
IN_PROGRESS = "In Progress"
BLOCKED = "Blocked"
DONE = "Done"
SKIPPED = "Skipped"
TASK_STATUSES = [NOT_STARTED, IN_PROGRESS, BLOCKED, DONE, SKIPPED]


class SessionTeam:
    """Who fills each role on a project."""

    TABLE = "Session Team"
    ID = "ID"
    SESSION = "Session"
    ROLE = "Role"
    USER = "User"
    ASSIGNMENT = "Assignment"


class ActivityLog:
    """Project history, and notes on tasks."""

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
    VISIBILITY = "Visibility"  # added by migrate_airtable: Internal or Shared
    BATCH = "Batch"  # added by migrate_airtable


class Links:
    """Drive and Canva links on tasks and projects. Table added by migrate_airtable."""

    TABLE = "Links"
    TITLE = "Title"  # Primary field
    URL = "URL"
    KIND = "Kind"  # Google Drive, Canva, Other
    WORK = "Work"
    SESSION = "Session"
    ADDED_BY = "Added By"


class Reminders:
    """Custom reminders, and a log of every reminder email. Added by migrate_airtable."""

    TABLE = "Reminders"
    NAME = "Name"  # Primary field
    WORK = "Work"
    RECIPIENT = "Recipient"
    KIND = "Kind"
    SEND_ON = "Send On"
    STATUS = "Status"
    SENT_AT = "Sent At"
    ERROR = "Error"
    CREATED_BY = "Created By"
    NOTE = "Note"


class TemplateVersions:
    """One row per template version. Added by migrate_airtable."""

    TABLE = "Template Versions"
    NAME = "Name"  # Primary field
    TEMPLATE = "Template"
    VERSION = "Version"
    STATUS = "Status"  # Draft, Live, Retired
    STEPS_JSON = "Steps JSON"
    CHANGE_NOTE = "Change Note"
    PUBLISHED_AT = "Published At"
    PUBLISHED_BY = "Published By"


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
    Links,
    Reminders,
    TemplateVersions,
]


def field_names(table) -> list[str]:
    """Return every field name declared on one of the classes above."""
    return [
        value
        for name, value in vars(table).items()
        if name.isupper() and name != "TABLE"
    ]
