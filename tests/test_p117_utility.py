from __future__ import annotations

from typing import Any

import pytest

from app.services.p117_utility import (
    P117UtilityError,
    calibrate_confidence,
    compute_expected_utility,
    select_label_from_utility,
)


def _component(name: str, value: float, *, low: float | None = None, high: float | None = None) -> dict[str, object]:
    return {
        "name": name,
        "numerator": value,
        "denominator": 1,
        "value": value,
        "nullable": False,
        "interval": [value if low is None else low, value if high is None else high],
        "scenario_family": "deploy_config",
        "action_family": "restart",
        "split": "development",
        "artifact_hash": "sha256:" + "a" * 64,
    }


def test_expected_utility_preserves_components_and_subtracts_penalties() -> None:
    report = compute_expected_utility(
        measured_benefit_vs_no_action=_component("measured_benefit_vs_no_action", 0.80, low=0.50, high=0.90),
        expected_harm=_component("expected_harm", 0.10),
        uncertainty_penalty=_component("uncertainty_penalty", 0.05),
        contradiction_penalty=_component("contradiction_penalty", 0.04),
        missing_evidence_penalty=_component("missing_evidence_penalty", 0.02),
        authority_penalty=_component("authority_penalty", 0.0),
        natural_recovery_dominates=False,
    ).to_dict()

    assert report["expected_utility"] == pytest.approx(0.59)
    assert report["utility_interval"][0] > 0
    assert report["components"]["measured_benefit_vs_no_action"]["denominator"] == 1
    assert report["components"]["authority_penalty"]["value"] == 0.0


def test_utility_rejects_missing_denominator_nullable_zero_coercion_and_natural_recovery_credit() -> None:
    bad_denominator = _component("measured_benefit_vs_no_action", 0.8)
    bad_denominator["denominator"] = 0
    with pytest.raises(P117UtilityError, match="missing_denominator"):
        compute_expected_utility(
            measured_benefit_vs_no_action=bad_denominator,
            expected_harm=_component("expected_harm", 0.1),
            uncertainty_penalty=_component("uncertainty_penalty", 0.1),
            contradiction_penalty=_component("contradiction_penalty", 0.0),
            missing_evidence_penalty=_component("missing_evidence_penalty", 0.0),
            authority_penalty=_component("authority_penalty", 0.0),
            natural_recovery_dominates=False,
        )

    nullable = _component("measured_benefit_vs_no_action", 0.0)
    nullable["nullable"] = True
    nullable["value"] = None
    with pytest.raises(P117UtilityError, match="nullable_metric_unevaluable"):
        compute_expected_utility(
            measured_benefit_vs_no_action=nullable,
            expected_harm=_component("expected_harm", 0.1),
            uncertainty_penalty=_component("uncertainty_penalty", 0.1),
            contradiction_penalty=_component("contradiction_penalty", 0.0),
            missing_evidence_penalty=_component("missing_evidence_penalty", 0.0),
            authority_penalty=_component("authority_penalty", 0.0),
            natural_recovery_dominates=False,
        )

    with pytest.raises(P117UtilityError, match="natural_recovery_dominates"):
        compute_expected_utility(
            measured_benefit_vs_no_action=_component("measured_benefit_vs_no_action", 0.8),
            expected_harm=_component("expected_harm", 0.1),
            uncertainty_penalty=_component("uncertainty_penalty", 0.1),
            contradiction_penalty=_component("contradiction_penalty", 0.0),
            missing_evidence_penalty=_component("missing_evidence_penalty", 0.0),
            authority_penalty=_component("authority_penalty", 0.0),
            natural_recovery_dominates=True,
        )


def test_calibration_reports_overall_and_per_family_ece() -> None:
    report = calibrate_confidence(
        [
            {"scenario_family": "deploy_config", "confidence": 0.9, "correct": True},
            {"scenario_family": "deploy_config", "confidence": 0.8, "correct": True},
            {"scenario_family": "queue", "confidence": 0.2, "correct": False},
            {"scenario_family": "queue", "confidence": 0.1, "correct": False},
        ],
        bin_count=2,
    )

    assert report["overall"]["denominator"] == 4
    assert report["overall"]["ece"] <= 0.15
    assert set(report["by_family"]) == {"deploy_config", "queue"}


@pytest.mark.parametrize(
    ("kwargs", "label", "reason"),
    [
        ({"prerequisites_complete": False}, "abstain", "prerequisites_incomplete"),
        ({"contraindications_present": True}, "abstain", "contraindication_present"),
        ({"confidence": 0.3}, "abstain", "low_confidence"),
        ({"measured_outcomes_present": False}, "abstain", "missing_measured_outcomes"),
        ({"authority_counter_total": 1}, "abstain", "authority_counter_nonzero"),
        ({"missing_required_evidence": True, "utility_interval": [0.2, 0.5]}, "investigate_more", "missing_required_evidence"),
        ({"utility_interval": [-0.1, 0.5]}, "abstain", "utility_interval_crosses_zero"),
        ({"expected_utility": -0.1, "utility_interval": [-0.4, -0.1]}, "no_action", "utility_not_positive"),
    ],
)
def test_selection_policy_forces_abstention_or_non_action_when_gates_fail(kwargs: dict[str, object], label: str, reason: str) -> None:
    base: dict[str, Any] = {
        "expected_utility": 0.5,
        "utility_interval": [0.2, 0.7],
        "confidence": 0.9,
        "confidence_threshold": 0.7,
        "prerequisites_complete": True,
        "contraindications_present": False,
        "missing_required_evidence": False,
        "measured_outcomes_present": True,
        "authority_counter_total": 0,
        "escalation_required": False,
    }
    decision = select_label_from_utility(**{**base, **kwargs})

    assert decision["selected_label"] == label
    assert decision["reason"] == reason


def test_selection_policy_allows_act_only_for_strictly_positive_measured_utility() -> None:
    decision = select_label_from_utility(
        expected_utility=0.5,
        utility_interval=[0.2, 0.7],
        confidence=0.9,
        confidence_threshold=0.7,
        prerequisites_complete=True,
        contraindications_present=False,
        missing_required_evidence=False,
        measured_outcomes_present=True,
        authority_counter_total=0,
        escalation_required=False,
    )

    assert decision == {"selected_label": "act", "reason": None}
