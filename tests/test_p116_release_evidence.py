from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.causal_remediation_benchmark import build_causal_scenario_catalog
from app.services.p110_evaluation import stable_hash
from app.services.p116_lab_runner import P116_LAB_BOUNDARY
from app.services.p116_paired_outcomes import hash_p116_source_results
from app.services.p116_release_evidence import (
    P116_RELEASE_EVIDENCE_SCHEMA_VERSION,
    produce_p116_release_evidence,
    run_p116_release_evidence,
    validate_p116_release_evidence,
)
from scripts.run_p116_lab_benchmark import main as cli_main
from scripts.validate_p116_release_evidence import main as validate_cli_main


def test_release_evidence_builds_contract_ready_report_from_synthetic_records() -> None:
    primary = _synthetic_run()
    replay = _synthetic_run()

    release = produce_p116_release_evidence(primary_run=primary, replay_run=replay)

    assert release["schema_version"] == P116_RELEASE_EVIDENCE_SCHEMA_VERSION
    assert release["contract_ready"] is True
    assert release["outcome_qualified"] is False
    assert release["acceptance_gates"]["experiments_at_least_500"] is False
    assert release["gates"]["exact_zero_production_authority"] is True
    assert release["gates"]["repeated_run_replay_match"] is True
    assert release["authority"]["exact_zero_production_authority"] is True
    assert release["safety_counters"]["reset_verification_failed_count"] == 0
    assert release["safety_counters"]["crash_count"] == 0
    assert release["safety_counters"]["idempotency_violation_count"] == 0
    assert release["scenario_seed_manifest"][0]["seed"] == 116
    assert release["record_hashes"] == release["replay_comparison"]["replay_record_hashes"]
    assert len(release["paired_outcome_records"]) == 1
    assert len(release["raw_observations"]) == 5
    assert release["raw_observations_hash"] == stable_hash(release["raw_observations"])
    assert release["per_family_arm_denominators"]["families"]["deploy_config"]["selected_action"]["denominator"] == 1
    assert release["natural_recovery_attribution"]["selected_qualified_without_natural_recovery"] == 1
    assert release["release_evidence_hash"] == stable_hash({key: value for key, value in release.items() if key != "release_evidence_hash"})


def test_release_evidence_qualifies_measured_natural_recovery_without_claiming_action_success() -> None:
    primary = _synthetic_run(natural_recovered=True)
    replay = _synthetic_run(natural_recovered=True)

    release = produce_p116_release_evidence(primary_run=primary, replay_run=replay)

    assert release["contract_ready"] is True
    assert release["outcome_qualified"] is False
    assert release["natural_recovery_attribution"]["natural_recovery_recovered_without_action"] == 1
    assert release["natural_recovery_attribution"]["selected_qualified"] == 0
    assert "experiments_at_least_500 failed closed" in release["reasons"]


def test_release_evidence_fails_contract_on_replay_drift_and_production_authority() -> None:
    primary = _synthetic_run()
    replay = _synthetic_run()
    replay["boundary"] = {**replay["boundary"], "production_mutation_enabled": True}
    replay["arm_results"][0]["post"] = {**replay["arm_results"][0]["post"], "utility": 0.1}

    release = produce_p116_release_evidence(primary_run=primary, replay_run=replay)

    assert release["contract_ready"] is False
    assert release["outcome_qualified"] is False
    assert release["gates"]["exact_zero_production_authority"] is False
    assert release["gates"]["repeated_run_replay_match"] is False
    assert release["safety_counters"]["idempotency_violation_count"] == 1
    assert release["authority"]["production_authority_counters"]["production_mutation_enabled"] == 1


def test_release_evidence_loopback_smoke_runs_one_case_twice() -> None:
    scenario = next(case for case in build_causal_scenario_catalog() if case.family == "deploy_config" and case.variant == "obvious")

    release = run_p116_release_evidence(scenario_ids=[scenario.case_id], seeds=[116], max_cases=1, sample_size=5)

    assert release["contract_ready"] is True
    assert release["gates"]["local_loopback_only"] is True
    assert len(release["scenario_seed_manifest"]) == 1
    assert release["scenario_seed_manifest"][0]["case_id"] == scenario.case_id


def test_cli_writes_json_atomically(tmp_path: Path) -> None:
    scenario = next(case for case in build_causal_scenario_catalog() if case.family == "deploy_config" and case.variant == "obvious")
    output = tmp_path / "nested" / "p116-release.json"

    assert cli_main(["--scenario-id", scenario.case_id, "--seed", "116", "--max-cases", "1", "--output", str(output)]) == 0

    release = json.loads(output.read_text(encoding="utf-8"))
    assert release["schema_version"] == P116_RELEASE_EVIDENCE_SCHEMA_VERSION
    assert release["contract_ready"] is True
    assert not list(output.parent.glob("*.tmp"))


