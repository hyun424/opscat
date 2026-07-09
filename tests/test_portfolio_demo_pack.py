from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.services.portfolio_demo_pack import (
    build_portfolio_demo_pack,
    render_portfolio_demo_pack_markdown,
)

FIXTURE = Path("evals/actions/p93_portfolio_demo_pack.json")
ZERO_COUNTERS = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "external_model_call_count": 0,
    "real_remediation_execution_count": 0,
}


def _pack() -> dict[str, Any]:
    return build_portfolio_demo_pack(FIXTURE)


def test_portfolio_demo_pack_exposes_required_structured_fields() -> None:
    payload = _pack()

    assert payload["demo_id"] == "p93-portfolio-demo-pack"
    assert payload["title"] == "OpsCat Portfolio Demo Narrative & Operator Walkthrough"
    assert "agentic AI incident-response" in payload["portfolio_pitch"]
    assert payload["readiness_status"] == "portfolio_demo_ready_local_mock"
    assert payload["zero_side_effect_counters"] == ZERO_COUNTERS

    for required in [
        "demo_id",
        "title",
        "portfolio_pitch",
        "target_role_signals",
        "architecture_sections",
        "operator_walkthrough_steps",
        "proof_points",
        "safety_boundaries",
        "forbidden_claims",
        "demo_commands",
        "expected_outputs",
        "readiness_status",
        "remaining_gaps",
        "zero_side_effect_counters",
    ]:
        assert required in payload


def test_operator_walkthrough_and_role_signals_cover_agentic_ai_portfolio_story() -> None:
    payload = _pack()
    stages = [step["stage"] for step in payload["operator_walkthrough_steps"]]
    role_signals = {item["signal"]: item for item in payload["target_role_signals"]}

    assert len(stages) >= 8
    assert stages[:8] == ["observe", "correlate", "investigate", "decide", "draft", "act_safely", "verify", "report"]
    assert "improve" in stages
    assert len(payload["proof_points"]) >= 6

    for signal in [
        "tool_use",
        "evidence_grounded_reasoning",
        "policy_safety_gates",
        "autonomous_loop",
        "evaluation_benchmarking",
        "human_approval_handoff",
        "local_mock_dry_run_boundary",
    ]:
        assert signal in role_signals
        assert role_signals[signal]["evidence_refs"]


def test_demo_pack_commands_point_to_existing_one_command_evidence() -> None:
    payload = _pack()
    commands = [item["command"] for item in payload["demo_commands"]]
    expected_outputs = " ".join(payload["expected_outputs"])

    assert len(commands) >= 3
    assert "uv run --no-sync --extra dev python scripts/run_portfolio_demo_pack.py" in commands
    assert any("scripts/run_operator_replacement_acceptance_drill_v3.py" in item for item in commands)
    assert "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs" in commands
    assert "walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0" in expected_outputs


def test_safety_boundaries_and_forbidden_claims_do_not_overstate_autonomy() -> None:
    payload = _pack()
    text = json.dumps(payload, sort_keys=True)

    for required_boundary in [
        "no auth work",
        "no live APIs",
        "no credentials",
        "no network",
        "no production mutation",
        "no real remediation/action execution",
        "no external model/API calls",
    ]:
        assert required_boundary in payload["safety_boundaries"]
    for forbidden in [
        "production_autonomy",
        "unattended_production_operator_replacement",
        "production_remediation_execution",
        "live_api_operation",
        "credentialed_operation",
    ]:
        assert forbidden in payload["forbidden_claims"]
    assert "production autonomy approved" not in text
    assert "unattended production ready" not in text


def test_markdown_renderer_is_portfolio_readable_and_local_mock_bounded() -> None:
    payload = _pack()
    markdown = render_portfolio_demo_pack_markdown(payload)

    assert markdown.startswith("# OpsCat Portfolio Demo Narrative & Operator Walkthrough")
    assert "## One-command demo" in markdown
    assert "## Operator walkthrough" in markdown
    assert "## Proof points" in markdown
    assert "local/mock" in markdown
    assert "not production autonomy" in markdown
    assert "walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0" in markdown


def test_cli_smoke_outputs_required_count_style_line(tmp_path: Path) -> None:
    output_json = tmp_path / "p93.json"
    output_md = tmp_path / "p93.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_portfolio_demo_pack.py",
            "--input",
            str(FIXTURE),
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

    assert "walkthrough_steps>=8 proof_points>=6 commands>=3 executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["walkthrough_steps"] >= 8
    assert payload["summary"]["proof_points"] >= 6
    assert payload["summary"]["commands"] >= 3
    assert payload["summary"]["executions"] == 0
    assert "# OpsCat Portfolio Demo Narrative & Operator Walkthrough" in markdown
