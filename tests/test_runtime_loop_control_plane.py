from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.judgment_dataset import load_judgment_cases
from app.services.runtime_loop_control import (
    ApprovalMode,
    ApprovalProfile,
    RuntimeLoopRunner,
    RuntimeQueueItem,
    render_runtime_markdown,
)


def test_runtime_queue_processes_one_incident_per_tick_and_records_closed_loop_result() -> None:
    cases = load_judgment_cases("evals/judgment/seed/cases.json")[:2]
    runner = RuntimeLoopRunner(approval_profile=ApprovalProfile.for_mode(ApprovalMode.AUTO_READONLY))
    for case in cases:
        runner.enqueue_case(case)

    first = runner.process_tick()
    snapshot = runner.snapshot()

    assert first is not None
    assert first.status in {"approval_waiting", "completed"}
    assert snapshot["queue_depth"] == 1
    assert snapshot["processed_count"] == 1
    assert snapshot["items"][0]["case_id"] == cases[0].id
    assert snapshot["items"][0]["closed_loop"]["trace"]
    assert snapshot["boundary"]["action_execution_enabled"] is False


def test_approval_profiles_deny_mutating_tools_in_every_mode() -> None:
    for mode in ApprovalMode:
        profile = ApprovalProfile.for_mode(mode)
        assert profile.allows_capability("read_only_evidence") is (mode in {ApprovalMode.AUTO_READONLY, ApprovalMode.AUTO_SAFE_MOCK})
        assert profile.denies_tool("kubectl rollout restart production") is True
        assert profile.denies_tool("mock.execute_restart_worker") is True
        assert profile.denies_tool("shell.execute") is True

    assert ApprovalProfile.for_mode(ApprovalMode.AUTO_SAFE_MOCK).allows_capability("safe_mock_artifact") is True
    assert ApprovalProfile.for_mode(ApprovalMode.LOCKED).allows_capability("safe_mock_artifact") is False


def test_runtime_pause_resume_and_abort_controls() -> None:
    case = load_judgment_cases("evals/judgment/seed/cases.json")[0]
    runner = RuntimeLoopRunner()
    runner.enqueue_case(case)

    runner.pause("operator reviewing")
    assert runner.process_tick() is None
    assert runner.snapshot()["status"] == "paused"

    runner.resume()
    assert runner.snapshot()["status"] == "running"
    runner.abort_next("test abort")
    snapshot = runner.snapshot()

    assert snapshot["queue_depth"] == 0
    assert snapshot["items"][0]["status"] == "aborted"
    assert "test abort" in snapshot["items"][0]["status_reason"]


def test_runtime_markdown_report_exposes_queue_and_approval_state() -> None:
    case = load_judgment_cases("evals/judgment/seed/cases.json")[0]
    runner = RuntimeLoopRunner(approval_profile=ApprovalProfile.for_mode(ApprovalMode.MANUAL))
    runner.enqueue_case(case)
    runner.process_tick()

    markdown = render_runtime_markdown(runner.snapshot())

    assert "# OpsCat Runtime Loop Runner" in markdown
    assert "Approval mode" in markdown
    assert "Queue depth" in markdown
    assert "no remediation execution" in markdown


def test_runtime_cli_runs_bounded_ticks_and_writes_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "runtime.json"
    output_md = tmp_path / "runtime.md"

    subprocess.run(
        [
            "python",
            "scripts/run_runtime_loop.py",
            "--cases",
            "evals/judgment/seed/cases.json",
            "--max-cases",
            "2",
            "--max-ticks",
            "2",
            "--approval-mode",
            "auto_readonly",
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
    assert payload["processed_count"] == 2
    assert payload["queue_depth"] == 0
    assert payload["approval_profile"]["mode"] == "auto_readonly"
    assert payload["boundary"]["action_execution_enabled"] is False
    assert "# OpsCat Runtime Loop Runner" in markdown


def test_runtime_queue_item_serializes_without_closed_loop_result() -> None:
    item = RuntimeQueueItem.from_case(load_judgment_cases("evals/judgment/seed/cases.json")[0])

    payload = item.to_dict()

    assert payload["status"] == "queued"
    assert payload["attempts"] == 0
    assert payload["closed_loop"] is None
