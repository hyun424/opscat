from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p69_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p69-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p69-final-summary.md").read_text(encoding="utf-8")
    for required in ["P69-001", "P69-002", "P69-003", "P69-004", "P69-005", "P69-006", "P69-007", "P69-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P69 Autonomous Worker Runner Evidence",
        "app/services/autonomous_worker_runner.py",
        "scripts/run_autonomous_worker_runner.py",
        "tests/test_autonomous_worker_runner.py",
        "/tmp/opscat-autonomous-worker-runner-latest.md",
    ]:
        assert required in release
    assert "autonomous_worker_runner_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
