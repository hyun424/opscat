from __future__ import annotations

from pathlib import Path

from scripts.run_agentic_evals import REQUIRED_DIMENSIONS, run_agentic_evals


def test_agentic_eval_runner_reports_required_dimensions(tmp_path: Path) -> None:
    json_path = tmp_path / "agentic.json"
    md_path = tmp_path / "agentic.md"

    summary = run_agentic_evals(output_json=json_path, output_md=md_path)

    assert summary["total"] >= 20
    assert set(REQUIRED_DIMENSIONS).issubset(summary["dimensions"])
    assert summary["dimensions"]["unsafe_action_blocking"]["passed"] == summary["dimensions"]["unsafe_action_blocking"]["total"]
    assert json_path.exists()
    assert "OpsCat P6 Agentic Eval Report" in md_path.read_text()
