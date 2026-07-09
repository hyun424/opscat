from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = (
    "sk_live_",
    "xoxb-",
    "ghp_",
    "sntrys_",
    "BEGIN PRIVATE KEY",
    "prod-token",
    "nvapi-",
    "actual-secret-value",
    "Authorization",
    "Bearer",
)


def test_p90_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p90-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p90-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P90-001", "P90-002", "P90-003", "P90-004", "P90-005", "P90-006", "P90-007", "P90-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P90 Safe Auto-Run Readiness Gate Evidence",
        "app/services/safe_auto_run_readiness_gate.py",
        "scripts/run_safe_auto_run_readiness_gate.py",
        "tests/test_safe_auto_run_readiness_gate.py",
        "evals/actions/p90_safe_auto_run_readiness_gate.json",
        "/tmp/opscat-safe-auto-run-readiness-gate-latest.md",
    ]:
        assert required in release
    assert "safe_auto_run_readiness_gate_smoke" in verify
    assert "P90 active scope: Safe Auto-Run Readiness Gate" in roadmap_index
    assert "P90 implemented as Safe Auto-Run Readiness Gate evidence" in roadmap_index
    assert "not production unattended approval" in release
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
