from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.read_only_polling_v2 import (
    ReadOnlyPollingV2Report,
    render_read_only_polling_v2_markdown,
    run_read_only_polling_v2_fixture,
)

JOBS = Path("evals/polling/v2/p34_polling_jobs.json")
DRY_RUN = Path("evals/connectors/dry_run/p33_connectors.json")


def test_polling_v2_uses_dry_run_readiness_gate_and_emits_trends() -> None:
    report = run_read_only_polling_v2_fixture(JOBS, DRY_RUN)
    payload = report.to_dict()

    assert isinstance(report, ReadOnlyPollingV2Report)
    assert payload["summary"]["job_count"] >= 5
    assert payload["summary"]["polled_count"] >= 2
    assert payload["summary"]["skipped_count"] >= 2
    assert payload["summary"]["blocked_count"] >= 1
    assert payload["summary"]["snapshot_count"] >= 2
    assert payload["summary"]["trend_window_count"] >= 4
    assert payload["score"]["poll_success_rate"] == 1.0
    assert payload["score"]["readiness_gate_rate"] == 1.0
    assert payload["score"]["unsafe_poll_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["boundary"]["read_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False


def test_polling_v2_skips_degraded_blocked_and_blocks_write_jobs() -> None:
    payload = run_read_only_polling_v2_fixture(JOBS, DRY_RUN).to_dict()
    by_id = {item["job_id"]: item for item in payload["jobs"]}
    serialized = json.dumps(payload)

    assert by_id["poll-sentry-degraded"]["status"] == "skipped"
    assert "connector_not_ready" in by_id["poll-sentry-degraded"]["reasons"]
    assert by_id["poll-admin-blocked"]["status"] == "skipped"
    assert by_id["poll-write-mutation"]["status"] == "blocked"
    assert "write_or_mutation_job" in by_id["poll-write-mutation"]["reasons"]
    assert "actual-secret-value" not in serialized


def test_polling_v2_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p34.json"
    output_md = tmp_path / "p34.md"

    subprocess.run(
        [
            "python",
            "scripts/run_read_only_polling_v2.py",
            "--jobs",
            str(JOBS),
            "--dry-run-manifest",
            str(DRY_RUN),
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
    assert payload["score"]["poll_success_rate"] == 1.0
    assert "# OpsCat Read-only Polling Runtime v2 Report" in markdown
    assert "Readiness gate" in markdown
    assert render_read_only_polling_v2_markdown(payload).startswith("# OpsCat Read-only Polling Runtime v2 Report")
