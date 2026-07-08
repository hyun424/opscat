from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p39_ticket_roadmap_lists_learning_scope() -> None:
    text = Path("docs/operations/p39-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P39 Ticket Roadmap — Runbook Learning Loop",
        "P39-001",
        "P39-002",
        "P39-003",
        "P39-004",
        "P39-005",
        "P39-006",
        "P39-007",
        "P39-008",
        "no automatic production runbook edits",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p39_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p39-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P39 Final Summary — Runbook Learning Loop",
        "P39-001",
        "P39-002",
        "P39-003",
        "P39-004",
        "P39-005",
        "P39-006",
        "P39-007",
        "P39-008",
        "app/services/runbook_learning_loop.py",
        "scripts/run_runbook_learning_loop.py",
        "evals/learning/p39_sources.json",
        "applied change count",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P39 Runbook Learning Loop Evidence",
        "docs/operations/p39-ticket-roadmap.md",
        "docs/operations/p39-final-summary.md",
        "tests/test_runbook_learning_loop.py",
        "tests/test_p39_release_evidence.py",
        "/tmp/opscat-runbook-learning-loop-latest.md",
    ]:
        assert required in release
    assert "P39 active scope: Runbook Learning Loop" in roadmap
    assert "runbook_learning_loop_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
