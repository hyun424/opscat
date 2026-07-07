from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p19_ticket_roadmap_lists_operator_improvement_scope() -> None:
    text = Path("docs/operations/p19-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P19 Ticket Roadmap — Operator Judgment Improvement Loop",
        "P19-001",
        "P19-002",
        "P19-003",
        "P19-004",
        "P19-005",
        "P19-006",
        "P19-007",
        "P19-008",
        "No auth work",
        "No production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p19_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p19-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P19 Final Summary — Operator Judgment Improvement Loop",
        "P19-001",
        "P19-002",
        "P19-003",
        "P19-004",
        "P19-005",
        "P19-006",
        "P19-007",
        "P19-008",
        "app/services/operator_improvement_loop.py",
        "scripts/run_improvement_loop.py",
        "tests/test_operator_improvement_loop.py",
        "regression pack",
        "failure priorities",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P19 Operator Judgment Improvement Loop Evidence",
        "docs/operations/p19-ticket-roadmap.md",
        "docs/operations/p19-final-summary.md",
        "tests/test_operator_improvement_loop.py",
        "tests/test_p19_release_evidence.py",
        "/tmp/opscat-improvement-loop-latest.md",
    ]:
        assert required in release
    assert "P19 implemented as Operator Judgment Improvement Loop evidence" in roadmap
    assert "operator_improvement_loop_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
