from __future__ import annotations

import importlib
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_cohort_fingerprints")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention cohort fingerprint module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _valid_case() -> dict[str, Any]:
    return {
        "episode_id": "episode-fp-001",
        "service": "checkout-api",
        "environment": "local",
        "deterministic_seed": "p107-fixed-seed",
        "primary_metric": "false_alert_rate",
        "guardrails": {"latency_p95_ms": {"max": 250}},
        "cohort_bounds": {
            "services": ["checkout-api"],
            "environments": ["local"],
            "max_treatment_size": 1,
            "max_control_size": 1,
        },
        "telemetry_window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:05:00Z", "complete": True},
        "false_alert_denominator_present": True,
        "public_initial_state": {
            "error_rate": 0.02,
            "request_rate": 120,
            "rollback_state": "ready",
            "public_version_hash": "sha256:version-a",
        },
        "arms": [
            {
                "arm": "treatment",
                "selector": {"service": "checkout-api", "environment": "local", "instance": "a"},
                "declared_initial_condition_fingerprint": "computed_by_p107",
            },
            {
                "arm": "control",
                "selector": {"service": "checkout-api", "environment": "local", "instance": "b"},
                "declared_initial_condition_fingerprint": "computed_by_p107",
            },
        ],
    }


def test_equivalent_treatment_control_fingerprints_required() -> None:
    result = _api().validate_canary_cohort(_valid_case())

    assert _get(result, "accepted") is True
    fingerprints = _get(result, "treatment_control_fingerprints")
    assert set(fingerprints) == {"treatment", "control"}
    assert len(set(fingerprints.values())) == 1
    assert _get(result, "cohort_fingerprint_hash", "").startswith("sha256:")
    episode_fields = _get(result, "episode_binding")
    assert _get(episode_fields, "service") == "checkout-api"
    assert _get(episode_fields, "environment") == "local"
    assert _get(episode_fields, "telemetry_window") == _valid_case()["telemetry_window"]


def test_declared_fingerprint_cannot_mask_arm_specific_mutation() -> None:
    case = _valid_case()
    for arm in case["arms"]:
        arm["declared_initial_condition_fingerprint"] = "sha256:forged-same-value"
    case["arms"][0]["arm_specific_public_state"] = {"rollback_state": "not-ready"}

    result = _api().validate_canary_cohort(case)

    assert _get(result, "accepted") is False
    assert _get(result, "attempt_allowed") is False
    assert "fingerprint" in _get(result, "rejection_reason", "")


def test_cohort_escape_rejected() -> None:
    case = _valid_case()
    case["arms"][0]["selector"] = {"service": "billing-api", "environment": "local", "instance": "escape"}

    result = _api().validate_canary_cohort(case)

    assert _get(result, "accepted") is False
    assert _get(result, "attempt_allowed") is False
    assert _get(result, "cohort_escape_accepted_count") == 0
    assert "cohort" in _get(result, "rejection_reason", "")


def test_telemetry_loss_before_attempt_rejects() -> None:
    case = _valid_case()
    case["telemetry_window"] = {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:05:00Z", "complete": False}

    result = _api().validate_canary_cohort(case)

    assert _get(result, "accepted") is False
    assert _get(result, "attempt_allowed") is False
    assert _get(result, "telemetry_loss_success_claim_count") == 0
    assert "telemetry" in _get(result, "rejection_reason", "")


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("natural_recovery", True, "natural recovery"),
        ("cohort_interference", True, "interference"),
        ("false_alert_denominator_present", False, "denominator"),
    ],
)
def test_natural_recovery_or_interference_rejected(field: str, value: Any, expected_reason: str) -> None:
    case = _valid_case()
    case[field] = value

    result = _api().validate_canary_cohort(case)

    assert _get(result, "accepted") is False
    assert _get(result, "attempt_allowed") is False
    assert expected_reason in _get(result, "rejection_reason", "")
