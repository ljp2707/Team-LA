"""The app's idea of "now" and "today", always in APP_TIMEZONE (Pacific by default).

Every "today", "overdue" and "this week" in the app comes from here. Tests replace
`today` and `now` with fixed values.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().APP_TIMEZONE)


def now() -> datetime:
    """The current time, timezone aware, in APP_TIMEZONE."""
    return datetime.now(tz())


def today() -> date:
    return now().date()


def utc_now_iso() -> str:
    """For Airtable date time fields, which are stored in UTC."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def end_of_week(day: date) -> date:
    """The Sunday on or after this day. "This week" is today through Sunday."""
    return day + timedelta(days=6 - day.weekday())


def parse_date(value) -> date | None:
    """Read an Airtable date or date time ("2026-09-28" or "2026-09-28T00:00:00.000Z")."""
    if not value:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
        if not value:
            return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
