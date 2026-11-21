"""F40: the Docker image starts from pinned bases and carries only what production needs."""

import re

from app.config import REPO_ROOT

DOCKERFILE = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORED = {line.strip() for line in (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()}


def test_every_base_image_is_pinned_by_digest():
    bases = re.findall(r"^FROM\s+(\S+)", DOCKERFILE, re.M)
    assert len(bases) == 2
    for base in bases:
        assert re.search(r"@sha256:[0-9a-f]{64}$", base), base


def test_runs_as_a_normal_user_with_a_health_check():
    assert re.search(r"^USER appuser$", DOCKERFILE, re.M)
    assert "HEALTHCHECK" in DOCKERFILE and "/api/health" in DOCKERFILE
    assert "--no-server-header" in DOCKERFILE


def test_tests_dev_tools_and_secrets_stay_out():
    for path in (".env", ".env.*", "backend/tests", "backend/requirements-dev.*", "**/*.map", ".claude", ".git",
                 "frontend/e2e", "**/node_modules"):
        assert path in IGNORED, path
