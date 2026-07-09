from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.post_action_outcome_monitor import (
    OutcomeDecision,
    PostActionOutcomeReport,
    evaluate_post_action_outcome_fixture,
    render_post_action_outcome_markdown,
)

FIXTURE = Path("evals/actions/p83_post_action_outcome_monitor.json")


def test_post_action_outcome_monitor_evaluates_required_scenarios() -> None:
    report = evaluate_post_action_outcome_fixture(FIXTURE)
    payload = report.to_dict()
    outcomes = {row["scenario_id"]: row for row in payload["outcomes"]}

    assert isinstance(report, PostActionOutcomeReport)
    assert set(outcomes) == {
        "restart-worker-improves-error-rate-and-queue-lag",
        "rollback-draft-applied-in-mock-evidence",
        "db-saturation-unchanged",
        "mitigation-worsens-latency-and-error-rate",
        "noisy-incomplete-telemetry",
        "blocked-unsafe-action",
    }

    for row in outcomes.values():
        assert row["decision"] in {item.value for item in OutcomeDecision}
        assert 0.0 <= row["confidence"] <= 1.0
        assert row["evidence_references"]
        assert isinstance(row["metric_deltas"], dict)
        assert isinstance(row["log_deltas"], dict)
        assert "next_recommended_step" in row
        assert "communication_draft_should_be_updated" in row
        assert "rollback_draft_should_be_promoted_for_human_review" in row
        assert row["audit_metadata"]["local_mock_only"] is True
        assert row["execution_plan"]["action_execution_count"] == 0
        assert row["execution_plan"]["live_api_call_count"] == 0
        assert row["execution_plan"]["credential_read_count"] == 0
        assert row["execution_plan"]["network_call_count"] == 0
        assert row["execution_plan"]["production_mutation_count"] == 0
        assert row["execution_plan"]["shell_execution_count"] == 0


def test_post_action_outcome_monitor_classifies_improvement_and_mock_rollback_resolution() -> None:
    payload = evaluate_post_action_outcome_fixture(FIXTURE).to_dict()
    outcomes = {row["scenario_id"]: row for row in payload["outcomes"]}

    restart = outcomes["restart-worker-improves-error-rate-and-queue-lag"]
    rollback = outcomes["rollback-draft-applied-in-mock-evidence"]

    assert restart["decision"] in {
        OutcomeDecision.IMPROVING_KEEP_WATCHING.value,
        OutcomeDecision.RESOLVED.value,
    }
    assert restart["metric_deltas"]["error_rate"]["direction"] == "improved"
    assert restart["metric_deltas"]["queue_lag"]["direction"] == "improved"
    assert restart["communication_draft_should_be_updated"] is True
    assert restart["rollback_draft_should_be_promoted_for_human_review"] is False
    assert "continue monitoring" in restart["next_recommended_step"]

    assert rollback["decision"] == OutcomeDecision.RESOLVED.value
    assert rollback["verification_checklist"]
    assert rollback["rollback_pr_draft_status"] == "mock_applied"
    assert "verification checklist satisfied" in rollback["next_recommended_step"]
    assert rollback["rollback_draft_should_be_promoted_for_human_review"] is False


def test_post_action_outcome_monitor_routes_unchanged_worsened_noisy_and_blocked_cases() -> None:
    payload = evaluate_post_action_outcome_fixture(FIXTURE).to_dict()
    outcomes = {row["scenario_id"]: row for row in payload["outcomes"]}

    unchanged = outcomes["db-saturation-unchanged"]
    worsened = outcomes["mitigation-worsens-latency-and-error-rate"]
    noisy = outcomes["noisy-incomplete-telemetry"]
    blocked = outcomes["blocked-unsafe-action"]

    assert unchanged["decision"] == OutcomeDecision.UNCHANGED_INVESTIGATE.value
    assert unchanged["communication_draft_should_be_updated"] is True
    assert unchanged["rollback_draft_should_be_promoted_for_human_review"] is False
    assert "investigate alternate causes" in unchanged["next_recommended_step"]

    assert worsened["decision"] == OutcomeDecision.WORSENED_ROLLBACK_OR_ESCALATE.value
    assert worsened["metric_deltas"]["latency_p95_ms"]["direction"] == "worsened"
    assert worsened["metric_deltas"]["error_rate"]["direction"] == "worsened"
    assert worsened["rollback_draft_should_be_promoted_for_human_review"] is True
    assert "promote rollback draft for human review" in worsened["next_recommended_step"]

    assert noisy["decision"] == OutcomeDecision.INCONCLUSIVE_NEED_MORE_EVIDENCE.value
    assert noisy["missing_evidence"]
    assert noisy["confidence"] <= 0.55
    assert "collect more evidence" in noisy["next_recommended_step"]

    assert blocked["decision"] == OutcomeDecision.BLOCKED_UNSAFE_TO_CONTINUE.value
    assert blocked["guardrails"]["unsafe_to_continue"] is True
    assert blocked["rollback_draft_should_be_promoted_for_human_review"] is True
    assert "stop automated follow-up" in blocked["next_recommended_step"]


def test_post_action_outcome_monitor_summary_preserves_zero_side_effects() -> None:
    payload = evaluate_post_action_outcome_fixture(FIXTURE).to_dict()

    assert payload["summary"]["scenario_count"] == 6
    assert payload["summary"]["resolved_count"] == 1
    assert payload["summary"]["improving_keep_watching_count"] >= 1
    assert payload["summary"]["unchanged_investigate_count"] == 1
    assert payload["summary"]["worsened_rollback_or_escalate_count"] == 1
    assert payload["summary"]["inconclusive_need_more_evidence_count"] == 1
    assert payload["summary"]["blocked_unsafe_to_continue_count"] == 1
    assert payload["summary"]["communication_update_count"] >= 4
    assert payload["summary"]["rollback_human_review_promotion_count"] == 2
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["live_api_call_count"] == 0
    assert payload["summary"]["credential_read_count"] == 0
    assert payload["summary"]["network_call_count"] == 0
    assert payload["summary"]["production_mutation_count"] == 0
    assert payload["summary"]["shell_execution_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["action_execution_enabled"] is False


def test_post_action_outcome_monitor_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p83.json"
    output_md = tmp_path / "p83.md"

    subprocess.run(
        [
            "python",
            "scripts/run_post_action_outcome_monitor.py",
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
    assert "# OpsCat Post-Action Outcome Monitor" in markdown
    assert "Zero-side-effect boundary" in markdown
    assert "restart-worker-improves-error-rate-and-queue-lag" in markdown
    assert render_post_action_outcome_markdown(payload).startswith("# OpsCat Post-Action Outcome Monitor")
