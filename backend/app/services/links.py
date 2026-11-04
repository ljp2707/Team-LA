"""Drive and Canva links on tasks and projects."""

from urllib.parse import urlparse

DRIVE_HOSTS = {"drive.google.com", "docs.google.com"}
CANVA_HOSTS = {"canva.com", "www.canva.com"}


def link_kind(url: str) -> str:
    """Google Drive, Canva or Other, from the URL's host."""
    host = (urlparse(url).hostname or "").lower()
    if host in DRIVE_HOSTS:
        return "Google Drive"
    if host in CANVA_HOSTS:
        return "Canva"
    return "Other"


def calendar_url(title: str, due_iso: str | None, details: str) -> str | None:
    """An "Add to Google Calendar" link for an all-day event on the due date."""
    from datetime import date, timedelta
    from urllib.parse import urlencode

    if not due_iso:
        return None
    day = date.fromisoformat(due_iso)
    dates = f"{day:%Y%m%d}/{day + timedelta(days=1):%Y%m%d}"
    query = urlencode({"action": "TEMPLATE", "text": title, "dates": dates, "details": details})
    return f"https://calendar.google.com/calendar/render?{query}"
