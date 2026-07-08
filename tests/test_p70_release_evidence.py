from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p70_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p70-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p70-final-summary.md").read_text(encoding="utf-8")
    for required in ["P70-001", "P70-002", "P70-003", "P70-004", "P70-005", "P70-006", "P70-007", "P70-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P70 Gated Worker Process Runner Evidence",
        "app/services/gated_worker_process_runner.py",
        "scripts/run_gated_worker_process_runner.py",
        "tests/test_gated_worker_process_runner.py",
        "/tmp/opscat-gated-worker-process-runner-latest.md",
    ]:
        assert required in release
    assert "gated_worker_process_runner_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
