from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p34_ticket_roadmap_lists_polling_v2_scope() -> None:
    text = Path("docs/operations/p34-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P34 Ticket Roadmap — Live Read-only Polling Runtime v2",
        "P34-001",
        "P34-002",
        "P34-003",
        "P34-004",
        "P34-005",
        "P34-006",
        "P34-007",
        "P34-008",
        "no live API calls",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p34_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p34-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P34 Final Summary — Live Read-only Polling Runtime v2",
        "P34-001",
        "P34-002",
        "P34-003",
        "P34-004",
        "P34-005",
        "P34-006",
        "P34-007",
        "P34-008",
        "app/services/read_only_polling_v2.py",
        "scripts/run_read_only_polling_v2.py",
        "evals/polling/v2/p34_polling_jobs.json",
        "poll_success_rate",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P34 Live Read-only Polling Runtime v2 Evidence",
        "docs/operations/p34-ticket-roadmap.md",
        "docs/operations/p34-final-summary.md",
        "tests/test_read_only_polling_v2.py",
        "tests/test_p34_release_evidence.py",
        "/tmp/opscat-read-only-polling-v2-latest.md",
    ]:
        assert required in release
    assert "P34 implemented as Live Read-only Polling Runtime v2 evidence" in roadmap
    assert "read_only_polling_v2_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
