from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "Bearer secret-token")


def test_p31_ticket_roadmap_lists_operator_replacement_scope() -> None:
    text = Path("docs/operations/p31-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P31 Ticket Roadmap — End-to-End Operator Replacement Drill",
        "P31-001",
        "P31-002",
        "P31-003",
        "P31-004",
        "P31-005",
        "P31-006",
        "P31-007",
        "P31-008",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p31_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p31-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P31 Final Summary — End-to-End Operator Replacement Drill",
        "P31-001",
        "P31-002",
        "P31-003",
        "P31-004",
        "P31-005",
        "P31-006",
        "P31-007",
        "P31-008",
        "app/services/operator_replacement_drill.py",
        "scripts/run_operator_replacement_drill.py",
        "evals/operator_replacement/p31_scenarios.json",
        "portfolio-grade operator replacement drill",
        "operator_replacement_score",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P31 End-to-End Operator Replacement Drill Evidence",
        "docs/operations/p31-ticket-roadmap.md",
        "docs/operations/p31-final-summary.md",
        "tests/test_operator_replacement_drill.py",
        "tests/test_p31_release_evidence.py",
        "/tmp/opscat-operator-replacement-latest.md",
    ]:
        assert required in release
    assert "P31 implemented as End-to-End Operator Replacement Drill evidence" in roadmap
    assert "operator_replacement_drill_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
