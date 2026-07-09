from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.resumable_local_supervisor_runner import (
    ResumableLocalSupervisorReport,
    ResumableSupervisorStopReason,
    evaluate_resumable_local_supervisor_fixture,
    render_resumable_local_supervisor_markdown,
)

FIXTURE = Path("evals/actions/p86_resumable_local_supervisor_runner.json")


def test_resumable_runner_evaluates_required_scenarios() -> None:
    report = evaluate_resumable_local_supervisor_fixture(FIXTURE)
    payload = report.to_dict()
    runs = {row["scenario_id"]: row for row in payload["runs"]}

    assert isinstance(report, ResumableLocalSupervisorReport)
    assert set(runs) == {
        "fresh-run-completes-two-safe-items",
        "interrupted-run-resumes-without-duplicates",
        "max-iteration-limit-keeps-resumable-cursor",
        "needs-human-records-blocked-work",
        "guardrail-failure-stops-after-failure-streak",
        "completed-all-terminal",
    }

    for row in runs.values():
        assert row["run_id"].startswith("p86-")
        assert row["stop_reason"] in {item.value for item in ResumableSupervisorStopReason}
        assert isinstance(row["cursor"], int)
        assert isinstance(row["completed_item_ids"], list)
        assert isinstance(row["skipped_item_ids"], list)
        assert isinstance(row["iteration_count"], int)
        assert isinstance(row["failure_streak"], int)
        assert row["checkpoints"]
        assert row["checkpoints"][-1]["atomic_write_plan"]["temp_path"].endswith(".tmp")
        assert row["checkpoints"][-1]["atomic_write_plan"]["final_path"].endswith(".json")
        assert row["audit_metadata"]["local_mock_only"] is True
        assert row["audit_metadata"]["p86_resumable_runner"] is True
        assert row["zero_side_effect_counters"] == {
            "action_execution_count": 0,
            "live_api_call_count": 0,
            "credential_read_count": 0,
            "network_call_count": 0,
            "production_mutation_count": 0,
            "shell_execution_count": 0,
            "process_spawn_count": 0,
            "agent_spawn_count": 0,
        }


def test_fresh_run_completes_two_safe_items_over_multiple_iterations() -> None:
    payload = evaluate_resumable_local_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["fresh-run-completes-two-safe-items"]

    assert run["stop_reason"] == ResumableSupervisorStopReason.COMPLETED_ALL.value
    assert run["completed_item_ids"] == ["p86-safe-local-evidence", "p86-safe-docs-smoke"]
    assert run["selected_item_ids"] == ["p86-safe-local-evidence", "p86-safe-docs-smoke"]
    assert run["cursor"] == 2
    assert run["iteration_count"] == 2
    assert run["next_recommended_wakeup"] is None
    assert [step["dry_run_command_name"] for step in run["modeled_steps"]] == [
        "pytest-p86-local-evidence",
        "docs-profile-smoke",
    ]


def test_interrupted_run_resumes_from_cursor_and_avoids_duplicate_completion() -> None:
    payload = evaluate_resumable_local_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["interrupted-run-resumes-without-duplicates"]

    assert run["resume_metadata"]["resumed_from_state"] is True
    assert run["resume_metadata"]["initial_cursor"] == 1
    assert run["resume_metadata"]["initial_completed_item_ids"] == ["p86-resume-already-done"]
    assert run["completed_item_ids"] == ["p86-resume-already-done", "p86-resume-next-safe"]
    assert run["selected_item_ids"] == ["p86-resume-next-safe"]
    assert [step["item_id"] for step in run["modeled_steps"]] == ["p86-resume-next-safe"]
    assert run["cursor"] == 2
    assert run["stop_reason"] == ResumableSupervisorStopReason.COMPLETED_ALL.value


def test_max_iteration_limit_stops_with_resumable_cursor() -> None:
    payload = evaluate_resumable_local_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["max-iteration-limit-keeps-resumable-cursor"]

    assert run["stop_reason"] == ResumableSupervisorStopReason.MAX_ITERATIONS.value
    assert run["completed_item_ids"] == ["p86-iteration-first"]
    assert run["cursor"] == 1
    assert run["iteration_count"] == 1
    assert run["next_recommended_wakeup"]["reason"] == "resume_after_iteration_limit"
    assert run["checkpoints"][-1]["cursor"] == 1


def test_needs_human_stops_and_preserves_blocked_reason() -> None:
    payload = evaluate_resumable_local_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["needs-human-records-blocked-work"]

    assert run["stop_reason"] == ResumableSupervisorStopReason.NEEDS_HUMAN.value
    assert run["completed_item_ids"] == []
    assert run["skipped_item_ids"] == ["p86-human-approval-required"]
    assert run["skipped_items"] == [
        {
            "item_id": "p86-human-approval-required",
            "reason": "approval_required",
            "blocked_by": "human_review",
        }
    ]
    assert run["next_recommended_wakeup"]["reason"] == "human_review_required"


