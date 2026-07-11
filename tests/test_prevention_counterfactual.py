from __future__ import annotations

import importlib
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_counterfactual")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P108 RED: missing prevention counterfactual module ({exc}).", pytrace=False)


def _estimate(episode: dict[str, Any]) -> dict[str, Any]:
    estimator = getattr(_api(), "estimate_counterfactual_effect", None)
    if estimator is None:
        pytest.fail("P108 RED: expose estimate_counterfactual_effect(episode).", pytrace=False)
    result = estimator(episode)
    assert isinstance(result, dict)
    return result


def _base_episode() -> dict[str, Any]:
    return {
        "episode_id": "p108-cf-001",
        "incident_threshold": 0.7,
        "minimum_useful_delay_seconds": 300,
        "impact_scale": 1000,
        "treatment": {
            "cohort_fingerprint": "sha256:cohort-a",
            "window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:30:00Z"},
            "sample_count": 40,
            "telemetry_complete": True,
            "max_severity": 0.2,
            "incident_at": None,
            "recovered_without_intervention": False,
        },
        "control": {
            "cohort_fingerprint": "sha256:cohort-a",
            "window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:30:00Z"},
            "sample_count": 42,
            "telemetry_complete": True,
            "max_severity": 0.9,
            "incident_at": "2026-07-10T00:04:00Z",
            "recovered_without_intervention": False,
        },
    }


def test_counterfactual_estimates_bounded_prevented_effect_and_avoided_impact() -> None:
    result = _estimate(_base_episode())

    assert result["status"] == "identified"
    assert result["comparable"] is True
    assert result["effect_direction"] == "beneficial"
    assert result["effect_size"] == pytest.approx(0.7)
    assert result["useful_delay_seconds"] is None
    assert result["avoided_impact"] == pytest.approx(700.0)
    assert result["confidence"] == "high"


def test_counterfactual_computes_useful_delay_when_both_cohorts_fail() -> None:
    episode = _base_episode()
    episode["treatment"]["max_severity"] = 0.8
    episode["treatment"]["incident_at"] = "2026-07-10T00:12:00Z"

    result = _estimate(episode)

    assert result["status"] == "identified"
    assert result["effect_direction"] == "beneficial"
    assert result["useful_delay_seconds"] == 480
    assert result["confidence"] == "high"


def test_counterfactual_missing_or_incomparable_control_is_not_identifiable() -> None:
    missing_control = _base_episode()
    missing_control.pop("control")
    assert _estimate(missing_control)["status"] == "not_identifiable"

    incomparable = _base_episode()
    incomparable["control"]["cohort_fingerprint"] = "sha256:other"
    result = _estimate(incomparable)

    assert result["status"] == "not_identifiable"
    assert result["comparable"] is False
    assert "fingerprint" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize(
    ("cohort", "telemetry_value"),
    [
        ("treatment", False),
        ("control", False),
        ("treatment", None),
        ("control", None),
        ("treatment", "unknown"),
        ("control", "unknown"),
    ],
)
def test_counterfactual_requires_explicit_complete_telemetry_for_both_cohorts(cohort: str, telemetry_value: Any) -> None:
    episode = _base_episode()
    if telemetry_value is None:
        episode[cohort].pop("telemetry_complete")
    else:
        episode[cohort]["telemetry_complete"] = telemetry_value

    result = _estimate(episode)

    assert result["status"] == "not_identifiable"
    assert result["comparable"] is False
    assert result["effect_direction"] == "unknown"
    assert result["avoided_impact"] == 0
    assert "telemetry" in " ".join(result["reasons"]).lower()


def test_counterfactual_natural_recovery_receives_no_avoided_impact_credit() -> None:
    episode = _base_episode()
    episode["treatment"]["max_severity"] = 0.1
    episode["control"]["max_severity"] = 0.1
    episode["control"]["incident_at"] = None
    episode["treatment"]["recovered_without_intervention"] = True
    episode["control"]["recovered_without_intervention"] = True

    result = _estimate(episode)

    assert result["status"] == "identified"
    assert result["effect_direction"] == "neutral"
    assert result["avoided_impact"] == 0
    assert result["natural_recovery"] is True
