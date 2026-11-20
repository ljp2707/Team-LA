"""F26: the Content-Security-Policy is the smallest set the built app needs.

These tests fail if someone widens the policy (adds a host, 'unsafe-inline' and so on) or
if the frontend starts loading something the policy would block. The browser test in
frontend/e2e checks the real pages under the enforced policy.
"""

import re
from pathlib import Path

import pytest

from app.security import content_security_policy

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

EXPECTED = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self' https://accounts.google.com",
    "report-uri /api/security/csp-report",
    "report-to csp-endpoint",
]


def _directives(policy: str) -> list[str]:
    return [d.strip() for d in policy.split(";")]


def test_policy_is_exactly_the_expected_set_locally():
    assert _directives(content_security_policy(production=False)) == EXPECTED


def test_production_also_upgrades_insecure_requests():
    assert _directives(content_security_policy(production=True)) == EXPECTED + ["upgrade-insecure-requests"]


@pytest.mark.parametrize("production", [False, True])
def test_no_unsafe_sources_or_third_party_hosts(production):
    policy = content_security_policy(production)
    for unsafe in ("'unsafe-inline'", "'unsafe-eval'", "'unsafe-hashes'", "*", "http:", "https: ", "blob:"):
        assert unsafe not in policy
    # The only other site named anywhere is Google sign-in, and only for form-action.
    assert re.findall(r"https://[^\s;]+", policy) == ["https://accounts.google.com"]
    assert "googleapis" not in policy and "gstatic" not in policy


def test_header_uses_the_production_policy_in_production(client, settings):
    settings(ENV="production", CSP_MODE="enforce")
    policy = client.get("/api/health").headers["content-security-policy"]
    assert policy.endswith("upgrade-insecure-requests")


def test_localhost_does_not_upgrade_requests(client, settings):
    settings(CSP_MODE="enforce")
    assert "upgrade-insecure-requests" not in client.get("/api/health").headers["content-security-policy"]


# --- The frontend loads nothing the policy would block ---------------------------------

needs_frontend = pytest.mark.skipif(not (FRONTEND / "src").exists(), reason="frontend source not present")


@needs_frontend
def test_index_html_has_no_inline_code_and_no_other_sites():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "<style" not in html and " style=" not in html
    for script in re.findall(r"<script[^>]*>", html):
        assert "src=" in script, f"inline script: {script}"
    assert not re.search(r"(src|href)=\"https?://", html), "index.html loads something from another site"


@needs_frontend
def test_fonts_are_self_hosted_with_their_licenses():
    css = "".join(p.read_text(encoding="utf-8") for p in (FRONTEND / "src" / "styles").glob("*.css"))
    assert "fonts.googleapis.com" not in css and "fonts.gstatic.com" not in css
    for url in re.findall(r"url\(\"?([^\")]+)", css):
        assert url.startswith(("/fonts/", "data:")), f"stylesheet loads {url}"
    fonts = FRONTEND / "public" / "fonts"
    assert (fonts / "OFL-Figtree.txt").exists() and (fonts / "OFL-Bricolage-Grotesque.txt").exists()
    assert "SIL OPEN FONT LICENSE Version 1.1" in (fonts / "OFL-Figtree.txt").read_text(encoding="utf-8")


@needs_frontend
def test_frontend_source_never_loads_other_sites_or_evaluates_code():
    for path in (FRONTEND / "src").rglob("*.ts*"):
        source = path.read_text(encoding="utf-8")
        assert "eval(" not in source and "new Function(" not in source, path
        assert "dangerouslySetInnerHTML" not in source, path
        assert not re.search(r"fetch\(\s*[\"'`]https?://", source), f"{path} fetches another site"
