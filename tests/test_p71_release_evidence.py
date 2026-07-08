from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p71_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p71-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p71-final-summary.md").read_text(encoding="utf-8")
    for required in ["P71-001", "P71-002", "P71-003", "P71-004", "P71-005", "P71-006", "P71-007", "P71-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P71 Supervised Worker Execution Harness Evidence",
        "app/services/supervised_worker_execution_harness.py",
        "scripts/run_supervised_worker_execution_harness.py",
        "tests/test_supervised_worker_execution_harness.py",
        "/tmp/opscat-supervised-worker-execution-harness-latest.md",
    ]:
        assert required in release
    assert "supervised_worker_execution_harness_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
