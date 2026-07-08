from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p74_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p74-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p74-final-summary.md").read_text(encoding="utf-8")
    for required in ["P74-001", "P74-002", "P74-003", "P74-004", "P74-005", "P74-006", "P74-007", "P74-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P74 Real Subprocess Execution Dry-Run Gate Evidence",
        "app/services/real_subprocess_execution_dry_run_gate.py",
        "scripts/run_real_subprocess_execution_dry_run_gate.py",
        "tests/test_real_subprocess_execution_dry_run_gate.py",
        "/tmp/opscat-real-subprocess-dry-run-gate-latest.md",
    ]:
        assert required in release
    assert "real_subprocess_execution_dry_run_gate_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
