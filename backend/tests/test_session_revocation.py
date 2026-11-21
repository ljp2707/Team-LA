"""F30 (findings F15, option A): signing someone out on every device through Session Version."""

import pytest
from fastapi.testclient import TestClient

from app.airtable.schema import ActivityLog, Users
from app.auth import revocation
from app.auth.google import oauth
from app.main import app


@pytest.fixture
def device(monkeypatch):
    """A separate browser, signed in as someone, like a second laptop or a phone."""

    def _device(email: str) -> TestClient:
        browser = TestClient(app, follow_redirects=False, headers={"Origin": "http://localhost:5173"})

        async def fake_token(request):
            return {"userinfo": {"email": email, "email_verified": True}}

        monkeypatch.setattr(oauth.google, "authorize_access_token", fake_token)
        assert browser.get("/auth/callback").status_code == 302
        assert browser.get("/api/me").status_code == 200
        return browser

    return _device


def _version(fake, user_id: str) -> int:
    return int(fake.find(Users.TABLE, user_id)["fields"].get(Users.SESSION_VERSION) or 0)


# --- "Sign out of all devices" ----------------------------------------------------------


def test_sign_out_of_all_devices_ends_every_session(device, fake):
    laptop, phone = device("staff@example.org"), device("staff@example.org")
    response = laptop.post("/auth/logout-everywhere")
    assert response.status_code == 303 and response.headers["location"] == "/"
    assert laptop.get("/api/me").status_code == 401
    assert phone.get("/api/me").status_code == 401
    assert _version(fake, "recStaff") == 1


def test_signing_in_again_works_after(device, fake):
    device("staff@example.org").post("/auth/logout-everywhere")
    again = device("staff@example.org")
    assert again.get("/api/me").status_code == 200


def test_other_people_stay_signed_in(device):
    staff, admin = device("staff@example.org"), device("admin@example.org")
    staff.post("/auth/logout-everywhere")
    assert admin.get("/api/me").status_code == 200


def test_an_ended_cookie_cannot_sign_its_owner_out_again(device, fake):
    """An old copied cookie must not be usable to keep signing someone out."""
    laptop, stolen_copy = device("staff@example.org"), device("staff@example.org")
    laptop.post("/auth/logout-everywhere")
    assert stolen_copy.post("/auth/logout-everywhere").status_code == 303
    assert _version(fake, "recStaff") == 1


def test_signed_out_visitor_changes_nothing(client, fake):
    before = len(fake.writes)
    assert client.post("/auth/logout-everywhere").status_code == 303
    assert len(fake.writes) == before


def test_needs_a_post_from_our_own_site(device):
    staff = device("staff@example.org")
    assert staff.get("/auth/logout-everywhere").status_code in (404, 405)
    forged = staff.post("/auth/logout-everywhere", headers={"Origin": "https://evil.example"})
    assert forged.status_code == 403
    assert staff.get("/api/me").status_code == 200


# --- An admin signs someone out ---------------------------------------------------------


def test_admin_signs_someone_out_everywhere(device, fake):
    staff, admin = device("staff@example.org"), device("admin@example.org")
    response = admin.post("/api/users/recStaff/sign-out-everywhere")
    assert response.status_code == 200 and response.json() == {"signed_out": True}
    assert staff.get("/api/me").status_code == 401
    assert admin.get("/api/me").status_code == 200
    texts = [r["fields"].get(ActivityLog.TEXT) for r in fake.rows(ActivityLog.TABLE)]
    assert "signed Sam out on every device" in texts


@pytest.mark.parametrize("email", ["staff@example.org", "viewer@example.org", "partner@example.org"])
def test_only_admins_can_sign_others_out(device, fake, email):
    person = device(email)
    assert person.post("/api/users/recAdmin/sign-out-everywhere").status_code == 403
    assert _version(fake, "recAdmin") == 0


