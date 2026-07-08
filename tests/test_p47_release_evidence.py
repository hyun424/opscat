from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value")


def test_p47_docs_and_verify_are_wired() -> None:
    summary = Path("docs/operations/p47-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")
    verify = Path("scripts/verify.sh").read_text(encoding="utf-8")
    fixture = Path("evals/investigator/p47_tool_selection_cases.json").read_text(encoding="utf-8")
    for required in ["P47-001", "P47-002", "P47-003", "P47-004", "P47-005", "P47-006", "P47-007", "P47-008", "app/services/tool_selection_planner.py", "scripts/run_tool_selection_planner.py"]:
        assert required in summary
    for required in ["P47 Tool Selection Planner Evidence", "tests/test_tool_selection_planner.py", "/tmp/opscat-tool-selection-planner-latest.md"]:
        assert required in release
    assert "tool_selection_planner_smoke" in verify
    assert "p47-dangerous-tool" in fixture
    assert all(marker not in summary + release + fixture for marker in SECRET_MARKERS)
