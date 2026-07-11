from __future__ import annotations

import importlib
from typing import Any

import pytest

HASHES = {
    "ingress_hash": "sha256:" + "1" * 64,
    "ledger_head_hash": "sha256:" + "2" * 64,
    "benchmark_hash": "sha256:" + "3" * 64,
    "fixture_matrix_hash": "sha256:" + "4" * 64,
    "holdout_report_hash": "sha256:" + "5" * 64,
    "promotion_report_hash": "sha256:" + "6" * 64,
    "recommendation_manifest_hash": "sha256:" + "7" * 64,
    "authority_scan_hash": "sha256:" + "8" * 64,
    "docs_scan_hash": "sha256:" + "9" * 64,
    "release_profile_hash": "sha256:" + "a" * 64,
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.p108_release_evidence")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P108 RED: missing P108 release evidence module ({exc}).", pytrace=False)


def _complete_inputs() -> dict[str, Any]:
    raw_matrix = {
        "schema_version": "p108.learning_fixture_matrix.v1",
        "source_path": "evals/prevention/p108_learning_cases.json",
        "fixtures": [
            {
                "fixture_id": f"L{index:02d}",
                "scenario": scenario,
                "expected_label": label,
                "expected_evaluation": {"label": label, "ledger_admitted": index not in {15, 16}, "failed_before_ledger": index in {15, 16}},
                "episode_group": f"group-l{index:02d}",
                "time_split": "pre" if index % 2 else "post",
                "seed": [101, 202, 303][index % 3],
                "p107_handoff_valid": index not in {15, 16},
                "episode_input": {
                    "p107_ingress": {
                        "schema_version": "p107.prevention_handoff.v1",
                        "episode_id": f"episode-l{index:02d}",
                        "payload_hash": HASHES["fixture_matrix_hash"],
                        "signed_payload_hash": ("sha256:" + "b" * 64) if index == 15 else HASHES["fixture_matrix_hash"],
                        "offline_authority": True,
                    },
                    "ledger_candidate": {"episode_id": f"episode-l{index:02d}", "payload_hash": HASHES["fixture_matrix_hash"]},
                    "outcome": {"actual_outcome": label, "control_available": label not in {"inconclusive", "rejected"}, "horizon_censored": label == "censored"},
                    "counterfactual": {"mode": "abstained" if label in {"inconclusive", "censored", "rejected"} else "identified", "reason": "fixture"},
                    "training_episode_groups": ["training-a"],
                    "authority_requests": [{"kind": "db_session_query", "target": "production"}, {"kind": "online_policy_mutation", "target": "production"}] if index == 16 else [],
                },
                "recommendation": {"direction": "conservative" if index in {5, 8, 13, 14} else "none", "applied": False, "rollback_to_version": "p108-baseline-v1"},
                "authority_counters": _api().zero_authority_counters(),
                "evidence_gates": {gate: True for gate in _api().REQUIRED_EVIDENCE_GATES},
            }
            for index, (_, scenario, label) in enumerate(_api().REQUIRED_FIXTURE_IDENTITIES, start=1)
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
    fixture_result = _api().evaluate_prevention_learning_fixture_matrix(raw_matrix)
    return {
        "producer_id": "p108-release-producer",
        "fixture_matrix_result": {**fixture_result, "raw_matrix": raw_matrix},
        "ingress_result": {"accepted": True, "ingress_hash": HASHES["ingress_hash"], "schema_version": "p108.ingress_result.v1", "source": "offline"},
        "ledger_result": {"accepted": True, "ledger_head_hash": HASHES["ledger_head_hash"], "schema_version": "p108.ledger_result.v1", "sealed": True},
        "benchmark_result": {
            "accepted": True,
            "benchmark_hash": HASHES["benchmark_hash"],
            "metrics": raw_matrix["metrics"],
            "paired_learning_utility_deltas": raw_matrix["paired_learning_utility_deltas"],
            "family_results": raw_matrix["family_results"],
        },
        "recommendation_manifest": {
            "accepted": True,
            "recommendation_manifest_hash": HASHES["recommendation_manifest_hash"],
            "applied": False,
            "rollback_to_version": "p108-baseline-v1",
            "recommendations": [{"fixture_id": "L14", "direction": "conservative", "applied": False}],
        },
        "promotion_report": {
            "accepted": True,
            "holdout_report_hash": HASHES["holdout_report_hash"],
            "promotion_report_hash": HASHES["promotion_report_hash"],
            "holdout_disjoint": True,
            "promotion_ready": True,
        },
        "authority_scan": {"accepted": True, "authority_scan_hash": HASHES["authority_scan_hash"], "authority_counters": _api().zero_authority_counters()},
        "docs_scan": {"accepted": True, "docs_scan_hash": HASHES["docs_scan_hash"], "overclaiming_phrases": []},
        "verify_profile": {"profile": "p108-release", "passed": True, "fresh": True, "release_profile_hash": HASHES["release_profile_hash"]},
    }


def _complete_review(release_hash: str = "sha256:release", artifact_hashes: dict[str, Any] | None = None) -> dict[str, Any]:
    bound_hashes = artifact_hashes or HASHES
    return {
        "schema_version": "p108.independent_review.v1",
        "review_id": "p108-review-0001",
        "reviewer": {"role": "verifier", "id": "p108-reviewer-a01"},
        "producer_id": "p108-release-producer",
        "verdict": "pass",
        "reviewed_at": "2026-07-10T03:10:00Z",
        "freshness": {"evidence_generated_at": "2026-07-10T03:00:00Z", "max_age_seconds": 3600, "fresh": True},
        "reviewed_artifact_hashes": {
            "ingress_hash": bound_hashes["ingress_hash"],
            "ledger_head_hash": bound_hashes["ledger_head_hash"],
            "benchmark_hash": bound_hashes["benchmark_hash"],
            "release_evidence_hash": release_hash,
            "fixture_matrix_hash": bound_hashes["fixture_matrix_hash"],
            "holdout_report_hash": bound_hashes["holdout_report_hash"],
            "promotion_report_hash": bound_hashes["promotion_report_hash"],
            "recommendation_manifest_hash": bound_hashes["recommendation_manifest_hash"],
            "authority_scan_hash": bound_hashes["authority_scan_hash"],
            "docs_scan_hash": bound_hashes["docs_scan_hash"],
            "release_profile_hash": bound_hashes["release_profile_hash"],
        },
    }


def _artifact_hashes_from_unsigned(unsigned: dict[str, Any]) -> dict[str, Any]:
    return {key: unsigned[key] for key in HASHES}


def _produce(inputs: dict[str, Any] | None = None, review: dict[str, Any] | None = None) -> dict[str, Any]:
    producer = getattr(_api(), "produce_p108_release_evidence", None)
    if producer is None:
        pytest.fail("P108 RED: expose produce_p108_release_evidence(...).", pytrace=False)
    base = inputs or _complete_inputs()
    unsigned = producer(**base, independent_review=None, trusted_now="2026-07-10T03:30:00Z")
    final_review = review or _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    return producer(**base, independent_review=final_review, trusted_now="2026-07-10T03:30:00Z")


def test_release_evidence_qualifies_only_when_six_gates_and_review_pass() -> None:
    evidence = _produce()

    assert evidence["schema_version"] == "p108.release_evidence.v1"
    assert evidence["release_qualified"] is True
    assert evidence["six_release_gates"] == {
        "p107_ingress_ready": True,
        "immutable_ledger_ready": True,
        "benchmark_metrics_ready": True,
        "recommendation_manifest_ready": True,
        "promotion_ready": True,
        "authority_boundary_ready": True,
    }
    assert evidence["independent_review"]["accepted"] is True
    assert evidence["independent_review"]["review_id"] == "p108-review-0001"


@pytest.mark.parametrize(
    ("section", "field", "gate"),
    [
        ("ingress_result", "accepted", "p107_ingress_ready"),
        ("ledger_result", "accepted", "immutable_ledger_ready"),
        ("benchmark_result", "accepted", "benchmark_metrics_ready"),
        ("recommendation_manifest", "accepted", "recommendation_manifest_ready"),
        ("promotion_report", "accepted", "promotion_ready"),
        ("authority_scan", "accepted", "authority_boundary_ready"),
    ],
)
def test_each_release_gate_fails_closed(section: str, field: str, gate: str) -> None:
    inputs = _complete_inputs()
    inputs[section].pop(field)

    evidence = _produce(inputs)

    assert evidence["release_qualified"] is False
    assert evidence["six_release_gates"][gate] is False
    assert gate in " ".join(evidence["reasons"])


def test_release_evidence_requires_exact_l01_l16_fixture_identity() -> None:
    inputs = _complete_inputs()
    inputs["fixture_matrix_result"]["fixture_ids"] = [f"L{index:02d}" for index in range(1, 16)]

    evidence = _produce(inputs)

    assert evidence["release_qualified"] is False
    assert "L01-L16" in " ".join(evidence["reasons"])


def test_independent_review_rejects_stale_hash_mismatch_wrong_role_and_self_review() -> None:
    inputs = _complete_inputs()
    unsigned = _api().produce_p108_release_evidence(**inputs, independent_review=None)
    review = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    review["reviewer"] = {"role": "producer", "id": "p108-release-producer"}
    review["freshness"]["fresh"] = False
    review["reviewed_artifact_hashes"]["ledger_head_hash"] = "sha256:other-ledger"

    evidence = _api().produce_p108_release_evidence(**inputs, independent_review=review)

    assert evidence["release_qualified"] is False
    assert evidence["independent_review"]["accepted"] is False
    assert evidence["independent_review"]["fresh"] is False
    assert evidence["independent_review"]["reviewed_artifact_hashes_match"] is False
    assert any("approved" in reason or "producer" in reason for reason in evidence["independent_review"]["reasons"])


def test_independent_review_must_bind_to_actual_release_producer() -> None:
    inputs = _complete_inputs()
    unsigned = _api().produce_p108_release_evidence(**inputs, independent_review=None, trusted_now="2026-07-10T03:30:00Z")
    review = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    review["producer_id"] = "different-p108-producer"

    evidence = _api().produce_p108_release_evidence(**inputs, independent_review=review, trusted_now="2026-07-10T03:30:00Z")

    assert evidence["release_qualified"] is False
    assert evidence["independent_review"]["accepted"] is False
    assert "producer_id must match release producer" in evidence["independent_review"]["reasons"]


def test_independent_review_requires_lowercase_pass_and_exact_schema() -> None:
    inputs = _complete_inputs()
    unsigned = _api().produce_p108_release_evidence(**inputs, independent_review=None)
    review = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    review["schema_version"] = "p107.independent_review.v1"
    review["verdict"] = "PASS"

    evidence = _api().produce_p108_release_evidence(**inputs, independent_review=review)

    assert evidence["release_qualified"] is False
    assert evidence["independent_review"]["accepted"] is False
    assert "schema_version" in " ".join(evidence["independent_review"]["reasons"])


def test_independent_review_requires_non_empty_review_id_and_canonical_complete_hashes() -> None:
    inputs = _complete_inputs()
    unsigned = _api().produce_p108_release_evidence(**inputs, independent_review=None, trusted_now="2026-07-10T03:30:00Z")
    review = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    review["review_id"] = ""
    review["reviewed_artifact_hashes"]["benchmark_hash"] = "sha256:not-canonical"
    review["reviewed_artifact_hashes"].pop("ingress_hash")

    evidence = _api().produce_p108_release_evidence(**inputs, independent_review=review, trusted_now="2026-07-10T03:30:00Z")

    assert evidence["release_qualified"] is False
    assert evidence["independent_review"]["accepted"] is False
    reasons = " ".join(evidence["independent_review"]["reasons"])
    assert "review_id" in reasons
    assert "canonical" in reasons
    assert evidence["independent_review"]["reviewed_artifact_hashes_match"] is False


def test_independent_review_rejects_future_backdated_and_stale_against_trusted_now() -> None:
    inputs = _complete_inputs()
    unsigned = _api().produce_p108_release_evidence(**inputs, independent_review=None, trusted_now="2026-07-10T03:30:00Z")

    future = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    future["reviewed_at"] = "2026-07-10T04:00:01Z"
    assert _api().produce_p108_release_evidence(**inputs, independent_review=future, trusted_now="2026-07-10T03:30:00Z")["independent_review"]["accepted"] is False

    backdated = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    backdated["reviewed_at"] = "2026-07-10T02:59:59Z"
    assert _api().produce_p108_release_evidence(**inputs, independent_review=backdated, trusted_now="2026-07-10T03:30:00Z")["independent_review"]["accepted"] is False

    stale = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    stale["reviewed_at"] = "2026-07-10T03:20:01Z"
    stale["freshness"]["max_age_seconds"] = 60
    assert _api().produce_p108_release_evidence(**inputs, independent_review=stale, trusted_now="2026-07-10T03:30:00Z")["independent_review"]["accepted"] is False


def test_independent_review_expires_when_trusted_now_exceeds_review_max_age_even_with_rebound_hashes() -> None:
    inputs = _complete_inputs()
    trusted_now = "2026-07-11T03:30:00Z"
    unsigned = _api().produce_p108_release_evidence(**inputs, independent_review=None, trusted_now=trusted_now)
    review = _complete_review(unsigned["release_evidence_hash"], _artifact_hashes_from_unsigned(unsigned))
    review["reviewed_at"] = "2026-07-10T03:10:00Z"
    review["freshness"] = {"evidence_generated_at": "2026-07-10T03:00:00Z", "max_age_seconds": 3600, "fresh": True}

    evidence = _api().produce_p108_release_evidence(**inputs, independent_review=review, trusted_now=trusted_now)

    assert evidence["release_qualified"] is False
    assert evidence["independent_review"]["accepted"] is False
    assert evidence["independent_review"]["fresh"] is False


def test_release_aggregator_recomputes_fixture_and_benchmark_sections_fail_closed() -> None:
    inputs = _complete_inputs()
    inputs["fixture_matrix_result"] = {
        "accepted": True,
        "matrix_hash": HASHES["fixture_matrix_hash"],
        "fixture_ids": [f"L{index:02d}" for index in range(1, 17)],
    }
    inputs["benchmark_result"]["metrics"]["median_learning_utility_delta"] = 0.99
    inputs["benchmark_result"]["paired_learning_utility_deltas"] = [
        {"seed": 101, "time_split": "early", "delta": 0.001},
        {"seed": 101, "time_split": "late", "delta": 0.001},
        {"seed": 202, "time_split": "early", "delta": 0.001},
        {"seed": 202, "time_split": "late", "delta": 0.001},
        {"seed": 303, "time_split": "early", "delta": 0.001},
        {"seed": 303, "time_split": "late", "delta": 0.001},
    ]

    evidence = _produce(inputs)

    assert evidence["release_qualified"] is False
    assert evidence["six_release_gates"]["benchmark_metrics_ready"] is False
    assert "fixture matrix did not pass recomputation" in " ".join(evidence["reasons"])
