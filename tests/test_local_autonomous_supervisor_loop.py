from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.local_autonomous_supervisor_loop import (
    LocalAutonomousSupervisorReport,
    SupervisorStopReason,
    evaluate_local_autonomous_supervisor_fixture,
    render_local_autonomous_supervisor_markdown,
)

FIXTURE = Path("evals/actions/p85_local_autonomous_supervisor_loop.json")


def test_local_autonomous_supervisor_loop_evaluates_required_scenarios() -> None:
    report = evaluate_local_autonomous_supervisor_fixture(FIXTURE)
    payload = report.to_dict()
    runs = {row["scenario_id"]: row for row in payload["runs"]}

    assert isinstance(report, LocalAutonomousSupervisorReport)
    assert set(runs) == {
        "safe-batch-two-local-items",
        "approval-blocked-no-safe-work",
        "failure-streak-exceeded",
        "budget-exhausted-mid-queue",
        "outcome-worsened-queues-review",
        "resume-from-checkpoint",
    }

    for row in runs.values():
        assert row["run_id"].startswith("p85-")
        assert row["stop_reason"] in {item.value for item in SupervisorStopReason}
        assert isinstance(row["selected_item_ids"], list)
        assert isinstance(row["skipped_item_ids"], list)
        assert isinstance(row["skipped_items"], list)
        assert isinstance(row["completed_mock_steps"], list)
        assert "next_wakeup_recommendation" in row
        assert row["checkpoint_records"]
        assert row["audit_metadata"]["local_mock_only"] is True
        assert row["audit_metadata"]["supervisor_only"] is True
        assert row["zero_side_effect_counters"]["action_execution_count"] == 0
        assert row["zero_side_effect_counters"]["live_api_call_count"] == 0
        assert row["zero_side_effect_counters"]["credential_read_count"] == 0
        assert row["zero_side_effect_counters"]["network_call_count"] == 0
        assert row["zero_side_effect_counters"]["production_mutation_count"] == 0
        assert row["zero_side_effect_counters"]["shell_execution_count"] == 0
        assert row["zero_side_effect_counters"]["process_spawn_count"] == 0
        assert row["zero_side_effect_counters"]["agent_spawn_count"] == 0


def test_supervisor_completes_safe_batch_and_persists_checkpoint() -> None:
    payload = evaluate_local_autonomous_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["safe-batch-two-local-items"]

    assert run["stop_reason"] == SupervisorStopReason.COMPLETED_BATCH.value
    assert run["selected_item_ids"] == ["p85-local-evidence-refresh", "p85-local-docs-smoke"]
    assert run["skipped_item_ids"] == []
    assert [step["item_id"] for step in run["completed_mock_steps"]] == [
        "p85-local-evidence-refresh",
        "p85-local-docs-smoke",
    ]
    assert run["completed_mock_steps"][0]["dry_run_command_name"] == "pytest-p85-local-evidence"
    assert run["next_wakeup_recommendation"]["reason"] == "batch_complete"
    assert run["checkpoint_records"][-1]["cursor"] == 2
    assert run["checkpoint_records"][-1]["completed_item_ids"] == [
        "p85-local-evidence-refresh",
        "p85-local-docs-smoke",
    ]


def test_supervisor_routes_approval_blocked_work_to_human_without_execution() -> None:
    payload = evaluate_local_autonomous_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["approval-blocked-no-safe-work"]

    assert run["stop_reason"] == SupervisorStopReason.NEEDS_HUMAN.value
    assert run["selected_item_ids"] == []
    assert run["completed_mock_steps"] == []
    assert run["skipped_item_ids"] == ["p85-restart-worker-approval"]
    assert run["skipped_items"][0]["reason"] == "approval_required"
    assert run["next_wakeup_recommendation"]["reason"] == "human_review_required"


