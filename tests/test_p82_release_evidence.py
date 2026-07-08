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


def test_p82_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p82-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p82-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P82-001", "P82-002", "P82-003", "P82-004", "P82-005", "P82-006", "P82-007", "P82-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P82 Slack and Ticket Draft Automation Evidence",
        "app/services/slack_ticket_draft_automation.py",
        "scripts/run_slack_ticket_draft_automation.py",
        "tests/test_slack_ticket_draft_automation.py",
        "evals/policy/p82_slack_ticket_draft_automation.json",
        "/tmp/opscat-slack-ticket-draft-automation-latest.md",
    ]:
        assert required in release
    assert "slack_ticket_draft_automation_smoke" in verify
    assert "P82 active scope: Slack and Ticket Draft Automation" in roadmap_index
    assert "P82 implemented as Slack and Ticket Draft Automation evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
