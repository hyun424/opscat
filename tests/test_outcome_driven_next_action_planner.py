from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.outcome_driven_next_action_planner import (
    NextActionDecision,
    OutcomeDrivenNextActionReport,
    evaluate_outcome_driven_next_action_fixture,
    render_outcome_driven_next_action_markdown,
)

FIXTURE = Path("evals/actions/p84_outcome_driven_next_action_planner.json")


def test_outcome_driven_next_action_planner_evaluates_required_scenarios() -> None:
    report = evaluate_outcome_driven_next_action_fixture(FIXTURE)
    payload = report.to_dict()
    plans = {row["scenario_id"]: row for row in payload["next_action_plans"]}

    assert isinstance(report, OutcomeDrivenNextActionReport)
    assert set(plans) == {
        "resolved-final-report-ready",
        "improving-worker-recheck",
        "unchanged-db-saturation-window-exceeded",
        "worsened-after-mitigation",
        "inconclusive-noisy-no-execution",
        "blocked-unsafe-action-human-escalation",
    }

    for row in plans.values():
        assert row["selected_next_action"] in {item.value for item in NextActionDecision}
        assert row["rationale"]
        assert isinstance(row["required_evidence"], list)
        assert isinstance(row["human_approval_required"], bool)
        assert isinstance(row["communication_update_required"], bool)
        assert isinstance(row["rollback_promotion_required"], bool)
        assert "wait_minutes" in row["wait_recheck_window"]
        assert "recheck_by_minute" in row["wait_recheck_window"]
        assert row["guardrails"]["local_mock_only"] is True
        assert row["audit_metadata"]["local_mock_only"] is True
        assert row["zero_side_effect_counters"]["action_execution_count"] == 0
        assert row["zero_side_effect_counters"]["live_api_call_count"] == 0
        assert row["zero_side_effect_counters"]["credential_read_count"] == 0
        assert row["zero_side_effect_counters"]["network_call_count"] == 0
        assert row["zero_side_effect_counters"]["production_mutation_count"] == 0
        assert row["zero_side_effect_counters"]["shell_execution_count"] == 0
        assert row["zero_side_effect_counters"]["rollback_execution_count"] == 0
        assert row["zero_side_effect_counters"]["message_send_count"] == 0
        assert row["zero_side_effect_counters"]["ticket_creation_count"] == 0


def test_outcome_driven_next_action_planner_routes_resolved_and_improving_cases() -> None:
    payload = evaluate_outcome_driven_next_action_fixture(FIXTURE).to_dict()
    plans = {row["scenario_id"]: row for row in payload["next_action_plans"]}

    resolved = plans["resolved-final-report-ready"]
    improving = plans["improving-worker-recheck"]

    assert resolved["selected_next_action"] == NextActionDecision.STOP_RESOLVED.value
    assert resolved["communication_update_required"] is True
    assert resolved["human_approval_required"] is False
    assert resolved["rollback_promotion_required"] is False
    assert resolved["wait_recheck_window"]["wait_minutes"] == 0
    assert "final report" in resolved["rationale"]

    assert improving["selected_next_action"] == NextActionDecision.KEEP_WATCHING.value
    assert improving["communication_update_required"] is False
    assert improving["human_approval_required"] is False
    assert improving["rollback_promotion_required"] is False
    assert improving["wait_recheck_window"]["wait_minutes"] > 0
    assert "recheck" in improving["rationale"]


def test_outcome_driven_next_action_planner_routes_unchanged_worsened_noisy_and_blocked_cases() -> None:
    payload = evaluate_outcome_driven_next_action_fixture(FIXTURE).to_dict()
    plans = {row["scenario_id"]: row for row in payload["next_action_plans"]}

    unchanged = plans["unchanged-db-saturation-window-exceeded"]
    worsened = plans["worsened-after-mitigation"]
    noisy = plans["inconclusive-noisy-no-execution"]
    blocked = plans["blocked-unsafe-action-human-escalation"]

    assert unchanged["selected_next_action"] == NextActionDecision.GATHER_MORE_EVIDENCE.value
    assert unchanged["human_approval_required"] is True
    assert "db owner confirmation" in unchanged["required_evidence"]
    assert "window exceeded" in unchanged["rationale"]

    assert worsened["selected_next_action"] == NextActionDecision.PREPARE_ROLLBACK_REVIEW.value
    assert worsened["rollback_promotion_required"] is True
    assert worsened["communication_update_required"] is True
    assert worsened["human_approval_required"] is True
    assert "rollback draft" in worsened["rationale"]

    assert noisy["selected_next_action"] == NextActionDecision.GATHER_MORE_EVIDENCE.value
    assert noisy["human_approval_required"] is False
    assert noisy["communication_update_required"] is False
    assert noisy["rollback_promotion_required"] is False
    assert noisy["zero_side_effect_counters"]["action_execution_count"] == 0
    assert "no action execution" in noisy["rationale"]

    assert blocked["selected_next_action"] == NextActionDecision.BLOCK_UNSAFE_PATH.value
    assert blocked["human_approval_required"] is True
    assert blocked["communication_update_required"] is True
    assert blocked["rollback_promotion_required"] is False
    assert "unsafe boundary" in blocked["rationale"]


def test_outcome_driven_next_action_planner_summary_preserves_zero_side_effects() -> None:
    payload = evaluate_outcome_driven_next_action_fixture(FIXTURE).to_dict()
    summary = payload["summary"]

    assert summary["scenario_count"] == 6
    assert summary["stop_resolved_count"] == 1
    assert summary["keep_watching_count"] == 1
    assert summary["gather_more_evidence_count"] == 2
    assert summary["escalate_to_human_count"] == 0
    assert summary["prepare_rollback_review_count"] == 1
    assert summary["update_comms_draft_count"] == 0
    assert summary["block_unsafe_path_count"] == 1
    assert summary["human_approval_required_count"] == 3
    assert summary["communication_update_required_count"] == 3
    assert summary["rollback_promotion_required_count"] == 1
    assert summary["action_execution_count"] == 0
    assert summary["live_api_call_count"] == 0
    assert summary["credential_read_count"] == 0
    assert summary["network_call_count"] == 0
    assert summary["production_mutation_count"] == 0
    assert summary["shell_execution_count"] == 0
    assert summary["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["action_execution_enabled"] is False


def test_outcome_driven_next_action_planner_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p84.json"
    output_md = tmp_path / "p84.md"

    subprocess.run(
        [
            "python",
            "scripts/run_outcome_driven_next_action_planner.py",
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

    assert payload["summary"]["passed"] is True
    assert "# OpsCat Outcome-Driven Next Action Planner" in markdown
    assert "Zero-side-effect boundary" in markdown
    assert "blocked-unsafe-action-human-escalation" in markdown
    assert render_outcome_driven_next_action_markdown(payload).startswith("# OpsCat Outcome-Driven Next Action Planner")
