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


def test_p89_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p89-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p89-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P89-001", "P89-002", "P89-003", "P89-004", "P89-005", "P89-006", "P89-007", "P89-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P89 Safe Local Auto-Run Entrypoint Evidence",
        "app/services/safe_local_auto_run_entrypoint.py",
        "scripts/run_safe_local_auto_run_entrypoint.py",
        "tests/test_safe_local_auto_run_entrypoint.py",
        "evals/actions/p89_safe_local_auto_run_entrypoint.json",
        "/tmp/opscat-safe-local-auto-run-entrypoint-latest.md",
    ]:
        assert required in release
    assert "safe_local_auto_run_entrypoint_smoke" in verify
    assert "P89 active scope: Safe Local Auto-Run Entrypoint" in roadmap_index
    assert "P89 implemented as Safe Local Auto-Run Entrypoint evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
