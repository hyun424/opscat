"""CI-ready verification profile contract for P5."""

from __future__ import annotations

from pathlib import Path


def test_verify_script_exposes_named_profiles() -> None:
    verify = Path("scripts/verify.sh").read_text()

    assert "VERIFY_PROFILE" in verify
    assert "--profile" in verify
    for profile in ["fast", "full", "eval", "docs"]:
        assert profile in verify
    assert "Unknown verify profile" in verify


def test_github_actions_ci_runs_secret_free_full_verification() -> None:
    workflow = Path(".github/workflows/ci.yml")

    assert workflow.exists()
    text = workflow.read_text()
    for required in [
        "OpsCat CI",
        "bash scripts/verify.sh --profile full",
        "OPSCAT_MODE: test",
        "DATABASE_URL",
        "contents: read",
    ]:
        assert required in text
    forbidden = ["SENTRY_AUTH_TOKEN", "GITHUB_TOKEN", "SLACK_BOT_TOKEN", "secrets."]
    assert all(marker not in text for marker in forbidden)


def test_release_evidence_documents_ci_profiles() -> None:
    text = Path("docs/release-evidence.md").read_text()

    for required in [
        "--profile fast",
        "--profile full",
        "--profile eval",
        "--profile docs",
        ".github/workflows/ci.yml",
    ]:
        assert required in text
