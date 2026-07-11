from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

P108_CASES_PATH = Path("evals/prevention/p108_learning_cases.json")
CANONICAL_HASH = "sha256:" + "a" * 64
REQUIRED_FIXTURE_IDENTITIES = (
    ("L01", "valid_prevented", "prevented"),
    ("L02", "valid_delayed", "delayed"),
    ("L03", "unaffected", "unaffected"),
    ("L04", "natural_recovery", "naturally_recovered"),
    ("L05", "harmful_guardrail_breach", "harmful"),
    ("L06", "inconclusive_missing_control", "inconclusive"),
    ("L07", "censored_horizon", "censored"),
    ("L08", "false_positive_intervention", "unaffected"),
    ("L09", "near_miss_abstention", "unaffected"),
    ("L10", "conflicting_evidence", "inconclusive"),
    ("L11", "telemetry_loss", "inconclusive"),
    ("L12", "family_level_drift", "delayed"),
    ("L13", "candidate_safety_regression", "harmful"),
    ("L14", "valid_conservative_recommendation", "prevented"),
    ("L15", "forged_p107_handoff", "rejected"),
    ("L16", "online_mutation_attempt", "rejected"),
)

LABEL_INPUTS = {
    "prevented": {"actual_outcome": "prevented", "control_available": True},
    "delayed": {"actual_outcome": "delayed", "control_available": True},
    "unaffected": {"actual_outcome": "unaffected", "control_available": True},
    "naturally_recovered": {"actual_outcome": "prevented", "control_available": True, "natural_recovery": True},
    "harmful": {"actual_outcome": "harmful", "control_available": True, "intervention_harm": True},
    "inconclusive": {"actual_outcome": "unknown", "control_available": False},
    "censored": {"actual_outcome": "unknown", "control_available": True, "horizon_censored": True},
    "rejected": {"actual_outcome": "unknown", "control_available": False},
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.p108_release_evidence")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P108 RED: missing P108 release evidence module ({exc}).", pytrace=False)


def _evaluate(matrix: dict[str, Any]) -> dict[str, Any]:
    evaluator = getattr(_api(), "evaluate_prevention_learning_fixture_matrix", None)
    if evaluator is None:
        pytest.fail("P108 RED: expose evaluate_prevention_learning_fixture_matrix(matrix).", pytrace=False)
    return evaluator(matrix)


