"""F27: cross-origin isolation headers on every answer, and no Server header."""

import re
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import uvicorn

from app.main import app

ROOT = Path(__file__).resolve().parents[2]

EXPECTED = {
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "x-permitted-cross-domain-policies": "none",
}


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",  # cacheable public API
        "/api/tasks/mine",  # signed-out 401
        "/calendar/" + "A" * 43 + ".ics",  # unknown feed, 404
        "/projects/recProj",  # the frontend (index.html, or 404 if it is not built)
        "/api/nothing-here",  # API 404
    ],
)
def test_every_answer_has_the_headers(client, path):
    headers = client.get(path).headers
    for name, value in EXPECTED.items():
        assert headers.get(name) == value, f"{name} on {path}"


def test_headers_on_refused_and_failed_requests(client):
    refused = client.post("/api/me/view", json={"view": "staff"}, headers={"Origin": "https://evil.example"})
    assert refused.status_code == 403
    too_big = client.post("/api/me/view", content=b"x" * (3 * 1024 * 1024), headers={"Content-Type": "application/json"})
    assert too_big.status_code == 413
    for response in (refused, too_big):
        for name, value in EXPECTED.items():
            assert response.headers.get(name) == value


def test_no_cross_origin_embedder_policy():
    """Not added: it would need every cross-origin resource to opt in, for no gain here."""
    from app.security import SECURITY_HEADERS

    assert "Cross-Origin-Embedder-Policy" not in SECURITY_HEADERS


# --- No Server header -------------------------------------------------------------------


def test_dockerfile_turns_off_the_server_header():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    cmd = [line for line in dockerfile.splitlines() if line.startswith("CMD ")]
    assert len(cmd) == 1 and "--no-server-header" in cmd[0]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _served_headers(server_header: bool) -> dict[str, str]:
    """Run the real app under uvicorn for one request, as the Dockerfile does."""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", server_header=server_header, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            return {k.lower(): v for k, v in response.headers.items()}
    finally:
        server.should_exit = True
        thread.join(5)


def test_uvicorn_sends_no_server_header_with_the_flag():
    assert "server" not in _served_headers(server_header=False)


def test_uvicorn_would_name_itself_without_the_flag():
    """Shows the test above can see the header, so its pass means something."""
    assert re.match("uvicorn", _served_headers(server_header=True).get("server", ""))
