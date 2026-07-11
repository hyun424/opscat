"""P121 counterfactual prevention utility and baseline contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121SignalError, validate_exact_zero_authority, zero_authority_counters

P121_COUNTERFACTUAL_SCHEMA_VERSION = "p121.counterfactual_prevention.v1"
BASELINES = frozenset({"action", "no_action", "investigate_more", "safe_null"})
OUTCOME_LABELS = frozenset({"prevented", "delayed", "unaffected", "naturally_recovered", "harmful", "false_positive", "inconclusive", "censored", "rollback_recovered", "aborted_fail_closed"})
NO_CREDIT_OUTCOMES = frozenset({"naturally_recovered", "false_positive", "inconclusive", "censored", "rollback_recovered", "aborted_fail_closed"})


class P121CounterfactualError(ValueError):
    """Raised when counterfactual prevention utility fails closed."""


def evaluate_prevention_utility(data: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate action utility against no-action, investigate-more, and safe-null baselines."""

    baselines = _baselines(data.get("baselines"))
    rejected_credit_reasons = _text_list(data.get("rejected_credit_reasons", []), allow_empty=True)
    outcome_label = _text(data, "outcome_label")
    if outcome_label not in OUTCOME_LABELS:
        raise P121CounterfactualError("invalid_outcome_label")
    comparable = bool(data.get("treatment_control_comparable"))
    natural_recovery = bool(data.get("natural_recovery"))
    censored_horizon = bool(data.get("censored_horizon"))
    ambiguous_attribution = bool(data.get("ambiguous_attribution"))
    rollback_recovery = outcome_label == "rollback_recovered" or bool(data.get("rollback_recovery"))
    components = {
        "avoided_impact": _number(data, "avoided_impact"),
        "useful_delay": _number(data, "useful_delay"),
        "rollback_cost": _number(data, "rollback_cost"),
        "false_positive_cost": _number(data, "false_positive_cost"),
        "alert_fatigue_cost": _number(data, "alert_fatigue_cost"),
        "operator_burden": _number(data, "operator_burden"),
        "intervention_harm": _number(data, "intervention_harm"),
        "uncertainty_penalty": _number(data, "uncertainty_penalty"),
    }
    gross = components["avoided_impact"] + components["useful_delay"]
    costs = (
        components["rollback_cost"]
        + components["false_positive_cost"]
        + components["alert_fatigue_cost"]
        + components["operator_burden"]
        + components["intervention_harm"]
        + components["uncertainty_penalty"]
    )
    utility = round(gross - costs, 6)
    blockers = _promotion_blockers(
        comparable=comparable,
        natural_recovery=natural_recovery,
        censored_horizon=censored_horizon,
        ambiguous_attribution=ambiguous_attribution,
        rollback_recovery=rollback_recovery,
        outcome_label=outcome_label,
        components=components,
        baselines=baselines,
        rejected_credit_reasons=rejected_credit_reasons,
    )
    payload: dict[str, Any] = {
        "schema_version": P121_COUNTERFACTUAL_SCHEMA_VERSION,
        "decision_id": _text(data, "decision_id"),
        "forecast_id": _text(data, "forecast_id"),
        "counterfactual_refs": _text_list(data.get("counterfactual_refs")),
        "natural_recovery_control_refs": _text_list(data.get("natural_recovery_control_refs"), allow_empty=not natural_recovery),
        "baselines": baselines,
        "components": components,
        "utility": utility if not blockers else min(utility, 0.0),
        "raw_utility": utility,
        "treatment_control_comparable": comparable,
        "confidence": _text(data, "confidence"),
        "natural_recovery": natural_recovery,
        "censored_horizon": censored_horizon,
        "ambiguous_attribution": ambiguous_attribution,
        "rollback_recovery": rollback_recovery,
        "outcome_label": outcome_label,
        "rejected_credit_reasons": sorted(set([*rejected_credit_reasons, *blockers])),
        "promotion_allowed": not blockers and utility > 0.0,
        "denominator_visible": True,
        "authority_counters": dict(data.get("authority_counters", zero_authority_counters())),
    }
    validate_counterfactual_result(payload)
    payload["counterfactual_hash"] = stable_hash(payload)
    return payload


def validate_counterfactual_result(result: Mapping[str, Any]) -> None:
    """Validate denominator-visible counterfactual output and exact-zero authority."""

    if result.get("schema_version") != P121_COUNTERFACTUAL_SCHEMA_VERSION:
        raise P121CounterfactualError("invalid_counterfactual_schema")
    if set(str(key) for key in _mapping(result.get("baselines"))) != BASELINES:
        raise P121CounterfactualError("missing_counterfactual_baseline")
    if result.get("outcome_label") not in OUTCOME_LABELS:
        raise P121CounterfactualError("invalid_outcome_label")
    if result.get("denominator_visible") is not True:
        raise P121CounterfactualError("counterfactual_not_denominator_visible")
    if result.get("promotion_allowed") is True and _sequence(result.get("rejected_credit_reasons")):
        raise P121CounterfactualError("rejected_credit_promoted")
    if result.get("promotion_allowed") is True and float(result.get("utility", 0.0)) <= 0.0:
        raise P121CounterfactualError("nonpositive_utility_promoted")
    try:
        validate_exact_zero_authority(result.get("authority_counters"))
    except P121SignalError as exc:
        raise P121CounterfactualError(str(exc)) from exc


def _promotion_blockers(
    *,
    comparable: bool,
    natural_recovery: bool,
    censored_horizon: bool,
    ambiguous_attribution: bool,
    rollback_recovery: bool,
    outcome_label: str,
    components: Mapping[str, float],
    baselines: Mapping[str, Any],
    rejected_credit_reasons: Sequence[str],
) -> list[str]:
    blockers: list[str] = []
    if set(str(key) for key in baselines) != BASELINES:
        blockers.append("missing_baseline")
    if not comparable:
        blockers.append("weak_comparability")
    if natural_recovery:
        blockers.append("natural_recovery_credited")
    if censored_horizon:
        blockers.append("censored_horizon_credited")
    if ambiguous_attribution:
        blockers.append("ambiguous_attribution")
    if rollback_recovery:
        blockers.append("rollback_recovery_credit_rejected")
    if outcome_label in NO_CREDIT_OUTCOMES:
        blockers.append(f"{outcome_label}_credit_rejected")
    if outcome_label == "harmful" or components["intervention_harm"] > components["avoided_impact"]:
        blockers.append("treatment_harm_promoted")
    if outcome_label == "prevented" and "false_prevention_credit" in rejected_credit_reasons:
        blockers.append("false_prevention_credit")
    return blockers


def _baselines(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise P121CounterfactualError("missing_counterfactual_baselines")
    keys = set(str(key) for key in value)
    if keys != BASELINES:
        missing = sorted(BASELINES - keys)
        raise P121CounterfactualError(f"missing_counterfactual_baseline:{missing[0] if missing else 'unknown'}")
    return {str(key): value[key] for key in sorted(value)}


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P121CounterfactualError(f"missing_{key}")
    return value


def _text_list(value: Any, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or (not value and not allow_empty):
        raise P121CounterfactualError("missing_text_list")
    result = [str(item) for item in value]
    if any(not item.strip() for item in result):
        raise P121CounterfactualError("invalid_text_list")
    return result


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise P121CounterfactualError(f"invalid_{key}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise P121CounterfactualError(f"invalid_{key}") from exc
    if result < 0.0:
        raise P121CounterfactualError(f"invalid_{key}")
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
