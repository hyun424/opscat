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


def test_p83_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p83-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p83-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P83-001", "P83-002", "P83-003", "P83-004", "P83-005", "P83-006", "P83-007", "P83-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P83 Post-Action Outcome Monitor Evidence",
        "app/services/post_action_outcome_monitor.py",
        "scripts/run_post_action_outcome_monitor.py",
        "tests/test_post_action_outcome_monitor.py",
        "evals/actions/p83_post_action_outcome_monitor.json",
        "/tmp/opscat-post-action-outcome-monitor-latest.md",
    ]:
        assert required in release
    assert "post_action_outcome_monitor_smoke" in verify
    assert "P83 active scope: Post-Action Outcome Monitor" in roadmap_index
    assert "P83 implemented as Post-Action Outcome Monitor evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
