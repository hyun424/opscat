from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_p73_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p73-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p73-final-summary.md").read_text(encoding="utf-8")
    for required in ["P73-001", "P73-002", "P73-003", "P73-004", "P73-005", "P73-006", "P73-007", "P73-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P73 Long-Run Loop Controller Evidence",
        "app/services/long_run_loop_controller.py",
        "scripts/run_long_run_loop_controller.py",
        "tests/test_long_run_loop_controller.py",
        "/tmp/opscat-long-run-loop-controller-latest.md",
    ]:
        assert required in release
    assert "long_run_loop_controller_smoke" in verify
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
