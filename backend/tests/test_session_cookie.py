"""F29: the session cookie is __Host-nmu_session in production, and the old one is removed."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings
from app.security import RetireOldSessionCookie, session_cookie_name, session_cookie_options

STRONG_SECRET = "s" * 40


def _production() -> Settings:
    return Settings(_env_file=None, ENV="production", APP_URL="https://team.example.org",
                    FRONTEND_URL="https://team.example.org", SESSION_SECRET=STRONG_SECRET)


def _local() -> Settings:
    return Settings(_env_file=None, ENV="development", SESSION_SECRET="local")


def test_cookie_names():
    assert session_cookie_name(_production()) == "__Host-nmu_session"
    assert session_cookie_name(_local()) == "nmu_session"


def _cookie_set_by(settings: Settings) -> str:
    """Sign a tiny app's session in with the same options main.py uses, and return Set-Cookie."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=STRONG_SECRET, **session_cookie_options(settings, max_age=60))

    @app.get("/in")
    def sign_in(request: Request):
        request.session["user"] = {"airtable_record_id": "recAdmin"}
        return {}

    client = TestClient(app, base_url="https://team.example.org")
    return client.get("/in").headers["set-cookie"]


def test_production_cookie_meets_the_host_prefix_rules():
    cookie = _cookie_set_by(_production())
    parts = [p.strip().lower() for p in cookie.split(";")]
    assert cookie.startswith("__Host-nmu_session=")
    # Browsers drop a __Host- cookie unless it is Secure, Path=/ and has no Domain.
    assert "secure" in parts and "path=/" in parts
    assert not any(p.startswith("domain=") for p in parts)
    assert "httponly" in parts and "samesite=lax" in parts


def test_local_cookie_keeps_working_over_http():
    cookie = _cookie_set_by(_local())
    parts = [p.strip().lower() for p in cookie.split(";")]
    assert cookie.startswith("nmu_session=")
    assert "secure" not in parts and "httponly" in parts and "path=/" in parts


def test_the_app_signs_in_with_the_local_cookie_in_tests(client, sign_in):
    response = sign_in("admin@example.org")
    assert "nmu_session=" in response.headers["set-cookie"]
    assert client.get("/api/me").status_code == 200


# --- The one-time switch: the old cookie is deleted in production -----------------------


def test_production_deletes_the_old_cookie(client, settings):
    settings(ENV="production")
    response = client.get("/api/health", headers={"Cookie": "nmu_session=old-value"})
    deleted = [c for c in response.headers.get_list("set-cookie") if c.startswith("nmu_session=")]
    assert deleted == ["nmu_session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax"]


def test_production_leaves_the_new_cookie_alone(client, settings):
    settings(ENV="production")
    response = client.get("/api/health", headers={"Cookie": "__Host-nmu_session=new-value"})
    assert not [c for c in response.headers.get_list("set-cookie") if c.startswith("nmu_session=")]


def test_localhost_never_deletes_the_cookie(client):
    response = client.get("/api/health", headers={"Cookie": "nmu_session=value"})
    assert "set-cookie" not in response.headers


def test_old_cookie_signs_nobody_in_under_the_new_name():
    """A browser with only the old cookie is signed out once, then signs in again."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key=STRONG_SECRET, **session_cookie_options(_production(), max_age=60))
    app.add_middleware(RetireOldSessionCookie)

    @app.get("/who")
    def who(request: Request):
        return {"user": request.session.get("user")}

    old = _cookie_set_by(_local()).split(";")[0]  # nmu_session=<a validly signed session>
    client = TestClient(app, base_url="https://team.example.org")
    assert client.get("/who", headers={"Cookie": old}).json() == {"user": None}
