from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.night_shift_drill import (
    DrillScenario,
    load_drill_scenarios,
    render_night_shift_markdown,
    run_night_shift_drill,
)
from app.services.runtime_loop_control import ApprovalMode


def test_load_drill_scenarios_wraps_judgment_cases_with_sla_metadata() -> None:
    scenarios = load_drill_scenarios("evals/judgment/seed/cases.json", max_cases=3)

    assert len(scenarios) == 3
    assert all(isinstance(scenario, DrillScenario) for scenario in scenarios)
    assert scenarios[0].case.id == "seed-loghub-deploy-regression"
    assert scenarios[0].sla_ticks == 1
    assert scenarios[1].expected_route_class == "blocked"
    assert scenarios[1].safety_constraints["no_mutating_tools"] is True


def test_night_shift_drill_scores_runtime_safety_and_sla() -> None:
    scenarios = load_drill_scenarios("evals/judgment/seed/cases.json", max_cases=4)

    result = run_night_shift_drill(
        scenarios,
        approval_mode=ApprovalMode.AUTO_READONLY,
        max_ticks=4,
    )
    payload = result.to_dict()

    assert payload["summary"]["scenario_count"] == 4
    assert payload["summary"]["processed_count"] == 4
    assert payload["summary"]["queue_depth"] == 0
    assert payload["score"]["processed_ratio"] == 1.0
    assert payload["score"]["queue_drain_ratio"] == 1.0
    assert payload["score"]["unexpected_completion_count"] == 0
    assert payload["score"]["safety_violation_count"] == 0
    assert payload["boundary"]["action_execution_enabled"] is False
    assert {item["scenario_id"] for item in payload["scenarios"]} == {scenario.scenario_id for scenario in scenarios}


def test_night_shift_markdown_contains_operator_grade_report_sections() -> None:
    result = run_night_shift_drill(
        load_drill_scenarios("evals/judgment/seed/cases.json", max_cases=2),
        approval_mode="auto_readonly",
        max_ticks=2,
    )

    markdown = render_night_shift_markdown(result.to_dict())

    assert "# OpsCat Night-shift Runtime Drill" in markdown
    assert "## Score" in markdown
    assert "## Scenarios" in markdown
    assert "no remediation execution" in markdown
    assert "does not claim unattended production operation" in markdown


def test_night_shift_drill_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "night-drill.json"
    output_md = tmp_path / "night-drill.md"

    subprocess.run(
        [
            "python",
            "scripts/run_night_shift_drill.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--max-cases",
            "3",
            "--max-ticks",
            "3",
            "--approval-mode",
            "auto_readonly",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["scenario_count"] == 3
    assert payload["score"]["safety_violation_count"] == 0
    assert payload["approval_profile"]["mode"] == "auto_readonly"
    assert "# OpsCat Night-shift Runtime Drill" in markdown
