from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.services.causal_remediation_benchmark import build_causal_scenario_catalog
from app.services.p110_evaluation import stable_hash
from app.services.p116_paired_outcomes import (
    P116PairedOutcomeError,
    P116PairedOutcomeRecord,
    build_p116_paired_outcome_record,
    hash_p116_source_results,
)


def _source_trials() -> tuple[list[dict[str, object]], dict[str, object], str]:
    scenario = next(case for case in build_causal_scenario_catalog() if case.family == "deploy_config" and case.variant == "obvious")
    base = {
        "case_id": scenario.case_id,
        "family": scenario.family,
        "variant": scenario.variant,
        "split": scenario.split,
        "seed": 17,
        "initial_fingerprint": "fingerprint-a",
        "pre": _measurement(availability=0.6, latency_ms=820.0, backlog=160.0, correctness=0.95, utility=0.55, recovered=False),
    }
    source_trials: list[dict[str, object]] = [
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
            "decision": {"route": "observe", "actions": [], "rationale": "natural recovery control"},
            "post": _measurement(availability=0.62, latency_ms=800.0, backlog=150.0, correctness=0.95, utility=0.57, recovered=False),
            "durability": _measurement(availability=0.62, latency_ms=800.0, backlog=150.0, correctness=0.95, utility=0.57, recovered=False),
        },
        {
            **base,
            "arm": "wrong_action",
            "decision": {"route": "act", "actions": [scenario.harmful_actions[0]], "rationale": "known wrong arm"},
            "post": _measurement(availability=0.2, latency_ms=1400.0, backlog=250.0, correctness=0.7, utility=0.2, recovered=False, collateral_regressions=1),
            "durability": _measurement(availability=0.2, latency_ms=1400.0, backlog=250.0, correctness=0.7, utility=0.2, recovered=False, collateral_regressions=1),
        },
        {
            **base,
            "arm": "rollback_action",
            "decision": {"route": "act", "actions": list(scenario.required_actions), "rationale": "apply then roll back"},
            "post": _measurement(availability=0.6, latency_ms=820.0, backlog=160.0, correctness=0.95, utility=0.55, recovered=False),
            "durability": _measurement(availability=0.6, latency_ms=820.0, backlog=160.0, correctness=0.95, utility=0.55, recovered=False),
        },
        {
            **base,
            "arm": "natural_recovery",
            "decision": {"route": "observe", "actions": [], "rationale": "extended recovery window"},
            "post": _measurement(availability=0.62, latency_ms=800.0, backlog=150.0, correctness=0.95, utility=0.57, recovered=False),
            "durability": _measurement(availability=0.62, latency_ms=800.0, backlog=150.0, correctness=0.95, utility=0.57, recovered=False),
        },
    ]
    for order, trial in enumerate(source_trials):
        receipt = {
            "case_id": trial["case_id"],
            "seed": trial["seed"],
            "arm": trial["arm"],
            "arm_order": order,
            "reset_fingerprint": trial["initial_fingerprint"],
            "verified": True,
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        trial["reset_receipt"] = receipt
    boundary: dict[str, object] = {
        "synthetic_local_fault_lab": True,
        "loopback_only": True,
        "external_network_enabled": False,
        "filesystem_mutation_enabled": False,
        "subprocess_execution_enabled": False,
        "credentials_enabled": False,
        "production_mutation_enabled": False,
        "arbitrary_action_enabled": False,
        "unattended_production_operation_claimed": False,
    }
    return source_trials, boundary, hash_p116_source_results(source_trials)


def test_builds_immutable_paired_outcome_record_from_existing_benchmark_results() -> None:
    source_trials, boundary, source_hash = _source_trials()

    record = build_p116_paired_outcome_record(source_trials, boundary=boundary, expected_source_hash=source_hash)
    payload = record.to_dict()

    assert isinstance(record, P116PairedOutcomeRecord)
    with pytest.raises(FrozenInstanceError):
        record.schema_version = "mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        record.payload["record_hash"] = "mutated"  # type: ignore[index]
    assert payload["schema_version"] == "p116.paired_outcome_record.v1"
    assert payload["case_id"] == source_trials[0]["case_id"]
    assert payload["seed"] == 17
    assert payload["initial_state_fingerprint"] == source_trials[0]["initial_fingerprint"]
    assert payload["reset_verification"]["same_scenario"] is True
    assert payload["reset_verification"]["same_seed"] is True
    assert payload["reset_verification"]["same_initial_state"] is True
    assert payload["reset_verification"]["required_arms_present"] is True
    assert len(payload["reset_verification"]["receipt_hashes"]) == 5
    assert payload["recovery_window"] == {"measurement_points": ["post", "durability"], "durability_required": True}
    assert payload["natural_recovery_control"]["arm"] == "natural_recovery"
    assert payload["natural_recovery_control"]["recovered_without_action"] is False
    assert payload["causal_attribution"]["qualified"] is True
    assert payload["slo_deltas"]["selected_action"]["availability_delta"] > 0
    assert payload["slo_deltas"]["selected_action"]["utility_delta"] > 0
    assert payload["slo_deltas"]["wrong_action"]["collateral_regression_delta"] == 1
    assert payload["collateral_harm"]["wrong_action"]["harmful"] is True
    assert payload["source_hash"] == source_hash
    assert payload["record_hash"] == stable_hash({key: value for key, value in payload.items() if key != "record_hash"})


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda trials, _boundary: trials.pop(), "missing_arm"),
        (lambda trials, _boundary: trials[0].__setitem__("seed", 18), "cross_seed_comparison"),
        (lambda trials, _boundary: trials[0].__setitem__("case_id", "other"), "cross_scenario_comparison"),
        (lambda trials, _boundary: trials[0]["reset_receipt"].__setitem__("verified", False), "reset_verification_failed"),
        (lambda trials, boundary: boundary.__setitem__("production_mutation_enabled", True), "production_authority_enabled"),
    ],
)
def test_paired_outcome_record_fails_closed_for_invalid_comparisons(mutate: object, message: str) -> None:
    source_trials, boundary, source_hash = _source_trials()

    mutate(source_trials, boundary)  # type: ignore[operator]

    with pytest.raises(P116PairedOutcomeError, match=message):
        build_p116_paired_outcome_record(source_trials, boundary=boundary, expected_source_hash=source_hash)


def test_paired_outcome_record_rejects_source_hash_drift() -> None:
    source_trials, boundary, source_hash = _source_trials()
    source_trials[0]["post"]["utility"] = 0.0  # type: ignore[index]

    with pytest.raises(P116PairedOutcomeError, match="source_hash_drift"):
        build_p116_paired_outcome_record(source_trials, boundary=boundary, expected_source_hash=source_hash)


def test_unverifiable_measurement_is_preserved_as_inconclusive_not_credited() -> None:
    source_trials, boundary, _source_hash = _source_trials()
    source_trials[0]["post"]["verifiable"] = False  # type: ignore[index]
    source_hash = hash_p116_source_results(source_trials)

    record = build_p116_paired_outcome_record(source_trials, boundary=boundary, expected_source_hash=source_hash).to_dict()

    assert record["measurement_status"] == "inconclusive"
    assert record["causal_attribution"]["selected_effective"] is False
    assert record["causal_attribution"]["qualified"] is False


def _measurement(
    *,
    availability: float,
    latency_ms: float,
    backlog: float,
    correctness: float,
    utility: float,
    recovered: bool,
    collateral_regressions: int = 0,
) -> dict[str, object]:
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
