from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.connector_readiness import (
    ConnectorReadinessEvaluator,
    ConnectorReadinessReport,
    evaluate_connector_readiness_fixture,
    render_connector_readiness_markdown,
)

FIXTURE_DIR = Path("evals/connectors/readiness")


def test_read_only_manifest_is_ready_and_redacts_credentials() -> None:
    report = evaluate_connector_readiness_fixture(FIXTURE_DIR / "read_only_sources.json")
    payload = report.to_dict()

    assert isinstance(report, ConnectorReadinessReport)
    assert payload["summary"]["source_count"] == 3
    assert payload["summary"]["ready_count"] == 2
    assert payload["summary"]["degraded_count"] == 1
    assert payload["summary"]["blocked_count"] == 0
    assert payload["boundary"]["live_writes_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False
    serialized = json.dumps(payload)
    assert "Bearer secret-token" not in serialized
    assert "nvapi-" not in serialized
    assert "PROMETHEUS_TOKEN_REF" in serialized


def test_mutating_manifest_is_blocked_even_if_connector_declares_it() -> None:
    report = evaluate_connector_readiness_fixture(FIXTURE_DIR / "unsafe_sources.json")
    payload = report.to_dict()

    assert payload["summary"]["blocked_count"] >= 2
    blocked = [source for source in payload["sources"] if source["state"] == "blocked"]
    assert any("write" in reason or "mutation" in reason for source in blocked for reason in source["reasons"])
    assert all("delete" in source["denied_capabilities"] or "shell_execute" in source["denied_capabilities"] for source in blocked)
    assert payload["score"]["mutation_capability_count"] >= 2


def test_backoff_policy_is_bounded_and_distinguishes_degraded_reasons() -> None:
    evaluator = ConnectorReadinessEvaluator()
    report = evaluator.evaluate_path(FIXTURE_DIR / "degraded_sources.json")
    payload = report.to_dict()

    states = {source["source"]: source for source in payload["sources"]}
    assert states["datadog"]["state"] == "degraded"
    assert "rate_limit" in states["datadog"]["reasons"]
    assert states["datadog"]["next_safe_retry_seconds"] == 120
    assert states["sentry"]["state"] == "unavailable"
    assert "auth_failure" in states["sentry"]["reasons"]
    assert states["sentry"]["next_safe_retry_seconds"] == 300
    assert payload["score"]["tight_loop_risk_count"] == 0


def test_connector_readiness_cli_writes_secret_free_report(tmp_path: Path) -> None:
    output_json = tmp_path / "readiness.json"
    output_md = tmp_path / "readiness.md"

    subprocess.run(
        [
            "python",
            "scripts/run_connector_readiness.py",
            "--manifests",
            str(FIXTURE_DIR / "read_only_sources.json"),
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
    assert payload["summary"]["source_count"] == 3
    assert payload["summary"]["blocked_count"] == 0
    assert "# OpsCat Connector Readiness Report" in markdown
    assert "read-only connector readiness" in markdown
    assert "Bearer secret-token" not in markdown
    assert render_connector_readiness_markdown(payload).startswith("# OpsCat Connector Readiness Report")
