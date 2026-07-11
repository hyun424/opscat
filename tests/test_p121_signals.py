from __future__ import annotations

import pytest

from app.services.p121_signals import (
    P121SignalError,
    build_forecast,
    build_leading_indicator,
    evaluate_intervention_eligibility,
    indicator_non_action_reason,
    zero_authority_counters,
)

HASH = "sha256:" + "a" * 64


def _indicator(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "indicator_id": "ind-1",
        "source_id": "src-local",
        "system_id": "sys-a",
        "service_id": "checkout",
        "observed_at": "2026-07-12T00:05:00Z",
        "window_start": "2026-07-12T00:00:00Z",
        "window_end": "2026-07-12T00:10:00Z",
        "signal_family": "latency",
        "signal_name": "p95_latency",
        "normalized_value": 0.8,
        "baseline_ref": "baseline:checkout:p95",
        "deviation_score": 2.4,
        "trend_ref": "trend:checkout:p95",
        "seasonality_ref": "seasonality:weekday",
        "deploy_config_refs": ["deploy:42"],
        "topology_refs": ["svc:checkout"],
        "recurrence_refs": [],
        "missingness_status": "complete",
        "data_quality_status": "good",
        "evidence_ids": ["ev-1"],
        "artifact_hash": HASH,
        "authority_counters": zero_authority_counters(),
    }
    return {**base, **patch}


def _forecast(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "forecast_id": "fc-1",
        "indicator_ids": ["ind-1"],
        "failure_mode": "checkout_latency_slo_breach",
        "incident_family": "latency",
        "probability": 0.7,
        "calibrated_probability": 0.64,
        "calibration_bucket": "acceptable",
        "confidence_interval": {"lower": 0.55, "upper": 0.75},
        "horizon_start": "2026-07-12T00:30:00Z",
        "horizon_end": "2026-07-12T01:30:00Z",
        "minimum_useful_lead_time_seconds": 600,
        "forecast_created_at": "2026-07-12T00:00:00Z",
        "expires_at": "2026-07-12T00:20:00Z",
        "expected_impact": 100.0,
        "uncertainty_reasons": [],
        "ood_status": "in_distribution",
        "abstention_status": "not_abstained",
        "required_evidence_ids": ["ev-1"],
        "resolved_evidence_ids": ["ev-1"],
        "model_rule_version": "p121.rule.v1",
        "frozen_config_hash": HASH,
        "artifact_hash": HASH,
        "authority_counters": zero_authority_counters(),
    }
    return {**base, **patch}


def test_leading_indicator_is_hash_bound_and_exact_zero_authority() -> None:
    indicator = build_leading_indicator(_indicator())

    assert indicator["indicator_hash"].startswith("sha256:")
    assert indicator["authority_counters"] == zero_authority_counters()
    assert indicator_non_action_reason(indicator) is None


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"future_outcome_label": "incident"}, "forbidden_indicator_field"),
        ({"artifact_hash": "missing"}, "invalid_artifact_hash"),
        ({"duplicate_lineage_status": "unresolved"}, "unresolved_duplicate_lineage"),
        ({"system_identity_status": "ambiguous"}, "ambiguous_system_identity"),
        ({"authority_counters": {**zero_authority_counters(), "production_mutation_count": 1}}, "production_mutation_count_nonzero"),
    ],
)
def test_indicator_rejects_leakage_lineage_ambiguity_and_authority_drift(patch: dict[str, object], expected: str) -> None:
    with pytest.raises(P121SignalError, match=expected):
        build_leading_indicator(_indicator(**patch))


def test_recurrence_only_indicator_routes_to_non_action() -> None:
    indicator = build_leading_indicator(_indicator(recurrence_refs=["recurrence:old"], fresh_current_evidence=False))

    assert indicator_non_action_reason(indicator) == "recurrence_without_fresh_evidence"


def test_forecast_becomes_candidate_only_with_valid_horizon_and_evidence() -> None:
    forecast = build_forecast(_forecast())

    decision = evaluate_intervention_eligibility(forecast, now="2026-07-12T00:10:00Z")

    assert decision == {"route": "candidate", "eligible": True, "reason": "eligible_with_evidence"}
    assert forecast["forecast_hash"].startswith("sha256:")


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"horizon_start": "2026-07-12T00:05:00Z"}, "negative_or_insufficient_lead_time"),
        ({"horizon_end": "2026-07-12T00:20:00Z", "horizon_start": "2026-07-12T00:20:00Z"}, "invalid_horizon"),
        ({"calibration_bucket": "poor"}, "low_calibration_actioned"),
        ({"ood_status": "far_ood"}, "high_ood_actioned"),
        ({"resolved_evidence_ids": []}, "required_evidence_missing"),
    ],
)
def test_forecast_red_cases_fail_closed_or_investigate_more(patch: dict[str, object], reason: str) -> None:
    if reason in {"negative_or_insufficient_lead_time", "invalid_horizon"}:
        with pytest.raises(P121SignalError, match=reason):
            build_forecast(_forecast(**patch))
        return

    forecast = build_forecast(_forecast(**patch))
    decision = evaluate_intervention_eligibility(forecast, now="2026-07-12T00:10:00Z")

    assert decision["eligible"] is False
    assert decision["reason"] == reason


def test_expired_forecast_cannot_be_reused_for_action() -> None:
    forecast = build_forecast(_forecast())

    decision = evaluate_intervention_eligibility(forecast, now="2026-07-12T00:21:00Z")

    assert decision == {"route": "abstain_fail_closed", "eligible": False, "reason": "expired_forecast"}
