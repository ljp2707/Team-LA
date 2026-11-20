"""F39: dependencies are pinned exactly, Python ones with hashes, and the image gets no test tools."""

import json
import re

from app.config import REPO_ROOT

BACKEND = REPO_ROOT / "backend"
FRONTEND = REPO_ROOT / "frontend"


def _packages(lock_text: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in re.finditer(r"^([A-Za-z0-9_.\-\[\]]+)==(\S+)", lock_text, re.M)}


def _top_level(in_text: str) -> list[str]:
    return [line.strip() for line in in_text.splitlines() if line.strip() and not line.startswith(("#", "-r"))]


def test_every_top_level_python_package_is_pinned_exactly():
    for name in ("requirements.in", "requirements-dev.in"):
        for line in _top_level((BACKEND / name).read_text(encoding="utf-8")):
            assert re.fullmatch(r"[A-Za-z0-9_.\-]+(\[[a-z,]+\])?==[^=<>~!*\s]+", line), f"{name}: {line}"


def test_python_locks_have_hashes_for_every_package():
    for name in ("requirements.txt", "requirements-dev.txt"):
        text = (BACKEND / name).read_text(encoding="utf-8")
        entries = re.split(r"\n(?=[A-Za-z0-9])", text)
        packages = [e for e in entries if re.match(r"[A-Za-z0-9_.\-\[\]]+==", e)]
        assert packages, name
        for entry in packages:
            assert "--hash=sha256:" in entry, f"{name}: {entry.splitlines()[0]} has no hash"


def test_locks_match_the_pins_in_the_in_files():
    lock = _packages((BACKEND / "requirements.txt").read_text(encoding="utf-8"))
    for line in _top_level((BACKEND / "requirements.in").read_text(encoding="utf-8")):
        name, version = re.sub(r"\[.*\]", "", line).split("==")
        assert lock.get(name.lower()) == version, f"requirements.txt is out of date for {name}; regenerate it"


def test_test_tools_never_reach_the_docker_image():
    lock = _packages((BACKEND / "requirements.txt").read_text(encoding="utf-8"))
    for tool in ("pytest", "pytest-cov", "coverage", "google-auth-oauthlib"):
        assert tool not in lock


def test_docker_installs_with_hashes_only():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--require-hashes" in dockerfile and "requirements-dev" not in dockerfile
    assert "npm ci" in dockerfile and "npm install" not in dockerfile


def test_npm_versions_are_exact():
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))
    for group in ("dependencies", "devDependencies"):
        for name, version in package.get(group, {}).items():
            assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{name}: {version}"
            assert lock["packages"][f"node_modules/{name}"]["version"] == version
    assert "save-exact=true" in (FRONTEND / ".npmrc").read_text(encoding="utf-8")
