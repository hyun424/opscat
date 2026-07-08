from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.real_subprocess_execution_dry_run_gate import (
    RealSubprocessExecutionDryRunGateReport,
    StaticGitWorktreeStatusProvider,
    render_real_subprocess_execution_dry_run_gate_markdown,
    run_real_subprocess_execution_dry_run_gate_fixture,
)

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_dry_run_gate_marks_clean_allowlisted_commands_ready_without_spawning(tmp_path: Path) -> None:
    report = run_real_subprocess_execution_dry_run_gate_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        enable_real_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
    )
    payload = report.to_dict()

    assert isinstance(report, RealSubprocessExecutionDryRunGateReport)
    assert payload["summary"]["validated_command_count"] == 3
    assert payload["summary"]["dry_run_ready_count"] == 2
    assert payload["summary"]["budget_blocked_count"] == 1
    assert payload["summary"]["dirty_git_block_count"] == 0
    assert payload["summary"]["actual_spawn_count"] == 0
    assert payload["summary"]["passed"] is True
    assert [item["ticket_id"] for item in payload["execution_plan"] if item["status"] == "dry_run_ready"] == ["P66", "P68"]
    assert all(Path(item["stdout_path"]).exists() for item in payload["execution_plan"])
    assert all(Path(item["stderr_path"]).exists() for item in payload["execution_plan"])
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["dry_run_ready_tickets"] == ["P66", "P68"]
    assert state["actual_spawn_count"] == 0


def test_dry_run_gate_blocks_all_commands_when_git_worktree_is_dirty(tmp_path: Path) -> None:
    payload = run_real_subprocess_execution_dry_run_gate_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=3,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        enable_real_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=False, entries=("M app/services/example.py",)),
    ).to_dict()

    assert payload["summary"]["dry_run_ready_count"] == 0
    assert payload["summary"]["dirty_git_block_count"] == 3
    assert payload["summary"]["passed"] is False
    assert all(item["status"] == "blocked_dirty_git" for item in payload["execution_plan"])
    assert payload["operator_handoff"]["next_step"] == "clean or explicitly review worktree changes before real subprocess execution"


def test_dry_run_gate_blocks_when_explicit_enablement_is_missing(tmp_path: Path) -> None:
    payload = run_real_subprocess_execution_dry_run_gate_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        max_processes=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        enable_real_subprocess=False,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
    ).to_dict()

    assert payload["summary"]["dry_run_ready_count"] == 0
    assert payload["summary"]["enablement_blocked_count"] == 2
    assert payload["summary"]["passed"] is False
    assert all(item["status"] == "blocked_enablement_missing" for item in payload["execution_plan"])


def test_dry_run_gate_preserves_p70_command_gate_blocks(tmp_path: Path) -> None:
    payload = run_real_subprocess_execution_dry_run_gate_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        max_processes=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        enable_real_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
        command_mutator=lambda command: command.replace(str(tmp_path / "dispatch"), "/tmp/outside-dispatch"),
    ).to_dict()

    assert payload["summary"]["command_gate_blocked_count"] == 2
    assert payload["summary"]["dry_run_ready_count"] == 0
    assert payload["summary"]["passed"] is False
    assert all(item["status"] == "blocked_command_gate" for item in payload["execution_plan"])
    assert "prompt_path_outside_dispatch_dir" in payload["execution_plan"][0]["reasons"]


def test_dry_run_gate_preserves_zero_live_action_production_side_effects(tmp_path: Path) -> None:
    payload = run_real_subprocess_execution_dry_run_gate_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_processes=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        enable_real_subprocess=True,
        git_status_provider=StaticGitWorktreeStatusProvider(clean=True),
    ).to_dict()

    assert payload["score"]["would_spawn_count"] == 2
    assert payload["score"]["actual_spawn_count"] == 0
    assert payload["score"]["shell_command_execution_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["state_write_count"] == 1


def test_real_subprocess_dry_run_gate_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "dry-run.json"
    output_md = tmp_path / "dry-run.md"

    subprocess.run(
        [
            "python",
            "scripts/run_real_subprocess_execution_dry_run_gate.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--max-tickets",
            "3",
            "--max-processes",
            "2",
            "--enable-real-subprocess",
            "--git-status",
            "clean",
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
    assert "# OpsCat Real Subprocess Execution Dry-Run Gate" in markdown
    assert "Execution plan" in markdown
    assert "Safety counters" in markdown
    assert render_real_subprocess_execution_dry_run_gate_markdown(payload).startswith("# OpsCat Real Subprocess Execution Dry-Run Gate")
