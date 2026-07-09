from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.safe_local_auto_run_entrypoint import (
    SafeLocalAutoRunEntrypointReport,
    SafeLocalStopReason,
    evaluate_safe_local_auto_run_entrypoint_fixture,
    render_safe_local_auto_run_entrypoint_markdown,
)

FIXTURE = Path("evals/actions/p89_safe_local_auto_run_entrypoint.json")


def test_entrypoint_evaluates_required_scenarios() -> None:
    report = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE)
    payload = report.to_dict()
    runs = {row["scenario_id"]: row for row in payload["entrypoint_runs"]}

    assert isinstance(report, SafeLocalAutoRunEntrypointReport)
    assert set(runs) == {
        "dry-run-completes-safe-local-batch",
        "resume-continues-from-checkpoint",
        "needs-human-stops-with-handoff",
        "failed-guardrail-stops-with-failure-report",
        "max-cycles-stops-with-next-command",
        "no-safe-work-schedules-later-recheck",
    }

    for run in runs.values():
        assert run["entrypoint_id"].startswith("p89-")
        assert run["config_summary"]["max_cycles"] >= 1
        assert run["config_summary"]["max_iterations"] >= 1
        assert "budgets" in run["config_summary"]
        assert "wakeup_policy" in run["config_summary"]
        assert "backoff_policy" in run["config_summary"]
        assert run["terminal_status"] in {"completed", "resumable", "needs_human", "failed_guardrail", "scheduled_recheck"}
        assert run["stop_reason"] in {item.value for item in SafeLocalStopReason}
        assert run["resume_state_write_plan"]["atomic_write_plan"]["temp_path"].endswith(".tmp")
        assert run["resume_state_write_plan"]["atomic_write_plan"]["final_path"].endswith(".json")
        assert run["resume_state_write_plan"]["atomic_write_plan"]["executed"] is False
        assert run["report_write_plan"]["atomic_write_plan"]["temp_path"].endswith(".tmp")
        assert run["report_write_plan"]["atomic_write_plan"]["final_path"].endswith(".md")
        assert run["report_write_plan"]["atomic_write_plan"]["executed"] is False
        assert run["audit_metadata"]["local_mock_only"] is True
        assert run["audit_metadata"]["p89_safe_local_auto_run_entrypoint"] is True
        assert run["audit_metadata"]["side_effect_free"] is True
        assert run["zero_side_effect_counters"] == {
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


def test_dry_run_completes_safe_local_batch_and_emits_write_plans() -> None:
    payload = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["entrypoint_runs"]}["dry-run-completes-safe-local-batch"]

    assert run["dry_run"] is True
    assert run["resumed"] is False
    assert run["terminal_status"] == "completed"
    assert run["stop_reason"] == SafeLocalStopReason.COMPLETED.value
    assert [cycle["cycle_id"] for cycle in run["scheduled_cycles"]] == ["p89-dry-cycle-1", "p89-dry-cycle-2"]
    assert run["resume_state_metadata"]["path"] == "/tmp/opscat-p89-dry-run-state.json"
    assert run["generated_report_metadata"]["path"] == "/tmp/opscat-p89-dry-run-report.md"
    assert run["next_recommended_command"] == "Review /tmp/opscat-p89-dry-run-report.md"
    assert run["human_handoff_summary"]["required"] is False


def test_resume_continues_from_checkpoint_without_duplicate_cycle_ids() -> None:
    payload = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["entrypoint_runs"]}["resume-continues-from-checkpoint"]

    assert run["dry_run"] is False
    assert run["resumed"] is True
    assert run["resume_state_metadata"]["resumed_from_checkpoint"] is True
    assert run["resume_state_metadata"]["initial_completed_cycle_ids"] == ["p89-resume-cycle-1"]
    assert run["scheduled_cycle_ids"] == ["p89-resume-cycle-1", "p89-resume-cycle-2"]
    assert run["scheduled_cycle_ids"] == list(dict.fromkeys(run["scheduled_cycle_ids"]))
    assert run["scheduled_cycles"][0]["event"] == "resume_skip_completed_cycle"
    assert run["scheduled_cycles"][-1]["event"] == "modeled_cycle"
    assert run["stop_reason"] == SafeLocalStopReason.COMPLETED.value


