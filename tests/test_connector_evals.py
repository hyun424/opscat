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

    payload: dict[str, Any] = json.loads(json_path.read_text())
    assert payload["summary"] == {"total": summary["total"], "passed": summary["passed"], "failed": 0}
    markdown = md_path.read_text()
    assert "# OpsCat Connector Eval Report" in markdown
    assert "connector_timeout" in markdown
    assert "connector_contract_violation" in markdown
    assert "idempotency" in markdown


def test_verify_script_includes_connector_eval_release_gate() -> None:
    verify = Path("scripts/verify.sh").read_text()

    assert "Connector eval runner" in verify
    assert "scripts/run_connector_evals.py" in verify
