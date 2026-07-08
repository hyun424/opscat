from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p72_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p72-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p72-final-summary.md").read_text(encoding="utf-8")
    for required in ["P72-001", "P72-002", "P72-003", "P72-004", "P72-005", "P72-006", "P72-007", "P72-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P72 Stateful All-Day Loop Orchestrator Evidence",
        "app/services/stateful_all_day_loop_orchestrator.py",
        "scripts/run_stateful_all_day_loop_orchestrator.py",
        "tests/test_stateful_all_day_loop_orchestrator.py",
        "/tmp/opscat-stateful-all-day-loop-orchestrator-latest.md",
    ]:
        assert required in release
    assert "stateful_all_day_loop_orchestrator_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
