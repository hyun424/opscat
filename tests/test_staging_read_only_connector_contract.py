from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.staging_read_only_connector_contract import (
    StagingReadOnlyConnectorContractReport,
    render_staging_read_only_connector_contract_markdown,
    run_staging_read_only_connector_contract_fixture,
)

FIXTURE = Path("evals/staging/p62_staging_connector_contract.json")


def test_staging_read_only_contract_scores_provider_shapes_without_live_calls() -> None:
    report = run_staging_read_only_connector_contract_fixture(FIXTURE)
    payload = report.to_dict()

    assert isinstance(report, StagingReadOnlyConnectorContractReport)
    assert payload["summary"]["connector_count"] == 4
    assert payload["summary"]["ready_count"] == 3
    assert payload["summary"]["blocked_count"] == 1
    assert payload["summary"]["provider_count"] == 3
    assert payload["summary"]["schema_compatible_count"] == 3
    assert payload["summary"]["passed"] is True
    assert payload["score"]["provider_coverage_rate"] == 1.0
    assert payload["score"]["read_only_safety_rate"] >= 0.75
    assert payload["score"]["staging_environment_rate"] == 0.75
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["score"]["production_mutation_count"] == 0
    assert payload["score"]["action_execution_count"] == 0
    assert payload["boundary"]["staging_contract_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False
    assert payload["boundary"]["production_mutation_enabled"] is False


def test_staging_read_only_contract_blocks_production_admin_and_redacts_secrets() -> None:
    payload = run_staging_read_only_connector_contract_fixture(FIXTURE).to_dict()
    by_id = {item["connector_id"]: item for item in payload["connectors"]}
    serialized = json.dumps(payload)

    blocked = by_id["p62-prod-admin-blocked"]
    assert blocked["status"] == "blocked"
    assert "production_environment" in blocked["reasons"]
    assert "write_or_admin_scope" in blocked["reasons"]
    assert "mutation_operation" in blocked["reasons"]
    assert "raw_endpoint_url" in blocked["reasons"]
    assert "actual-secret-value" not in serialized
    assert "env:GRAFANA_STAGING_READ_TOKEN" in serialized


def test_staging_read_only_contract_provider_specific_schema_requirements() -> None:
    payload = run_staging_read_only_connector_contract_fixture(FIXTURE).to_dict()
    by_id = {item["connector_id"]: item for item in payload["connectors"]}

    assert by_id["p62-grafana-staging"]["schema"]["required_fields"] == ["series"]
    assert by_id["p62-sentry-staging"]["schema"]["required_fields"] == ["events"]
    assert by_id["p62-datadog-staging"]["schema"]["required_fields"] == ["monitors", "logs"]
    assert all(by_id[item]["schema"]["compatible"] is True for item in ("p62-grafana-staging", "p62-sentry-staging", "p62-datadog-staging"))
    assert payload["operator_handoff"]["next_step"] == "attach staging read-only credentials behind manual approval"


def test_staging_read_only_contract_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p62.json"
    output_md = tmp_path / "p62.md"

    subprocess.run(
        [
            "python",
            "scripts/run_staging_read_only_connector_contract.py",
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
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Staging Read-only Connector Contract" in markdown
    assert "Provider coverage" in markdown
    assert "Blocked connectors" in markdown
    assert render_staging_read_only_connector_contract_markdown(payload).startswith("# OpsCat Staging Read-only Connector Contract")
