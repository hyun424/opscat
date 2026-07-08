from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.audited_staging_transport_gate import (
    AuditedStagingTransportGateReport,
    MockAuditedStagingTransport,
    render_audited_staging_transport_gate_markdown,
    run_audited_staging_transport_gate_fixture,
)

FIXTURE = Path("evals/staging/p64_audited_credential_transport_gate.json")


def test_audited_staging_transport_gate_default_dry_run_records_audit_without_calls() -> None:
    report = run_audited_staging_transport_gate_fixture(FIXTURE)
    payload = report.to_dict()

    assert isinstance(report, AuditedStagingTransportGateReport)
    assert payload["summary"]["request_count"] == 4
    assert payload["summary"]["approved_request_count"] == 3
    assert payload["summary"]["blocked_request_count"] == 1
    assert payload["summary"]["attempted_request_count"] == 0
    assert payload["summary"]["audit_entry_count"] == 4
    assert payload["summary"]["passed"] is True
    assert payload["score"]["transport_call_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["raw_secret_block_count"] == 1
    assert payload["score"]["missing_approval_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["boundary"]["default_dry_run"] is True
    assert payload["boundary"]["real_network_required_for_tests"] is False


def test_audited_staging_transport_gate_mock_live_attempts_only_approved_gets() -> None:
    transport = MockAuditedStagingTransport()
    report = run_audited_staging_transport_gate_fixture(FIXTURE, live_staging=True, manual_approval=True, transport=transport)
    payload = report.to_dict()
    by_id = {item["request_id"]: item for item in payload["requests"]}

    assert payload["summary"]["attempted_request_count"] == 3
    assert payload["summary"]["successful_request_count"] == 3
    assert payload["summary"]["blocked_request_count"] == 1
    assert payload["score"]["transport_call_count"] == 3
    assert payload["score"]["live_api_call_count"] == 3
    assert all(call["method"] == "GET" for call in transport.calls)
    assert all(call["authorization_present"] is True for call in transport.calls)
    assert all(call["host"] in {"grafana.staging.internal", "sentry.staging.internal", "datadog.staging.internal"} for call in transport.calls)
    assert by_id["p64-prod-admin-raw-token-blocked"]["status"] == "blocked"
    assert "p63_preflight_not_eligible" in by_id["p64-prod-admin-raw-token-blocked"]["reasons"]
    assert "raw_credential_value" in by_id["p64-prod-admin-raw-token-blocked"]["reasons"]
    assert "non_get_method" in by_id["p64-prod-admin-raw-token-blocked"]["reasons"]
    assert "host_not_allowlisted" in by_id["p64-prod-admin-raw-token-blocked"]["reasons"]


def test_audited_staging_transport_gate_blocks_without_manual_approval() -> None:
    transport = MockAuditedStagingTransport()
    payload = run_audited_staging_transport_gate_fixture(FIXTURE, live_staging=True, manual_approval=False, transport=transport).to_dict()

    assert payload["summary"]["attempted_request_count"] == 0
    assert payload["score"]["transport_call_count"] == 0
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["missing_approval_count"] == 3
    assert transport.calls == []


def test_audited_staging_transport_gate_redacts_credentials_and_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p64.json"
    output_md = tmp_path / "p64.md"

    subprocess.run(
        [
            "python",
            "scripts/run_audited_staging_transport_gate.py",
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
    assert payload["summary"]["attempted_request_count"] == 0
    for forbidden in ["mock-grafana-read-token", "mock-sentry-read-token", "mock-datadog-read-token", "actual-secret-value", "Authorization", "Bearer"]:
        assert forbidden not in serialized
        assert forbidden not in markdown
    assert "credential_ref_fingerprint" in serialized
    assert "# OpsCat Audited Staging Credential + Transport Gate" in markdown
    assert "Audit ledger" in markdown
    assert render_audited_staging_transport_gate_markdown(payload).startswith("# OpsCat Audited Staging Credential + Transport Gate")
