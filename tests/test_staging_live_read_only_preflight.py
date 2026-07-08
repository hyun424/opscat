from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.staging_live_read_only_preflight import (
    MockStagingReadOnlyTransport,
    StagingLiveReadOnlyPreflightReport,
    render_staging_live_read_only_preflight_markdown,
    run_staging_live_read_only_preflight_fixture,
)

FIXTURE = Path("evals/staging/p63_staging_live_preflight.json")


def test_staging_live_preflight_default_mode_makes_zero_live_calls() -> None:
    report = run_staging_live_read_only_preflight_fixture(FIXTURE)
    payload = report.to_dict()

    assert isinstance(report, StagingLiveReadOnlyPreflightReport)
    assert payload["summary"]["check_count"] == 4
    assert payload["summary"]["eligible_check_count"] == 3
    assert payload["summary"]["blocked_check_count"] == 1
    assert payload["summary"]["attempted_check_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["score"]["non_get_check_count"] == 1
    assert payload["boundary"]["live_staging_enabled"] is False
    assert payload["boundary"]["default_no_live_mode"] is True
    assert payload["operator_handoff"]["next_step"] == "rerun with explicit live staging flag after manual approval and read-only credentials"


def test_staging_live_preflight_mock_live_mode_only_gets_allowlisted_ready_connectors() -> None:
    transport = MockStagingReadOnlyTransport()
    report = run_staging_live_read_only_preflight_fixture(FIXTURE, live_staging=True, manual_approval=True, transport=transport)
    payload = report.to_dict()
    by_id = {item["check_id"]: item for item in payload["checks"]}

    assert payload["summary"]["attempted_check_count"] == 3
    assert payload["summary"]["successful_check_count"] == 3
    assert payload["summary"]["blocked_check_count"] == 1
    assert payload["score"]["live_api_call_count"] == 3
    assert payload["score"]["mock_transport_call_count"] == 3
    assert payload["boundary"]["real_network_required_for_tests"] is False
    assert all(call["method"] == "GET" for call in transport.calls)
    assert all(call["host"] in {"grafana.staging.internal", "sentry.staging.internal", "datadog.staging.internal"} for call in transport.calls)
    assert by_id["p63-prod-admin-post-blocked"]["status"] == "blocked"
    assert "p62_connector_not_ready" in by_id["p63-prod-admin-post-blocked"]["reasons"]
    assert "non_get_method" in by_id["p63-prod-admin-post-blocked"]["reasons"]
    assert "host_not_allowlisted" in by_id["p63-prod-admin-post-blocked"]["reasons"]


def test_staging_live_preflight_blocks_live_without_manual_approval() -> None:
    transport = MockStagingReadOnlyTransport()
    payload = run_staging_live_read_only_preflight_fixture(FIXTURE, live_staging=True, manual_approval=False, transport=transport).to_dict()

    assert payload["summary"]["attempted_check_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["manual_approval_missing_count"] == 3
    assert all(check["status"] != "attempted" for check in payload["checks"])
    assert transport.calls == []


def test_staging_live_preflight_redacts_auth_and_cli_writes_default_no_live_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p63.json"
    output_md = tmp_path / "p63.md"

    subprocess.run(
        [
            "python",
            "scripts/run_staging_live_read_only_preflight.py",
            "--manifest",
            str(FIXTURE),
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
    serialized = json.dumps(payload)
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["attempted_check_count"] == 0
    assert "actual-secret-value" not in serialized
    assert "Authorization" not in serialized
    assert "# OpsCat Staging Live Read-only Preflight" in markdown
    assert "Default no-live mode" in markdown
    assert render_staging_live_read_only_preflight_markdown(payload).startswith("# OpsCat Staging Live Read-only Preflight")
