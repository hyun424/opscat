from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-")


def test_p20_ticket_roadmap_lists_closed_loop_scope() -> None:
    text = Path("docs/operations/p20-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P20 Ticket Roadmap — Closed-loop Agentic Incident Response",
        "P20-001",
        "P20-002",
        "P20-003",
        "P20-004",
        "P20-005",
        "P20-006",
        "P20-007",
        "P20-008",
        "No auth work",
        "No production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p20_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p20-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P20 Final Summary — Closed-loop Agentic Incident Response",
        "P20-001",
        "P20-002",
        "P20-003",
        "P20-004",
        "P20-005",
        "P20-006",
        "P20-007",
        "P20-008",
        "app/services/closed_loop_response.py",
        "scripts/run_closed_loop_response.py",
        "tests/test_closed_loop_response.py",
        "initial_judgment",
        "evidence_fetch",
        "revised_judgment",
        "simulation",
        "no-auth/local-mock by default",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P20 Closed-loop Agentic Incident Response Evidence",
        "docs/operations/p20-ticket-roadmap.md",
        "docs/operations/p20-final-summary.md",
        "tests/test_closed_loop_response.py",
        "tests/test_p20_release_evidence.py",
        "/tmp/opscat-closed-loop-latest.md",
    ]:
        assert required in release
    assert "P20 implemented as Closed-loop Agentic Incident Response evidence" in roadmap
    assert "closed_loop_response_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
