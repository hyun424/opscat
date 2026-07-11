"""Measured causal attribution, recurrence gate, and offline learning records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_operation_contract import exact_zero_authority_counters

P119_ATTRIBUTION_LABELS = frozenset({"action_helped", "no_action_recovered", "natural_recovery", "rollback_recovered", "action_harmed", "no_effect", "ambiguous", "invalid"})


@dataclass(frozen=True)
class P119AttributionResult:
    label: str
    recovery_eligible: bool
    recurrence_detected: bool
    action_delta: float | None
    control_delta: float | None
    reason: str
    attribution_hash: str


def attribute_p119_outcome(
    *,
    windows: Mapping[str, Any],
    controls_comparable: bool,
    contaminated: bool,
    guardrail_breach: bool,
    rollback_performed: bool,
    recurrence_detected: bool,
) -> P119AttributionResult:
    action = _number(windows.get("action"))
    no_action = _number(windows.get("no_action"))
    natural = _number(windows.get("natural_recovery"))
    if contaminated or not controls_comparable or action is None or no_action is None or natural is None:
        return _result("invalid" if contaminated else "ambiguous", False, recurrence_detected, action, None, "missing_or_contaminated_controls")
    control = max(no_action, natural)
    if rollback_performed:
        label, eligible, reason = "rollback_recovered", False, "rollback_is_safety_recovery"
    elif guardrail_breach or action < 0:
        label, eligible, reason = "action_harmed", False, "guardrail_or_negative_effect"
    elif natural > 0 and natural >= action:
        label, eligible, reason = "natural_recovery", False, "natural_control_dominates"
    elif no_action > 0 and no_action >= action:
        label, eligible, reason = "no_action_recovered", False, "no_action_control_dominates"
    elif action > control and action > 0:
        label, eligible, reason = "action_helped", not recurrence_detected, "action_beats_controls"
    else:
        label, eligible, reason = "no_effect", False, "no_positive_incremental_effect"
    if recurrence_detected:
        eligible = False
        reason += ":recurrence_detected"
    return _result(label, eligible, recurrence_detected, action, control, reason)


def build_p119_learning_record(
    *,
    incident_id: str,
    attribution: P119AttributionResult,
    denominator: int,
    split: str,
    fixture_version: str,
    seed: int,
    replay_ref: str,
) -> dict[str, Any]:
    if denominator <= 0 or split not in {"development", "holdout", "unseen"} or not replay_ref.startswith("sha256:"):
        raise ValueError("invalid_learning_record_provenance")
    record: dict[str, Any] = {
        "schema_version": "p119.offline_learning_record.v1",
        "incident_id": incident_id,
        "attribution": attribution.label,
        "recovery_eligible": attribution.recovery_eligible,
        "recurrence_detected": attribution.recurrence_detected,
        "denominator": denominator,
        "split": split,
        "fixture_version": fixture_version,
        "seed": seed,
        "replay_ref": replay_ref,
        "online_policy_write": False,
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
    record["record_hash"] = stable_hash(record)
    return record


def _result(label: str, eligible: bool, recurrence: bool, action: float | None, control: float | None, reason: str) -> P119AttributionResult:
    base = {"label": label, "recovery_eligible": eligible, "recurrence_detected": recurrence, "action_delta": action, "control_delta": control, "reason": reason}
    return P119AttributionResult(label, eligible, recurrence, action, control, reason, stable_hash(base))


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


__all__ = ["P119_ATTRIBUTION_LABELS", "P119AttributionResult", "attribute_p119_outcome", "build_p119_learning_record"]
