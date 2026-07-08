from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.controlled_remediation import (
    ControlledRemediationEngine,
    ControlledRemediationReport,
    render_controlled_remediation_markdown,
    run_controlled_remediation_fixture,
)

DRILLS = Path("evals/remediation/p30_drills.json")


def test_controlled_remediation_routes_actions_by_policy() -> None:
    report = run_controlled_remediation_fixture(DRILLS)
    payload = report.to_dict()

    assert isinstance(report, ControlledRemediationReport)
    assert payload["summary"]["drill_count"] >= 5
    assert payload["summary"]["action_count"] >= 12
    assert payload["summary"]["auto_allowed_count"] >= 3
    assert payload["summary"]["approval_required_count"] >= 3
    assert payload["summary"]["blocked_count"] >= 4
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert payload["score"]["simulation_before_decision_count"] == payload["summary"]["action_count"]
    assert payload["boundary"]["production_mutation_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_blocked_capabilities_cannot_be_downgraded_by_llm_or_profile() -> None:
    payload = run_controlled_remediation_fixture(DRILLS).to_dict()
    blocked = [action for drill in payload["drills"] for action in drill["actions"] if action["route"] == "blocked"]

    assert any(action["capability"] == "shell" for action in blocked)
    assert any(action["capability"] == "destructive_cleanup" for action in blocked)
    assert any(action["capability"] == "data_mutation" for action in blocked)
    assert any(action["capability"] == "privilege_escalation" for action in blocked)
    assert all(action["simulation"]["mutation_performed"] is False for action in blocked)
    assert all("blocked_by_policy" in action["reasons"] or "untrusted_evidence" in action["reasons"] for action in blocked)


def test_prompt_injection_and_no_data_restart_remain_blocked() -> None:
    engine = ControlledRemediationEngine()
    payload = engine.run_path(DRILLS).to_dict()
    by_id = {drill["drill_id"]: drill for drill in payload["drills"]}

    injection_actions = by_id["p30-prompt-injection"]["actions"]
    assert all(action["route"] == "blocked" for action in injection_actions if action["capability"] in {"shell", "rollback"})
    no_data_restart = next(action for action in by_id["p30-no-data-restart"]["actions"] if action["capability"] == "restart")
    assert no_data_restart["route"] == "blocked"
    assert "insufficient_evidence" in no_data_restart["reasons"]
    assert "Bearer secret-token" not in json.dumps(payload)


def test_controlled_remediation_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "remediation.json"
    output_md = tmp_path / "remediation.md"

    subprocess.run(
        [
            "python",
            "scripts/run_controlled_remediation.py",
            "--drills",
            str(DRILLS),
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
    assert payload["summary"]["drill_count"] >= 5
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert "# OpsCat Controlled Auto-remediation Simulation Report" in markdown
    assert "simulation-first controlled auto-remediation" in markdown
    assert render_controlled_remediation_markdown(payload).startswith("# OpsCat Controlled Auto-remediation Simulation Report")
