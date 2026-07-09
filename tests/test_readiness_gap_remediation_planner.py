from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.services.readiness_gap_remediation_planner import (
    ReadinessGapRemediationPlannerReport,
    evaluate_readiness_gap_remediation_planner_fixture,
    render_readiness_gap_remediation_planner_markdown,
)

FIXTURE = Path("evals/actions/p91_readiness_gap_remediation_planner.json")
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


def _plans_by_scenario() -> dict[str, dict[str, Any]]:
    payload = evaluate_readiness_gap_remediation_planner_fixture(FIXTURE).to_dict()
    return {str(row["source_scenario_id"]): dict(row) for row in payload["remediation_plans"]}


def test_planner_evaluates_required_scenarios_and_shape() -> None:
    report = evaluate_readiness_gap_remediation_planner_fixture(FIXTURE)
    payload = report.to_dict()
    plans = {row["source_scenario_id"]: row for row in payload["remediation_plans"]}

    assert isinstance(report, ReadinessGapRemediationPlannerReport)
    assert set(plans) == {
        "local-ready-minor-warnings",
        "missing-evidence-report",
        "side-effect-counter-detected",
        "failed-guardrail",
        "needs-human-high-severity",
        "clean-ready-state",
    }
    assert payload["summary"]["scenario_count"] == 6
    assert payload["summary"]["blocking_plans"] == 4
    assert payload["summary"]["emergency_items"] == 1
    assert payload["summary"]["human_gated_items"] == 1
    assert payload["summary"]["maturity_items"] >= 2
    assert payload["summary"]["executions"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["remediation_execution_enabled"] is False

    for plan in plans.values():
        assert str(plan["plan_id"]).startswith("p91:")
        assert str(plan["source_readiness_id"]).startswith("p90:")
        assert plan["audit_metadata"]["p91_readiness_gap_remediation_planner"] is True
        assert plan["audit_metadata"]["source_is_p90_readiness_result"] is True
        assert plan["audit_metadata"]["side_effect_free"] is True
        assert plan["zero_side_effect_counters"] == ZERO_COUNTERS
        assert "unattended_production_ready" in plan["claims_remain_forbidden_until_resolved"]
        assert "operator_replacement_approved" in plan["claims_remain_forbidden_until_resolved"]
        for item in plan["remediation_items"]:
            assert item["id"].startswith("P91-")
            assert item["severity"] in {"emergency", "high", "medium", "low", "maturity"}
            assert 0 <= item["expected_readiness_lift"] <= 40
            assert item["required_evidence_tests"]
            assert item["owner_lane"] in {
                "safety",
                "evidence",
                "failure-handling",
                "human-ops",
                "platform",
                "maturity",
            }
            assert item["risk"]
            assert item["stop_condition"]
            assert item["next_safe_operating_mode"] in {
                "no_auto_run",
                "local_dry_run_only",
                "supervised_shadow_only",
                "human_gated_staging_dry_run",
            }


def test_local_ready_with_minor_warnings_gets_low_priority_hardening_backlog() -> None:
    plan = _plans_by_scenario()["local-ready-minor-warnings"]
    items = plan["remediation_items"]

    assert plan["has_blocking_remediation"] is False
    assert [item["severity"] for item in items] == ["low", "maturity"]
    assert items[0]["id"] == "P91-HARDEN-RESUME-WARNING"
    assert items[0]["next_safe_operating_mode"] == "local_dry_run_only"
    assert "incomplete_run_requires_supervised_resume" in items[0]["required_evidence_tests"]


def test_missing_evidence_report_prioritizes_evidence_and_reportability_tasks() -> None:
    plan = _plans_by_scenario()["missing-evidence-report"]
    items = plan["remediation_items"]

    assert plan["has_blocking_remediation"] is True
    assert [item["id"] for item in items[:2]] == ["P91-EVIDENCE-SUFFICIENCY", "P91-REPORTABILITY"]
    assert all(item["owner_lane"] == "evidence" for item in items[:2])
    assert items[0]["next_safe_operating_mode"] == "no_auto_run"
    assert "p76_evidence_sufficiency_missing" in plan["claims_remain_forbidden_until_resolved"]


def test_side_effect_counter_detected_creates_emergency_safety_blocker_first() -> None:
    plan = _plans_by_scenario()["side-effect-counter-detected"]
    first = plan["remediation_items"][0]

    assert first["id"] == "P91-EMERGENCY-ZERO-SIDE-EFFECTS"
    assert first["severity"] == "emergency"
    assert first["owner_lane"] == "safety"
    assert first["expected_readiness_lift"] >= 30
    assert first["next_safe_operating_mode"] == "no_auto_run"
    assert "network_call_count=1" in first["risk"]
    assert "side_effect_counter_non_zero" in plan["claims_remain_forbidden_until_resolved"]


def test_failed_guardrail_prioritizes_failure_handling_and_rollback_drills() -> None:
    plan = _plans_by_scenario()["failed-guardrail"]
    first = plan["remediation_items"][0]

    assert first["id"] == "P91-GUARDRAIL-ROLLBACK-DRILL"
    assert first["severity"] == "high"
    assert first["owner_lane"] == "failure-handling"
    assert "rollback drill" in first["stop_condition"]
    assert first["next_safe_operating_mode"] == "no_auto_run"
    assert "guardrail_failure_requires_fix_before_auto_run" in plan["claims_remain_forbidden_until_resolved"]


def test_needs_human_high_severity_is_human_gated_and_approval_policy_first() -> None:
    plan = _plans_by_scenario()["needs-human-high-severity"]
    first = plan["remediation_items"][0]

    assert first["id"] == "P91-HUMAN-HANDOFF-APPROVAL"
    assert first["severity"] == "high"
    assert first["owner_lane"] == "human-ops"
    assert first["human_gated"] is True
    assert first["next_safe_operating_mode"] == "human_gated_staging_dry_run"
    assert plan["blocked_human_gated_items"] == ["P91-HUMAN-HANDOFF-APPROVAL"]


def test_clean_ready_state_has_no_blocking_remediation_only_maturity_tasks() -> None:
    plan = _plans_by_scenario()["clean-ready-state"]

    assert plan["has_blocking_remediation"] is False
    assert plan["blocked_human_gated_items"] == []
    assert [item["severity"] for item in plan["remediation_items"]] == ["maturity"]
    assert plan["remediation_items"][0]["id"] == "P91-MATURITY-SHADOW-SOAK"
    assert plan["remediation_items"][0]["next_safe_operating_mode"] == "supervised_shadow_only"


def test_cli_smoke_outputs_required_summary(tmp_path: Path) -> None:
    output_json = tmp_path / "p91.json"
    output_md = tmp_path / "p91.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_readiness_gap_remediation_planner.py",
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
    assert "blocking_plans=4" in result.stdout
    assert "emergency_items=1" in result.stdout
    assert "human_gated_items=1" in result.stdout
    assert "maturity_items=" in result.stdout
    assert "executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert "# OpsCat P91 Readiness Gap Remediation Planner" in markdown
    assert "roadmap/planning artifact" in markdown
    assert render_readiness_gap_remediation_planner_markdown(payload).startswith(
        "# OpsCat P91 Readiness Gap Remediation Planner"
    )
