"""P121 false-positive, alert-fatigue, and calibration guardrails."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_counterfactuals import P121_COUNTERFACTUAL_SCHEMA_VERSION
from app.services.p121_signals import ACTIONABLE_CALIBRATION_BUCKETS, ACTIONABLE_OOD_STATUSES, P121SignalError, validate_exact_zero_authority, zero_authority_counters

P121_FATIGUE_LEDGER_SCHEMA_VERSION = "p121.fatigue_ledger.v1"
P121_GUARDRAIL_DECISION_SCHEMA_VERSION = "p121.guardrail_decision.v1"


class P121GuardrailError(ValueError):
    """Raised when P121 guardrail inputs violate false-positive or fatigue contracts."""


def build_fatigue_ledger(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a per-system/service/family fatigue ledger with deterministic counters."""

    recommendation_budget = _nonnegative_int(data, "recommendation_budget")
    l3_attempt_budget = _nonnegative_int(data, "l3_attempt_budget")
    forecast_count = _nonnegative_int(data, "forecast_count")
    recommendation_count = _nonnegative_int(data, "recommendation_count")
    intervention_attempt_count = _nonnegative_int(data, "intervention_attempt_count")
    false_positive_count = _nonnegative_int(data, "false_positive_count")
    abstention_count = _nonnegative_int(data, "abstention_count")
    operator_acknowledgement_count = _nonnegative_int(data, "operator_acknowledgement_count")
    duplicate_suppression_count = _nonnegative_int(data, "duplicate_suppression_count")
    fatigue_score = round(
        (recommendation_count * 1.0 + intervention_attempt_count * 2.0 + false_positive_count * 1.5 + forecast_count * 0.1 - operator_acknowledgement_count * 0.25)
        / max(1.0, float(recommendation_budget + l3_attempt_budget)),
        6,
    )
    payload: dict[str, Any] = {
        "schema_version": P121_FATIGUE_LEDGER_SCHEMA_VERSION,
        "ledger_id": _text(data, "ledger_id"),
        "system_id": _text(data, "system_id"),
        "service_id": _text(data, "service_id"),
        "incident_family": _text(data, "incident_family"),
        "window_start": _text(data, "window_start"),
        "window_end": _text(data, "window_end"),
        "forecast_count": forecast_count,
        "recommendation_count": recommendation_count,
        "intervention_attempt_count": intervention_attempt_count,
        "false_positive_count": false_positive_count,
        "abstention_count": abstention_count,
        "operator_acknowledgement_count": operator_acknowledgement_count,
        "duplicate_suppression_count": duplicate_suppression_count,
        "recommendation_budget": recommendation_budget,
        "l3_attempt_budget": l3_attempt_budget,
        "fatigue_score": fatigue_score,
        "fatigue_budget_remaining": max(0, recommendation_budget - recommendation_count),
        "l3_attempt_budget_remaining": max(0, l3_attempt_budget - intervention_attempt_count),
        "suppression_reason": str(data.get("suppression_reason", "")),
        "authority_counters": dict(data.get("authority_counters", zero_authority_counters())),
    }
    validate_fatigue_ledger(payload)
    payload["ledger_hash"] = stable_hash(payload)
    return payload


def validate_fatigue_ledger(ledger: Mapping[str, Any]) -> None:
    """Validate ledger shape and exact-zero authority."""

    if ledger.get("schema_version") != P121_FATIGUE_LEDGER_SCHEMA_VERSION:
        raise P121GuardrailError("invalid_fatigue_ledger_schema")
    if _parse_time(ledger.get("window_end")) <= _parse_time(ledger.get("window_start")):
        raise P121GuardrailError("invalid_fatigue_window")
    if int(ledger.get("recommendation_count", 0)) > int(ledger.get("recommendation_budget", -1)):
        if not str(ledger.get("suppression_reason", "")).strip():
            raise P121GuardrailError("fatigue_budget_violation_without_suppression")
    if int(ledger.get("intervention_attempt_count", 0)) > int(ledger.get("l3_attempt_budget", -1)):
        if not str(ledger.get("suppression_reason", "")).strip():
            raise P121GuardrailError("l3_attempt_cap_bypassed")
    try:
        validate_exact_zero_authority(ledger.get("authority_counters"))
    except P121SignalError as exc:
        raise P121GuardrailError(str(exc)) from exc


