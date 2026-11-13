"""Drive and Canva links, and uploaded files, on tasks and projects."""

from urllib.parse import urlparse

from app.airtable import client
from app.airtable.schema import Links

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


# --- Uploaded files ------------------------------------------------------------

FILE_KIND = "File"

# Airtable's limit for files sent through its API.
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FILE_MB = MAX_FILE_BYTES // (1024 * 1024)

# The only files people may upload, by extension, and the type Airtable is told.
# No web pages, scripts or programs, since anyone on the project may open them.
ALLOWED_FILE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
}


def clean_filename(name: str | None) -> str:
    """The file's own name without any folders or odd characters, at most 200 long."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*').strip(" .")
    if len(base) > 200:
        stem, dot, ext = base.rpartition(".")
        base = (stem[: 200 - len(ext) - 1] + dot + ext) if dot else base[:200]
    return base or "file"


def file_content_type(filename: str) -> str | None:
    """The MIME type for an allowed extension, or None if this kind of file is not allowed."""
    _, dot, ext = filename.rpartition(".")
    return ALLOWED_FILE_TYPES.get(f".{ext.lower()}") if dot else None


def allowed_extensions_text() -> str:
    return "photos, PDFs, Word, Excel, PowerPoint, text and CSV files"


def read_upload(upload) -> tuple[str, bytes, str]:
    """Check an uploaded file (a FastAPI UploadFile). Returns (filename, content, type).

    Raises ValueError with a sentence to show the person if the file cannot be kept.
    """
    filename = clean_filename(upload.filename)
    content_type = file_content_type(filename)
    if content_type is None:
        raise ValueError(f"That kind of file cannot be uploaded. Use {allowed_extensions_text()}.")
    content = upload.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(f"Files can be up to {MAX_FILE_MB} MB. Put bigger files in Google Drive and attach a link.")
    if not content:
        raise ValueError("That file is empty.")
    return filename, content, content_type


def save_upload(
    title: str,
    filename: str,
    content: bytes,
    content_type: str,
    added_by: str,
    session_id: str | None,
    work_id: str | None = None,
) -> dict:
    """Make a Links row of Kind File and put the file on it. Returns the record.

    If Airtable will not take the file, the half made row is removed again.
    """
    fields = {
        Links.TITLE: title,
        Links.KIND: FILE_KIND,
        Links.SESSION: [session_id] if session_id else [],
        Links.ADDED_BY: [added_by],
    }
    if work_id:
        fields[Links.WORK] = [work_id]
    record = client.create_record(Links.TABLE, fields, typecast=True)
    try:
        return client.upload_attachment(Links.TABLE, record, Links.FILE, filename, content, content_type)
    except Exception:
        client.delete_records(Links.TABLE, [record["id"]])
        raise
