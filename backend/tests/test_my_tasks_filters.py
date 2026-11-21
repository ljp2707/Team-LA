"""My Tasks filters (state, city, program type) and sort (due date, program, location).

Sam (recStaff) has tasks on three programs:
  recProj   Rainier Beach, Seattle WA, Swim Safely        Design flyer, Community outreach, Ship equipment
  recKent   Kent, Kent WA, Learn to Swim                  Order caps
  recPdx    Portland Pool, Portland OR, Learn to Swim     Book lanes
Plus an Ada-only task on recPdx that Sam must never see.
"""

from datetime import date

import pytest

from app.airtable.schema import Site
from tests.builders import add_project, add_site, add_task, add_template, standard_project


@pytest.fixture
def world(fake):
    standard_project(fake)
    site = fake.find(Site.TABLE, "recSite")["fields"]
    site[Site.CITY], site[Site.STATE] = "Seattle", "wa"  # lower case on purpose
    add_template(fake, "recTplL", "Learn to Swim")
    add_site(fake, "recSiteKent", "Kent", **{Site.CITY: "Kent", Site.STATE: "WA"})
    add_site(fake, "recSitePdx", "Portland Pool", **{Site.CITY: "Portland", Site.STATE: "OR"})
    add_project(fake, "recKent", "Kent Learn to Swim", template="recTplL", site="recSiteKent")
    add_project(fake, "recPdx", "Portland Learn to Swim", template="recTplL", site="recSitePdx")
    add_task(fake, "recK1", "Order caps", date(2026, 11, 5), project="recKent", assigned="recStaff")
    add_task(fake, "recP1", "Book lanes", date(2026, 11, 3), project="recPdx", assigned="recStaff")
    add_task(fake, "recP2", "Ada's secret task", date(2026, 11, 3), project="recPdx", assigned="recAdmin")
    return fake


def _mine(client, **params):
    return client.get("/api/tasks/mine", params=params).json()


def _ids(body):
    return [t["id"] for g in ("overdue", "this_week", "later") for t in body["groups"][g]]


@pytest.fixture
def sam(client, sign_in, world):
    sign_in("staff@example.org")
    return client


def test_filter_choices_come_from_my_own_tasks(sam):
    filters = _mine(sam)["filters"]
    assert filters["states"] == ["OR", "WA"]
    assert filters["cities"] == [
        {"value": "Kent", "label": "Kent, WA"},
        {"value": "Portland", "label": "Portland, OR"},
        {"value": "Seattle", "label": "Seattle, WA"},
    ]
    assert filters["program_types"] == ["Learn to Swim", "Swim Safely"]


def test_filters_are_empty_until_sites_have_a_state(client, sign_in, fake):
    standard_project(fake)
    sign_in("staff@example.org")
    filters = _mine(client)["filters"]
    assert filters["states"] == [] and filters["cities"] == []
    assert filters["program_types"] == ["Swim Safely"]


def test_state_filter(sam):
    assert set(_ids(_mine(sam, state="WA"))) == {"recT2", "recT3", "recT4", "recK1"}
    assert _ids(_mine(sam, state="or")) == ["recP1"]  # case does not matter


def test_city_filter(sam):
    assert _ids(_mine(sam, city="Kent")) == ["recK1"]
    assert set(_ids(_mine(sam, city="seattle"))) == {"recT2", "recT3", "recT4"}


def test_program_type_filter(sam):
    assert set(_ids(_mine(sam, program_type="Learn to Swim"))) == {"recK1", "recP1"}
    assert set(_ids(_mine(sam, program_type="Swim Safely"))) == {"recT2", "recT3", "recT4"}


def test_filters_combine(sam):
    assert _ids(_mine(sam, state="WA", program_type="Learn to Swim")) == ["recK1"]
    assert _ids(_mine(sam, state="OR", program_type="Swim Safely")) == []
    assert _ids(_mine(sam, state="WA", city="Kent", project="recKent")) == ["recK1"]
    assert _ids(_mine(sam, city="Kent", project="recProj")) == []
    assert _ids(_mine(sam, filter="overdue", state="WA")) == ["recT2", "recT4"]


def test_sort_by_due_date_is_the_default(sam):
    assert _mine(sam)["groups"]["overdue"] == _mine(sam, sort="due")["groups"]["overdue"]
    assert [t["id"] for t in _mine(sam)["groups"]["overdue"]] == ["recT2", "recT4", "recP1"]


def test_sort_by_program(sam):
    overdue = [t["id"] for t in _mine(sam, sort="program")["groups"]["overdue"]]
    assert overdue == ["recP1", "recT2", "recT4"]  # Portland Pool, then Rainier Beach (by due date)


def test_sort_by_location(sam, world):
    add_site(world, "recSiteNone", "Nowhere Pool")
    add_project(world, "recNone", "No location", site="recSiteNone")
    add_task(world, "recN1", "Unplaced task", date(2026, 10, 1), project="recNone", assigned="recStaff")
    overdue = [t["id"] for t in _mine(sam, sort="location")["groups"]["overdue"]]
    assert overdue == ["recP1", "recT2", "recT4", "recN1"]  # OR, then WA Seattle, then no location last


def test_bad_sort_is_refused(sam):
    assert sam.get("/api/tasks/mine", params={"sort": "name; drop"}).status_code == 422


@pytest.mark.parametrize(
    "params",
    [{}, {"state": "OR"}, {"city": "Portland"}, {"program_type": "Learn to Swim"}, {"sort": "location"}],
)
def test_never_shows_someone_elses_tasks(sam, params):
    body = _mine(sam, **params)
    everything = [t for g in body["groups"].values() for t in g]
    assert "recP2" not in {t["id"] for t in everything}
    assert all("recStaff" in [a["id"] for a in t["assignees"]] for t in everything)


def test_choices_never_leak_other_peoples_places(client, sign_in, fake):
    """Ada has a task in Portland. Sam (no Portland tasks) must not see Portland as a choice."""
    standard_project(fake)
    add_site(fake, "recSitePdx", "Portland Pool", **{Site.CITY: "Portland", Site.STATE: "OR"})
    add_project(fake, "recPdx", "Portland", site="recSitePdx")
    add_task(fake, "recP2", "Ada's task", date(2026, 11, 3), project="recPdx", assigned="recAdmin")
    sign_in("staff@example.org")
    assert "OR" not in _mine(client)["filters"]["states"]


@pytest.mark.parametrize(
    "bad",
    ["recProj'", "Proj", "rec", "rec" + "x" * 40, "recProj OR 1=1", "recProj/../x", "recPro\nj"],
)
def test_project_filter_must_look_like_a_record_id(sam, bad):
    """F23: the project filter takes only a record ID, like the other inputs on this route."""
    assert sam.get("/api/tasks/mine", params={"project": bad}).status_code == 422


def test_project_filter_still_works_with_a_real_shaped_id(sam):
    assert sam.get("/api/tasks/mine", params={"project": "recAbCdEfGhIjKlMn"}).status_code == 200
    assert _ids(_mine(sam, project="recKent")) == ["recK1"]