def suppress_duplicates(forecasts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deterministically suppress duplicate or near-duplicate forecasts within a horizon."""

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for forecast in forecasts:
        key = "|".join(
            [
                str(forecast.get("system_id", "")),
                str(forecast.get("service_id", "")),
                str(forecast.get("incident_family", "")),
                str(forecast.get("failure_mode", "")),
                str(forecast.get("horizon_start", "")),
                str(forecast.get("horizon_end", "")),
                str(forecast.get("near_duplicate_fingerprint", forecast.get("forecast_id", ""))),
            ]
        )
        grouped[key].append(forecast)
    decisions: list[dict[str, Any]] = []
    for items in grouped.values():
        ordered = sorted(items, key=lambda item: str(item.get("forecast_id", "")))
        for index, item in enumerate(ordered):
            decisions.append(
                {
                    "forecast_id": str(item.get("forecast_id", "")),
                    "suppressed": index > 0,
                    "suppression_reason": "duplicate_forecast_within_horizon" if index > 0 else "",
                    "canonical_forecast_id": str(ordered[0].get("forecast_id", "")),
                    "decision_hash": stable_hash({"forecast_id": str(item.get("forecast_id", "")), "canonical": str(ordered[0].get("forecast_id", "")), "suppressed": index > 0}),
                }
            )
    return sorted(decisions, key=lambda item: item["forecast_id"])


def apply_prevention_guardrails(forecast: Mapping[str, Any], ledger: Mapping[str, Any], counterfactual: Mapping[str, Any], *, route: str) -> dict[str, Any]:
    """Apply calibration, abstention, false-positive, and fatigue gates before escalation or L3."""

    validate_fatigue_ledger(ledger)
    blockers: list[str] = []
    if str(forecast.get("calibration_bucket")) not in ACTIONABLE_CALIBRATION_BUCKETS:
        blockers.append("low_calibration_actioned")
    if str(forecast.get("ood_status")) not in ACTIONABLE_OOD_STATUSES:
        blockers.append("abstain_required_but_actioned")
    if str(forecast.get("abstention_status")) not in {"not_abstained", "actionable"}:
        blockers.append("forecast_abstained")
    required_strength = required_evidence_strength(float(ledger["fatigue_score"]))
    if str(forecast.get("evidence_strength", "weak")) not in _strengths_at_least(required_strength):
        blockers.append("evidence_strength_below_fatigue_threshold")
    if int(ledger["recommendation_count"]) >= int(ledger["recommendation_budget"]) and route in {"prevent_l1_recommend", "prevent_l2_dry_run", "prevent_l3_local_sandbox", "escalate"}:
        blockers.append("fatigue_budget_exhausted")
    if int(ledger["intervention_attempt_count"]) >= int(ledger["l3_attempt_budget"]) and route == "prevent_l3_local_sandbox":
        blockers.append("l3_attempt_cap_bypassed")
    if counterfactual.get("schema_version") != P121_COUNTERFACTUAL_SCHEMA_VERSION:
        blockers.append("missing_counterfactual")
    if counterfactual.get("promotion_allowed") is not True:
        blockers.append("counterfactual_not_promotable")
    false_positive = is_false_positive(forecast, counterfactual)
    if false_positive:
        blockers.append("false_positive_hidden")
    final_route = route if not blockers else ("abstain_fail_closed" if "abstain_required_but_actioned" in blockers else "investigate_more")
    payload: dict[str, Any] = {
        "schema_version": P121_GUARDRAIL_DECISION_SCHEMA_VERSION,
        "forecast_id": str(forecast.get("forecast_id", "")),
        "route": final_route,
        "requested_route": route,
        "blocked": bool(blockers),
        "blockers": sorted(set(blockers)),
        "false_positive": false_positive,
        "fatigue_score": ledger["fatigue_score"],
        "fatigue_budget_remaining": ledger["fatigue_budget_remaining"],
        "operator_burden_score": operator_burden_score([ledger]),
        "required_evidence_strength": required_strength,
        "authority_counters": dict(forecast.get("authority_counters", zero_authority_counters())),
    }
    try:
        validate_exact_zero_authority(payload["authority_counters"])
    except P121SignalError as exc:
        raise P121GuardrailError(str(exc)) from exc
    payload["guardrail_hash"] = stable_hash(payload)
    return payload


def is_false_positive(forecast: Mapping[str, Any], counterfactual: Mapping[str, Any]) -> bool:
    """Count false positives when the horizon passes without incident or identifiable benefit."""

    horizon_passed = bool(forecast.get("horizon_passed"))
    incident_occurred = bool(forecast.get("incident_occurred"))
    return horizon_passed and not incident_occurred and counterfactual.get("promotion_allowed") is not True


def required_evidence_strength(fatigue_score: float) -> str:
    """Require stronger evidence as fatigue rises."""

    if fatigue_score >= 1.0:
        return "very_strong"
    if fatigue_score >= 0.5:
        return "strong"
    return "standard"


def guardrail_metrics(ledgers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Report fatigue and alert burden overall and per system/service/family."""

    if not ledgers:
        raise P121GuardrailError("missing_fatigue_ledgers")
    slices: list[dict[str, Any]] = []
    aggregate = {
        "forecast_count": 0,
        "recommendation_count": 0,
        "intervention_attempt_count": 0,
        "false_positive_count": 0,
        "duplicate_suppression_count": 0,
        "fatigue_budget_violations": 0,
    }
    for ledger in ledgers:
        validate_fatigue_ledger(ledger)
        row = {
            "system_id": ledger["system_id"],
            "service_id": ledger["service_id"],
            "incident_family": ledger["incident_family"],
            "alert_burden": int(ledger["forecast_count"]) + int(ledger["recommendation_count"]) + int(ledger["intervention_attempt_count"]),
            "duplicate_suppression_count": ledger["duplicate_suppression_count"],
            "false_positive_count": ledger["false_positive_count"],
            "fatigue_budget_violation": int(ledger["recommendation_count"]) > int(ledger["recommendation_budget"]) or int(ledger["intervention_attempt_count"]) > int(ledger["l3_attempt_budget"]),
            "operator_burden_score": operator_burden_score([ledger]),
        }
        slices.append(row)
        for key in ("forecast_count", "recommendation_count", "intervention_attempt_count", "false_positive_count", "duplicate_suppression_count"):
            aggregate[key] += int(ledger[key])
        aggregate["fatigue_budget_violations"] += int(bool(row["fatigue_budget_violation"]))
    payload: dict[str, Any] = {
        "schema_version": "p121.guardrail_metrics.v1",
        "aggregate": aggregate,
        "slices": sorted(slices, key=lambda item: (str(item["system_id"]), str(item["service_id"]), str(item["incident_family"]))),
    }
    payload["metrics_hash"] = stable_hash(payload)
    return payload


def operator_burden_score(ledgers: Sequence[Mapping[str, Any]]) -> float:
    """Compute a denominator-visible operator burden score."""

    if not ledgers:
        return 0.0
    burden = 0.0
    for ledger in ledgers:
        burden += float(ledger.get("recommendation_count", 0)) + float(ledger.get("intervention_attempt_count", 0)) * 2.0 + float(ledger.get("false_positive_count", 0)) * 1.5
    return round(burden / len(ledgers), 6)


def _strengths_at_least(required: str) -> set[str]:
    order = ["weak", "standard", "strong", "very_strong"]
    index = order.index(required)
    return set(order[index:])


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P121GuardrailError(f"missing_{key}")
    return value


def _nonnegative_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise P121GuardrailError(f"invalid_{key}")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise P121GuardrailError(f"invalid_{key}") from exc
    if result < 0:
        raise P121GuardrailError(f"invalid_{key}")
    return result


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise P121GuardrailError("missing_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P121GuardrailError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
