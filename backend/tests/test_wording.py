"""The app says "program", not "launch", in everything people read.

Only user-facing text is checked (see tests/wording.py): code names, routes, JSON keys,
CSS classes and Airtable names keep "launch" on purpose. To keep the word somewhere on
purpose, add the phrase to wording.ALLOWED with a reason.
"""

from pathlib import Path

import pytest

from tests.wording import ALLOWED, launch_words, python_spans, ts_spans

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _python_files():
    for folder in ("app", "jobs"):
        yield from sorted((BACKEND / folder).rglob("*.py"))


def _frontend_files():
    yield from sorted((FRONTEND / "src").rglob("*.ts"))
    yield from sorted((FRONTEND / "src").rglob("*.tsx"))


def _report(found):
    return "\n".join(f"{path}:{line}: {text[:120]}" for path, line, text in found)


def test_backend_text_says_program():
    found = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        found += [(path.relative_to(ROOT), line, text) for line, text in launch_words(source, python_spans(source))]
    assert not found, "User-facing text still says launch:\n" + _report(found)


@pytest.mark.skipif(not (FRONTEND / "src").exists(), reason="frontend source not present")
def test_frontend_text_says_program():
    found = []
    for path in _frontend_files():
        source = path.read_text(encoding="utf-8")
        spans = ts_spans(source, jsx=path.suffix == ".tsx")
        found += [(path.relative_to(ROOT), line, text) for line, text in launch_words(source, spans)]
    assert not found, "User-facing text still says launch:\n" + _report(found)


@pytest.mark.skipif(not (FRONTEND / "index.html").exists(), reason="frontend source not present")
def test_browser_tab_title():
    assert "<title>NMU Programs</title>" in (FRONTEND / "index.html").read_text(encoding="utf-8")


# --- The checker itself --------------------------------------------------------------------


def test_checker_finds_text_but_not_code():
    source = (
        'const launches = data.launches;\n'
        'const label = "Start a launch";\n'
        '<p className="person-launch-head">Closed launches stay here</p>\n'
        "// a comment about a launch\n"
    )
    found = [text for _, text in launch_words(source, ts_spans(source))]
    assert found == ['"Start a launch"', "Closed launches stay here"]


def test_checker_skips_python_names_keys_docstrings_and_logs():
    source = (
        'def f():\n'
        '    """Docstring about a launch."""\n'
        '    logger.info("launch log line")\n'
        '    return {"launches": rows, "error": "This launch is closed"}\n'
    )
    assert [text for _, text in launch_words(source, python_spans(source))] == ['"This launch is closed"']


def test_allowed_phrases_are_kept():
    source = 'const a = "sites to launch"; const b = "nmu-launches";\n'
    assert launch_words(source, ts_spans(source)) == []
    assert all(phrase == phrase.lower() for phrase in ALLOWED)


# --- What people actually receive -----------------------------------------------------------


def test_emails_say_nmu_programs():
    from app.email import templates

    subject, text, html = templates.test_email("Sam")
    for part in (subject, text, html):
        assert "Launch" not in part and "launch" not in part
    assert "NMU Programs" in subject and "NMU Programs" in html


def test_calendar_feed_says_programs(client, sign_in, fake):
    from tests.builders import standard_project

    standard_project(fake)
    sign_in("staff@example.org")
    feed_url = client.post("/api/me/calendar-feed").json()["feed_url"]
    body = client.get("/calendar/" + feed_url.rsplit("/", 1)[1]).text
    assert "X-WR-CALNAME:NMU Programs tasks" in body
    assert "Program: " in body and "Launch: " not in body
