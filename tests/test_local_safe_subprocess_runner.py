from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.local_safe_subprocess_runner import (
    LocalSafeSubprocessRunnerReport,
    SimulatedLocalSubprocessTransport,
    StaticGitWorktreeStatusProvider,
    render_local_safe_subprocess_runner_markdown,
    run_local_safe_subprocess_runner_fixture,
)

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_local_safe_runner_executes_dry_run_ready_items_with_simulated_transport(tmp_path: Path) -> None:
    report = run_local_safe_subprocess_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=2,
        enable_real_subprocess=True,
        enable_local_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
        transport=SimulatedLocalSubprocessTransport(),
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
    )
    payload = report.to_dict()

    assert isinstance(report, LocalSafeSubprocessRunnerReport)
    assert payload["summary"]["dry_run_ready_count"] == 2
    assert payload["summary"]["started_run_count"] == 2
    assert payload["summary"]["succeeded_run_count"] == 2
    assert payload["summary"]["failed_run_count"] == 0
    assert payload["summary"]["retry_queue_count"] == 0
    assert payload["summary"]["upstream_blocked_count"] == 1
    assert payload["summary"]["actual_spawn_count"] == 0
    assert payload["summary"]["passed"] is True
    assert [run["ticket_id"] for run in payload["local_runs"]] == ["P66", "P68"]
    assert all(Path(run["stdout_path"]).exists() for run in payload["local_runs"])
    assert all(Path(run["stderr_path"]).exists() for run in payload["local_runs"])
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["completed_tickets"] == ["P66", "P68"]
    assert state["actual_spawn_count"] == 0


def test_local_safe_runner_blocks_when_local_subprocess_enablement_is_missing(tmp_path: Path) -> None:
    payload = run_local_safe_subprocess_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=2,
        enable_real_subprocess=True,
        enable_local_subprocess=False,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
        transport=SimulatedLocalSubprocessTransport(),
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
    ).to_dict()

    assert payload["summary"]["dry_run_ready_count"] == 2
    assert payload["summary"]["started_run_count"] == 0
    assert payload["summary"]["blocked_by_local_enablement_count"] == 2
    assert payload["summary"]["passed"] is False
    assert all(run["status"] == "blocked_local_enablement_missing" for run in payload["local_runs"])


def test_local_safe_runner_preserves_p74_dirty_git_blocks(tmp_path: Path) -> None:
    payload = run_local_safe_subprocess_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=2,
        enable_real_subprocess=True,
        enable_local_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=False, entries=("M app/services/example.py",)),
        transport=SimulatedLocalSubprocessTransport(),
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
    ).to_dict()

    assert payload["summary"]["dry_run_ready_count"] == 0
    assert payload["summary"]["started_run_count"] == 0
    assert payload["summary"]["upstream_blocked_count"] == 3
    assert payload["summary"]["passed"] is False
    assert all(run["status"] == "blocked_upstream_gate" for run in payload["local_runs"])


def test_local_safe_runner_records_retry_queue_on_simulated_failure(tmp_path: Path) -> None:
    payload = run_local_safe_subprocess_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=2,
        enable_real_subprocess=True,
        enable_local_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
        transport=SimulatedLocalSubprocessTransport(fail_ticket_ids={"P68"}),
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
    ).to_dict()

    assert payload["summary"]["started_run_count"] == 2
    assert payload["summary"]["succeeded_run_count"] == 1
    assert payload["summary"]["failed_run_count"] == 1
    assert payload["summary"]["retry_queue_count"] == 1
    assert payload["summary"]["passed"] is False
    assert payload["retry_queue"][0]["ticket_id"] == "P68"
    assert payload["retry_queue"][0]["reason"] == "simulated local subprocess nonzero exit"


def test_local_safe_runner_preserves_zero_live_action_production_side_effects(tmp_path: Path) -> None:
    payload = run_local_safe_subprocess_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=2,
        enable_real_subprocess=True,
        enable_local_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
        transport=SimulatedLocalSubprocessTransport(),
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        artifact_dir=tmp_path / "artifacts",
    ).to_dict()

    assert payload["score"]["simulated_local_process_run_count"] == 2
    assert payload["score"]["actual_spawn_count"] == 0
    assert payload["score"]["shell_command_execution_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["state_write_count"] == 1


def test_local_safe_subprocess_runner_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "runner.json"
    output_md = tmp_path / "runner.md"

    subprocess.run(
        [
            "python",
            "scripts/run_local_safe_subprocess_runner.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--max-tickets",
            "3",
            "--max-processes",
            "2",
            "--enable-real-subprocess",
            "--enable-local-subprocess",
            "--git-status",
            "clean",
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
    assert "# OpsCat Local Safe Subprocess Runner" in markdown
    assert "Local runs" in markdown
    assert "Retry queue" in markdown
    assert render_local_safe_subprocess_runner_markdown(payload).startswith("# OpsCat Local Safe Subprocess Runner")
