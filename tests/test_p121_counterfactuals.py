from __future__ import annotations

import pytest

from app.services.p121_counterfactuals import P121CounterfactualError, evaluate_prevention_utility
from app.services.p121_signals import zero_authority_counters


def _utility_case(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "decision_id": "dec-1",
        "forecast_id": "fc-1",
        "counterfactual_refs": ["cf:checkout:matched"],
        "natural_recovery_control_refs": [],
        "baselines": {
            "action": {"expected_impact": 10},
            "no_action": {"expected_impact": 90},
            "investigate_more": {"expected_impact": 50},
            "safe_null": {"expected_impact": 60},
        },
        "avoided_impact": 80.0,
        "useful_delay": 10.0,
        "rollback_cost": 2.0,
        "false_positive_cost": 1.0,
        "alert_fatigue_cost": 1.0,
        "operator_burden": 2.0,
        "intervention_harm": 0.0,
        "uncertainty_penalty": 5.0,
        "treatment_control_comparable": True,
        "confidence": "high",
        "natural_recovery": False,
        "censored_horizon": False,
        "ambiguous_attribution": False,
        "rollback_recovery": False,
        "outcome_label": "prevented",
        "rejected_credit_reasons": [],
        "authority_counters": zero_authority_counters(),
    }
    return {**base, **patch}


def test_positive_utility_requires_complete_baselines_and_identifiable_counterfactual() -> None:
    result = evaluate_prevention_utility(_utility_case())

    assert result["raw_utility"] == 79.0
    assert result["utility"] == 79.0
    assert result["promotion_allowed"] is True
    assert result["denominator_visible"] is True
    assert result["counterfactual_hash"].startswith("sha256:")


@pytest.mark.parametrize(
    ("patch", "blocker"),
    [
        ({"treatment_control_comparable": False}, "weak_comparability"),
        ({"natural_recovery": True, "natural_recovery_control_refs": ["control:natural"]}, "natural_recovery_credited"),
        ({"censored_horizon": True, "outcome_label": "censored"}, "censored_horizon_credited"),
        ({"ambiguous_attribution": True, "outcome_label": "inconclusive"}, "ambiguous_attribution"),
        ({"rollback_recovery": True, "outcome_label": "rollback_recovered"}, "rollback_recovery_credit_rejected"),
        ({"outcome_label": "false_positive"}, "false_positive_credit_rejected"),
        ({"outcome_label": "harmful", "intervention_harm": 20.0}, "treatment_harm_promoted"),
        ({"rejected_credit_reasons": ["false_prevention_credit"]}, "false_prevention_credit"),
    ],
)
def test_no_credit_outcomes_block_promotion_even_when_raw_utility_is_positive(patch: dict[str, object], blocker: str) -> None:
    result = evaluate_prevention_utility(_utility_case(**patch))

    assert result["raw_utility"] > 0
    assert result["utility"] == 0.0
    assert result["promotion_allowed"] is False
    assert blocker in result["rejected_credit_reasons"]


def test_omitted_no_action_investigate_or_safe_null_baseline_is_rejected() -> None:
    baselines = {
        "action": {"expected_impact": 10},
        "no_action": {"expected_impact": 90},
        "investigate_more": {"expected_impact": 50},
    }

    with pytest.raises(P121CounterfactualError, match="missing_counterfactual_baseline:safe_null"):
        evaluate_prevention_utility(_utility_case(baselines=baselines))


def test_nonzero_authority_counter_rejected() -> None:
    counters = zero_authority_counters()
    counters["freeform_action_execution_count"] = 1

    with pytest.raises(P121CounterfactualError, match="freeform_action_execution_count_nonzero"):
        evaluate_prevention_utility(_utility_case(authority_counters=counters))
