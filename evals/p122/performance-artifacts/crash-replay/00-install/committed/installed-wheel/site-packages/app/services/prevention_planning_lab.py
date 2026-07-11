"""Offline P106 treatment/control planning lab.

This module is intentionally simulation-only. It never calls execution
services; it only checks whether benchmark arms start from the same public
pre-treatment state.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_initial_state_bytes(public_initial_state: Mapping[str, Any], *, deterministic_seed: str) -> bytes:
    payload = {
        "deterministic_seed": deterministic_seed,
        "public_initial_state": public_initial_state,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def compute_initial_condition_fingerprint(
    public_initial_state: Mapping[str, Any],
    *,
    deterministic_seed: str,
    arm: str | None = None,
) -> str:
    del arm
    digest = hashlib.sha256(canonical_initial_state_bytes(public_initial_state, deterministic_seed=deterministic_seed)).hexdigest()
    return f"sha256:{digest}"


def evaluate_treatment_control_case(case: Mapping[str, Any]) -> dict[str, Any]:
    arms = case.get("arms")
    if not isinstance(arms, list) or len(arms) < 2:
        return _rejected("at least two benchmark arms are required")

    if case.get("cohort_interference"):
        return _rejected("cohort interference makes treatment/control arms non-comparable")
    if case.get("telemetry_loss"):
        return _rejected("telemetry loss makes treatment/control arms non-comparable")
    if case.get("natural_recovery_masquerading_as_treatment") or case.get("natural_recovery"):
        return _rejected("natural recovery cannot be scored as treatment effect")
    if case.get("noisy_false_positive") and not case.get("false_alert_denominator_present", True):
        return _rejected("noisy false positives require a false-alert denominator")

    public_initial_state = case.get("public_initial_state")
    if not isinstance(public_initial_state, Mapping):
        return _rejected("public_initial_state is required")
    deterministic_seed = str(case.get("deterministic_seed", ""))
    if not deterministic_seed:
        return _rejected("deterministic_seed is required")

    recomputed: dict[str, str] = {}
    canonical_payloads: dict[str, str] = {}
    for raw_arm in arms:
        if not isinstance(raw_arm, Mapping) or not raw_arm.get("arm"):
            return _rejected("each arm requires an arm name")
        arm_name = str(raw_arm["arm"])
        state = copy.deepcopy(dict(public_initial_state))
        mutation = raw_arm.get("arm_specific_public_state")
        if isinstance(mutation, Mapping):
            state.update(mutation)
        recomputed[arm_name] = compute_initial_condition_fingerprint(state, deterministic_seed=deterministic_seed, arm=arm_name)
        canonical_payloads[arm_name] = canonical_initial_state_bytes(state, deterministic_seed=deterministic_seed).decode("utf-8")

    if len(set(canonical_payloads.values())) != 1 or len(set(recomputed.values())) != 1:
        return _rejected("initial condition fingerprint mismatch across arms", recomputed, canonical_payloads)

    declared = {
        str(arm["arm"]): arm.get("declared_initial_condition_fingerprint")
        for arm in arms
        if isinstance(arm, Mapping) and arm.get("declared_initial_condition_fingerprint") not in (None, "computed_by_lab")
    }
    if declared and len(set(declared.values())) != 1:
        return _rejected("declared initial condition fingerprint mismatch across arms", recomputed, canonical_payloads)

    return {
        "case_id": case.get("case_id"),
        "comparable": True,
        "planner_executed": True,
        "scorer_executed": True,
        "initial_condition_fingerprints": recomputed,
        "canonical_initial_state_bytes": canonical_payloads,
        "execution_enabled": False,
        "simulation_only": True,
        "p107_required_for_execution": True,
    }


def _rejected(
    reason: str,
    fingerprints: Mapping[str, str] | None = None,
    canonical_payloads: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "comparable": False,
        "planner_executed": False,
        "scorer_executed": False,
        "rejection_reason": reason,
        "initial_condition_fingerprints": dict(fingerprints or {}),
        "canonical_initial_state_bytes": dict(canonical_payloads or {}),
        "execution_enabled": False,
        "simulation_only": True,
        "p107_required_for_execution": True,
    }