def test_supervisor_stops_on_failure_streak_guardrail() -> None:
    payload = evaluate_local_autonomous_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["failure-streak-exceeded"]

    assert run["stop_reason"] == SupervisorStopReason.FAILED_GUARDRAIL.value
    assert run["failure_streak"] == 2
    assert run["selected_item_ids"] == ["p85-flaky-local-check-one", "p85-flaky-local-check-two"]
    assert run["completed_mock_steps"] == []
    assert run["next_wakeup_recommendation"]["reason"] == "guardrail_review_required"
    assert run["checkpoint_records"][-1]["failure_streak"] == 2


def test_supervisor_stops_on_budget_exhaustion_with_resumable_cursor() -> None:
    payload = evaluate_local_autonomous_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["budget-exhausted-mid-queue"]

    assert run["stop_reason"] == SupervisorStopReason.BUDGET_EXHAUSTED.value
    assert run["selected_item_ids"] == ["p85-budget-first"]
    assert run["completed_mock_steps"][0]["item_id"] == "p85-budget-first"
    assert run["checkpoint_records"][-1]["cursor"] == 1
    assert run["resumable_cursor"] == 1
    assert run["next_wakeup_recommendation"]["reason"] == "resume_after_budget"


def test_supervisor_queues_rollback_review_when_outcome_worsened() -> None:
    payload = evaluate_local_autonomous_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["outcome-worsened-queues-review"]

    assert run["stop_reason"] == SupervisorStopReason.NEEDS_HUMAN.value
    assert run["selected_item_ids"] == []
    assert run["completed_mock_steps"] == []
    assert run["queued_review_items"] == [
        {
            "item_id": "p85-worsened-after-mock-action",
            "review_type": "rollback_or_escalation",
            "reason": "outcome_worsened",
        }
    ]
    assert run["skipped_items"][0]["reason"] == "outcome_worsened"


def test_supervisor_resume_checkpoint_does_not_duplicate_completed_items() -> None:
    payload = evaluate_local_autonomous_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["resume-from-checkpoint"]

    assert run["resume_metadata"]["resumed_from_checkpoint"] is True
    assert run["resume_metadata"]["initial_completed_item_ids"] == ["p85-resume-already-done"]
    assert run["selected_item_ids"] == ["p85-resume-next-safe"]
    assert [step["item_id"] for step in run["completed_mock_steps"]] == ["p85-resume-next-safe"]
    assert "p85-resume-already-done" not in [step["item_id"] for step in run["completed_mock_steps"]]
    assert run["stop_reason"] == SupervisorStopReason.COMPLETED_BATCH.value


def test_local_autonomous_supervisor_summary_preserves_zero_side_effects() -> None:
    payload = evaluate_local_autonomous_supervisor_fixture(FIXTURE).to_dict()
    summary = payload["summary"]

    assert summary["scenario_count"] == 6
    assert summary["completed_batch_count"] == 2
    assert summary["needs_human_count"] == 2
    assert summary["failed_guardrail_count"] == 1
    assert summary["budget_exhausted_count"] == 1
    assert summary["no_safe_work_count"] == 0
    assert summary["selected_item_count"] == 6
    assert summary["completed_mock_step_count"] == 4
    assert summary["action_execution_count"] == 0
    assert summary["live_api_call_count"] == 0
    assert summary["credential_read_count"] == 0
    assert summary["network_call_count"] == 0
    assert summary["production_mutation_count"] == 0
    assert summary["shell_execution_count"] == 0
    assert summary["process_spawn_count"] == 0
    assert summary["agent_spawn_count"] == 0
    assert summary["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["action_execution_enabled"] is False


def test_local_autonomous_supervisor_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p85.json"
    output_md = tmp_path / "p85.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_local_autonomous_supervisor_loop.py",
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
    assert "completed_batches=2" in result.stdout
    assert "needs_human=2" in result.stdout
    assert "failed_guardrail=1" in result.stdout
    assert "budget_exhausted=1" in result.stdout
    assert "executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Local Autonomous Supervisor Loop" in markdown
    assert "Zero-side-effect boundary" in markdown
    assert "safe-batch-two-local-items" in markdown
    assert render_local_autonomous_supervisor_markdown(payload).startswith("# OpsCat Local Autonomous Supervisor Loop")
