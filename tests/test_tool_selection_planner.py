from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.tool_selection_planner import ToolSelectionPlannerReport, build_tool_selection_planner_report, render_tool_selection_planner_markdown

CASES = Path("evals/investigator/p47_tool_selection_cases.json")


def test_tool_selection_planner_selects_read_only_tools_and_blocks_unsafe() -> None:
    payload = build_tool_selection_planner_report(CASES).to_dict()

    assert isinstance(build_tool_selection_planner_report(CASES), ToolSelectionPlannerReport)
    assert payload["summary"]["case_count"] == 3
    assert payload["summary"]["selected_tool_count"] >= 6
    assert payload["summary"]["blocked_tool_count"] >= 2
    assert payload["summary"]["unsafe_selected_count"] == 0
    assert payload["summary"]["read_only_ratio"] == 1.0
    assert payload["boundary"]["production_mutation_enabled"] is False
    assert all(tool["mode"] == "read_only" for case in payload["cases"] for tool in case["selected_tools"])
    assert any("rollback" in item["reason"] for case in payload["cases"] for item in case["blocked_tools"])


def test_tool_selection_planner_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p47.json"
    output_md = tmp_path / "p47.md"
    subprocess.run(
        ["python", "scripts/run_tool_selection_planner.py", "--cases", str(CASES), "--output-json", str(output_json), "--output-md", str(output_md)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["read_only_ratio"] == 1.0
    assert "# OpsCat Tool Selection Planner" in markdown
    assert "Blocked tools" in markdown
    assert render_tool_selection_planner_markdown(payload).startswith("# OpsCat Tool Selection Planner")