def test_persisted_release_validation_fails_closed_on_stale_source_hash() -> None:
    release = produce_p116_release_evidence(primary_run=_synthetic_run(), replay_run=_synthetic_run())
    release["contract_ready"] = True
    release["outcome_qualified"] = True
    release["source_hashes"]["app/services/p116_lab_runner.py"] = "sha256:stale"
    release["release_evidence_hash"] = stable_hash(
        {key: value for key, value in release.items() if key != "release_evidence_hash"}
    )

    report = validate_p116_release_evidence(release)

    assert report["valid"] is False
    assert report["checks"]["self_hash_current"] is True
    assert report["checks"]["source_hashes_current"] is False


def test_validation_cli_rejects_stale_artifact(tmp_path: Path) -> None:
    release = produce_p116_release_evidence(primary_run=_synthetic_run(), replay_run=_synthetic_run())
    release["source_hashes"]["app/services/p116_release_evidence.py"] = "sha256:stale"
    release["release_evidence_hash"] = stable_hash(
        {key: value for key, value in release.items() if key != "release_evidence_hash"}
    )
    artifact = tmp_path / "release.json"
    artifact.write_text(json.dumps(release), encoding="utf-8")

    assert validate_cli_main([str(artifact)]) == 1


def _synthetic_run(*, natural_recovered: bool = False) -> dict[str, Any]:
    scenario = next(case for case in build_causal_scenario_catalog() if case.family == "deploy_config" and case.variant == "obvious")
    base = {
        "case_id": scenario.case_id,
        "family": scenario.family,
        "variant": scenario.variant,
        "split": scenario.split,
        "seed": 116,
        "initial_fingerprint": "p116-initial",
        "pre": _measurement(availability=0.6, latency_ms=820.0, backlog=160.0, correctness=0.95, utility=0.55, recovered=False),
    }
    natural_post = _measurement(
        availability=0.97 if natural_recovered else 0.62,
        latency_ms=115.0 if natural_recovered else 800.0,
        backlog=6.0 if natural_recovered else 150.0,
        correctness=0.99 if natural_recovered else 0.95,
        utility=0.97 if natural_recovered else 0.57,
        recovered=natural_recovered,
    )
    arms: list[dict[str, Any]] = [
        {
            **base,
            "arm": "selected_action",
            "decision": {"route": "act", "actions": list(scenario.required_actions), "rationale": "selected arm"},
            "post": _measurement(availability=0.96, latency_ms=120.0, backlog=8.0, correctness=0.99, utility=0.96, recovered=True),
            "durability": _measurement(availability=0.96, latency_ms=120.0, backlog=8.0, correctness=0.99, utility=0.96, recovered=True),
        },
        {
            **base,
            "arm": "no_action",
            "decision": {"route": "observe", "actions": [], "rationale": "control"},
            "post": _measurement(availability=0.62, latency_ms=800.0, backlog=150.0, correctness=0.95, utility=0.57, recovered=False),
            "durability": _measurement(availability=0.62, latency_ms=800.0, backlog=150.0, correctness=0.95, utility=0.57, recovered=False),
        },
        {
            **base,
            "arm": "wrong_action",
            "decision": {"route": "act", "actions": [scenario.harmful_actions[0]], "rationale": "wrong arm"},
            "post": _measurement(availability=0.2, latency_ms=1400.0, backlog=250.0, correctness=0.7, utility=0.2, recovered=False, collateral_regressions=1),
            "durability": _measurement(availability=0.2, latency_ms=1400.0, backlog=250.0, correctness=0.7, utility=0.2, recovered=False, collateral_regressions=1),
        },
        {
            **base,
            "arm": "rollback_action",
            "decision": {"route": "act", "actions": list(scenario.required_actions), "rationale": "rollback"},
            "post": _measurement(availability=0.6, latency_ms=820.0, backlog=160.0, correctness=0.95, utility=0.55, recovered=False),
            "durability": _measurement(availability=0.6, latency_ms=820.0, backlog=160.0, correctness=0.95, utility=0.55, recovered=False),
        },
        {
            **base,
            "arm": "natural_recovery",
            "decision": {"route": "observe", "actions": [], "rationale": "natural control"},
            "post": natural_post,
            "durability": natural_post,
        },
    ]
    for order, arm in enumerate(arms):
        receipt: dict[str, Any] = {
            "case_id": arm["case_id"],
            "seed": arm["seed"],
            "arm": arm["arm"],
            "arm_order": order,
            "reset_fingerprint": arm["initial_fingerprint"],
            "verified": True,
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        arm["reset_receipt"] = receipt
    run = {
        "schema_version": "p116.lab_run.v1",
        "arm_results": arms,
        "boundary": dict(P116_LAB_BOUNDARY),
    }
    run["run_hash"] = stable_hash({"schema_version": run["schema_version"], "arm_results": arms, "boundary": run["boundary"]})
    assert hash_p116_source_results(arms)
    return run


def _measurement(
    *,
    availability: float,
    latency_ms: float,
    backlog: float,
    correctness: float,
    utility: float,
    recovered: bool,
    collateral_regressions: int = 0,
) -> dict[str, Any]:
    return {
        "availability": availability,
        "latency_ms": latency_ms,
        "backlog": backlog,
        "correctness": correctness,
        "telemetry_coverage": 0.95,
        "collateral_regressions": collateral_regressions,
        "http_request_count": 5,
        "utility": utility,
        "recovered": recovered,
        "verifiable": True,
    }
