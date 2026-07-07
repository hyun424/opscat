"""Connector failure eval evidence for P4 release gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.run_connector_evals import run_connector_evals

REQUIRED_SCENARIOS = {
    "fake_read_success",
    "missing_credential_failed_closed",
    "provider_timeout_escalates",
    "malformed_result_escalates",
    "read_only_contract_violation_escalates",
    "idempotency_replay_no_duplicate_escalation",
    "idempotency_conflict_fails_closed",
    "connector_catalog_permission_metadata",
    "permission_mismatch_fails_closed",
    "secret_lifecycle_setup_failure",
    "fixture_import_normalization",
    "sentry_fixture_health_and_pagination",
    "sentry_provider_rate_limit_normalization",
}


def test_connector_eval_runner_reports_required_failure_classes(tmp_path: Path) -> None:
    json_path = tmp_path / "connector-evals.json"
    md_path = tmp_path / "connector-evals.md"

    summary = run_connector_evals(output_json=json_path, output_md=md_path)

    assert summary["failed"] == 0
    assert summary["total"] >= len(REQUIRED_SCENARIOS)
    results = {result["scenario"]: result for result in summary["results"]}
    assert REQUIRED_SCENARIOS.issubset(results)
    assert results["missing_credential_failed_closed"]["actual"]["failure_class"] == "connector_failure"
    assert results["provider_timeout_escalates"]["actual"]["failure_class"] == "connector_timeout"
    assert results["read_only_contract_violation_escalates"]["actual"]["failure_class"] == "connector_contract_violation"
    assert results["idempotency_replay_no_duplicate_escalation"]["actual"]["failure_evidence_count"] == 1
    assert results["idempotency_replay_no_duplicate_escalation"]["actual"]["human_escalation_count"] == 1
    assert results["idempotency_conflict_fails_closed"]["actual"]["audit_types"] == [
        "connector_call_requested",
        "connector_call_completed",
        "connector_idempotency_conflict",
    ]
    assert results["connector_catalog_permission_metadata"]["category"] == "setup_permission"
    assert results["connector_catalog_permission_metadata"]["actual"]["capabilities_with_metadata"] >= 4
    assert results["permission_mismatch_fails_closed"]["actual"]["failure_class"] == "permission_mismatch"
    assert results["secret_lifecycle_setup_failure"]["actual"]["failure_class"] == "setup_failure"
    assert results["fixture_import_normalization"]["actual"]["failure_class"] == "import_normalization"
    assert results["fixture_import_normalization"]["actual"]["incident_status"] in {"waiting_approval", "resolved", "action_proposed"}
    assert results["sentry_fixture_health_and_pagination"]["category"] == "sentry_setup_health"
    assert results["sentry_fixture_health_and_pagination"]["actual"]["health_state"] == "fixture_ok"
    assert results["sentry_provider_rate_limit_normalization"]["category"] == "sentry_fetch_failure"
    assert results["sentry_provider_rate_limit_normalization"]["actual"]["normalized_error"] == "rate_limited"

    payload: dict[str, Any] = json.loads(json_path.read_text())
    assert payload["summary"] == {"total": summary["total"], "passed": summary["passed"], "failed": 0}
    markdown = md_path.read_text()
    assert "# OpsCat Connector Eval Report" in markdown
    assert "connector_timeout" in markdown
    assert "connector_contract_violation" in markdown
    assert "idempotency" in markdown
    assert "setup_permission" in markdown
    assert "permission_mismatch" in markdown
    assert "setup_failure" in markdown
    assert "import_normalization" in markdown
    assert "sentry_setup_health" in markdown
    assert "sentry_fetch_failure" in markdown


def test_verify_script_includes_connector_eval_release_gate() -> None:
    verify = Path("scripts/verify.sh").read_text()

    assert "Connector eval runner" in verify
    assert "scripts/run_connector_evals.py" in verify