def test_unknown_person_is_404(device):
    assert device("admin@example.org").post("/api/users/recNobody/sign-out-everywhere").status_code == 404


# --- Changes that take access away end sessions ------------------------------------------


def test_new_access_level_ends_their_sessions(device, fake):
    staff, admin = device("staff@example.org"), device("admin@example.org")
    assert admin.patch("/api/users/recStaff", json={"access_level": "Viewer"}).status_code == 200
    assert staff.get("/api/me").status_code == 401
    assert device("staff@example.org").get("/api/me").json()["access_level"] == "Viewer"


def test_removing_a_role_ends_their_sessions(device, fake):
    fake.find(Users.TABLE, "recStaff")["fields"][Users.ROLES] = ["recRole", "recRoleOps"]
    staff, admin = device("staff@example.org"), device("admin@example.org")
    assert admin.patch("/api/users/recStaff", json={"role_ids": ["recRole"]}).status_code == 200
    assert staff.get("/api/me").status_code == 401


def test_adding_a_role_or_renaming_keeps_them_signed_in(device, fake):
    staff, admin = device("staff@example.org"), device("admin@example.org")
    admin.patch("/api/users/recStaff", json={"role_ids": ["recRole", "recRoleOps"]})
    admin.patch("/api/users/recStaff", json={"first_name": "Samuel"})
    assert staff.get("/api/me").status_code == 200
    assert _version(fake, "recStaff") == 0


def test_deactivating_raises_the_version(device, fake):
    fake.find(Users.TABLE, "recViewer")["fields"][Users.STATUS] = "Active"
    admin = device("admin@example.org")
    assert admin.patch("/api/users/recViewer", json={"status": "Inactive"}).status_code == 200
    assert _version(fake, "recViewer") == 1


def test_removing_access_raises_the_version(device, fake):
    admin = device("admin@example.org")
    assert admin.delete("/api/users/recViewer").status_code == 204
    assert _version(fake, "recViewer") == 1


def test_erasing_raises_the_version(device, fake):
    fake.find(Users.TABLE, "recGone")["fields"][Users.SESSION_VERSION] = 4
    admin = device("admin@example.org")
    assert admin.post("/api/users/recGone/erase").status_code == 200
    assert _version(fake, "recGone") == 5


# --- Existing sessions and the rules themselves ------------------------------------------


def test_blank_version_counts_as_zero_so_nobody_is_signed_out_by_the_upgrade(device, fake):
    assert Users.SESSION_VERSION not in fake.find(Users.TABLE, "recStaff")["fields"]
    staff = device("staff@example.org")
    assert staff.get("/api/me").status_code == 200


def test_a_version_set_in_airtable_ends_older_cookies(device, fake):
    staff = device("staff@example.org")
    fake.find(Users.TABLE, "recStaff")["fields"][Users.SESSION_VERSION] = 3
    assert staff.get("/api/me").status_code == 401


def test_is_revoked():
    assert not revocation.is_revoked(0, 0)
    assert not revocation.is_revoked(2, 2)
    assert revocation.is_revoked(0, 1)
    assert not revocation.is_revoked(3, 2)  # A row set back by hand does not sign people out


@pytest.mark.parametrize(
    "change, ends",
    [
        (dict(new_status="Inactive"), True),
        (dict(new_status="Active"), False),
        (dict(new_level="Viewer"), True),
        (dict(new_level="Staff"), False),  # Unchanged
        (dict(new_roles=["recRole"]), True),  # recRoleOps removed
        (dict(new_roles=["recRole", "recRoleOps", "recX"]), False),  # Only added
        (dict(), False),
    ],
)
def test_change_ends_sessions(change, ends):
    args = dict(old_status="Active", new_status=None, old_level="Staff", new_level=None,
                old_roles=["recRole", "recRoleOps"], new_roles=None)
    args.update(change)
    assert revocation.change_ends_sessions(**args) is ends
