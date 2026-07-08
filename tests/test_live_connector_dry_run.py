from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.live_connector_dry_run import (
    LiveConnectorDryRunReport,
    render_live_connector_dry_run_markdown,
    run_live_connector_dry_run_fixture,
)

MANIFEST = Path("evals/connectors/dry_run/p33_connectors.json")


def test_live_connector_dry_run_audits_permissions_schema_and_transport() -> None:
    report = run_live_connector_dry_run_fixture(MANIFEST)
    payload = report.to_dict()

    assert isinstance(report, LiveConnectorDryRunReport)
    assert payload["summary"]["connector_count"] >= 4
    assert payload["summary"]["ready_count"] >= 2
    assert payload["summary"]["blocked_count"] >= 1
    assert payload["summary"]["schema_drift_count"] >= 1
    assert payload["score"]["connector_health_score"] >= 0.75
    assert payload["score"]["permission_safety_rate"] >= 0.75
    assert payload["score"]["schema_compatibility_rate"] >= 0.75
    assert payload["score"]["live_api_call_count"] == 0
    assert payload["boundary"]["dry_run_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False
    assert payload["boundary"]["production_mutation_enabled"] is False


def test_live_connector_dry_run_blocks_write_admin_and_redacts_secret_refs() -> None:
    payload = run_live_connector_dry_run_fixture(MANIFEST).to_dict()
    by_id = {item["connector_id"]: item for item in payload["connectors"]}
    serialized = json.dumps(payload)

    assert by_id["p33-unsafe-admin-token"]["status"] == "blocked"
    assert "write_or_admin_scope" in by_id["p33-unsafe-admin-token"]["reasons"]
    assert "actual-secret-value" not in serialized
    assert "env:DATADOG_READ_TOKEN" in serialized


def test_live_connector_dry_run_cli_writes_operator_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p33.json"
    output_md = tmp_path / "p33.md"

    subprocess.run(
        [
            "python",
            "scripts/run_live_connector_dry_run.py",
            "--manifest",
            str(MANIFEST),
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
    assert payload["score"]["connector_health_score"] >= 0.75
    assert "# OpsCat Live Connector Dry-run Report" in markdown
    assert "Ready connectors" in markdown
    assert "Blocked connectors" in markdown
    assert render_live_connector_dry_run_markdown(payload).startswith("# OpsCat Live Connector Dry-run Report")
