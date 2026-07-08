from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.long_run_loop_controller import (
    LongRunLoopControllerReport,
    render_long_run_loop_controller_markdown,
    run_long_run_loop_controller_fixture,
)
from app.services.supervised_worker_execution_harness import SimulatedSupervisedProcessTransport

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_long_run_controller_repeats_stateful_windows_until_max_windows(tmp_path: Path) -> None:
    report = run_long_run_loop_controller_fixture(
        MANIFEST,
        completed={"P65"},
        max_windows=2,
        p72_cycles_per_window=2,
        max_tickets_per_cycle=3,
        max_parallel=2,
        duration_seconds=10_000,
        sleep_seconds=0,
        simulated_window_seconds=60,
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(),
        state_path=tmp_path / "controller-state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    )
    payload = report.to_dict()

    assert isinstance(report, LongRunLoopControllerReport)
    assert payload["summary"]["window_count"] == 2
    assert payload["summary"]["p72_cycle_count"] == 4
    assert payload["summary"]["completed_ticket_count"] == 11
    assert payload["summary"]["retry_queue_count"] == 0
    assert payload["summary"]["stop_reason"] == "max_windows_reached"
    assert payload["summary"]["passed"] is True
    assert payload["windows"][0]["started_ticket_ids"] == ["P66", "P68", "P88", "P69", "P86"]
    assert payload["windows"][1]["started_ticket_ids"] == ["P70", "P72", "P75", "P71", "P73", "P74"]
    assert payload["operator_handoff"]["resume_completed_tickets"] == [
        "P65",
        "P66",
        "P68",
        "P69",
        "P70",
        "P71",
        "P72",
        "P73",
        "P74",
        "P75",
        "P86",
        "P88",
    ]
    state = json.loads((tmp_path / "controller-state.json").read_text(encoding="utf-8"))
    assert state["last_window_index"] == 2
    assert state["resume_completed_tickets"] == payload["operator_handoff"]["resume_completed_tickets"]


def test_long_run_controller_stops_before_exceeding_duration_budget(tmp_path: Path) -> None:
    payload = run_long_run_loop_controller_fixture(
        MANIFEST,
        completed={"P65"},
        max_windows=5,
        p72_cycles_per_window=2,
        duration_seconds=90,
        sleep_seconds=30,
        simulated_window_seconds=60,
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(),
        state_path=tmp_path / "controller-state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["summary"]["window_count"] == 1
    assert payload["summary"]["elapsed_seconds"] == 90
    assert payload["summary"]["planned_sleep_count"] == 1
    assert payload["summary"]["stop_reason"] == "duration_budget_reached"
    assert payload["summary"]["passed"] is True


def test_long_run_controller_stops_on_retry_queue(tmp_path: Path) -> None:
    payload = run_long_run_loop_controller_fixture(
        MANIFEST,
        completed={"P65"},
        max_windows=4,
        p72_cycles_per_window=2,
        duration_seconds=10_000,
        sleep_seconds=0,
        simulated_window_seconds=60,
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(fail_ticket_ids={"P70"}),
        state_path=tmp_path / "controller-state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["summary"]["window_count"] == 2
    assert payload["summary"]["retry_queue_count"] == 1
    assert payload["summary"]["failed_ticket_count"] == 1
    assert payload["summary"]["stop_reason"] == "retry_queue_non_empty"
    assert payload["summary"]["passed"] is False
    assert payload["retry_queue"][0]["ticket_id"] == "P70"


def test_long_run_controller_requires_process_execution_enablement(tmp_path: Path) -> None:
    payload = run_long_run_loop_controller_fixture(
        MANIFEST,
        completed={"P65"},
        max_windows=4,
        p72_cycles_per_window=2,
        duration_seconds=10_000,
        sleep_seconds=0,
        simulated_window_seconds=60,
        enable_process_execution=False,
        transport=SimulatedSupervisedProcessTransport(),
        state_path=tmp_path / "controller-state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["summary"]["window_count"] == 1
    assert payload["summary"]["completed_ticket_count"] == 0
    assert payload["summary"]["blocked_by_enable_flag_count"] == 3
    assert payload["summary"]["stop_reason"] == "process_execution_not_enabled"
    assert payload["summary"]["passed"] is False


def test_long_run_controller_preserves_zero_live_action_production_side_effects(tmp_path: Path) -> None:
    payload = run_long_run_loop_controller_fixture(
        MANIFEST,
        completed={"P65"},
        max_windows=2,
        p72_cycles_per_window=2,
        duration_seconds=10_000,
        sleep_seconds=0,
        simulated_window_seconds=60,
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(),
        state_path=tmp_path / "controller-state.json",
        artifact_dir=tmp_path / "artifacts",
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["score"]["supervised_process_run_count"] == 11
    assert payload["score"]["window_checkpoint_count"] == 2
    assert payload["score"]["state_write_count"] == 2
    assert payload["score"]["planned_sleep_seconds_total"] == 0
    assert payload["score"]["actual_sleep_seconds_total"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["real_subprocess_transport_count"] == 0


def test_long_run_controller_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "controller.json"
    output_md = tmp_path / "controller.md"

    subprocess.run(
        [
            "python",
            "scripts/run_long_run_loop_controller.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--max-windows",
            "2",
            "--p72-cycles-per-window",
            "2",
            "--max-tickets-per-cycle",
            "3",
            "--max-parallel",
            "2",
            "--duration-seconds",
            "10000",
            "--sleep-seconds",
            "0",
            "--simulated-window-seconds",
            "60",
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
    assert "# OpsCat Long-Run Loop Controller" in markdown
    assert "Window timeline" in markdown
    assert "Stop guard" in markdown
    assert render_long_run_loop_controller_markdown(payload).startswith("# OpsCat Long-Run Loop Controller")
