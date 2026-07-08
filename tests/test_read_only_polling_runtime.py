from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.read_only_polling_runtime import (
    PollingRuntime,
    PollingRuntimeReport,
    render_polling_runtime_markdown,
    run_polling_fixture,
)

JOB_DIR = Path("evals/polling/jobs")
READINESS_DIR = Path("evals/connectors/readiness")


def test_polling_runtime_polls_only_ready_sources_and_feeds_adapters() -> None:
    report = run_polling_fixture(JOB_DIR / "p28_polling_jobs.json", READINESS_DIR / "read_only_sources.json")
    payload = report.to_dict()

    assert isinstance(report, PollingRuntimeReport)
    assert payload["summary"]["job_count"] == 3
    assert payload["summary"]["polled_count"] == 2
    assert payload["summary"]["skipped_count"] == 1
    assert payload["summary"]["snapshot_count"] == 2
    assert payload["summary"]["trend_window_count"] >= 3
    assert payload["boundary"]["fixture_transport_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False
    assert payload["boundary"]["production_mutation_enabled"] is False
    assert any(item["source"] == "datadog" and item["status"] == "skipped" for item in payload["polls"])


def test_polling_runtime_blocks_mutating_or_unready_jobs() -> None:
    report = run_polling_fixture(JOB_DIR / "p28_unsafe_jobs.json", READINESS_DIR / "unsafe_sources.json")
    payload = report.to_dict()

    assert payload["summary"]["polled_count"] == 0
    assert payload["summary"]["blocked_count"] >= 2
    assert payload["score"]["mutation_schedule_count"] == 0
    assert all(item["status"] in {"blocked", "skipped"} for item in payload["polls"])
    assert any("readiness_blocked" in item["reasons"] for item in payload["polls"])


def test_polling_runtime_handles_transport_failures_without_tight_loop() -> None:
    runtime = PollingRuntime()
    report = runtime.run_fixture(JOB_DIR / "p28_failure_jobs.json", READINESS_DIR / "degraded_sources.json", ticks=2)
    payload = report.to_dict()

    assert payload["summary"]["failed_count"] >= 1
    assert payload["summary"]["dropped_batch_count"] >= 1
    assert payload["score"]["tight_loop_risk_count"] == 0
    assert any(item["next_safe_retry_seconds"] >= 120 for item in payload["polls"] if item["status"] in {"failed", "skipped"})
    assert "Bearer secret-token" not in json.dumps(payload)


def test_polling_runtime_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "polling.json"
    output_md = tmp_path / "polling.md"

    subprocess.run(
        [
            "python",
            "scripts/run_read_only_polling.py",
            "--jobs",
            str(JOB_DIR / "p28_polling_jobs.json"),
            "--readiness",
            str(READINESS_DIR / "read_only_sources.json"),
            "--ticks",
            "1",
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
    assert payload["summary"]["polled_count"] == 2
    assert "# OpsCat Read-only Polling Runtime Report" in markdown
    assert "fixture/local transport only" in markdown
    assert render_polling_runtime_markdown(payload).startswith("# OpsCat Read-only Polling Runtime Report")
