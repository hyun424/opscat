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


def test_p80_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p80-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p80-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P80-001", "P80-002", "P80-003", "P80-004", "P80-005", "P80-006", "P80-007", "P80-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P80 Approval Automation Policy Lab Evidence",
        "app/services/approval_automation_policy_lab.py",
        "scripts/run_approval_automation_policy_lab.py",
        "tests/test_approval_automation_policy_lab.py",
        "evals/policy/p80_approval_automation_policy_lab.json",
        "/tmp/opscat-approval-automation-policy-lab-latest.md",
    ]:
        assert required in release
    assert "approval_automation_policy_lab_smoke" in verify
    assert "P80 active scope: Approval Automation Policy Lab" in roadmap_index
    assert "P80 implemented as Approval Automation Policy Lab evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
