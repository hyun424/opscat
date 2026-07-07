"""Beta onboarding walkthrough docs for P5."""

from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_beta_walkthrough_is_copy_paste_local_and_auth_deferred() -> None:
    path = Path("docs/beta-walkthrough.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# 10-Minute Beta Walkthrough",
        "No auth setup is required",
        "local-header demo identity",
        "GET /connectors",
        "PUT /secrets/sentry.token",
        "POST /webhooks/alerts/fixture",
        "GET /operator/actions/",
        "POST /approvals/",
        "GET /incidents/",
        "POST /night-autopilot/simulate",
        "bash scripts/verify.sh --profile full",
        "not production-ready",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_readme_links_beta_walkthrough_and_release_boundaries() -> None:
    text = Path("README.md").read_text()

    for required in [
        "docs/beta-walkthrough.md",
        "docs/connector-permissions.md",
        "docs/release-evidence.md",
        "docs/deployment-dry-run.md",
        "No auth setup is required",
        "auth is deferred",
    ]:
        assert required in text
