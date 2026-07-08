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


def test_p81_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p81-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p81-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P81-001", "P81-002", "P81-003", "P81-004", "P81-005", "P81-006", "P81-007", "P81-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P81 Rollback PR Draft Automation Evidence",
        "app/services/rollback_pr_draft_automation.py",
        "scripts/run_rollback_pr_draft_automation.py",
        "tests/test_rollback_pr_draft_automation.py",
        "evals/policy/p81_rollback_pr_draft_automation.json",
        "/tmp/opscat-rollback-pr-draft-automation-latest.md",
    ]:
        assert required in release
    assert "rollback_pr_draft_automation_smoke" in verify
    assert "P81 active scope: Rollback PR Draft Automation" in roadmap_index
    assert "P81 implemented as Rollback PR Draft Automation evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
