from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.autonomous_day_loop_backlog import (
    AutonomousDayLoopBacklogReport,
    render_autonomous_day_loop_backlog_markdown,
    run_autonomous_day_loop_backlog_fixture,
)

FIXTURE = Path("evals/planning/p66_autonomous_day_loop_backlog.json")


def test_autonomous_day_loop_gathers_large_safe_backlog_without_side_effects() -> None:
    report = run_autonomous_day_loop_backlog_fixture(FIXTURE, completed={"P65"})
    payload = report.to_dict()

    assert isinstance(report, AutonomousDayLoopBacklogReport)
    assert payload["summary"]["ticket_count"] >= 25
    assert payload["summary"]["safe_local_count"] >= 15
    assert payload["summary"]["gated_live_count"] >= 1
    assert payload["summary"]["gated_action_count"] >= 3
    assert payload["summary"]["blocked_production_count"] >= 1
    assert payload["summary"]["runnable_now_count"] >= 2
    assert payload["summary"]["day_loop_cycle_count"] == 72
    assert payload["summary"]["planned_batch_count"] >= 6
    assert payload["summary"]["passed"] is True
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["credential_read_count"] == 0
    assert payload["score"]["network_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["boundary"]["dry_run_plan_only"] is True
    assert payload["boundary"]["executes_commands"] is False


def test_autonomous_day_loop_prioritizes_safe_batches_and_gates_live_work() -> None:
    payload = run_autonomous_day_loop_backlog_fixture(FIXTURE, completed={"P65"}).to_dict()
    first_batch = payload["execution_batches"][0]
    first_ids = {item["ticket_id"] for item in first_batch["tickets"]}
    gated = {item["ticket_id"]: item for item in payload["tickets"] if item["safety_class"] != "safe-local"}

    assert "P66" in first_ids
    assert "P68" in first_ids
    assert "P67" not in first_ids
    assert gated["P67"]["status"] == "gated"
    assert gated["P79"]["status"] == "blocked_by_dependencies"
    assert gated["P92"]["status"] == "blocked_by_dependencies"
    assert all(ticket["safety_class"] == "safe-local" for batch in payload["execution_batches"] for ticket in batch["tickets"])
    assert "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full" in payload["loop_contract"]["checkpoint_commands"]


def test_autonomous_day_loop_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p66.json"
    output_md = tmp_path / "p66.md"

    subprocess.run(
        [
            "python",
            "scripts/run_autonomous_day_loop_backlog.py",
            "--manifest",
            str(FIXTURE),
            "--completed",
            "P65",
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
    assert "# OpsCat Autonomous Day Loop Backlog" in markdown
    assert "First runnable batches" in markdown
    assert "Gated but retained work" in markdown
    assert render_autonomous_day_loop_backlog_markdown(payload).startswith("# OpsCat Autonomous Day Loop Backlog")
