from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.bounded_local_supervisor_scheduler import (
    BoundedLocalSupervisorSchedulerReport,
    SchedulerStopReason,
    evaluate_bounded_local_supervisor_scheduler_fixture,
    render_bounded_local_supervisor_scheduler_markdown,
)

FIXTURE = Path("evals/actions/p88_bounded_local_supervisor_scheduler.json")


def test_scheduler_evaluates_required_scenarios() -> None:
    report = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE)
    payload = report.to_dict()
    plans = {row["scenario_id"]: row for row in payload["scheduler_plans"]}

    assert isinstance(report, BoundedLocalSupervisorSchedulerReport)
    assert set(plans) == {
        "completes-all-before-max-cycles",
        "resumable-until-max-cycles",
        "needs-human-stops-immediately",
        "failure-streak-backoff-then-guardrail",
        "no-safe-work-recheck-then-budget-stop",
        "resumed-scheduler-continues-without-duplicates",
    }

    for plan in plans.values():
        assert plan["scheduler_id"].startswith("p88-")
        assert plan["current_cycle_index"] >= 0
        assert plan["max_cycles"] >= 1
        assert plan["modeled_wall_clock_budget_minutes"] >= 1
        assert plan["selected_run_state_ids"] == list(dict.fromkeys(plan["selected_run_state_ids"]))
        assert plan["terminal_classification"] in {"terminal", "resumable"}
        assert plan["stop_reason"] in {item.value for item in SchedulerStopReason}
        assert plan["checkpoint_write_plan"]["atomic_write_plan"]["temp_path"].endswith(".tmp")
        assert plan["checkpoint_write_plan"]["atomic_write_plan"]["final_path"].endswith(".json")
        assert plan["audit_metadata"]["local_mock_only"] is True
        assert plan["audit_metadata"]["p88_bounded_scheduler_contract"] is True
        assert plan["audit_metadata"]["consumes_p86_runner_state"] is True
        assert plan["audit_metadata"]["consumes_p87_report_status"] is True
        assert plan["zero_side_effect_counters"] == {
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


def test_scheduler_completes_all_work_before_max_cycles() -> None:
    payload = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE).to_dict()
    plan = {row["scenario_id"]: row for row in payload["scheduler_plans"]}["completes-all-before-max-cycles"]

    assert plan["stop_reason"] == SchedulerStopReason.COMPLETED_ALL.value
    assert plan["terminal_classification"] == "terminal"
    assert plan["current_cycle_index"] == 2
    assert plan["selected_run_state_ids"] == ["p88-complete-cycle-1", "p88-complete-cycle-2"]
    assert plan["next_scheduled_wakeup"] is None
    assert [cycle["p87_report_status"] for cycle in plan["cycles"]] == ["max_iterations", "completed_all"]


def test_scheduler_repeats_resumable_work_until_max_cycles_stop() -> None:
    payload = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE).to_dict()
    plan = {row["scenario_id"]: row for row in payload["scheduler_plans"]}["resumable-until-max-cycles"]

    assert plan["stop_reason"] == SchedulerStopReason.MAX_CYCLES.value
    assert plan["terminal_classification"] == "resumable"
    assert plan["current_cycle_index"] == 2
    assert plan["selected_run_state_ids"] == ["p88-max-cycle-1", "p88-max-cycle-2"]
    assert plan["next_scheduled_wakeup"]["reason"] == "resume_after_max_cycles"
    assert plan["cycles"][-1]["terminal_classification"] == "resumable"


def test_scheduler_needs_human_stops_immediately_with_handoff() -> None:
    payload = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE).to_dict()
    plan = {row["scenario_id"]: row for row in payload["scheduler_plans"]}["needs-human-stops-immediately"]

    assert plan["stop_reason"] == SchedulerStopReason.NEEDS_HUMAN.value
    assert plan["terminal_classification"] == "terminal"
    assert plan["current_cycle_index"] == 1
    assert plan["selected_run_state_ids"] == ["p88-human-cycle-1"]
    assert plan["human_handoff"] == {
        "required": True,
        "reason": "approval_required",
        "run_state_id": "p88-human-cycle-1",
    }
    assert plan["next_scheduled_wakeup"]["reason"] == "human_review_required"


