from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.safe_auto_run_readiness_gate import (
    P90ReadinessLevel,
    SafeAutoRunReadinessGateReport,
    evaluate_safe_auto_run_readiness_gate_fixture,
    render_safe_auto_run_readiness_gate_markdown,
)

FIXTURE = Path("evals/actions/p90_safe_auto_run_readiness_gate.json")
ZERO_COUNTERS = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "shell_execution_count": 0,
    "process_spawn_count": 0,
    "agent_spawn_count": 0,
    "sleep_call_count": 0,
}
GATE_IDS = {
    "evidence",
    "approval_safety",
    "sandbox_safety",
    "resume_safety",
    "reportability",
    "bounded_scheduling",
    "zero_side_effects",
    "human_handoff",
    "failure_handling",
}


def test_readiness_gate_evaluates_required_scenarios_and_shape() -> None:
    report = evaluate_safe_auto_run_readiness_gate_fixture(FIXTURE)
    payload = report.to_dict()
    scenarios = {row["scenario_id"]: row for row in payload["readiness_results"]}

    assert isinstance(report, SafeAutoRunReadinessGateReport)
    assert set(scenarios) == {
        "clean-local-dry-run",
        "resumable-incomplete",
        "needs-human-severe",
        "failed-guardrail",
        "missing-report-evidence",
        "side-effect-counter-blocked",
    }
    assert payload["summary"]["scenario_count"] == 6
    assert payload["summary"]["executions"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["unattended_production_operation_claimed"] is False

    for result in scenarios.values():
        assert result["readiness_level"] in {level.value for level in P90ReadinessLevel}
        assert 0 <= result["score"] <= 100
        assert set(result["component_scores"]) == GATE_IDS
        assert set(result["gates"]) == GATE_IDS
        assert result["allowed_operating_mode"] in {
            "local_dry_run_only",
            "supervised_shadow_only",
            "human_gated_staging_dry_run",
            "no_auto_run",
        }
        assert "unattended_production_ready" in result["forbidden_claims"]
        assert "operator_replacement_approved" in result["forbidden_claims"]
        assert result["audit_metadata"]["p90_safe_auto_run_readiness_gate"] is True
        assert result["audit_metadata"]["consumes_p89_entrypoint_result"] is True
        assert result["audit_metadata"]["side_effect_free"] is True or result["readiness_level"] == "blocked"
        assert result["zero_side_effect_counters"] == ZERO_COUNTERS or result["readiness_level"] == "blocked"


def test_clean_local_dry_run_is_local_dry_run_ready() -> None:
    payload = evaluate_safe_auto_run_readiness_gate_fixture(FIXTURE).to_dict()
    result = {row["scenario_id"]: row for row in payload["readiness_results"]}["clean-local-dry-run"]

    assert result["readiness_level"] == P90ReadinessLevel.LOCAL_DRY_RUN_READY.value
    assert result["score"] >= 90
    assert all(gate["passed"] is True for gate in result["gates"].values())
    assert result["blockers"] == []
    assert result["warnings"] == []
    assert result["allowed_operating_mode"] == "local_dry_run_only"


def test_resumable_incomplete_is_supervised_shadow_ready_with_warning() -> None:
    payload = evaluate_safe_auto_run_readiness_gate_fixture(FIXTURE).to_dict()
    result = {row["scenario_id"]: row for row in payload["readiness_results"]}["resumable-incomplete"]

    assert result["readiness_level"] == P90ReadinessLevel.SUPERVISED_SHADOW_READY.value
    assert result["score"] >= 80
    assert result["gates"]["resume_safety"]["passed"] is True
    assert result["gates"]["bounded_scheduling"]["passed"] is True
    assert "incomplete_run_requires_supervised_resume" in result["warnings"]
    assert result["allowed_operating_mode"] == "supervised_shadow_only"


def test_needs_human_maps_to_human_gated_staging_or_blocked_by_severity() -> None:
    payload = evaluate_safe_auto_run_readiness_gate_fixture(FIXTURE).to_dict()
    result = {row["scenario_id"]: row for row in payload["readiness_results"]}["needs-human-severe"]

    assert result["readiness_level"] == P90ReadinessLevel.HUMAN_GATED_STAGING_READY.value
    assert result["gates"]["human_handoff"]["passed"] is True
    assert result["allowed_operating_mode"] == "human_gated_staging_dry_run"
    assert "human_review_required_before_continue" in result["warnings"]


def test_failed_guardrail_blocks_auto_run_readiness() -> None:
    payload = evaluate_safe_auto_run_readiness_gate_fixture(FIXTURE).to_dict()
    result = {row["scenario_id"]: row for row in payload["readiness_results"]}["failed-guardrail"]

    assert result["readiness_level"] == P90ReadinessLevel.BLOCKED.value
    assert result["score"] < 70
    assert result["gates"]["failure_handling"]["passed"] is False
    assert "guardrail_failure_requires_fix_before_auto_run" in result["blockers"]
    assert result["allowed_operating_mode"] == "no_auto_run"


def test_missing_report_or_evidence_is_not_ready() -> None:
    payload = evaluate_safe_auto_run_readiness_gate_fixture(FIXTURE).to_dict()
    result = {row["scenario_id"]: row for row in payload["readiness_results"]}["missing-report-evidence"]

    assert result["readiness_level"] == P90ReadinessLevel.NOT_READY.value
    assert result["gates"]["evidence"]["passed"] is False
    assert result["gates"]["reportability"]["passed"] is False
    assert "p87_report_missing" in result["blockers"]
    assert "p76_evidence_sufficiency_missing" in result["blockers"]
    assert result["allowed_operating_mode"] == "no_auto_run"


def test_any_side_effect_counter_blocks_readiness() -> None:
    payload = evaluate_safe_auto_run_readiness_gate_fixture(FIXTURE).to_dict()
    result = {row["scenario_id"]: row for row in payload["readiness_results"]}["side-effect-counter-blocked"]

    assert result["readiness_level"] == P90ReadinessLevel.BLOCKED.value
    assert result["gates"]["zero_side_effects"]["passed"] is False
    assert result["zero_side_effect_counters"]["network_call_count"] == 1
    assert "side_effect_counter_non_zero" in result["blockers"]
    assert result["allowed_operating_mode"] == "no_auto_run"


def test_readiness_gate_summary_counts_and_cli_smoke(tmp_path: Path) -> None:
    output_json = tmp_path / "p90.json"
    output_md = tmp_path / "p90.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_safe_auto_run_readiness_gate.py",
            "--cases",
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

    assert "scenarios=6" in result.stdout
    assert "local_ready=1" in result.stdout
    assert "shadow_ready=1" in result.stdout
    assert "human_gated=1" in result.stdout
    assert "not_ready=1" in result.stdout
    assert "blocked=2" in result.stdout
    assert "executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["local_ready_count"] == 1
    assert payload["summary"]["shadow_ready_count"] == 1
    assert payload["summary"]["human_gated_count"] == 1
    assert payload["summary"]["not_ready_count"] == 1
    assert payload["summary"]["blocked_count"] == 2
    assert "# OpsCat P90 Safe Auto-Run Readiness Gate" in markdown
    assert "not production unattended approval" in markdown
    assert render_safe_auto_run_readiness_gate_markdown(payload).startswith(
        "# OpsCat P90 Safe Auto-Run Readiness Gate"
    )
