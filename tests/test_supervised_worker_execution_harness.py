from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.supervised_worker_execution_harness import (
    RealSubprocessSupervisedTransport,
    SimulatedSupervisedProcessTransport,
    SupervisedWorkerExecutionHarnessReport,
    render_supervised_worker_execution_harness_markdown,
    run_supervised_worker_execution_harness_fixture,
)

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_supervised_harness_runs_gate_approved_commands_with_simulated_transport(tmp_path: Path) -> None:
    report = run_supervised_worker_execution_harness_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_parallel=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(),
    )
    payload = report.to_dict()

    assert isinstance(report, SupervisedWorkerExecutionHarnessReport)
    assert payload["summary"]["eligible_command_count"] == 3
    assert payload["summary"]["started_run_count"] == 3
    assert payload["summary"]["succeeded_run_count"] == 3
    assert payload["summary"]["failed_run_count"] == 0
    assert payload["summary"]["retry_queue_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["policy"]["process_execution_enabled"] is True
    assert payload["policy"]["transport"] == "simulated-supervised"
    assert payload["policy"]["max_parallel"] == 2
    assert [run["ticket_id"] for run in payload["supervised_runs"]] == ["P66", "P68", "P88"]
    assert all(run["exit_code"] == 0 for run in payload["supervised_runs"])
    assert all(Path(run["stdout_path"]).exists() for run in payload["supervised_runs"])
    assert all(Path(run["stderr_path"]).exists() for run in payload["supervised_runs"])
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["completed_tickets"] == ["P66", "P68", "P88"]


def test_supervised_harness_requires_explicit_enable_flag(tmp_path: Path) -> None:
    payload = run_supervised_worker_execution_harness_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        enable_process_execution=False,
        transport=SimulatedSupervisedProcessTransport(),
    ).to_dict()

    assert payload["summary"]["eligible_command_count"] == 2
    assert payload["summary"]["started_run_count"] == 0
    assert payload["summary"]["blocked_by_enable_flag_count"] == 2
    assert payload["summary"]["passed"] is False
    assert all(run["status"] == "blocked_by_enable_flag" for run in payload["supervised_runs"])


def test_supervised_harness_records_retry_queue_on_nonzero_exit(tmp_path: Path) -> None:
    transport = SimulatedSupervisedProcessTransport(fail_ticket_ids={"P68"})
    payload = run_supervised_worker_execution_harness_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        enable_process_execution=True,
        transport=transport,
    ).to_dict()

    assert payload["summary"]["started_run_count"] == 3
    assert payload["summary"]["succeeded_run_count"] == 2
    assert payload["summary"]["failed_run_count"] == 1
    assert payload["summary"]["retry_queue_count"] == 1
    assert payload["summary"]["passed"] is False
    retry = payload["retry_queue"][0]
    assert retry["ticket_id"] == "P68"
    assert retry["reason"] == "simulated worker nonzero exit"
    assert retry["exit_code"] == 1


def test_supervised_harness_preserves_live_action_production_zero_counters(tmp_path: Path) -> None:
    payload = run_supervised_worker_execution_harness_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
        enable_process_execution=True,
        transport=SimulatedSupervisedProcessTransport(),
    ).to_dict()

    assert payload["score"]["supervised_process_run_count"] == 2
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["timeout_count"] == 0
    assert payload["score"]["state_write_count"] == 1


def test_supervised_harness_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "harness.json"
    output_md = tmp_path / "harness.md"

    subprocess.run(
        [
            "python",
            "scripts/run_supervised_worker_execution_harness.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--max-tickets",
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
    assert "# OpsCat Supervised Worker Execution Harness" in markdown
    assert "Supervised runs" in markdown
    assert "Retry queue" in markdown
    assert render_supervised_worker_execution_harness_markdown(payload).startswith("# OpsCat Supervised Worker Execution Harness")


def test_shipped_real_supervised_transport_rejects_arbitrary_command_strings(tmp_path: Path) -> None:
    outcome = RealSubprocessSupervisedTransport().run("python -c 'raise SystemExit(13)'", ticket_id="P122", timeout_seconds=1, artifact_dir=tmp_path)

    assert outcome.status == "failed_closed"
    assert outcome.exit_code == 126
    assert outcome.timed_out is False
