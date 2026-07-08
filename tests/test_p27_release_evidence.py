from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "Bearer secret-token")


def test_p27_ticket_roadmap_lists_connector_readiness_scope() -> None:
    text = Path("docs/operations/p27-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P27 Ticket Roadmap — Connector Readiness and Permission Contract",
        "P27-001",
        "P27-002",
        "P27-003",
        "P27-004",
        "P27-005",
        "P27-006",
        "P27-007",
        "P27-008",
        "no remediation execution",
        "no live writes",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p27_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p27-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P27 Final Summary — Connector Readiness and Permission Contract",
        "P27-001",
        "P27-002",
        "P27-003",
        "P27-004",
        "P27-005",
        "P27-006",
        "P27-007",
        "P27-008",
        "app/services/connector_readiness.py",
        "scripts/run_connector_readiness.py",
        "evals/connectors/readiness/read_only_sources.json",
        "read-only connector readiness",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P27 Connector Readiness and Permission Contract Evidence",
        "docs/operations/p27-ticket-roadmap.md",
        "docs/operations/p27-final-summary.md",
        "tests/test_connector_readiness_contract.py",
        "tests/test_p27_release_evidence.py",
        "/tmp/opscat-connector-readiness-latest.md",
    ]:
        assert required in release
    assert "P27 implemented as Connector Readiness and Permission Contract evidence" in roadmap
    assert "connector_readiness_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
