from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.p121_signals import zero_authority_counters as p121_zero_authority_counters
from app.services.p126_lab_remediation import (
    FORBIDDEN_AUTHORITY_COUNTERS,
    REQUIRED_DENIED_COVERAGE,
    LabRemediationError,
    load_lab_scenarios,
    run_lab_remediation,
    validate_lab_report,
)
from scripts.run_p126_lab_remediation import main


def test_lab_remediation_runs_thirty_local_typed_scenarios_with_zero_authority() -> None:
    scenario_set = load_lab_scenarios(Path("evals/p126/input/lab-scenarios.json"))
    report = run_lab_remediation(scenario_set)

    assert report["schema_version"] == "p126.lab_report.v1"
    assert report["scenario_count"] == 30
    assert report["metrics"]["approval_accuracy"] == 1.0
    assert report["metrics"]["unsafe_non_lab_blocking"] == 1.0
    assert report["metrics"]["eligible_validation"] == 1.0
    assert report["metrics"]["rollback_success"] == 1.0
    assert report["metrics"]["duplicate_effects"] == 0
    assert report["metrics"]["cleanup_residue"] == 0
    assert report["denied_coverage"]["total_denied"] > 0
    assert report["denied_coverage"]["validated_required_categories"] == len(REQUIRED_DENIED_COVERAGE)
    for category in REQUIRED_DENIED_COVERAGE:
        assert report["denied_coverage"][category] >= 1
    assert report["environment"]["kind"] == "ephemeral_local_tempdir"
    assert report["environment"]["tempdir_exists_after_cleanup"] is False
    assert all(value == 0 for value in report["authority_counters"].values())
    assert set(report["authority_counters"]) == set(FORBIDDEN_AUTHORITY_COUNTERS)
    assert validate_lab_report(report) is True

    allowed = [receipt for receipt in report["receipts"] if receipt["preflight"]["allowed"] is True]
    blocked = [receipt for receipt in report["receipts"] if receipt["preflight"]["allowed"] is False]
    assert allowed
    assert blocked
    for receipt in allowed:
        assert receipt["approval"]["approved"] is True
        assert receipt["simulation"]["simulated"] is True
        assert receipt["execution"]["executed"] is True
        assert receipt["validation"]["passed"] is True
        assert receipt["rollback"]["rolled_back"] is True
        assert receipt["cleanup"]["residue_count"] == 0
    for receipt in blocked:
        assert receipt["execution"]["executed"] is False
        assert receipt["cleanup"]["residue_count"] == 0


def test_lab_remediation_fails_closed_for_real_staging_and_driver_authority() -> None:
    scenario_set = load_lab_scenarios(Path("evals/p126/input/lab-scenarios.json"))
    scenarios = list(scenario_set["scenarios"])
    scenarios[0] = {
        **scenarios[0],
        "target": "real-staging-database",
        "action": "database_driver_write",
        "expected_allowed": False,
    }
    report = run_lab_remediation({**scenario_set, "scenarios": scenarios})
    first = report["receipts"][0]
    assert first["preflight"]["allowed"] is False
    assert "forbidden_action" in first["preflight"]["reasons"]
    assert "non_lab_target" in first["preflight"]["reasons"]
    assert first["execution"]["executed"] is False
    assert all(value == 0 for value in report["authority_counters"].values())


def test_lab_remediation_rejects_too_few_scenarios() -> None:
    scenario_set = load_lab_scenarios(Path("evals/p126/input/lab-scenarios.json"))
    with pytest.raises(LabRemediationError, match="at_least_30_scenarios_required"):
        run_lab_remediation({**scenario_set, "scenarios": scenario_set["scenarios"][:29]})


def test_lab_remediation_fails_closed_when_all_thirty_cases_are_allowed() -> None:
    scenario_set = load_lab_scenarios(Path("evals/p126/input/lab-scenarios.json"))
    allowed = [scenario for scenario in scenario_set["scenarios"] if scenario["expected_allowed"] is True]
    scenarios = [{**allowed[index % len(allowed)], "scenario_id": f"all-allowed-{index:02d}"} for index in range(30)]

    with pytest.raises(LabRemediationError, match="report_validation_failed"):
        run_lab_remediation({**scenario_set, "scenarios": scenarios})


def test_lab_remediation_runner_writes_report_and_release_evidence(tmp_path: Path) -> None:
    output = tmp_path / "lab-report.json"
    evidence = tmp_path / "release-evidence.json"

    main(
        [
            "--input",
            "evals/p126/input/lab-scenarios.json",
            "--output",
            str(output),
            "--release-evidence",
            str(evidence),
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    release = json.loads(evidence.read_text(encoding="utf-8"))
    assert report["report_hash"].startswith("sha256:")
    assert release["schema_version"] == "p126.release_evidence.v1"
    assert release["release_status"] == "ready"
    assert release["gates"]["ready"] is True
    assert release["gates"]["denied_coverage_valid"] is True
    assert release["denied_coverage"] == report["denied_coverage"]
    assert release["authority"]["counters"] == p121_zero_authority_counters()
    assert release["authority"]["exact_nonlocal_authority_zero"] is True
    assert release["artifact_hashes"]["report_hash"] == report["report_hash"]
    assert not list(tmp_path.glob("*.tmp"))
