from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p178_policy import (
    P178PolicyError,
    evaluate_decision,
    false_prevention_one_sided_exact_95ub,
    score_counterfactual_outcomes,
    validate_precursor_window,
)
from app.services.p178_release import P178ReleaseError, build_readiness_artifact, validate_readiness_artifact

ROOT = Path(__file__).resolve().parents[1]


def _evidence_records() -> list[dict[str, object]]:
    return [
        {"evidence_id": "ev-metrics", "source_class": "metrics", "fresh": True, "read_only": True, "supports": ["checkout_latency_rise"]},
        {"evidence_id": "ev-trace", "source_class": "trace", "fresh": True, "read_only": True, "supports": ["checkout_latency_rise"]},
    ]


def _safe_decision() -> dict[str, object]:
    return {
        "schema_version": "p178.prevention_decision.v1",
        "window_id": "win-checkout-latency",
        "decision_type": "act",
        "prevention_class": "traffic_shift_shadow_recommendation",
        "cited_evidence_ids": ["ev-metrics", "ev-trace"],
        "confidence": 0.86,
        "expected_benefit": 0.24,
        "possible_harm": 0.03,
        "counterfactual_action": "recommend_operator_reviewed_traffic_shift",
        "safety": {"supported": True, "reversible": True, "blast_radius": "single_service", "mutation_authority": "none"},
    }


def test_precursor_window_taxonomy_and_decision_schema_are_hash_bound() -> None:
    window = {
        "schema_version": "p178.precursor_window.v1",
        "window_id": "win-checkout-latency",
        "family": "latency",
        "service": "checkout",
        "taxonomy": "actionable_precursor",
        "lead_time_seconds": 900,
        "expected_prevention_classes": ["traffic_shift_shadow_recommendation"],
        "non_actionable_signal": False,
        "p177_trace_id": "trace-001",
        "p177_evidence_ids": ["ev-metrics", "ev-trace"],
    }

    validated_window = validate_precursor_window(window)
    assert validated_window["window_hash"] == stable_hash({key: value for key, value in validated_window.items() if key != "window_hash"})

    evaluated = evaluate_decision(_safe_decision(), precursor_window=validated_window, evidence_records=_evidence_records())
    assert evaluated["decision_type"] == "act"
    assert evaluated["eligible"] is True
    assert evaluated["unsupported_prevention_proposal"] is False
    assert evaluated["unsafe_action_advice"] is False
    assert evaluated["citation_confidence"] == 1.0
    assert evaluated["decision_hash"] == stable_hash({key: value for key, value in evaluated.items() if key != "decision_hash"})


def test_no_act_and_seek_evidence_are_explicit_fail_closed_decisions() -> None:
    noisy = validate_precursor_window(
        {
            "schema_version": "p178.precursor_window.v1",
            "window_id": "win-noisy",
            "family": "latency",
            "service": "checkout",
            "taxonomy": "noisy_non_actionable",
            "lead_time_seconds": 600,
            "expected_prevention_classes": [],
            "non_actionable_signal": True,
            "p177_trace_id": "trace-noisy",
            "p177_evidence_ids": ["ev-metrics"],
        }
    )
    no_act = evaluate_decision(
        {
            "schema_version": "p178.prevention_decision.v1",
            "window_id": "win-noisy",
            "decision_type": "no-act",
            "prevention_class": None,
            "cited_evidence_ids": ["ev-metrics"],
            "confidence": 0.2,
            "expected_benefit": 0.0,
            "possible_harm": 0.0,
            "abstention_reason": "non_actionable_signal",
            "safety": {"supported": True, "reversible": True, "blast_radius": "none", "mutation_authority": "none"},
        },
        precursor_window=noisy,
        evidence_records=_evidence_records(),
    )
    assert no_act["eligible"] is False
    assert no_act["stop_reason"] == "non_actionable_signal"

    seek = evaluate_decision(
        {
            "schema_version": "p178.prevention_decision.v1",
            "window_id": "win-noisy",
            "decision_type": "seek-evidence",
            "prevention_class": None,
            "cited_evidence_ids": ["ev-metrics"],
            "confidence": 0.45,
            "expected_benefit": 0.1,
            "possible_harm": 0.02,
            "escalation_reason": "single_source_evidence",
            "safety": {"supported": True, "reversible": True, "blast_radius": "none", "mutation_authority": "none"},
        },
        precursor_window=noisy,
        evidence_records=_evidence_records(),
    )
    assert seek["eligible"] is False
    assert seek["stop_reason"] == "seek_more_evidence"


