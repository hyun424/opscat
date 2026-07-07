"""OSS release packaging and versioned evidence documentation contracts."""

from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "secrets.")


def test_changelog_describes_p4_evidence_and_p5_active_scope() -> None:
    path = Path("CHANGELOG.md")

    assert path.exists()
    text = path.read_text()
    for required in [
        "# Changelog",
        "Unreleased",
        "P4 evidence",
        "P5 OSS productization",
        "auth deferred",
        "local/mock",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_release_evidence_includes_versioned_snapshot_command_and_artifacts() -> None:
    text = Path("docs/release-evidence.md").read_text()

    for required in [
        "versioned release evidence snapshot",
        "bash scripts/verify.sh --profile full",
        "docs/release-evidence.md",
        "/tmp/opscat-evals-latest.md",
        "/tmp/opscat-connector-evals-latest.md",
        "stable vs experimental",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_deployment_dry_run_docs_are_linked_from_readme() -> None:
    deployment = Path("docs/deployment-dry-run.md")
    readme = Path("README.md").read_text()

    assert deployment.exists()
    text = deployment.read_text()
    for required in [
        "# Deployment Dry Run",
        "Docker Compose",
        "local Postgres",
        "DATABASE_URL",
        "auth remains deferred",
        "stable vs experimental",
        "no production credentials",
    ]:
        assert required in text
    assert "docs/deployment-dry-run.md" in readme
    assert all(marker not in text for marker in SECRET_MARKERS)
