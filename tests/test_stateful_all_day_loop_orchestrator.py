from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.stateful_all_day_loop_orchestrator import (
    StatefulAllDayLoopOrchestratorReport,
    render_stateful_all_day_loop_orchestrator_markdown,
    run_stateful_all_day_loop_orchestrator_fixture,
)
from app.services.supervised_worker_execution_harness import SimulatedSupervisedProcessTransport

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_orchestrator_runs_multiple_supervised_cycles_and_persists_resume_state(tmp_path: Path) -> None:
    report = run_stateful_all_day_loop_orchestrator_fixture(
        MANIFEST,
        completed={"P65"},
        max_cycles=3,
        max_tickets_per_cycle=3,
        max_parallel=2,
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(),
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    )
    payload = report.to_dict()

    assert isinstance(report, StatefulAllDayLoopOrchestratorReport)
    assert payload["summary"]["cycle_count"] == 3
    assert payload["summary"]["completed_ticket_count"] == 8
    assert payload["summary"]["failed_ticket_count"] == 0
    assert payload["summary"]["retry_queue_count"] == 0
    assert payload["summary"]["stop_reason"] == "max_cycles_reached"
    assert payload["summary"]["passed"] is True
    assert payload["cycles"][0]["started_ticket_ids"] == ["P66", "P68", "P88"]
    assert payload["cycles"][1]["started_ticket_ids"] == ["P69", "P86"]
    assert payload["cycles"][2]["started_ticket_ids"] == ["P70", "P72", "P75"]
    assert payload["operator_handoff"]["resume_completed_tickets"] == ["P65", "P66", "P68", "P69", "P70", "P72", "P75", "P86", "P88"]
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["resume_completed_tickets"] == payload["operator_handoff"]["resume_completed_tickets"]
    assert state["last_cycle_index"] == 3


def test_orchestrator_stops_on_retry_queue_and_preserves_failure_artifacts(tmp_path: Path) -> None:
    payload = run_stateful_all_day_loop_orchestrator_fixture(
        MANIFEST,
        completed={"P65"},
        max_cycles=4,
        max_tickets_per_cycle=3,
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(fail_ticket_ids={"P69"}),
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["summary"]["cycle_count"] == 2
    assert payload["summary"]["failed_ticket_count"] == 1
    assert payload["summary"]["retry_queue_count"] == 1
    assert payload["summary"]["stop_reason"] == "retry_queue_non_empty"
    assert payload["summary"]["passed"] is False
    assert payload["retry_queue"][0]["ticket_id"] == "P69"
    assert Path(payload["retry_queue"][0]["stderr_path"]).exists()
    assert "P69" not in payload["operator_handoff"]["resume_completed_tickets"]


def test_orchestrator_blocks_when_process_execution_is_not_enabled(tmp_path: Path) -> None:
    payload = run_stateful_all_day_loop_orchestrator_fixture(
        MANIFEST,
        completed={"P65"},
        max_cycles=3,
        max_tickets_per_cycle=3,
        enable_process_execution=False,
        transport=SimulatedSupervisedProcessTransport(),
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["summary"]["cycle_count"] == 1
    assert payload["summary"]["completed_ticket_count"] == 0
    assert payload["summary"]["blocked_by_enable_flag_count"] == 3
    assert payload["summary"]["stop_reason"] == "process_execution_not_enabled"
    assert payload["summary"]["passed"] is False
    assert payload["cycles"][0]["blocked_ticket_ids"] == ["P66", "P68", "P88"]


def test_orchestrator_preserves_zero_live_action_production_side_effects(tmp_path: Path) -> None:
    payload = run_stateful_all_day_loop_orchestrator_fixture(
        MANIFEST,
        completed={"P65"},
        max_cycles=2,
        max_tickets_per_cycle=3,
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(),
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["score"]["supervised_process_run_count"] == 5
    assert payload["score"]["cycle_checkpoint_count"] == 2
    assert payload["score"]["state_write_count"] == 2
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["real_subprocess_transport_count"] == 0


def test_orchestrator_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "orchestrator.json"
    output_md = tmp_path / "orchestrator.md"

    subprocess.run(
        [
            "python",
            "scripts/run_stateful_all_day_loop_orchestrator.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--max-cycles",
            "3",
            "--max-tickets-per-cycle",
            "3",
            "--max-parallel",
            "2",
            "--enable-process-execution",
            "--transport",
            "simulated",
            "--dispatch-dir",
            str(tmp_path / "dispatch"),
            "--state-path",
            str(tmp_path / "state.json"),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
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
    assert "# OpsCat Stateful All-Day Loop Orchestrator" in markdown
    assert "Cycle timeline" in markdown
    assert "Operator handoff" in markdown
    assert render_stateful_all_day_loop_orchestrator_markdown(payload).startswith("# OpsCat Stateful All-Day Loop Orchestrator")
