from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.night_operator_drill_v2 import NightOperatorDrillV2Report, build_night_operator_drill_v2_report, render_night_operator_drill_v2_markdown

CASES = Path("evals/investigator/p50_night_operator_cases.json")


def test_night_operator_drill_v2_chains_operator_gates_without_prod_autopilot_claim() -> None:
    report = build_night_operator_drill_v2_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, NightOperatorDrillV2Report)
    assert payload["summary"]["drill_count"] >= 2
    assert payload["summary"]["evidence_contract_pass_count"] == payload["summary"]["drill_count"]
    assert payload["summary"]["investigation_complete_count"] == payload["summary"]["drill_count"]
    assert payload["summary"]["read_only_tool_plan_count"] >= payload["summary"]["drill_count"]
    assert payload["summary"]["remediation_verification_count"] >= 1
    assert payload["summary"]["production_execution_count"] == 0
    assert payload["summary"]["unsafe_auto_execute_count"] == 0
    assert payload["readiness"]["local_night_watch_ready"] is True
    assert payload["readiness"]["unattended_production_ready"] is False
    assert all(drill["decision_trace"] for drill in payload["drills"])


def test_night_operator_drill_v2_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p50.json"
    output_md = tmp_path / "p50.md"
    subprocess.run(
        ["python", "scripts/run_night_operator_drill_v2.py", "--drills", str(CASES), "--output-json", str(output_json), "--output-md", str(output_md)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Night Operator Drill v2" in markdown
    assert "unattended_production_ready=false" in markdown
    assert render_night_operator_drill_v2_markdown(payload).startswith("# OpsCat Night Operator Drill v2")
