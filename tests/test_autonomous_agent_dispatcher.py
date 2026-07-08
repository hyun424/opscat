from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.autonomous_agent_dispatcher import (
    AutonomousAgentDispatcherReport,
    render_autonomous_agent_dispatcher_markdown,
    run_autonomous_agent_dispatcher_fixture,
)

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")
SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token", "nvapi-", "actual-secret-value", "Authorization", "Bearer")


def test_dispatcher_emits_safe_local_packets_without_spawning_processes(tmp_path: Path) -> None:
    report = run_autonomous_agent_dispatcher_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=3,
        max_parallel=2,
        dispatch_dir=tmp_path / "dispatch",
    )
    payload = report.to_dict()

    assert isinstance(report, AutonomousAgentDispatcherReport)
    assert payload["summary"]["dispatch_packet_count"] == 3
    assert payload["summary"]["queued_packet_count"] == 3
    assert payload["summary"]["blocked_dispatch_count"] == 6
    assert payload["summary"]["next_runnable_ticket"] == "P69"
    assert payload["summary"]["passed"] is True
    assert payload["policy"]["agent_type"] == "executor"
    assert payload["policy"]["dispatch_mode"] == "packet-only"
    assert payload["policy"]["spawn_processes"] is False
    assert payload["policy"]["execute_shell_commands"] is False
    assert payload["policy"]["max_parallel"] == 2
    assert [packet["ticket_id"] for packet in payload["dispatch_packets"]] == ["P66", "P68", "P88"]
    assert all(packet["safety_class"] == "safe-local" for packet in payload["dispatch_packets"])
    assert all(packet["status"] == "queued" for packet in payload["dispatch_packets"])


def test_dispatcher_writes_packet_files_with_tdd_and_verification_contract(tmp_path: Path) -> None:
    payload = run_autonomous_agent_dispatcher_fixture(
        MANIFEST,
        completed={"P65"},
        max_tickets=2,
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert payload["score"]["dispatch_packet_count"] == 2
    assert payload["score"]["spawned_process_count"] == 0
    assert payload["score"]["shell_command_execution_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0

    for packet in payload["dispatch_packets"]:
        prompt = Path(packet["prompt_path"])
        spec = Path(packet["packet_path"])
        assert prompt.exists()
        assert spec.exists()
        prompt_text = prompt.read_text(encoding="utf-8")
        spec_payload = json.loads(spec.read_text(encoding="utf-8"))
        assert "TDD" in prompt_text
        assert "Do not read credentials" in prompt_text
        assert "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs" in prompt_text
        assert spec_payload["agent_type"] == "executor"
        assert spec_payload["ticket_id"] == packet["ticket_id"]
        assert spec_payload["approval_policy"] == "safe-local-auto"
        assert all(marker not in prompt_text + spec.read_text(encoding="utf-8") for marker in SECRET_MARKERS)


def test_dispatcher_blocks_gated_work_and_resumes_after_batch(tmp_path: Path) -> None:
    payload = run_autonomous_agent_dispatcher_fixture(
        MANIFEST,
        completed={"P65", "P66", "P68", "P88"},
        max_tickets=2,
        dispatch_dir=tmp_path / "dispatch",
    ).to_dict()

    assert [packet["ticket_id"] for packet in payload["dispatch_packets"]] == ["P69", "P86"]
    assert payload["summary"]["next_runnable_ticket"] == "P70"
    assert payload["blocked_dispatches"]["P67"]["reason"] == "gated-live dispatch denied by policy"
    assert payload["blocked_dispatches"]["P79"]["reason"] == "gated-action dispatch denied by policy"
    assert payload["blocked_dispatches"]["P92"]["reason"] == "blocked-production dispatch denied by policy"


def test_dispatcher_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "dispatcher.json"
    output_md = tmp_path / "dispatcher.md"
    dispatch_dir = tmp_path / "packets"

    subprocess.run(
        [
            "python",
            "scripts/run_autonomous_agent_dispatcher.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--max-tickets",
            "3",
            "--max-parallel",
            "2",
            "--dispatch-dir",
            str(dispatch_dir),
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
    assert "# OpsCat Autonomous Agent Dispatcher" in markdown
    assert "Dispatch packets" in markdown
    assert "Blocked dispatches" in markdown
    assert render_autonomous_agent_dispatcher_markdown(payload).startswith("# OpsCat Autonomous Agent Dispatcher")
