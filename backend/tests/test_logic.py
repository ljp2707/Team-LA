"""Pure rules: due dates, timing labels, waiting on, at risk, complete % and more."""

from datetime import date

import pytest

from app.services import logic
from app.services.records import TaskRec

TODAY = date(2026, 11, 4)
DAY_ONE = date(2026, 11, 22)
END = date(2026, 11, 26)


def task(id, status="Not Started", due=None, depends=()):
    return TaskRec(id=id, name=id.title(), session_id="p", status=status, due=due, depends_on=list(depends))


@pytest.mark.parametrize(
    "anchor,days,expected",
    [
        ("Start", 42, date(2026, 10, 11)),  # 6 weeks before Day 1
        ("Start", 0, DAY_ONE),
        ("Start", -7, date(2026, 11, 29)),  # negative means after
        ("End", -7, date(2026, 12, 3)),  # a week after the program ends
        ("End", 2, date(2026, 11, 24)),  # before the end
    ],
)
def test_due_date_math(anchor, days, expected):
    assert logic.due_date_for(anchor, days, DAY_ONE, END) == expected


def test_due_date_needs_day_one():
    assert logic.due_date_for("Start", 7, None, None) is None


@pytest.mark.parametrize(
    "anchor,days,expected",
    [
        ("Start", 42, "6 weeks before Day 1"),
        ("Start", 7, "1 week before Day 1"),
        ("Start", -7, "1 week after Day 1"),
        ("Start", 0, "On Day 1"),
        ("Start", 3, "3 days before Day 1"),
        ("Start", 1, "1 day before Day 1"),
        ("End", -7, "1 week after the program ends"),
        ("End", 2, "2 days before the program ends"),
    ],
)
def test_timing_label(anchor, days, expected):
    assert logic.timing_label(anchor, days) == expected


def test_short_timing_for_template_rows():
    assert logic.short_timing("Start", 42) == "6 weeks before"
    assert logic.short_timing("Start", 0) == "Day 1"
    assert logic.short_timing("Start", -7) == "1 week after"


def test_open_and_overdue():
    assert logic.is_open("Blocked")
    assert not logic.is_open("Done")
    assert not logic.is_open("Skipped")
    assert logic.is_overdue(task("a", due=date(2026, 11, 3)), TODAY)
    assert not logic.is_overdue(task("a", due=TODAY), TODAY)
    assert not logic.is_overdue(task("a", "Done", date(2026, 11, 1)), TODAY)


def test_waiting_on_lists_only_open_dependencies():
    flyer = task("flyer", due=date(2026, 10, 30))
    coach = task("coach", "Done", date(2026, 10, 1))
    outreach = task("outreach", depends=["flyer", "coach"])
    by_id = {t.id: t for t in (flyer, coach, outreach)}
    waiting = logic.waiting_on(outreach, by_id)
    assert [t.id for t in waiting] == ["flyer"]
    assert logic.waiting_text(waiting) == "Waiting on Flyer"
    assert logic.display_status(outreach, waiting) == "Blocked"


def test_waiting_text_with_several():
    many = [task("a"), task("b"), task("c")]
    assert logic.waiting_text(many) == "Waiting on A and 2 more"


def test_stored_status_shows_when_nothing_is_waiting():
    manual = task("x", "Blocked")
    assert logic.display_status(manual, []) == "Blocked"
    assert logic.display_status(task("y", "In Progress"), []) == "In Progress"


def test_at_risk_when_a_dependency_is_overdue():
    late = task("late", due=date(2026, 11, 1))
    dependent = task("dependent", due=date(2026, 11, 20), depends=["late"])
    by_id = {"late": late, "dependent": dependent}
    assert logic.is_at_risk(dependent, by_id, TODAY)
    assert not logic.is_at_risk(late, by_id, TODAY)
    assert len(logic.dependents_map(by_id.values())["late"]) == 1


def test_complete_percent_rounds_down():
    tasks = [task("a", "Done"), task("b", "Skipped"), task("c")]
    assert logic.complete_percent(tasks) == 66
    assert logic.complete_percent([]) == 0


def test_next_milestone_is_earliest_open():
    tasks = [
        task("done", "Done", date(2026, 10, 1)),
        task("later", due=date(2026, 12, 1)),
        task("soon", due=date(2026, 11, 10)),
    ]
    assert logic.next_milestone(tasks).id == "soon"


def test_phase_grouping():
    assert logic.phase_for(date(2026, 11, 21), DAY_ONE, END) == logic.BEFORE
    assert logic.phase_for(DAY_ONE, DAY_ONE, END) == logic.PROGRAM_WEEK
    assert logic.phase_for(END, DAY_ONE, END) == logic.PROGRAM_WEEK
    assert logic.phase_for(date(2026, 11, 27), DAY_ONE, END) == logic.AFTER


def test_due_text():
    assert logic.due_text(task("a", due=date(2026, 11, 2)), TODAY) == "Due Nov 2, 2 days late"
    assert logic.due_text(task("a", due=TODAY), TODAY) == "Due today"
    assert logic.due_text(task("a", due=date(2026, 11, 6)), TODAY) == "Due Fri, Nov 6"
    assert logic.due_text(task("a", due=date(2026, 11, 13)), TODAY) == "Due Nov 13"
    assert logic.due_text(task("a", due=date(2027, 1, 10)), TODAY) == "Due Jan 10, 2027"


def test_lead_time_text():
    assert logic.lead_time_text([42, 7, 0]) == "starts 6 weeks before Day 1"
    assert logic.lead_time_text([0]) == "starts on Day 1"
