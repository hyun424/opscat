from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.p127_chaos_validation import (
    P127_ALLOWED_SCOPES,
    P127_AUTHORITY_COUNTERS,
    P127_FAULT_CLASSES,
    build_p127_release_evidence,
    load_p127_chaos_scenarios,
    run_p127_chaos_validation,
    write_p127_outputs,
)

SCENARIOS = Path("evals/p127/input/chaos-scenarios.json")


def test_p127_fixture_has_40_deterministic_cases_across_documented_fault_classes() -> None:
    scenarios = load_p127_chaos_scenarios(SCENARIOS)

    assert len(scenarios) >= 40
    assert {scenario.fault_class for scenario in scenarios} == set(P127_FAULT_CLASSES)
    assert all(scenario.scope in P127_ALLOWED_SCOPES for scenario in scenarios)
    assert len({scenario.case_id for scenario in scenarios}) == len(scenarios)


def test_p127_chaos_validation_fails_closed_with_zero_authority_and_no_loss_or_duplicates() -> None:
    report = run_p127_chaos_validation(SCENARIOS)

    assert report["schema_version"] == "p127.chaos_report.v1"
    assert report["summary"]["case_count"] >= 40
    assert report["summary"]["passed"] is True
    assert report["summary"]["deterministic_replay_rate"] == 1.0
    assert report["summary"]["visible_fail_closed_reason_rate"] == 1.0
    assert report["summary"]["max_retry_attempts"] <= 3
    assert report["containment"] == {
        "fail_open_count": 0,
        "authority_escape_count": 0,
        "duplicate_effect_count": 0,
        "lost_record_count": 0,
        "claim_promotion_after_failure_count": 0,
    }
    assert report["authority_counters"] == {counter: 0 for counter in P127_AUTHORITY_COUNTERS}
    assert all(receipt["decision"] == "fail_closed" for receipt in report["receipts"])
    assert all(receipt["receipt_hash"].startswith("sha256:") for receipt in report["receipts"])


def test_p127_receipts_are_replayable_and_tamper_evident() -> None:
    first = run_p127_chaos_validation(SCENARIOS)
    second = run_p127_chaos_validation(SCENARIOS)

    assert first["report_hash"] == second["report_hash"]
    assert [receipt["receipt_hash"] for receipt in first["receipts"]] == [receipt["receipt_hash"] for receipt in second["receipts"]]

    tampered = json.loads(json.dumps(first["receipts"][0]))
    tampered["operator_reason"] = ""
    report = json.loads(json.dumps(first))
    report["receipts"][0] = tampered
    evidence = build_p127_release_evidence(report)
    assert evidence["gates"]["visible_fail_closed_reasons"] is False


def test_p127_rejects_authority_expanding_or_retry_storm_scenarios(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(
        json.dumps(
            {
                "schema_version": "p127.chaos_scenarios.v1",
                "scenarios": [
                    {
                        "schema_version": "p127.chaos_scenario.v1",
                        "case_id": "production_chaos_target",
                        "fault_class": "authority_drift",
                        "scope": "production",
                        "evidence_ids": ["ev-prod"],
                        "blocked_action": "restart production database",
                        "expected_reason": "production target rejected",
                        "retry_budget": 10,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="forbidden_scope"):
        run_p127_chaos_validation(bad_path)


def test_p127_runner_writes_report_and_release_evidence(tmp_path: Path) -> None:
    report_path = tmp_path / "chaos-report.json"
    evidence_path = tmp_path / "release-evidence.json"

    report = run_p127_chaos_validation(SCENARIOS)
    evidence = write_p127_outputs(report, output_json=report_path, release_evidence_json=evidence_path)

    assert report_path.is_file()
    assert evidence_path.is_file()
    assert evidence["schema_version"] == "p127.release_evidence.v1"
    assert evidence["gates"]["release_ready"] is True

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_p127_chaos_validation.py",
            "--input",
            str(SCENARIOS),
            "--output-json",
            str(report_path),
            "--release-evidence-json",
            str(evidence_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "OpsCat P127 chaos validation" in completed.stdout
