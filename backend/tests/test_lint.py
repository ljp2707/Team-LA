"""F41: the backend passes its lint and security rules (ruff.toml), and checks that must not be
skipped are not asserts."""

import shutil
import subprocess
import sys

import pytest

from app.config import REPO_ROOT
from app.services import templates


def test_ruff_finds_nothing():
    try:
        import ruff  # noqa: F401
    except ImportError:
        if not shutil.which("ruff"):
            pytest.skip("ruff is not installed (pip install --require-hashes -r requirements-dev.txt)")
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."], cwd=REPO_ROOT / "backend", capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout[-3000:]


def test_unreadable_draft_raises_even_with_asserts_off(monkeypatch):
    """This used to be an assert, which python -O removes."""
    from types import SimpleNamespace

    monkeypatch.setattr(templates, "get_template", lambda _id: SimpleNamespace(version=1, name="Swim"))
    monkeypatch.setattr(templates, "validate", lambda steps: None)
    monkeypatch.setattr(templates, "get_draft", lambda *args, **kwargs: None)
    monkeypatch.setattr(templates.client, "create_record", lambda *args, **kwargs: {"id": "recV"})
    with pytest.raises(RuntimeError, match="could not be read back"):
        templates.save_draft("recTpl", [], "recAdmin")
