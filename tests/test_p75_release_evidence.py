from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p75_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p75-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p75-final-summary.md").read_text(encoding="utf-8")
    for required in ["P75-001", "P75-002", "P75-003", "P75-004", "P75-005", "P75-006", "P75-007", "P75-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P75 Local Safe Subprocess Runner Evidence",
        "app/services/local_safe_subprocess_runner.py",
        "scripts/run_local_safe_subprocess_runner.py",
        "tests/test_local_safe_subprocess_runner.py",
        "/tmp/opscat-local-safe-subprocess-runner-latest.md",
    ]:
        assert required in release
    assert "local_safe_subprocess_runner_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
