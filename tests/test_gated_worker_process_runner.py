from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.gated_worker_process_runner import (
    GatedWorkerProcessRunnerReport,
    RecordingProcessTransport,
    render_gated_worker_process_runner_markdown,
    run_gated_worker_process_runner_fixture,
)

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_process_runner_validates_allowed_codex_commands_without_spawning(tmp_path: Path) -> None:
    report = run_gated_worker_process_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_parallel=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        transport=RecordingProcessTransport(),
    )
    payload = report.to_dict()

    assert isinstance(report, GatedWorkerProcessRunnerReport)
    assert payload["summary"]["validated_command_count"] == 3
    assert payload["summary"]["process_capable_count"] == 3
    assert payload["summary"]["spawned_process_count"] == 0
    assert payload["summary"]["blocked_command_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["policy"]["process_execution_enabled"] is False
    assert payload["policy"]["allowed_binary"] == "codex"
    assert payload["policy"]["required_subcommand"] == "exec"
    assert payload["policy"]["max_parallel"] == 2
    assert [item["ticket_id"] for item in payload["validated_commands"]] == ["P66", "P68", "P88"]
    assert all(item["status"] == "process_ready_not_spawned" for item in payload["validated_commands"])
    assert all("--sandbox workspace-write" in item["command"] for item in payload["validated_commands"])


def test_process_runner_blocks_unsafe_command_mutations(tmp_path: Path) -> None:
    def mutate(command: str) -> str:
        return command.replace("codex exec", "rm -rf")

    payload = run_gated_worker_process_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        command_mutator=mutate,
        transport=RecordingProcessTransport(),
    ).to_dict()

    assert payload["summary"]["validated_command_count"] == 2
    assert payload["summary"]["process_capable_count"] == 0
    assert payload["summary"]["blocked_command_count"] == 2
    assert payload["summary"]["passed"] is False
    assert all(item["status"] == "blocked" for item in payload["validated_commands"])
    assert all("binary_not_allowlisted" in item["reasons"] for item in payload["validated_commands"])


def test_process_runner_enforces_prompt_path_under_dispatch_dir(tmp_path: Path) -> None:
    def mutate(command: str) -> str:
        return command.rsplit(" ", 1)[0] + " /tmp/outside-prompt.md"

    payload = run_gated_worker_process_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=1,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        command_mutator=mutate,
        transport=RecordingProcessTransport(),
    ).to_dict()

    assert payload["summary"]["blocked_command_count"] == 1
    assert payload["validated_commands"][0]["status"] == "blocked"
    assert "prompt_path_outside_dispatch_dir" in payload["validated_commands"][0]["reasons"]


def test_process_runner_preserves_forbidden_side_effect_counters(tmp_path: Path) -> None:
    payload = run_gated_worker_process_runner_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        dispatch_dir=tmp_path / "dispatch",
        state_path=tmp_path / "state.json",
        transport=RecordingProcessTransport(),
    ).to_dict()

    assert payload["score"]["spawned_process_count"] == 0
    assert payload["score"]["shell_command_execution_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["blocked_command_count"] == 0


def test_process_runner_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "process-runner.json"
    output_md = tmp_path / "process-runner.md"

    subprocess.run(
        [
            "python",
            "scripts/run_gated_worker_process_runner.py",
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
            str(tmp_path / "state.json"),
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
    assert "# OpsCat Gated Worker Process Runner" in markdown
    assert "Validated commands" in markdown
    assert "Blocked commands" in markdown
    assert render_gated_worker_process_runner_markdown(payload).startswith("# OpsCat Gated Worker Process Runner")
