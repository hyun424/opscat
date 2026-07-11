from __future__ import annotations

import importlib
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_outcome_learner")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P108 RED: missing prevention outcome learner module ({exc}).", pytrace=False)


def _classify(episode: dict[str, Any]) -> dict[str, Any]:
    classifier = getattr(_api(), "classify_prevention_outcome", None)
    if classifier is None:
        pytest.fail("P108 RED: expose classify_prevention_outcome(episode).", pytrace=False)
    result = classifier(episode)
    assert isinstance(result, dict)
    return result


def _credit(episode: dict[str, Any]) -> dict[str, Any]:
    assigner = getattr(_api(), "assign_phase_credit", None)
    if assigner is None:
        pytest.fail("P108 RED: expose assign_phase_credit(episode).", pytrace=False)
    result = assigner(episode)
    assert isinstance(result, dict)
    return result


def _base_episode() -> dict[str, Any]:
    return {
        "episode_id": "p108-label-001",
        "incident_threshold": 0.7,
        "minimum_useful_delay_seconds": 300,
        "impact_scale": 1000,
        "horizon_complete": True,
        "conflicting_evidence": False,
        "phase_cutoffs": {
            "evidence_search": "2026-07-10T00:01:00Z",
            "forecast": "2026-07-10T00:02:00Z",
            "plan": "2026-07-10T00:03:00Z",
            "execution": "2026-07-10T00:05:00Z",
        },
        "evidence": [
            {"id": "e-search", "phase": "evidence_search", "observed_at": "2026-07-10T00:00:30Z", "supports": "risk_signal", "source": "replay"},
            {"id": "e-forecast", "phase": "forecast", "observed_at": "2026-07-10T00:01:30Z", "supports": "forecast", "source": "replay"},
            {"id": "e-plan", "phase": "plan", "observed_at": "2026-07-10T00:02:30Z", "supports": "plan", "source": "replay"},
            {"id": "e-execution", "phase": "execution", "observed_at": "2026-07-10T00:04:30Z", "supports": "execution", "source": "replay"},
            {"id": "future-scorer", "phase": "forecast", "observed_at": "2026-07-10T00:09:00Z", "supports": "forecast", "source": "private_scorer"},
        ],
        "treatment": {
            "cohort_fingerprint": "sha256:cohort-a",
            "window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:30:00Z"},
            "sample_count": 40,
            "telemetry_complete": True,
            "max_severity": 0.2,
            "incident_at": None,
            "guardrail_breached": False,
            "collateral_regression": False,
            "recovered_without_intervention": False,
        },
        "control": {
            "cohort_fingerprint": "sha256:cohort-a",
            "window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:30:00Z"},
            "sample_count": 42,
            "telemetry_complete": True,
            "max_severity": 0.9,
            "incident_at": "2026-07-10T00:04:00Z",
            "guardrail_breached": False,
            "collateral_regression": False,
            "recovered_without_intervention": False,
        },
    }


@pytest.mark.parametrize(
    ("mutator", "expected_label"),
    [
        (lambda e: None, "prevented"),
        (
            lambda e: (
                e["treatment"].update({"max_severity": 0.8, "incident_at": "2026-07-10T00:12:00Z"}),
                e["control"].update({"max_severity": 0.9, "incident_at": "2026-07-10T00:04:00Z"}),
            ),
            "delayed",
        ),
        (
            lambda e: (
                e["treatment"].update({"max_severity": 0.88, "incident_at": "2026-07-10T00:04:10Z"}),
                e["control"].update({"max_severity": 0.9, "incident_at": "2026-07-10T00:04:00Z"}),
            ),
            "unaffected",
        ),
        (
            lambda e: (
                e["treatment"].update({"max_severity": 0.1, "incident_at": None, "recovered_without_intervention": True}),
                e["control"].update({"max_severity": 0.1, "incident_at": None, "recovered_without_intervention": True}),
            ),
            "naturally_recovered",
        ),
        (lambda e: e["treatment"].update({"guardrail_breached": True}), "harmful"),
        (lambda e: e.pop("control"), "inconclusive"),
        (lambda e: e.update({"horizon_complete": False}), "censored"),
    ],
)
def test_outcome_classifier_covers_all_seven_conservative_labels(mutator: Any, expected_label: str) -> None:
    episode = _base_episode()
    mutator(episode)

    assert _classify(episode)["label"] == expected_label


def test_harm_conflict_and_censoring_take_precedence_over_optimistic_labels() -> None:
    harmful = _base_episode()
    harmful["treatment"]["guardrail_breached"] = True
    harmful["horizon_complete"] = False
    assert _classify(harmful)["label"] == "harmful"

    conflicting = _base_episode()
    conflicting["conflicting_evidence"] = True
    assert _classify(conflicting)["label"] == "inconclusive"

    censored = _base_episode()
    censored["horizon_complete"] = False
    assert _classify(censored)["label"] == "censored"


def test_missing_control_and_telemetry_loss_cannot_claim_prevention_or_delay() -> None:
    missing_control = _base_episode()
    missing_control.pop("control")
    assert _classify(missing_control)["label"] == "inconclusive"

    telemetry_loss = _base_episode()
    telemetry_loss["control"]["telemetry_complete"] = False
    result = _classify(telemetry_loss)

    assert result["label"] == "inconclusive"
    assert result["label"] not in {"prevented", "delayed"}


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
def test_outcome_requires_explicit_complete_telemetry_for_both_cohorts(cohort: str, telemetry_value: Any) -> None:
    episode = _base_episode()
    if telemetry_value is None:
        episode[cohort].pop("telemetry_complete")
    else:
        episode[cohort]["telemetry_complete"] = telemetry_value

    result = _classify(episode)

    assert result["label"] == "inconclusive"
    assert result["label"] not in {"prevented", "delayed"}
    assert result["counterfactual"]["status"] == "not_identifiable"
    assert "telemetry" in " ".join(result["reasons"]).lower()


def test_phase_credit_denies_positive_credit_when_telemetry_is_not_explicitly_complete() -> None:
    episode = _base_episode()
    episode["treatment"].pop("telemetry_complete")

    result = _credit(episode)

    assert result["label"] == "inconclusive"
    assert result["counterfactual"]["status"] == "not_identifiable"
    assert result["total_credit"] == 0


def test_phase_credit_is_evidence_bound_and_excludes_private_scorer_leakage() -> None:
    result = _credit(_base_episode())

    assert result["accepted"] is False
    assert result["label"] == "prevented"
    assert result["total_credit"] > 0
    assert result["phases"]["forecast"]["credit"] > 0
    assert result["phases"]["forecast"]["used_evidence_ids"] == ["e-forecast"]
    assert "future-scorer" in result["rejected_evidence_ids"]
    assert "private scorer" in " ".join(result["reasons"]).lower()


def test_harmful_inconclusive_and_censored_episodes_receive_no_positive_credit() -> None:
    harmful = _base_episode()
    harmful["treatment"]["guardrail_breached"] = True
    assert _credit(harmful)["total_credit"] <= 0

    inconclusive = _base_episode()
    inconclusive["conflicting_evidence"] = True
    assert _credit(inconclusive)["total_credit"] == 0

    censored = _base_episode()
    censored["horizon_complete"] = False
    assert _credit(censored)["total_credit"] == 0
