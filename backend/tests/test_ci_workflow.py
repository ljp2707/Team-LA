"""F42: CI runs every check, and the workflow follows the supply chain rules."""

import re

from app.config import REPO_ROOT

WORKFLOW = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
DEPENDABOT = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")


def test_every_action_is_pinned_to_a_commit():
    uses = re.findall(r"uses:\s*(\S+)", WORKFLOW)
    assert uses
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action


def test_scanner_images_are_pinned_by_digest():
    images = re.findall(r"^\s+\w+_IMAGE:\s*(\S+)", WORKFLOW, re.M)
    assert len(images) == 3
    for image in images:
        assert re.search(r"@sha256:[0-9a-f]{64}$", image), image


def test_token_is_read_only_and_never_kept():
    assert re.search(r"^permissions:\n  contents: read$", WORKFLOW, re.M)
    assert "write" not in WORKFLOW.split("jobs:")[0]
    checkouts = WORKFLOW.count("uses: actions/checkout@")
    assert checkouts and WORKFLOW.count("persist-credentials: false") == checkouts
    assert "pull_request_target" not in WORKFLOW


def test_every_required_check_runs():
    for step in (
        "--cov-fail-under=",
        "tests/test_access_matrix.py",
        "ruff check",
        "pip_audit --require-hashes",
        "npm ci",
        "npm audit",
        "npm run build",
        "playwright test",
        "gitleaks",
        "semgrep scan",
        "image --severity HIGH,CRITICAL",
        "config --severity HIGH,CRITICAL",
        "actionlint",
        "zizmor",
    ):
        assert step in WORKFLOW, step


def test_python_tools_come_from_the_hash_locked_file():
    for line in re.findall(r"pip install[^\n]*", WORKFLOW):
        assert "--require-hashes" in line, line


def test_dependabot_watches_everything():
    for ecosystem in ("npm", "github-actions", "docker"):
        assert f"package-ecosystem: {ecosystem}" in DEPENDABOT
    # Python packages are checked by the weekly CI run instead (F43): Dependabot's rewrite of
    # requirements.txt drops the platform markers and breaks installs on Windows.
    assert "package-ecosystem: pip" not in DEPENDABOT
    assert re.search(r"^  schedule:\n    - cron: ", WORKFLOW, re.M)


def test_dependabot_never_proposes_major_updates():
    blocks = DEPENDABOT.split("- package-ecosystem:")[1:]
    assert blocks
    for block in blocks:
        assert '"version-update:semver-major"' in block, block.split()[0]
