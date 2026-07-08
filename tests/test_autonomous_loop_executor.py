from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.autonomous_loop_executor import (
    AutonomousLoopExecutorReport,
    render_autonomous_loop_executor_markdown,
    run_autonomous_loop_executor_fixture,
)

MANIFEST = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_executor_runs_only_safe_local_tickets_and_blocks_gated_work() -> None:
    report = run_autonomous_loop_executor_fixture(MANIFEST, completed={"P65"}, max_tickets=3, mode="local-auto")
    payload = report.to_dict()

    assert isinstance(report, AutonomousLoopExecutorReport)
    assert payload["summary"]["mode"] == "local-auto"
    assert payload["summary"]["selected_ticket_count"] == 3
    assert payload["summary"]["completed_ticket_count"] == 3
    assert payload["summary"]["blocked_ticket_count"] >= 5
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["next_runnable_ticket"] == "P69"
    assert [ticket["ticket_id"] for ticket in payload["selected_tickets"]] == ["P66", "P68", "P88"]
    assert all(ticket["safety_class"] == "safe-local" for ticket in payload["selected_tickets"])
    assert payload["blocked_tickets"]["P67"]["reason"] == "gated-live denied by executor policy"
    assert payload["blocked_tickets"]["P79"]["reason"] == "gated-action denied by executor policy"
    assert payload["blocked_tickets"]["P92"]["reason"] == "blocked-production denied by executor policy"


def test_executor_records_commands_checkpoints_and_zero_forbidden_side_effects() -> None:
    payload = run_autonomous_loop_executor_fixture(MANIFEST, completed={"P65"}, max_tickets=2, mode="local-auto").to_dict()

    assert payload["policy"]["auto_approve_safe_local"] is True
    assert payload["policy"]["deny_live"] is True
    assert payload["policy"]["deny_actions"] is True
    assert payload["policy"]["deny_production"] is True
    assert payload["score"]["executed_safe_local_ticket_count"] == 2
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["gated_execution_attempt_count"] == 0
    assert payload["checkpoints"]
    assert payload["checkpoints"][0]["command"] == "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs"
    assert payload["ticket_results"][0]["status"] == "completed"
    assert payload["ticket_results"][0]["delegation_prompt_path"].endswith("P66.md")


def test_executor_can_resume_after_completed_safe_local_batch() -> None:
    payload = run_autonomous_loop_executor_fixture(MANIFEST, completed={"P65", "P66", "P68", "P88"}, max_tickets=2, mode="local-auto").to_dict()

    assert [ticket["ticket_id"] for ticket in payload["selected_tickets"]] == ["P69", "P86"]
    assert payload["summary"]["next_runnable_ticket"] == "P70"
    assert payload["summary"]["passed"] is True


def test_executor_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "executor.json"
    output_md = tmp_path / "executor.md"

    subprocess.run(
        [
            "python",
            "scripts/run_autonomous_loop_executor.py",
            "--manifest",
            str(MANIFEST),
            "--completed",
            "P65",
            "--mode",
            "local-auto",
            "--max-tickets",
            "3",
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
    assert "# OpsCat Autonomous Loop Executor" in markdown
    assert "Selected safe-local tickets" in markdown
    assert "Blocked gated work" in markdown
    assert render_autonomous_loop_executor_markdown(payload).startswith("# OpsCat Autonomous Loop Executor")
