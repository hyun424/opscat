from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.autonomous_worker_runner import (
    AutonomousWorkerRunnerReport,
    RecordingWorkerTransport,
    render_autonomous_worker_runner_markdown,
    run_autonomous_worker_runner_fixture,
)

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_worker_runner_claims_packets_and_records_success_without_spawning(tmp_path: Path) -> None:
    dispatch_dir = tmp_path / "dispatch"
    state_path = tmp_path / "state.json"
    report = run_autonomous_worker_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_parallel=2,
        dispatch_dir=dispatch_dir,
        state_path=state_path,
        transport=RecordingWorkerTransport(),
    )
    payload = report.to_dict()

    assert isinstance(report, AutonomousWorkerRunnerReport)
    assert payload["summary"]["claimed_packet_count"] == 3
    assert payload["summary"]["succeeded_run_count"] == 3
    assert payload["summary"]["failed_run_count"] == 0
    assert payload["summary"]["retry_queue_count"] == 0
    assert payload["summary"]["next_runnable_ticket"] == "P69"
    assert payload["summary"]["passed"] is True
    assert payload["policy"]["transport"] == "recording"
    assert payload["policy"]["spawn_processes"] is False
    assert payload["policy"]["execute_shell_commands"] is False
    assert payload["policy"]["max_parallel"] == 2
    assert [run["ticket_id"] for run in payload["worker_runs"]] == ["P66", "P68", "P88"]
    assert all(run["status"] == "succeeded" for run in payload["worker_runs"])
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["completed_tickets"] == ["P66", "P68", "P88"]


def test_worker_runner_records_retry_queue_on_transport_failure(tmp_path: Path) -> None:
    transport = RecordingWorkerTransport(fail_ticket_ids={"P68"})
    payload = run_autonomous_worker_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        transport=transport,
    ).to_dict()

    assert payload["summary"]["claimed_packet_count"] == 3
    assert payload["summary"]["succeeded_run_count"] == 2
    assert payload["summary"]["failed_run_count"] == 1
    assert payload["summary"]["retry_queue_count"] == 1
    assert payload["summary"]["passed"] is False
    retry = payload["retry_queue"][0]
    assert retry["ticket_id"] == "P68"
    assert retry["reason"] == "recording transport injected failure"
    assert retry["attempt"] == 1


def test_worker_runner_preserves_forbidden_side_effect_counters(tmp_path: Path) -> None:
    payload = run_autonomous_worker_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        transport=RecordingWorkerTransport(),
    ).to_dict()

    assert payload["score"]["spawned_process_count"] == 0
    assert payload["score"]["shell_command_execution_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["state_write_count"] == 1
    assert payload["worker_runs"][0]["planned_command"].startswith("codex exec")
    assert "--sandbox workspace-write" in payload["worker_runs"][0]["planned_command"]


def test_worker_runner_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "runner.json"
    output_md = tmp_path / "runner.md"
    state_path = tmp_path / "state.json"

    subprocess.run(
        [
            "python",
            "scripts/run_autonomous_worker_runner.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--max-tickets",
            "3",
            "--max-parallel",
            "2",
            "--dispatch-dir",
            str(tmp_path / "dispatch"),
            "--state-path",
            str(state_path),
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
    assert "# OpsCat Autonomous Worker Runner" in markdown
    assert "Worker runs" in markdown
    assert "Retry queue" in markdown
    assert render_autonomous_worker_runner_markdown(payload).startswith("# OpsCat Autonomous Worker Runner")
