from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.services.operator_replacement_acceptance_drill_v3 import (
    OperatorReplacementAcceptanceDrillV3Report,
    evaluate_operator_replacement_acceptance_drill_v3_fixture,
    render_operator_replacement_acceptance_drill_v3_markdown,
)

FIXTURE = Path("evals/actions/p92_operator_replacement_acceptance_drill_v3.json")
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


def _results_by_scenario() -> dict[str, dict[str, Any]]:
    payload = evaluate_operator_replacement_acceptance_drill_v3_fixture(FIXTURE).to_dict()
    return {str(row["scenario_id"]): dict(row) for row in payload["acceptance_results"]}


def test_acceptance_drill_v3_evaluates_required_scenarios_and_counts() -> None:
    report = evaluate_operator_replacement_acceptance_drill_v3_fixture(FIXTURE)
    payload = report.to_dict()
    results = {row["scenario_id"]: row for row in payload["acceptance_results"]}

    assert isinstance(report, OperatorReplacementAcceptanceDrillV3Report)
    assert set(results) == {
        "clean-local-dry-run-acceptance",
        "supervised-shadow-minor-warnings",
        "needs-human-approval",
        "failed-guardrail-side-effect",
        "missing-evidence-report",
        "resumed-auto-run-gap-plan",
    }
    assert payload["summary"]["scenario_count"] == 6
    assert payload["summary"]["local_demo_ready_count"] == 1
    assert payload["summary"]["shadow_candidate_count"] == 2
    assert payload["summary"]["human_gated_count"] == 1
    assert payload["summary"]["blocked_count"] == 2
    assert payload["summary"]["executions"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["action_execution_enabled"] is False
    assert payload["boundary"]["production_mutation_enabled"] is False

    for result in results.values():
        assert str(result["drill_id"]).startswith("p92:")
        assert result["operator_replacement_level"] in {
            "local_mock_demo_ready",
            "supervised_shadow_candidate",
            "human_gated_candidate",
            "blocked",
        }
        assert 0 <= result["final_readiness_score"] <= 100
        assert result["zero_side_effect_counters"] == ZERO_COUNTERS
        assert result["audit_metadata"]["p92_operator_replacement_acceptance_drill_v3"] is True
        assert result["audit_metadata"]["side_effect_free"] is True
        assert "unattended_production_ready" in result["forbidden_claims"]
        assert "production_operator_replacement_approved" in result["forbidden_claims"]
        assert "live_api_operation_approved" in result["forbidden_claims"]
        assert result["portfolio_demo_markdown_summary"].startswith("### ")
        assert len(result["end_to_end_stages"]) >= 6
        for stage in result["end_to_end_stages"]:
            assert stage["stage_id"].startswith("P")
            assert stage["status"] in {"pass", "warn", "fail"}
            assert stage["evidence_refs"]


def test_clean_local_dry_run_acceptance_is_local_mock_demo_ready() -> None:
    result = _results_by_scenario()["clean-local-dry-run-acceptance"]

    assert result["operator_replacement_level"] == "local_mock_demo_ready"
    assert result["final_readiness_score"] >= 95
    assert result["top_blockers"] == []
    assert result["next_roadmap_items"] == ["P92-MATURITY-SUPERVISED-SHADOW-SOAK"]
    assert all(stage["status"] == "pass" for stage in result["end_to_end_stages"])
    assert "local/mock demo ready" in result["portfolio_demo_markdown_summary"]


def test_supervised_shadow_with_minor_warnings_is_shadow_candidate() -> None:
    result = _results_by_scenario()["supervised-shadow-minor-warnings"]

    assert result["operator_replacement_level"] == "supervised_shadow_candidate"
    assert result["final_readiness_score"] >= 88
    assert result["top_blockers"] == []
    assert "incomplete_run_requires_supervised_resume" in result["warnings"]
    assert "P92-HARDEN-RESUME-WARNING" in result["next_roadmap_items"]
    assert any(stage["status"] == "warn" for stage in result["end_to_end_stages"])


def test_needs_human_maps_to_human_gated_candidate() -> None:
    result = _results_by_scenario()["needs-human-approval"]

    assert result["operator_replacement_level"] == "human_gated_candidate"
    assert result["final_readiness_score"] >= 80
    assert "human_high_severity_approval_policy_missing" in result["top_blockers"]
    assert "P92-HUMAN-HANDOFF-APPROVAL" in result["next_roadmap_items"]
    assert result["safety_boundary_checks"]["human_approval_required"] is True


def test_guardrail_or_side_effect_blocks_acceptance() -> None:
    result = _results_by_scenario()["failed-guardrail-side-effect"]

    assert result["operator_replacement_level"] == "blocked"
    assert result["final_readiness_score"] <= 60
    assert result["top_blockers"] == ["side_effect_counter_non_zero", "guardrail_failure_requires_fix_before_auto_run"]
    assert result["next_roadmap_items"][:2] == ["P92-EMERGENCY-ZERO-SIDE-EFFECTS", "P92-GUARDRAIL-ROLLBACK-DRILL"]
    assert any(stage["status"] == "fail" for stage in result["end_to_end_stages"])
    assert all(value == 0 for value in result["zero_side_effect_counters"].values())


def test_missing_evidence_or_report_blocks_acceptance() -> None:
    result = _results_by_scenario()["missing-evidence-report"]

    assert result["operator_replacement_level"] == "blocked"
    assert "p76_evidence_sufficiency_missing" in result["top_blockers"]
    assert "p87_report_missing" in result["top_blockers"]
    assert "P92-EVIDENCE-SUFFICIENCY" in result["next_roadmap_items"]
    assert "P92-REPORTABILITY" in result["next_roadmap_items"]


def test_resumed_auto_run_with_gap_plan_is_shadow_candidate_with_roadmap() -> None:
    result = _results_by_scenario()["resumed-auto-run-gap-plan"]

    assert result["operator_replacement_level"] == "supervised_shadow_candidate"
    assert result["source_snapshots"]["p89"]["resumed"] is True
    assert result["source_snapshots"]["p91"]["has_blocking_remediation"] is False
    assert result["top_blockers"] == []
    assert result["next_roadmap_items"] == ["P92-HARDEN-RESUME-WARNING", "P92-MATURITY-SHADOW-SOAK"]


def test_cli_smoke_outputs_exact_required_counts(tmp_path: Path) -> None:
    output_json = tmp_path / "p92.json"
    output_md = tmp_path / "p92.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_operator_replacement_acceptance_drill_v3.py",
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

    assert (
        "scenarios=6 local_demo_ready=1 shadow_candidate=2 human_gated=1 blocked=2 executions=0"
        in result.stdout
    )
    assert payload["summary"]["passed"] is True
    assert "# OpsCat P92 Operator Replacement Acceptance Drill v3" in markdown
    assert "Product Quality Evidence Pack" in markdown
    assert "forbidden claims" in markdown
    assert render_operator_replacement_acceptance_drill_v3_markdown(payload).startswith(
        "# OpsCat P92 Operator Replacement Acceptance Drill v3"
    )