def test_scheduler_failure_streak_backs_off_then_failed_guardrail() -> None:
    payload = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE).to_dict()
    plan = {row["scenario_id"]: row for row in payload["scheduler_plans"]}["failure-streak-backoff-then-guardrail"]

    assert plan["stop_reason"] == SchedulerStopReason.FAILED_GUARDRAIL.value
    assert plan["terminal_classification"] == "terminal"
    assert [cycle["backoff"]["delay_minutes"] for cycle in plan["cycles"]] == [10, 20]
    assert plan["backoff_policy"]["failure_streak"] == 2
    assert plan["next_scheduled_wakeup"]["reason"] == "guardrail_review_required"


def test_scheduler_no_safe_work_rechecks_then_stops_by_budget() -> None:
    payload = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE).to_dict()
    plan = {row["scenario_id"]: row for row in payload["scheduler_plans"]}["no-safe-work-recheck-then-budget-stop"]

    assert plan["stop_reason"] == SchedulerStopReason.BUDGET_EXHAUSTED.value
    assert plan["terminal_classification"] == "resumable"
    assert [cycle["backoff"]["delay_minutes"] for cycle in plan["cycles"]] == [30, 60]
    assert plan["next_scheduled_wakeup"]["reason"] == "budget_exhausted"
    assert plan["modeled_elapsed_minutes"] == 90


def test_resumed_scheduler_continues_without_duplicate_run_state_ids() -> None:
    payload = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE).to_dict()
    plan = {row["scenario_id"]: row for row in payload["scheduler_plans"]}[
        "resumed-scheduler-continues-without-duplicates"
    ]

    assert plan["resume_metadata"]["resumed_from_state"] is True
    assert plan["resume_metadata"]["initial_cycle_index"] == 1
    assert plan["resume_metadata"]["initial_selected_run_state_ids"] == ["p88-resume-cycle-1"]
    assert plan["selected_run_state_ids"] == ["p88-resume-cycle-1", "p88-resume-cycle-2"]
    assert plan["cycles"][0]["event"] == "resume_skip_selected"
    assert plan["cycles"][-1]["run_state_id"] == "p88-resume-cycle-2"
    assert plan["stop_reason"] == SchedulerStopReason.COMPLETED_ALL.value


def test_scheduler_summary_counts_and_zero_side_effects() -> None:
    payload = evaluate_bounded_local_supervisor_scheduler_fixture(FIXTURE).to_dict()
    summary = payload["summary"]

    assert summary["scenario_count"] == 6
    assert summary["completed_all_count"] == 2
    assert summary["max_cycles_count"] == 1
    assert summary["needs_human_count"] == 1
    assert summary["failed_guardrail_count"] == 1
    assert summary["budget_exhausted_count"] == 1
    assert summary["executions"] == 0
    assert summary["action_execution_count"] == 0
    assert summary["sleep_call_count"] == 0
    assert summary["process_spawn_count"] == 0
    assert summary["passed"] is True


def test_bounded_scheduler_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p88.json"
    output_md = tmp_path / "p88.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_bounded_local_supervisor_scheduler.py",
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
    assert "completed_all=2" in result.stdout
    assert "max_cycles=1" in result.stdout
    assert "needs_human=1" in result.stdout
    assert "failed_guardrail=1" in result.stdout
    assert "budget_exhausted=1" in result.stdout
    assert "executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Bounded Local Supervisor Scheduler Contract" in markdown
    assert "not a daemon" in markdown
    assert render_bounded_local_supervisor_scheduler_markdown(payload).startswith(
        "# OpsCat Bounded Local Supervisor Scheduler Contract"
    )
