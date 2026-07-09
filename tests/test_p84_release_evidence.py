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


def test_p84_docs_and_verify_are_wired() -> None:
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    roadmap = Path("docs/operations/p84-ticket-roadmap.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p84-final-summary.md").read_text(encoding="utf-8")
    roadmap_index = Path("ROADMAP.md").read_text(encoding="utf-8")

    for required in ["P84-001", "P84-002", "P84-003", "P84-004", "P84-005", "P84-006", "P84-007", "P84-008"]:
        assert required in roadmap
        assert required in summary
    for required in [
        "P84 Outcome-Driven Next Action Planner Evidence",
        "app/services/outcome_driven_next_action_planner.py",
        "scripts/run_outcome_driven_next_action_planner.py",
        "tests/test_outcome_driven_next_action_planner.py",
        "evals/actions/p84_outcome_driven_next_action_planner.json",
        "/tmp/opscat-outcome-driven-next-action-planner-latest.md",
    ]:
        assert required in release
    assert "outcome_driven_next_action_planner_smoke" in verify
    assert "P84 active scope: Outcome-Driven Next Action Planner" in roadmap_index
    assert "P84 implemented as Outcome-Driven Next Action Planner evidence" in roadmap_index
    assert all(marker not in release + roadmap + summary for marker in SECRET_MARKERS)
