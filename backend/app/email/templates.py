"""Every email the app sends, as plain Python string templates.

Each function returns (subject, text, html). The HTML part is deliberately simple:
inline styles, a white background, navy text, one blue button and no images. Every
value that comes from Airtable or a person is HTML-escaped before it goes in.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from string import Template

from app.config import get_settings

NAVY = "#0d2438"
MUTED = "#4e6175"
BLUE = "#1767c9"
FOOTER = "You get this because you have tasks in NMU Launches."


def footer_lines() -> list[str]:
    """Why this email came, how to stop it, and who sent it. Every email ends with these."""
    settings = get_settings()
    stop = (
        f"To stop these emails, reply to this email or write to {settings.CONTACT_EMAIL}."
        if settings.CONTACT_EMAIL
        else "To stop these emails, reply to this email and ask to be removed."
    )
    org = settings.ORG_NAME + (f", {settings.ORG_ADDRESS}" if settings.ORG_ADDRESS else "")
    return [FOOTER, stop, org]

Email = tuple[str, str, str]

LAYOUT = Template(
    """<!doctype html>
<html><body style="margin:0;padding:0;background:#ffffff;">
<div style="max-width:560px;margin:0 auto;padding:32px 24px;background:#ffffff;color:$navy;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.5;">
<p style="margin:0 0 24px;font-weight:bold;font-size:14px;color:$muted;">NMU Launches</p>
<h1 style="margin:0 0 16px;font-size:24px;line-height:1.2;color:$navy;">$heading</h1>
$body
<p style="margin:24px 0;"><a href="$url" style="display:inline-block;padding:12px 24px;border-radius:999px;background:$blue;color:#ffffff;text-decoration:none;font-weight:bold;">$button</a></p>
<p style="margin:32px 0 0;font-size:13px;line-height:1.5;color:$muted;">$footer</p>
</div></body></html>"""
)

TEXT_LAYOUT = Template("$heading\n\n$body\n\n$button: $url\n\n--\n$footer\n")


@dataclass
class TaskLine:
    """One task as it appears in an email."""

    name: str
    site: str
    due_text: str
    url: str
    waiting: str | None = None


def app_url(path: str = "") -> str:
    return get_settings().APP_URL.rstrip("/") + path


def task_url(task_id: str) -> str:
    return app_url(f"/tasks/{task_id}")


def _p(text: str) -> str:
    return f'<p style="margin:0 0 12px;">{escape(text)}</p>'


def _footer_html() -> str:
    lines = [escape(line) for line in footer_lines()]
    privacy = escape(app_url("/privacy"), quote=True)
    lines.append(f'<a href="{privacy}" style="color:{MUTED};">Privacy</a>')
    return "<br>".join(lines)


def _render(heading: str, paragraphs_html: str, paragraphs_text: str, url: str, button: str) -> tuple[str, str]:
    html = LAYOUT.substitute(
        navy=NAVY,
        muted=MUTED,
        blue=BLUE,
        heading=escape(heading),
        body=paragraphs_html,
        url=escape(url, quote=True),
        button=escape(button),
        footer=_footer_html(),
    )
    text = TEXT_LAYOUT.substitute(
        heading=heading, body=paragraphs_text, button=button, url=url, footer="\n".join(footer_lines())
        + f"\nPrivacy: {app_url('/privacy')}"
    )
    return text, html


def _task_list_html(tasks: list[TaskLine]) -> str:
    items = "".join(
        f'<li style="margin:0 0 8px;"><a href="{escape(t.url, quote=True)}" '
        f'style="color:{BLUE};font-weight:bold;">{escape(t.name)}</a>'
        f'<br><span style="color:{MUTED};">{escape(t.site)} · {escape(t.due_text)}'
        f"{(' · ' + escape(t.waiting)) if t.waiting else ''}</span></li>"
        for t in tasks
    )
    return f'<ul style="margin:0 0 12px;padding-left:20px;">{items}</ul>'


def _task_list_text(tasks: list[TaskLine]) -> str:
    return "\n".join(
        f"- {t.name} ({t.site}, {t.due_text}){' - ' + t.waiting if t.waiting else ''}\n  {t.url}"
        for t in tasks
    )


def due_in_seven(task: TaskLine) -> Email:
    subject = f"Due in 7 days: {task.name} ({task.site})"
    lines = [f"{task.name} at {task.site} is {task.due_text[0].lower() + task.due_text[1:]}."]
    if task.waiting:
        lines.append(f"{task.waiting}.")
    text, html = _render(
        f"Due in 7 days: {task.name}",
        "".join(_p(line) for line in lines),
        "\n".join(lines),
        task.url,
        "Open task",
    )
    return subject, text, html


def due_today(task: TaskLine) -> Email:
    subject = f"Due today: {task.name} ({task.site})"
    lines = [f"{task.name} at {task.site} is due today."]
    if task.waiting:
        lines.append(f"{task.waiting}.")
    lines.append("Mark it done in NMU Launches when it is finished.")
    text, html = _render(
        f"Due today: {task.name}",
        "".join(_p(line) for line in lines),
        "\n".join(lines),
        task.url,
        "Open task",
    )
    return subject, text, html


def custom_reminder(task: TaskLine, note: str = "") -> Email:
    subject = f"Reminder: {task.name} ({task.site})"
    lines = [f"You asked for a reminder about {task.name} at {task.site}. It is {task.due_text[0].lower() + task.due_text[1:]}."]
    if note:
        lines.append(f"Your note: {note}")
    text, html = _render(
        f"Reminder: {task.name}",
        "".join(_p(line) for line in lines),
        "\n".join(lines),
        task.url,
        "Open task",
    )
    return subject, text, html


def weekly_digest(week_of: str, first_name: str, overdue: list[TaskLine], upcoming: list[TaskLine]) -> Email:
    subject = f"Your NMU tasks for the week of {week_of}"
    html_parts = [_p(f"Hi {first_name}, here is what is on your list.")]
    text_parts = [f"Hi {first_name}, here is what is on your list."]
    if overdue:
        html_parts.append(f'<h2 style="margin:16px 0 8px;font-size:16px;color:#a3460e;">Overdue</h2>')
        html_parts.append(_task_list_html(overdue))
        text_parts.append("OVERDUE\n" + _task_list_text(overdue))
    if upcoming:
        html_parts.append(f'<h2 style="margin:16px 0 8px;font-size:16px;color:{NAVY};">Due in the next 7 days</h2>')
        html_parts.append(_task_list_html(upcoming))
        text_parts.append("DUE IN THE NEXT 7 DAYS\n" + _task_list_text(upcoming))
    text, html = _render(
        f"Your tasks for the week of {week_of}",
        "".join(html_parts),
        "\n\n".join(text_parts),
        app_url("/my-tasks"),
        "Open My Tasks",
    )
    return subject, text, html


def assignment(tasks: list[TaskLine], assigned_by: str) -> Email:
    sites = {t.site for t in tasks}
    if len(tasks) == 1:
        subject = f"New task for you: {tasks[0].name}"
        heading = subject
        url = tasks[0].url
        button = "Open task"
    else:
        where = f" at {next(iter(sites))}" if len(sites) == 1 else ""
        subject = f"{len(tasks)} new tasks for you{where}"
        heading = subject
        url = app_url("/my-tasks")
        button = "Open My Tasks"
    intro = f"{assigned_by} gave you {'this task' if len(tasks) == 1 else 'these tasks'} in NMU Launches."
    text, html = _render(
        heading,
        _p(intro) + _task_list_html(tasks),
        intro + "\n\n" + _task_list_text(tasks),
        url,
        button,
    )
    return subject, text, html


def welcome(first_name: str, email: str) -> Email:
    subject = "You've been added to NMU Launches"
    lines = [
        f"Hi {first_name}," if first_name else "Hi,",
        f"You've been added to NMU Launches. Sign in with Google at {app_url()} using this email ({email}).",
        "NMU Launches is where No More Under plans every new swim program site. You will see your own tasks on My Tasks.",
    ]
    text, html = _render(
        "Welcome to NMU Launches",
        "".join(_p(line) for line in lines),
        "\n\n".join(lines),
        app_url("/"),
        "Sign in with Google",
    )
    return subject, text, html


def test_email(first_name: str) -> Email:
    subject = "NMU Launches test email"
    lines = [
        f"Hi {first_name}," if first_name else "Hi,",
        "This is a test email from NMU Launches. If you can read it, email is working.",
    ]
    text, html = _render(
        "Email is working",
        "".join(_p(line) for line in lines),
        "\n\n".join(lines),
        app_url("/users"),
        "Open NMU Launches",
    )
    return subject, text, html