def test_unsupported_or_unsafe_prevention_and_fabricated_predecessor_fail_closed() -> None:
    window = validate_precursor_window(
        {
            "schema_version": "p178.precursor_window.v1",
            "window_id": "win-checkout-latency",
            "family": "latency",
            "service": "checkout",
            "taxonomy": "actionable_precursor",
            "lead_time_seconds": 900,
            "expected_prevention_classes": ["traffic_shift_shadow_recommendation"],
            "non_actionable_signal": False,
            "p177_trace_id": "trace-001",
            "p177_evidence_ids": ["ev-metrics", "ev-trace"],
        }
    )

    unsupported = deepcopy(_safe_decision())
    unsupported["prevention_class"] = "restart_production_database"
    with pytest.raises(P178PolicyError, match="unsupported_prevention_proposal"):
        evaluate_decision(unsupported, precursor_window=window, evidence_records=_evidence_records())

    unsafe = deepcopy(_safe_decision())
    unsafe["safety"] = {"supported": True, "reversible": False, "blast_radius": "multi_service", "mutation_authority": "production"}
    with pytest.raises(P178PolicyError, match="unsafe_action_advice"):
        evaluate_decision(unsafe, precursor_window=window, evidence_records=_evidence_records())

    fabricated = {"schema_version": "p177.release_evidence.v1", "qualified": True, "evidence_hash": "sha256:" + "0" * 64}
    artifact = build_readiness_artifact(project_root=ROOT, p177_release_evidence=fabricated)
    assert artifact["qualified"] is False
    assert artifact["p177_release_evidence"]["valid"] is False
    with pytest.raises(P178ReleaseError, match="fabricated_or_unqualified_p177_evidence"):
        forged = deepcopy(artifact)
        forged["p177_release_evidence"]["valid"] = True
        forged["readiness_hash"] = stable_hash({key: value for key, value in forged.items() if key != "readiness_hash"})
        validate_readiness_artifact(forged, project_root=ROOT)


def test_false_prevention_exact_upper_bound_gate_and_operator_metrics() -> None:
    assert false_prevention_one_sided_exact_95ub(false_prevention_count=0, negative_window_count=300) <= 0.01
    assert false_prevention_one_sided_exact_95ub(false_prevention_count=1, negative_window_count=300) > 0.01

    report = score_counterfactual_outcomes(
        rows=[
            {"window_id": "w1", "family": "latency", "decision_type": "act", "actual_outcome": "incident", "baseline_utility": 0.2, "candidate_utility": 0.8, "operator_interrupted": True},
            {"window_id": "w2", "family": "latency", "decision_type": "no-act", "actual_outcome": "healthy", "baseline_utility": 0.7, "candidate_utility": 0.7, "operator_interrupted": False},
            {
                "window_id": "w3",
                "family": "network",
                "decision_type": "seek-evidence",
                "actual_outcome": "natural_recovery",
                "baseline_utility": 0.4,
                "candidate_utility": 0.5,
                "operator_interrupted": True,
            },
        ],
        false_prevention_count=0,
        negative_window_count=300,
    )
    assert report["fatigue_metrics"]["operator_interruption_count"] == 2
    assert report["fatigue_metrics"]["operator_interruption_rate"] == pytest.approx(2 / 3)
    assert report["counterfactual_metrics"]["mean_net_prevention_utility"] == pytest.approx((0.6 + 0.0 + 0.1) / 3)
    assert report["false_prevention_gate"]["passed"] is True


def test_p178_readiness_is_blocked_until_qualified_p177_evidence_exists() -> None:
    artifact = build_readiness_artifact(project_root=ROOT, p177_release_evidence=None)
    assert artifact["qualified"] is False
    assert artifact["maximum_claim"] == "readiness_only_not_qualification"
    assert "bounded_prevention_shadow_qualified" in artifact["forbidden_claims"]
    assert "missing_qualified_p177_release_evidence" in artifact["stop_reasons"]
    assert validate_readiness_artifact(artifact, project_root=ROOT)["qualified"] is False

    forged = deepcopy(artifact)
    forged["qualified"] = True
    forged["maximum_claim"] = "bounded_prevention_shadow_qualified"
    forged["readiness_hash"] = stable_hash({key: value for key, value in forged.items() if key != "readiness_hash"})
    with pytest.raises(P178ReleaseError, match="qualification_forbidden"):
        validate_readiness_artifact(forged, project_root=ROOT)