def _complete_matrix() -> dict[str, Any]:
    return {
        "schema_version": "p108.learning_fixture_matrix.v1",
        "source_path": str(P108_CASES_PATH),
        "fixtures": [
            {
                "fixture_id": fixture_id,
                "scenario": scenario,
                "expected_label": label,
                "expected_evaluation": {
                    "label": label,
                    "ledger_admitted": fixture_id not in {"L15", "L16"},
                    "failed_before_ledger": fixture_id in {"L15", "L16"},
                },
                "episode_input": {
                    "p107_ingress": {
                        "schema_version": "p107.prevention_handoff.v1",
                        "episode_id": f"episode-{fixture_id.lower()}",
                        "payload_hash": CANONICAL_HASH,
                        "signed_payload_hash": ("sha256:" + "b" * 64) if fixture_id == "L15" else CANONICAL_HASH,
                        "offline_authority": True,
                    },
                    "ledger_candidate": {
                        "episode_id": f"episode-{fixture_id.lower()}",
                        "payload_hash": CANONICAL_HASH,
                    },
                    "outcome": LABEL_INPUTS[label],
                    "counterfactual": {
                        "mode": "abstained" if label in {"inconclusive", "censored", "rejected"} else "identified",
                        "reason": "insufficient_control" if label in {"inconclusive", "rejected"} else ("censored_horizon" if label == "censored" else ""),
                    },
                    "training_episode_groups": ["group-training-a", "group-training-b"],
                    "authority_requests": (
                        [{"kind": "db_session_query", "target": "production"}, {"kind": "online_policy_mutation", "target": "production"}]
                        if fixture_id == "L16"
                        else []
                    ),
                },
                "episode_group": f"group-{fixture_id.lower()}",
                "time_split": "pre" if index % 2 else "post",
                "seed": [101, 202, 303][index % 3],
                "p107_handoff_valid": fixture_id not in {"L15", "L16"},
                "recommendation": {
                    "direction": "conservative" if fixture_id in {"L05", "L08", "L13", "L14"} else "none",
                    "applied": False,
                    "rollback_to_version": "p108-baseline-v1",
                },
                "authority_counters": {
                    "auth": 0,
                    "credential_reads": 0,
                    "network_calls": 0,
                    "shell_calls": 0,
                    "subprocess_calls": 0,
                    "cloud_calls": 0,
                    "db_access": 0,
                    "live_calls": 0,
                    "production_adapter_calls": 0,
                    "production_mutation": 0,
                    "executor_calls": 0,
                    "online_policy_writes": 0,
                },
                "evidence_gates": {
                    "ingress_recomputed": True,
                    "ledger_content_bound": True,
                    "temporal_cutoff_enforced": True,
                    "counterfactual_identifiable_or_abstained": True,
                    "recommendation_unapplied": True,
                    "holdout_disjoint": True,
                    "authority_zero": True,
                },
            }
            for index, (fixture_id, scenario, label) in enumerate(REQUIRED_FIXTURE_IDENTITIES)
        ],
        "metrics": {
            "prevented_precision": 0.82,
            "unnecessary_intervention_rate": 0.08,
            "harmful_intervention_rate": 0.0,
            "natural_recovery_miscredit_rate": 0.0,
            "inconclusive_rate": 0.1875,
            "censored_rate": 0.0625,
            "net_avoided_impact": 4.2,
            "forecast_calibration_drift": 0.006,
            "median_learning_utility_delta": 0.0415,
            "one_sided_exact_sign_probability": "1/64",
        },
        "paired_learning_utility_deltas": [
            {"seed": 101, "time_split": "early", "delta": 0.031},
            {"seed": 101, "time_split": "late", "delta": 0.037},
            {"seed": 202, "time_split": "early", "delta": 0.044},
            {"seed": 202, "time_split": "late", "delta": 0.052},
            {"seed": 303, "time_split": "early", "delta": 0.039},
            {"seed": 303, "time_split": "late", "delta": 0.048},
        ],
        "family_results": {
            "latency": {"episode_count": 6, "evaluated_rows": 12, "effect_delta": 0.036, "calibration_drift_delta": 0.004},
            "safety": {"episode_count": 6, "evaluated_rows": 12, "effect_delta": 0.033, "calibration_drift_delta": 0.005},
        },
    }


def test_fixture_matrix_requires_exact_l01_l16_identity_order_and_labels() -> None:
    result = _evaluate(_complete_matrix())

    assert result["accepted"] is True
    assert tuple(result["fixture_identities"]) == REQUIRED_FIXTURE_IDENTITIES
    assert result["missing_fixture_ids"] == []


def test_real_p108_learning_cases_match_exact_fixture_identity() -> None:
    assert P108_CASES_PATH.exists(), f"P108 RED: missing real learning fixture file {P108_CASES_PATH}"

    matrix = json.loads(P108_CASES_PATH.read_text(encoding="utf-8"))
    result = _evaluate(matrix)

    assert matrix["schema_version"] == "p108.learning_fixture_matrix.v1"
    assert tuple((item["fixture_id"], item["scenario"], item["expected_label"]) for item in matrix["fixtures"]) == REQUIRED_FIXTURE_IDENTITIES
    assert result["accepted"] is True
    assert result["matrix_source_path"] == str(P108_CASES_PATH)


@pytest.mark.parametrize("fixture_id", [fixture_id for fixture_id, _, _ in REQUIRED_FIXTURE_IDENTITIES])
def test_fixture_matrix_rejects_missing_any_required_fixture(fixture_id: str) -> None:
    matrix = _complete_matrix()
    matrix["fixtures"] = [fixture for fixture in matrix["fixtures"] if fixture["fixture_id"] != fixture_id]

    result = _evaluate(matrix)

    assert result["accepted"] is False
    assert fixture_id in result["missing_fixture_ids"]


def test_fixture_matrix_rejects_duplicate_or_unknown_fixture_identity() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][0]["fixture_id"] = "L99"
    matrix["fixtures"].append(dict(matrix["fixtures"][1]))

    result = _evaluate(matrix)

    assert result["accepted"] is False
    assert "L99" in result["unexpected_fixture_ids"]
    assert "L02" in result["duplicate_fixture_ids"]


