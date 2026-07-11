"""P107 treatment/control cohort fingerprint validation.

The validator is intentionally local and deterministic. It reuses the P106
public initial-condition fingerprint semantics and only returns a bound cohort
when treatment/control arms are comparable before any attempt can run.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from app.services.prevention_planning_lab import compute_initial_condition_fingerprint


def validate_canary_cohort(case: Mapping[str, Any]) -> dict[str, Any]:
    telemetry_window = case.get("telemetry_window")
    if not isinstance(telemetry_window, Mapping) or telemetry_window.get("complete") is not True:
        return _rejected("telemetry window is missing, stale, or incomplete", telemetry_loss_success_claim_count=0)

    if case.get("natural_recovery"):
        return _rejected("natural recovery cannot masquerade as preventive effect")
    if case.get("cohort_interference"):
        return _rejected("cohort interference detected before attempt")
    if case.get("false_alert_denominator_present") is not True:
        return _rejected("false-alert denominator is required")

    public_initial_state = case.get("public_initial_state")
    if not isinstance(public_initial_state, Mapping):
        return _rejected("public initial state is required for fingerprint binding")

    seed = str(case.get("deterministic_seed", ""))
    if not seed:
        return _rejected("deterministic seed is required for cohort fingerprint binding")

    arms = case.get("arms")
    if not isinstance(arms, list) or {arm.get("arm") for arm in arms if isinstance(arm, Mapping)} != {"treatment", "control"}:
        return _rejected("bounded treatment and control arms are required")

    bounds = case.get("cohort_bounds")
    if not isinstance(bounds, Mapping):
        return _rejected("cohort bounds are required")

    service = str(case.get("service", ""))
    environment = str(case.get("environment", ""))
    allowed_services = {str(item) for item in bounds.get("services", [])}
    allowed_environments = {str(item) for item in bounds.get("environments", [])}
    if service not in allowed_services or environment not in allowed_environments:
        return _rejected("cohort binding escapes declared service or environment bounds", cohort_escape_accepted_count=0)

    fingerprints: dict[str, str] = {}
    selectors: dict[str, Mapping[str, Any]] = {}
    for raw_arm in arms:
        if not isinstance(raw_arm, Mapping):
            return _rejected("cohort arm must be a mapping")
        arm_name = str(raw_arm["arm"])
        selector = raw_arm.get("selector")
        if not isinstance(selector, Mapping):
            return _rejected("cohort arm selector is required")
        selectors[arm_name] = selector
        if str(selector.get("service", "")) not in allowed_services or str(selector.get("environment", "")) not in allowed_environments:
            return _rejected("cohort selector escapes declared bounds", cohort_escape_accepted_count=0)

        state = dict(public_initial_state)
        mutation = raw_arm.get("arm_specific_public_state")
        if isinstance(mutation, Mapping):
            state.update(mutation)
        fingerprints[arm_name] = compute_initial_condition_fingerprint(state, deterministic_seed=seed, arm=arm_name)

    if len(set(fingerprints.values())) != 1:
        return _rejected(
            "treatment/control initial condition fingerprint mismatch",
            treatment_control_fingerprints=fingerprints,
        )

    binding = {
        "episode_id": case.get("episode_id"),
        "service": service,
        "environment": environment,
        "telemetry_window": dict(telemetry_window),
        "deterministic_seed": seed,
        "treatment_selector": dict(selectors["treatment"]),
        "control_selector": dict(selectors["control"]),
        "primary_metric": case.get("primary_metric"),
        "guardrails": case.get("guardrails", {}),
        "cohort_bounds": dict(bounds),
        "treatment_control_fingerprints": fingerprints,
    }
    return {
        "accepted": True,
        "attempt_allowed": True,
        "treatment_control_fingerprints": fingerprints,
        "cohort_fingerprint_hash": _sha256(binding),
        "episode_binding": binding,
        "cohort_escape_accepted_count": 0,
        "telemetry_loss_success_claim_count": 0,
    }


def _rejected(reason: str, **extra: Any) -> dict[str, Any]:
    result = {
        "accepted": False,
        "attempt_allowed": False,
        "rejection_reason": reason,
        "cohort_escape_accepted_count": 0,
        "telemetry_loss_success_claim_count": 0,
    }
    result.update(extra)
    return result


def _sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
