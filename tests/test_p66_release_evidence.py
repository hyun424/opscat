from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p66_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p66-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p66-final-summary.md").read_text(encoding="utf-8")
    for required in ["P66-001", "P66-002", "P66-003", "P66-004", "P66-005", "P66-006", "P66-007", "P66-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P66 Autonomous Day Loop Backlog Evidence",
        "evals/planning/p66_autonomous_day_loop_backlog.json",
        "app/services/autonomous_day_loop_backlog.py",
        "scripts/run_autonomous_day_loop_backlog.py",
        "tests/test_autonomous_day_loop_backlog.py",
        "/tmp/opscat-autonomous-day-loop-backlog-latest.md",
    ]:
        assert required in release
    assert "autonomous_day_loop_backlog_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
