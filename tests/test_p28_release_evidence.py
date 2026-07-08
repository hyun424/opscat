from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "Bearer secret-token")


def test_p28_ticket_roadmap_lists_polling_runtime_scope() -> None:
    text = Path("docs/operations/p28-ticket-roadmap.md").read_text(encoding="utf-8")
    for required in [
        "# OpsCat P28 Ticket Roadmap — Read-only Polling Runtime",
        "P28-001",
        "P28-002",
        "P28-003",
        "P28-004",
        "P28-005",
        "P28-006",
        "P28-007",
        "P28-008",
        "read-only polling only",
        "no production mutation",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_p28_final_summary_release_evidence_and_verify_exist() -> None:
    summary = Path("docs/operations/p28-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")

    for required in [
        "# OpsCat P28 Final Summary — Read-only Polling Runtime",
        "P28-001",
        "P28-002",
        "P28-003",
        "P28-004",
        "P28-005",
        "P28-006",
        "P28-007",
        "P28-008",
        "app/services/read_only_polling_runtime.py",
        "scripts/run_read_only_polling.py",
        "evals/polling/jobs/p28_polling_jobs.json",
        "fixture/local transport only",
        "P27 readiness",
        "P26 adapters",
        "does not claim unattended production operation",
    ]:
        assert required in summary
    for required in [
        "P28 Read-only Polling Runtime Evidence",
        "docs/operations/p28-ticket-roadmap.md",
        "docs/operations/p28-final-summary.md",
        "tests/test_read_only_polling_runtime.py",
        "tests/test_p28_release_evidence.py",
        "/tmp/opscat-read-only-polling-latest.md",
    ]:
        assert required in release
    assert "P28 implemented as Read-only Polling Runtime evidence" in roadmap
    assert "read_only_polling_smoke" in verify
    assert all(marker not in summary for marker in SECRET_MARKERS)
