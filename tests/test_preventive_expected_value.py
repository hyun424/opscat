from __future__ import annotations

import importlib
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_expected_value")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing preventive expected-value module ({exc}).", pytrace=False)


def _score(api: Any, **kwargs: Any) -> Any:
    scorer = getattr(api, "score_preventive_candidate", None)
    if scorer is None:
        pytest.fail("P106 RED: expose score_preventive_candidate(...).", pytrace=False)
    return scorer(**kwargs)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def test_expected_value_uses_documented_component_formula() -> None:
    result = _score(
        _api(),
        probability=0.8,
        avoided_impact=10.0,
        intervention_harm=1.0,
        operational_cost=0.5,
        uncertainty_penalty=0.25,
        false_alert_penalty=0.75,
    )

    assert _get(result, "expected_value") == pytest.approx(5.5)
    assert _get(result, "components") == {
        "probability_x_avoided_impact": pytest.approx(8.0),
        "intervention_harm": pytest.approx(1.0),
        "operational_cost": pytest.approx(0.5),
        "uncertainty_penalty": pytest.approx(0.25),
        "false_alert_penalty": pytest.approx(0.75),
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"probability": 0.2, "avoided_impact": 10.0, "intervention_harm": 1.0, "operational_cost": 1.0, "uncertainty_penalty": 0.5, "false_alert_penalty": 1.0},
        {"probability": 0.9, "avoided_impact": 5.0, "intervention_harm": 6.0, "operational_cost": 0.5, "uncertainty_penalty": 0.2, "false_alert_penalty": 0.1},
        {"probability": 0.7, "avoided_impact": 8.0, "intervention_harm": 1.0, "operational_cost": 1.0, "uncertainty_penalty": 5.0, "false_alert_penalty": 0.1},
    ],
)
def test_negative_or_high_burden_expected_value_loses_to_observe(kwargs: dict[str, float]) -> None:
    result = _score(_api(), **kwargs)

    assert _get(result, "selected_baseline") in {"observe", "escalate"}
    assert _get(result, "eligible_for_intervention") is False


def test_irreversible_candidate_loses_even_when_expected_value_is_positive() -> None:
    result = _score(
        _api(),
        probability=0.95,
        avoided_impact=50.0,
        intervention_harm=1.0,
        operational_cost=1.0,
        uncertainty_penalty=0.1,
        false_alert_penalty=0.1,
        reversible=False,
    )

    assert _get(result, "eligible_for_intervention") is False
    assert "irreversible" in " ".join(_get(result, "reasons", []))


def test_ties_choose_lower_blast_radius_and_more_reversible_option() -> None:
    api = _api()
    ranker = getattr(api, "rank_preventive_candidates", None)
    if ranker is None:
        pytest.fail("P106 RED: expose rank_preventive_candidates(candidates).", pytrace=False)

    ranked = ranker(
        [
            {"candidate_id": "workspace", "expected_value": 3.0, "blast_radius_order": 3, "reversible": True},
            {"candidate_id": "local", "expected_value": 3.0, "blast_radius_order": 1, "reversible": True},
            {"candidate_id": "irreversible", "expected_value": 3.0, "blast_radius_order": 1, "reversible": False},
        ]
    )

    assert _get(ranked[0], "candidate_id") == "local"
    assert _get(ranked[0], "tie_break_trace")
