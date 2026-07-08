from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p33_ticket_roadmap_lists_dry_run_scope() -> None:
    text = Path("docs/operations/p33-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P33 Ticket Roadmap — Live Connector Dry-run Harness",
        "P33-001",
        "P33-002",
        "P33-003",
        "P33-004",
        "P33-005",
        "P33-006",
        "P33-007",
        "P33-008",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p33_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p33-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P33 Final Summary — Live Connector Dry-run Harness",
        "P33-001",
        "P33-002",
        "P33-003",
        "P33-004",
        "P33-005",
        "P33-006",
        "P33-007",
        "P33-008",
        "app/services/live_connector_dry_run.py",
        "scripts/run_live_connector_dry_run.py",
        "evals/connectors/dry_run/p33_connectors.json",
        "connector_health_score",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P33 Live Connector Dry-run Harness Evidence",
        "docs/operations/p33-ticket-roadmap.md",
        "docs/operations/p33-final-summary.md",
        "tests/test_live_connector_dry_run.py",
        "tests/test_p33_release_evidence.py",
        "/tmp/opscat-live-connector-dry-run-latest.md",
    ]:
        assert required in release
    assert "P33 implemented as Live Connector Dry-run Harness evidence" in roadmap
    assert "live_connector_dry_run_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