def test_needs_human_stops_with_handoff_summary() -> None:
    payload = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["entrypoint_runs"]}["needs-human-stops-with-handoff"]

    assert run["terminal_status"] == "needs_human"
    assert run["stop_reason"] == SafeLocalStopReason.NEEDS_HUMAN.value
    assert run["human_handoff_summary"] == {
        "required": True,
        "reason": "approval_required",
        "summary": "Human approval required before continuing modeled local work.",
        "blocking_cycle_id": "p89-human-cycle-1",
    }
    assert run["next_recommended_command"] == "Open the generated report and resolve the human approval gate."


def test_failed_guardrail_stops_with_failure_report() -> None:
    payload = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["entrypoint_runs"]}["failed-guardrail-stops-with-failure-report"]

    assert run["terminal_status"] == "failed_guardrail"
    assert run["stop_reason"] == SafeLocalStopReason.FAILED_GUARDRAIL.value
    assert run["failure_report"] == {
        "required": True,
        "reason": "guardrail_failed",
        "summary": "Guardrail failure stopped the safe local auto-run entrypoint.",
        "failing_cycle_id": "p89-guardrail-cycle-1",
    }
    assert run["next_recommended_command"] == "Review guardrail failure report before any resume attempt."


def test_max_cycles_stops_with_next_command_suggestion() -> None:
    payload = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["entrypoint_runs"]}["max-cycles-stops-with-next-command"]

    assert run["terminal_status"] == "resumable"
    assert run["stop_reason"] == SafeLocalStopReason.MAX_CYCLES.value
    assert run["config_summary"]["max_cycles"] == 1
    assert run["next_recommended_command"] == (
        "python scripts/run_safe_local_auto_run_entrypoint.py --cases "
        "evals/actions/p89_safe_local_auto_run_entrypoint.json --resume"
    )


def test_no_safe_work_schedules_later_recheck_without_execution() -> None:
    payload = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE).to_dict()
    run = {row["scenario_id"]: row for row in payload["entrypoint_runs"]}["no-safe-work-schedules-later-recheck"]

    assert run["terminal_status"] == "scheduled_recheck"
    assert run["stop_reason"] == SafeLocalStopReason.NO_SAFE_WORK.value
    assert run["scheduled_cycles"] == []
    assert run["next_scheduled_wakeup"] == {"reason": "no_safe_work_recheck", "after_minutes": 45, "modeled_only": True}
    assert run["next_recommended_command"] == "Re-run the safe local auto-run entrypoint after the modeled recheck window."


def test_entrypoint_summary_counts_and_zero_side_effects() -> None:
    payload = evaluate_safe_local_auto_run_entrypoint_fixture(FIXTURE).to_dict()
    summary = payload["summary"]

    assert summary["scenario_count"] == 6
    assert summary["dry_run_count"] == 5
    assert summary["resumed_count"] == 1
    assert summary["completed_count"] == 2
    assert summary["needs_human_count"] == 1
    assert summary["failed_guardrail_count"] == 1
    assert summary["max_cycles_count"] == 1
    assert summary["no_safe_work_count"] == 1
    assert summary["executions"] == 0
    assert summary["sleep_call_count"] == 0
    assert summary["passed"] is True


def test_safe_local_auto_run_entrypoint_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p89.json"
    output_md = tmp_path / "p89.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_safe_local_auto_run_entrypoint.py",
            "--cases",
            str(FIXTURE),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--dry-run",
            "--resume",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")

    assert "scenarios=6" in result.stdout
    assert "dry_run=5" in result.stdout
    assert "resumed=1" in result.stdout
    assert "completed=2" in result.stdout
    assert "needs_human=1" in result.stdout
    assert "failed_guardrail=1" in result.stdout
    assert "max_cycles=1" in result.stdout
    assert "executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Safe Local Auto-Run Entrypoint" in markdown
    assert "not a real daemon" in markdown
    assert render_safe_local_auto_run_entrypoint_markdown(payload).startswith(
        "# OpsCat Safe Local Auto-Run Entrypoint"
    )