def test_guardrail_failure_stops_after_failure_streak() -> None:
    payload = evaluate_resumable_local_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["guardrail-failure-stops-after-failure-streak"]

    assert run["stop_reason"] == ResumableSupervisorStopReason.FAILED_GUARDRAIL.value
    assert run["failure_streak"] == 2
    assert run["selected_item_ids"] == ["p86-failing-local-check-one", "p86-failing-local-check-two"]
    assert run["completed_item_ids"] == []
    assert run["next_recommended_wakeup"]["reason"] == "guardrail_review_required"


def test_completed_all_has_no_next_wakeup_or_terminal_recommendation() -> None:
    payload = evaluate_resumable_local_supervisor_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["runs"]}["completed-all-terminal"]

    assert run["stop_reason"] == ResumableSupervisorStopReason.COMPLETED_ALL.value
    assert run["cursor"] == 1
    assert run["next_recommended_wakeup"] is None
    assert run["terminal_recommendation"] is None


def test_budget_and_no_safe_work_stop_reasons_are_supported(tmp_path: Path) -> None:
    fixture = tmp_path / "p86-budget-no-safe.json"
    fixture.write_text(
        json.dumps(
            {
                "suite": {"id": "p86-budget-no-safe"},
                "scenarios": [
                    {
                        "id": "budget-stop",
                        "run_id": "p86-budget-001",
                        "checkpoint_final_path": "/tmp/opscat-p86-budget-state.json",
                        "limits": {"max_iterations": 2, "max_budget_units": 0, "failure_streak_limit": 2},
                        "backlog": [
                            {
                                "id": "p86-budget-item",
                                "budget_units": 1,
                                "p76_gate": {"decision": "sufficient_read_only"},
                                "p79_sandbox": {"decision": "allow"},
                                "p80_approval": {"decision": "auto_approve"},
                                "p84_next_action": {"human_approval_required": False},
                                "dry_run_command_name": "budget-item",
                                "mock_step_result": "passed",
                            }
                        ],
                    },
                    {
                        "id": "no-safe-stop",
                        "run_id": "p86-no-safe-001",
                        "checkpoint_final_path": "/tmp/opscat-p86-no-safe-state.json",
                        "limits": {"max_iterations": 2, "max_budget_units": 2, "failure_streak_limit": 2},
                        "backlog": [
                            {
                                "id": "p86-insufficient-evidence",
                                "budget_units": 1,
                                "p76_gate": {"decision": "insufficient"},
                                "p79_sandbox": {"decision": "allow"},
                                "p80_approval": {"decision": "auto_approve"},
                                "p84_next_action": {"human_approval_required": False},
                                "dry_run_command_name": "insufficient-evidence",
                                "mock_step_result": "passed",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = evaluate_resumable_local_supervisor_fixture(fixture).to_dict()
    runs = {row["scenario_id"]: row for row in payload["runs"]}

    assert runs["budget-stop"]["stop_reason"] == ResumableSupervisorStopReason.BUDGET_EXHAUSTED.value
    assert runs["budget-stop"]["cursor"] == 0
    assert runs["budget-stop"]["next_recommended_wakeup"]["reason"] == "resume_after_budget"
    assert runs["no-safe-stop"]["stop_reason"] == ResumableSupervisorStopReason.NO_SAFE_WORK.value
    assert runs["no-safe-stop"]["skipped_items"][0]["reason"] == "insufficient_evidence"
    assert runs["no-safe-stop"]["next_recommended_wakeup"]["reason"] == "backlog_recheck"


def test_resumable_runner_summary_counts_and_zero_side_effects() -> None:
    payload = evaluate_resumable_local_supervisor_fixture(FIXTURE).to_dict()
    summary = payload["summary"]

    assert summary["scenario_count"] == 6
    assert summary["resumed_count"] == 1
    assert summary["completed_all_count"] == 3
    assert summary["max_iteration_count"] == 1
    assert summary["needs_human_count"] == 1
    assert summary["failed_guardrail_count"] == 1
    assert summary["budget_exhausted_count"] == 0
    assert summary["no_safe_work_count"] == 0
    assert summary["action_execution_count"] == 0
    assert summary["live_api_call_count"] == 0
    assert summary["credential_read_count"] == 0
    assert summary["network_call_count"] == 0
    assert summary["production_mutation_count"] == 0
    assert summary["shell_execution_count"] == 0
    assert summary["process_spawn_count"] == 0
    assert summary["agent_spawn_count"] == 0
    assert summary["passed"] is True


def test_resumable_runner_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p86.json"
    output_md = tmp_path / "p86.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_resumable_local_supervisor_runner.py",
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
    assert "resumed=1" in result.stdout
    assert "completed_all=3" in result.stdout
    assert "max_iteration=1" in result.stdout
    assert "needs_human=1" in result.stdout
    assert "failed_guardrail=1" in result.stdout
    assert "executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Resumable Local Supervisor Runner" in markdown
    assert "Atomic checkpoint write plan" in markdown
    assert render_resumable_local_supervisor_markdown(payload).startswith(
        "# OpsCat Resumable Local Supervisor Runner"
    )
