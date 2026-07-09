from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.supervisor_run_report_artifact import (
    SupervisorRunReportArtifact,
    evaluate_supervisor_run_report_artifact_fixture,
    render_supervisor_run_report_markdown,
)

FIXTURE = Path("evals/actions/p87_supervisor_run_report_artifact.json")


def test_report_artifact_evaluates_required_scenarios() -> None:
    report = evaluate_supervisor_run_report_artifact_fixture(FIXTURE)
    payload = report.to_dict()
    scenarios = {row["scenario_id"]: row for row in payload["reports"]}

    assert isinstance(report, SupervisorRunReportArtifact)
    assert set(scenarios) == {
        "completed-all-report",
        "max-iteration-report",
        "needs-human-report",
        "failed-guardrail-report",
        "no-safe-work-report",
        "resumed-run-report",
    }
    assert payload["summary"]["scenario_count"] == 6
    assert payload["summary"]["terminal_count"] == 5
    assert payload["summary"]["resumable_count"] == 1
    assert payload["summary"]["needs_human_count"] == 1
    assert payload["summary"]["failed_guardrail_count"] == 1
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["shell_execution_count"] == 0
    assert payload["summary"]["passed"] is True

    for row in scenarios.values():
        assert row["run_id"].startswith("p87-")
        assert row["status"] in {"completed_all", "max_iterations", "needs_human", "failed_guardrail", "no_safe_work"}
        assert row["terminal_classification"] in {"terminal", "non_terminal"}
        assert row["checkpoint_timeline"]
        assert row["audit_metadata"]["local_mock_only"] is True
        assert row["claim_boundary"]["local_mock_only"] is True
        assert row["claim_boundary"]["unattended_production_operation_claimed"] is False
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


def test_completed_all_report_is_terminal_success() -> None:
    payload = evaluate_supervisor_run_report_artifact_fixture(FIXTURE).to_dict()
    report = {row["scenario_id"]: row for row in payload["reports"]}["completed-all-report"]

    assert report["status"] == "completed_all"
    assert report["stop_reason"] == "completed_all"
    assert report["terminal_classification"] == "terminal"
    assert report["completed_items"] == [{"item_id": "p87-terminal-safe", "status": "completed"}]
    assert report["skipped_items"] == []
    assert report["blocked_items"] == []
    assert report["resumable_items"] == []
    assert report["safety_gates_hit"] == []
    assert report["next_recommended_action"]["action"] == "archive_report"
    assert report["next_recommended_wakeup"] is None
    assert report["human_decision_required"]["required"] is False


def test_max_iteration_report_keeps_resumable_cursor() -> None:
    payload = evaluate_supervisor_run_report_artifact_fixture(FIXTURE).to_dict()
    report = {row["scenario_id"]: row for row in payload["reports"]}["max-iteration-report"]

    assert report["terminal_classification"] == "non_terminal"
    assert report["safety_gates_hit"] == ["max_iterations"]
    assert report["completed_items"] == [{"item_id": "p87-iteration-first", "status": "completed"}]
    assert report["resumable_items"] == [
        {"item_id": "p87-iteration-second", "status": "resumable", "cursor": 1}
    ]
    assert report["next_recommended_action"]["action"] == "resume_from_cursor"
    assert report["next_recommended_wakeup"]["reason"] == "resume_after_iteration_limit"


def test_needs_human_report_records_blocked_reasons() -> None:
    payload = evaluate_supervisor_run_report_artifact_fixture(FIXTURE).to_dict()
    report = {row["scenario_id"]: row for row in payload["reports"]}["needs-human-report"]

    assert report["terminal_classification"] == "terminal"
    assert report["safety_gates_hit"] == ["approval_blocked"]
    assert report["blocked_items"] == [
        {
            "item_id": "p87-human-approval-required",
            "status": "blocked",
            "reason": "approval_required",
            "blocked_by": "human_review",
        }
    ]
    assert report["human_decision_required"] == {
        "required": True,
        "reason": "approval_required",
        "blocked_item_ids": ["p87-human-approval-required"],
    }
    assert report["next_recommended_action"]["action"] == "request_human_decision"


def test_failed_guardrail_report_includes_failure_evidence() -> None:
    payload = evaluate_supervisor_run_report_artifact_fixture(FIXTURE).to_dict()
    report = {row["scenario_id"]: row for row in payload["reports"]}["failed-guardrail-report"]

    assert report["terminal_classification"] == "terminal"
    assert report["safety_gates_hit"] == ["failure_streak"]
    assert report["failure_evidence"] == [
        {"item_id": "p87-failing-local-check-one", "result": "failed", "executed": False},
        {"item_id": "p87-failing-local-check-two", "result": "failed", "executed": False},
    ]
    assert report["next_recommended_action"]["action"] == "review_guardrail_failure"


def test_no_safe_work_report_is_safe_stop() -> None:
    payload = evaluate_supervisor_run_report_artifact_fixture(FIXTURE).to_dict()
    report = {row["scenario_id"]: row for row in payload["reports"]}["no-safe-work-report"]

    assert report["terminal_classification"] == "terminal"
    assert report["safety_gates_hit"] == ["evidence_insufficiency"]
    assert report["skipped_items"] == [
        {
            "item_id": "p87-insufficient-evidence",
            "status": "skipped",
            "reason": "insufficient_evidence",
            "blocked_by": "no_safe_local_work",
        }
    ]
    assert report["next_recommended_action"]["action"] == "recheck_backlog"


def test_resumed_run_report_has_no_duplicate_completed_items() -> None:
    payload = evaluate_supervisor_run_report_artifact_fixture(FIXTURE).to_dict()
    report = {row["scenario_id"]: row for row in payload["reports"]}["resumed-run-report"]

    completed_ids = [item["item_id"] for item in report["completed_items"]]
    assert completed_ids == ["p87-resume-already-done", "p87-resume-next-safe"]
    assert len(completed_ids) == len(set(completed_ids))
    assert report["audit_metadata"]["resumed_from_state"] is True
    assert report["checkpoint_timeline"][0]["event"] == "start"


def test_supervisor_run_report_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p87.json"
    output_md = tmp_path / "p87.md"

    result = subprocess.run(
        [
            "python",
            "scripts/run_supervisor_run_report_artifact.py",
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
    assert "terminal=5" in result.stdout
    assert "resumable=1" in result.stdout
    assert "needs_human=1" in result.stdout
    assert "failed_guardrail=1" in result.stdout
    assert "executions=0" in result.stdout
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Supervisor Run Report Artifact" in markdown
    assert "Human decision required" in markdown
    assert render_supervisor_run_report_markdown(payload).startswith("# OpsCat Supervisor Run Report Artifact")
