from __future__ import annotations

import pytest

from app.services.p121_counterfactuals import evaluate_prevention_utility
from app.services.p121_guardrails import (
    P121GuardrailError,
    apply_prevention_guardrails,
    build_fatigue_ledger,
    guardrail_metrics,
    required_evidence_strength,
    suppress_duplicates,
)
from app.services.p121_signals import zero_authority_counters


def _ledger(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ledger_id": "fatigue-1",
        "system_id": "sys-a",
        "service_id": "checkout",
        "incident_family": "latency",
        "window_start": "2026-07-12T00:00:00Z",
        "window_end": "2026-07-12T01:00:00Z",
        "forecast_count": 3,
        "recommendation_count": 1,
        "intervention_attempt_count": 0,
        "false_positive_count": 0,
        "abstention_count": 1,
        "operator_acknowledgement_count": 1,
        "duplicate_suppression_count": 0,
        "recommendation_budget": 3,
        "l3_attempt_budget": 1,
        "authority_counters": zero_authority_counters(),
    }
    return {**base, **patch}


def _forecast(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "forecast_id": "fc-1",
        "system_id": "sys-a",
        "service_id": "checkout",
        "incident_family": "latency",
        "failure_mode": "checkout_latency",
        "horizon_start": "2026-07-12T00:30:00Z",
        "horizon_end": "2026-07-12T01:30:00Z",
        "near_duplicate_fingerprint": "checkout-latency-h1",
        "calibration_bucket": "acceptable",
        "ood_status": "in_distribution",
        "abstention_status": "not_abstained",
        "evidence_strength": "standard",
        "horizon_passed": False,
        "incident_occurred": False,
        "authority_counters": zero_authority_counters(),
    }
    return {**base, **patch}


def _counterfactual(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "decision_id": "dec-1",
        "forecast_id": "fc-1",
        "counterfactual_refs": ["cf:1"],
        "natural_recovery_control_refs": [],
        "baselines": {
            "action": {},
            "no_action": {},
            "investigate_more": {},
            "safe_null": {},
        },
        "avoided_impact": 10.0,
        "useful_delay": 2.0,
        "rollback_cost": 1.0,
        "false_positive_cost": 0.0,
        "alert_fatigue_cost": 0.0,
        "operator_burden": 1.0,
        "intervention_harm": 0.0,
        "uncertainty_penalty": 1.0,
        "treatment_control_comparable": True,
        "confidence": "medium",
        "natural_recovery": False,
        "censored_horizon": False,
        "ambiguous_attribution": False,
        "rollback_recovery": False,
        "outcome_label": "prevented",
        "rejected_credit_reasons": [],
        "authority_counters": zero_authority_counters(),
    }
    return evaluate_prevention_utility({**base, **patch})


def test_fatigue_ledger_reports_required_counters_and_hash() -> None:
    ledger = build_fatigue_ledger(_ledger())

    assert ledger["ledger_hash"].startswith("sha256:")
    assert ledger["forecast_count"] == 3
    assert ledger["fatigue_budget_remaining"] == 2
    assert ledger["authority_counters"] == zero_authority_counters()


def test_duplicate_forecast_storm_is_suppressed_deterministically() -> None:
    decisions = suppress_duplicates([_forecast(forecast_id="fc-2"), _forecast(forecast_id="fc-1"), _forecast(forecast_id="fc-3")])

    assert [row["forecast_id"] for row in decisions] == ["fc-1", "fc-2", "fc-3"]
    assert decisions[0]["suppressed"] is False
    assert {row["suppression_reason"] for row in decisions[1:]} == {"duplicate_forecast_within_horizon"}
    assert {row["canonical_forecast_id"] for row in decisions} == {"fc-1"}


def test_guardrails_allow_valid_recommendation_with_counterfactual_evidence() -> None:
    decision = apply_prevention_guardrails(_forecast(), build_fatigue_ledger(_ledger()), _counterfactual(), route="prevent_l1_recommend")

    assert decision["blocked"] is False
    assert decision["route"] == "prevent_l1_recommend"
    assert decision["guardrail_hash"].startswith("sha256:")


@pytest.mark.parametrize(
    ("forecast_patch", "ledger_patch", "counterfactual_patch", "route", "blocker"),
    [
        ({"calibration_bucket": "poor"}, {}, {}, "prevent_l1_recommend", "low_calibration_actioned"),
        ({"ood_status": "far_ood"}, {}, {}, "prevent_l1_recommend", "abstain_required_but_actioned"),
        (
            {"evidence_strength": "standard"},
            {"recommendation_count": 5, "recommendation_budget": 5, "suppression_reason": "budget exhausted"},
            {},
            "prevent_l1_recommend",
            "fatigue_budget_exhausted",
        ),
        (
            {"evidence_strength": "standard"},
            {"false_positive_count": 5, "recommendation_count": 4, "recommendation_budget": 6, "suppression_reason": "fatigue high"},
            {},
            "prevent_l1_recommend",
            "evidence_strength_below_fatigue_threshold",
        ),
        ({"horizon_passed": True, "incident_occurred": False}, {}, {"outcome_label": "false_positive"}, "prevent_l1_recommend", "false_positive_hidden"),
        ({}, {"intervention_attempt_count": 1, "l3_attempt_budget": 1, "suppression_reason": "l3 cap"}, {}, "prevent_l3_local_sandbox", "l3_attempt_cap_bypassed"),
    ],
)
def test_guardrails_block_fatigue_calibration_ood_false_positive_and_l3_cap(
    forecast_patch: dict[str, object],
    ledger_patch: dict[str, object],
    counterfactual_patch: dict[str, object],
    route: str,
    blocker: str,
) -> None:
    decision = apply_prevention_guardrails(_forecast(**forecast_patch), build_fatigue_ledger(_ledger(**ledger_patch)), _counterfactual(**counterfactual_patch), route=route)

    assert decision["blocked"] is True
    assert blocker in decision["blockers"]
    assert decision["route"] in {"investigate_more", "abstain_fail_closed"}


def test_fatigue_budget_violation_without_suppression_is_rejected() -> None:
    with pytest.raises(P121GuardrailError, match="fatigue_budget_violation_without_suppression"):
        build_fatigue_ledger(_ledger(recommendation_count=4, recommendation_budget=3))


def test_guardrail_metrics_are_per_slice_not_aggregate_only() -> None:
    ledgers = [
        build_fatigue_ledger(_ledger()),
        build_fatigue_ledger(_ledger(ledger_id="fatigue-2", service_id="payments", false_positive_count=2, suppression_reason="false positive cluster")),
    ]
    metrics = guardrail_metrics(ledgers)

    assert metrics["aggregate"]["false_positive_count"] == 2
    assert len(metrics["slices"]) == 2
    assert {row["service_id"] for row in metrics["slices"]} == {"checkout", "payments"}
    assert metrics["metrics_hash"].startswith("sha256:")


def test_required_evidence_strength_increases_with_fatigue() -> None:
    assert required_evidence_strength(0.1) == "standard"
    assert required_evidence_strength(0.5) == "strong"
    assert required_evidence_strength(1.0) == "very_strong"
