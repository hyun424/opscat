from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.recovery_proof_engine import (
    RecoveryProofEngineReport,
    build_recovery_proof_engine_report,
    render_recovery_proof_engine_markdown,
)

CASES = Path("evals/investigator/p49_remediation_verification_cases.json")


def test_recovery_proof_engine_builds_proof_bundles_from_p49_cases() -> None:
    report = build_recovery_proof_engine_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, RecoveryProofEngineReport)
    assert payload["summary"]["case_count"] == 2
    assert payload["summary"]["recovery_proven_count"] == 1
    assert payload["summary"]["recovery_not_proven_count"] == 1
    assert payload["summary"]["escalation_required_count"] == 1
    assert payload["summary"]["production_execution_count"] == 0
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["score"]["mean_proof_score"] >= 0.6
    assert payload["score"]["criteria_checked_count"] == 4
    assert payload["boundary"]["production_mutation_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_recovery_proof_engine_preserves_case_level_proof_rationale() -> None:
    payload = build_recovery_proof_engine_report(CASES).to_dict()
    cases = {row["case_id"]: row for row in payload["cases"]}

    recovered = cases["p49-db-pool-recovered"]
    failed = cases["p49-provider-retry-not-recovered"]

    assert recovered["proof_status"] == "recovery_proven"
    assert recovered["proof_score"] >= 0.85
    assert recovered["proof_bundle"]["criteria_passed_count"] == 2
    assert recovered["proof_bundle"]["failed_criteria"] == []
    assert recovered["operator_next_step"] == "continue read-only monitoring"

    assert failed["proof_status"] == "recovery_not_proven"
    assert failed["proof_bundle"]["criteria_failed_count"] == 2
    assert failed["operator_next_step"] == "escalate to incident commander"
    assert "provider_timeout_rate_below_2_percent" in failed["proof_bundle"]["failed_criteria"]
    assert "checkout_error_rate_below_1_percent" in failed["proof_bundle"]["failed_criteria"]


def test_recovery_proof_engine_blocks_unsafe_execution_boundary() -> None:
    unsafe_case = {
        "case_id": "unsafe-recovered",
        "hypothesis": "unsafe rollback",
        "verification_status": "recovered",
        "precheck": {"passed": True},
        "execution_boundary": {
            "production_execution_allowed": True,
            "unsafe_action_allowed": True,
        },
        "postcheck": {
            "criteria": ["5xx_rate_below_1_percent"],
            "observed": {"five_xx_rate": 0.001},
            "status": "recovered",
        },
        "rollback_or_escalation": {"route": "monitor"},
    }

    payload = RecoveryProofEngineReport.from_verification_cases([unsafe_case]).to_dict()

    assert payload["summary"]["passed"] is False
    assert payload["summary"]["blocked_unsafe_execution_count"] == 1
    assert payload["cases"][0]["proof_status"] == "blocked_unsafe_execution"
    assert "unsafe execution boundary" in payload["cases"][0]["reasons"]


def test_recovery_proof_engine_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p77.json"
    output_md = tmp_path / "p77.md"

    subprocess.run(
        [
            "python",
            "scripts/run_recovery_proof_engine.py",
            "--cases",
            str(CASES),
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
    assert "# OpsCat Recovery Proof Engine" in markdown
    assert "Proof bundles" in markdown
    assert render_recovery_proof_engine_markdown(payload).startswith("# OpsCat Recovery Proof Engine")
