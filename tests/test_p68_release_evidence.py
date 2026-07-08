from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p68_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p68-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p68-final-summary.md").read_text(encoding="utf-8")
    for required in ["P68-001", "P68-002", "P68-003", "P68-004", "P68-005", "P68-006", "P68-007", "P68-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P68 Autonomous Agent Dispatcher Evidence",
        "app/services/autonomous_agent_dispatcher.py",
        "scripts/run_autonomous_agent_dispatcher.py",
        "tests/test_autonomous_agent_dispatcher.py",
        "/tmp/opscat-autonomous-agent-dispatcher-latest.md",
    ]:
        assert required in release
    assert "autonomous_agent_dispatcher_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
