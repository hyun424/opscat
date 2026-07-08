from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p38_ticket_roadmap_lists_dashboard_scope() -> None:
    text = Path("docs/operations/p38-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P38 Ticket Roadmap — Agent Evaluation Dashboard",
        "P38-001",
        "P38-002",
        "P38-003",
        "P38-004",
        "P38-005",
        "P38-006",
        "P38-007",
        "P38-008",
        "no hosted dashboard requirement",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p38_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p38-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P38 Final Summary — Agent Evaluation Dashboard",
        "P38-001",
        "P38-002",
        "P38-003",
        "P38-004",
        "P38-005",
        "P38-006",
        "P38-007",
        "P38-008",
        "app/services/agent_evaluation_dashboard.py",
        "scripts/run_agent_evaluation_dashboard.py",
        "evals/dashboard/p38_sources.json",
        "readiness tier",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P38 Agent Evaluation Dashboard Evidence",
        "docs/operations/p38-ticket-roadmap.md",
        "docs/operations/p38-final-summary.md",
        "tests/test_agent_evaluation_dashboard.py",
        "tests/test_p38_release_evidence.py",
        "/tmp/opscat-agent-evaluation-dashboard-latest.md",
    ]:
        assert required in release
    assert "P38 active scope: Agent Evaluation Dashboard" in roadmap
    assert "agent_evaluation_dashboard_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
