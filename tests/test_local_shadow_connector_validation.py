from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.local_shadow_connector_validation import (
    LocalShadowObservabilityConnector,
    LocalShadowConnectorValidationReport,
    build_local_shadow_connector_validation_report,
    render_local_shadow_connector_validation_markdown,
)

SOURCE = Path("evals/shadow/p61_local_shadow_source.json")


def test_local_shadow_connector_validation_reads_live_shaped_source_without_execution() -> None:
    connector = LocalShadowObservabilityConnector(SOURCE)
    assert not any(hasattr(connector, name) for name in ("restart", "rollback", "deploy", "write_config", "execute"))

    report = build_local_shadow_connector_validation_report(SOURCE)
    payload = report.to_dict()

    assert isinstance(report, LocalShadowConnectorValidationReport)
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["source_count"] == 3
    assert payload["summary"]["metric_signal_count"] >= 2
    assert payload["summary"]["log_signal_count"] >= 2
    assert payload["summary"]["error_signal_count"] >= 1
    assert payload["summary"]["deployment_signal_count"] >= 1
    assert payload["summary"]["empty_source_count"] == 1
    assert payload["summary"]["malformed_payload_count"] == 1
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["live_api_call_count"] == 0
    assert payload["summary"]["production_mutation_count"] == 0
    assert payload["readiness_link"]["local_operator_replacement_ready"] is True
    assert payload["readiness_link"]["unattended_production_ready"] is False
    assert payload["shadow_judgment"]["top_hypothesis"] == "recent_deploy_regression"
    assert payload["shadow_judgment"]["confidence"] >= 0.9
    assert payload["shadow_judgment"]["execution"] == "blocked_shadow_mode"
    assert payload["shadow_judgment"]["recommended_action"] == "prepare rollback PR draft"
    assert len(payload["evidence"]["supporting_evidence"]) >= 3
    assert len(payload["evidence"]["counter_evidence"]) >= 1
    assert len(payload["evidence"]["missing_evidence"]) >= 2
    assert all(gate["passed"] is True for gate in payload["validation_gates"])
    assert payload["boundary"]["local_shadow_connector_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_local_shadow_connector_validation_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p61.json"
    output_md = tmp_path / "p61.md"
    subprocess.run(
        [
            "python",
            "scripts/run_local_shadow_connector_validation.py",
            "--source",
            str(SOURCE),
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
    assert "# OpsCat Local Shadow Connector Validation" in markdown
    assert "Shadow judgment" in markdown
    assert "Validation gates" in markdown
    assert render_local_shadow_connector_validation_markdown(payload).startswith("# OpsCat Local Shadow Connector Validation")
