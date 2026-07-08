from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p67_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p67-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p67-final-summary.md").read_text(encoding="utf-8")
    for required in ["P67-001", "P67-002", "P67-003", "P67-004", "P67-005", "P67-006", "P67-007", "P67-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P67 Autonomous Loop Executor Evidence",
        "app/services/autonomous_loop_executor.py",
        "scripts/run_autonomous_loop_executor.py",
        "tests/test_autonomous_loop_executor.py",
        "/tmp/opscat-autonomous-loop-executor-latest.md",
    ]:
        assert required in release
    assert "autonomous_loop_executor_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