def test_fixture_matrix_fails_closed_on_missing_metric_or_statistical_cell() -> None:
    matrix = _complete_matrix()
    matrix["metrics"].pop("median_learning_utility_delta")
    matrix["paired_learning_utility_deltas"] = matrix["paired_learning_utility_deltas"][:5]

    result = _evaluate(matrix)

    assert result["accepted"] is False
    assert "median_learning_utility_delta" in result["metric_failures"]
    assert result["statistical_support"]["accepted"] is False


def test_fixture_matrix_recomputes_median_from_six_raw_deltas_and_rejects_trivial_claim() -> None:
    matrix = _complete_matrix()
    matrix["metrics"]["median_learning_utility_delta"] = 0.50
    matrix["paired_learning_utility_deltas"] = [
        {"seed": 101, "time_split": "early", "delta": 0.001},
        {"seed": 101, "time_split": "late", "delta": 0.001},
        {"seed": 202, "time_split": "early", "delta": 0.001},
        {"seed": 202, "time_split": "late", "delta": 0.001},
        {"seed": 303, "time_split": "early", "delta": 0.001},
        {"seed": 303, "time_split": "late", "delta": 0.001},
    ]

    result = _evaluate(matrix)

    assert result["accepted"] is False
    assert result["statistical_support"]["computed_median_delta"] == 0.001
    assert result["metric_failures"]["median_learning_utility_delta"] == "computed_median_delta_below_0.03"


def test_fixture_matrix_recomputes_raw_episode_logic_instead_of_trusting_gate_booleans() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][0]["evidence_gates"] = {gate: True for gate in _api().REQUIRED_EVIDENCE_GATES}
    matrix["fixtures"][0]["expected_label"] = "prevented"
    matrix["fixtures"][0]["expected_evaluation"]["label"] = "prevented"
    matrix["fixtures"][0]["episode_input"]["outcome"]["actual_outcome"] = "harmful"
    matrix["fixtures"][0]["episode_input"]["outcome"]["intervention_harm"] = True

    result = _evaluate(matrix)

    assert result["accepted"] is False
    assert result["episode_evaluation_failures"]["L01"]["actual_label"] == "harmful"


def test_fixture_matrix_identity_uses_recomputed_episode_label_not_declared_expected_label() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][0]["expected_label"] = "prevented"
    matrix["fixtures"][0]["expected_evaluation"]["label"] = "prevented"
    matrix["fixtures"][0]["evidence_gates"] = {gate: True for gate in _api().REQUIRED_EVIDENCE_GATES}
    matrix["fixtures"][0]["episode_input"]["outcome"] = {"actual_outcome": "unaffected", "control_available": True}

    result = _evaluate(matrix)

    assert result["accepted"] is False
    assert result["fixture_identities"][0] == ("L01", "valid_prevented", "unaffected")
    assert result["identity_mismatches"]["L01"]["expected"] == ("L01", "valid_prevented", "prevented")


def test_fixture_matrix_requires_executable_l15_l16_negative_inputs_that_fail_before_ledger() -> None:
    matrix = _complete_matrix()

    result = _evaluate(matrix)

    assert result["negative_case_results"]["L15"] == {"actual_label": "rejected", "failed_before_ledger": True, "ledger_admitted": False}
    assert result["negative_case_results"]["L16"] == {"actual_label": "rejected", "failed_before_ledger": True, "ledger_admitted": False}

    matrix["fixtures"][14]["episode_input"]["p107_ingress"]["signed_payload_hash"] = CANONICAL_HASH
    matrix["fixtures"][15]["episode_input"]["authority_requests"] = []
    bypassed = _evaluate(matrix)

    assert bypassed["accepted"] is False
    assert "L15" in bypassed["negative_case_failures"]
    assert "L16" in bypassed["negative_case_failures"]


def test_fixture_matrix_rejects_nonzero_or_unknown_authority_counter() -> None:
    matrix = _complete_matrix()
    matrix["fixtures"][0]["authority_counters"]["network_calls"] = 1
    matrix["fixtures"][1]["authority_counters"]["mystery_live_call"] = 0

    result = _evaluate(matrix)

    assert result["accepted"] is False
    assert result["authority_counter_failures"]["L01"] == {"network_calls": 1}
    assert result["authority_counter_failures"]["L02"] == {"mystery_live_call": 0}
