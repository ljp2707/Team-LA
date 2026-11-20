"""The Overdue section at the top of a program's page.

Today is Wed Nov 4, 2026. In the standard project, Design flyer (Oct 30) and Ship
equipment to site (Nov 1) are open and past due.
"""

from datetime import date

import pytest

from tests.builders import add_task, standard_project


@pytest.fixture
def project(fake):
    standard_project(fake)
    return fake


def _detail(client, sign_in, email="admin@example.org"):
    sign_in(email)
    return client.get("/api/projects/recProj").json()


def test_overdue_tasks_come_first_most_overdue_first(client, sign_in, project):
    add_task(project, "recLate", "Book the pool", date(2026, 10, 20), assigned="recStaff")
    body = _detail(client, sign_in)
    assert [t["name"] for t in body["overdue_tasks"]] == ["Book the pool", "Design flyer", "Ship equipment to site"]


def test_done_and_skipped_tasks_are_never_in_overdue(client, sign_in, project):
    add_task(project, "recSkip", "Old skipped task", date(2026, 10, 1), status="Skipped")
    body = _detail(client, sign_in)
    ids = {t["id"] for t in body["overdue_tasks"]}
    assert "recT1" not in ids  # Done, due Oct 11
    assert "recSkip" not in ids
    assert all(t["status"] not in ("Done", "Skipped") for t in body["overdue_tasks"])


def test_no_task_appears_twice(client, sign_in, project):
    body = _detail(client, sign_in)
    ids = [t["id"] for t in body["overdue_tasks"]] + [t["id"] for g in body["groups"] for t in g["tasks"]]
    assert len(ids) == len(set(ids))
    assert set(ids) == {"recT1", "recT2", "recT3", "recT4", "recT5", "recT6"}
    assert len(ids) == body["task_count"]


def test_overdue_is_empty_when_nothing_is_late(client, sign_in, project):
    for record_id in ("recT2", "recT4"):
        project.find("Work", record_id)["fields"]["Status"] = "Done"
    assert _detail(client, sign_in)["overdue_tasks"] == []


def test_staff_get_the_same_order(client, sign_in, project):
    body = _detail(client, sign_in, "staff@example.org")
    assert [t["id"] for t in body["overdue_tasks"]] == ["recT2", "recT4"]
