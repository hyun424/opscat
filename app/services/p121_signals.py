"""P121 leading-indicator and forecast horizon contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p120_governance import AUTHORITY_COUNTER_KEYS

P121_INDICATOR_SCHEMA_VERSION = "p121.leading_indicator.v1"
P121_FORECAST_SCHEMA_VERSION = "p121.forecast_horizon.v1"
HASH_PREFIX = "sha256:"
ACTIONABLE_CALIBRATION_BUCKETS = frozenset({"excellent", "good", "acceptable"})
ACTIONABLE_OOD_STATUSES = frozenset({"in_distribution", "near_distribution"})
NON_ACTION_ROUTES = frozenset({"investigate_more", "abstain_fail_closed"})
P121_AUTHORITY_COUNTER_KEYS = tuple(
    dict.fromkeys(
        (
            *AUTHORITY_COUNTER_KEYS,
            "unapproved_intervention_count",
            "evidence_bypass_count",
            "rollback_missing_execution_count",
        )
    )
)
FORBIDDEN_INDICATOR_FIELDS = frozenset(
    {
        "future_outcome_label",
        "future_label",
        "outcome_label",
        "ground_truth",
        "hidden_scorer_field",
        "scorer_only_truth",
        "post_intervention_telemetry",
        "post_incident_hindsight",
        "consumed_holdout_data",
    }
)


class P121SignalError(ValueError):
    """Raised when P121 signal or forecast contracts fail closed."""


def zero_authority_counters() -> dict[str, int]:
    """Return P121's exact-zero authority snapshot."""

    return {key: 0 for key in P121_AUTHORITY_COUNTER_KEYS}


def validate_exact_zero_authority(counters: Any) -> None:
    """Require every P121 authority dimension to be present and exactly zero."""

    if not isinstance(counters, Mapping):
        raise P121SignalError("missing_authority_counters")
    for key in P121_AUTHORITY_COUNTER_KEYS:
        if key not in counters:
            raise P121SignalError(f"missing_authority_counter:{key}")
        value = counters[key]
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            raise P121SignalError(f"{key}_nonzero")


def build_leading_indicator(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a hash-bound leading indicator without future or hidden scorer fields."""

    _reject_forbidden_fields(data)
    payload: dict[str, Any] = {
        "schema_version": P121_INDICATOR_SCHEMA_VERSION,
        "indicator_id": _text(data, "indicator_id"),
        "source_id": _text(data, "source_id"),
        "system_id": _text(data, "system_id"),
        "service_id": _text(data, "service_id"),
        "observed_at": _text(data, "observed_at"),
        "window_start": _text(data, "window_start"),
        "window_end": _text(data, "window_end"),
        "signal_family": _text(data, "signal_family"),
        "signal_name": _text(data, "signal_name"),
        "normalized_value": _number(data, "normalized_value"),
        "baseline_ref": _text(data, "baseline_ref"),
        "deviation_score": _number(data, "deviation_score"),
        "trend_ref": _text(data, "trend_ref"),
        "seasonality_ref": _text(data, "seasonality_ref"),
        "deploy_config_refs": _text_list(data.get("deploy_config_refs", []), allow_empty=True),
        "topology_refs": _text_list(data.get("topology_refs", []), allow_empty=True),
        "recurrence_refs": _text_list(data.get("recurrence_refs", []), allow_empty=True),
        "missingness_status": _text(data, "missingness_status"),
        "data_quality_status": _text(data, "data_quality_status"),
        "evidence_ids": _text_list(data.get("evidence_ids")),
        "artifact_hash": _hash(data, "artifact_hash"),
        "authority_counters": dict(data.get("authority_counters", zero_authority_counters())),
        "duplicate_lineage_status": str(data.get("duplicate_lineage_status", "resolved")),
        "system_identity_status": str(data.get("system_identity_status", "resolved")),
        "source_quality": str(data.get("source_quality", "acceptable")),
        "fresh_current_evidence": bool(data.get("fresh_current_evidence", True)),
    }
    validate_leading_indicator(payload)
    payload["indicator_hash"] = stable_hash(payload)
    return payload


def validate_leading_indicator(indicator: Mapping[str, Any]) -> None:
    """Validate a P121 leading indicator and reject leakage or authority drift."""

    if indicator.get("schema_version") != P121_INDICATOR_SCHEMA_VERSION:
        raise P121SignalError("invalid_indicator_schema")
    _reject_forbidden_fields(indicator)
    required = {
        "indicator_id",
        "source_id",
        "system_id",
        "service_id",
        "observed_at",
        "window_start",
        "window_end",
        "signal_family",
        "signal_name",
        "normalized_value",
        "baseline_ref",
        "deviation_score",
        "trend_ref",
        "seasonality_ref",
        "missingness_status",
        "data_quality_status",
        "evidence_ids",
        "artifact_hash",
        "authority_counters",
    }
    _require_fields(indicator, required, "indicator")
    if _parse_time(indicator["window_end"]) < _parse_time(indicator["window_start"]):
        raise P121SignalError("invalid_indicator_window")
    if _parse_time(indicator["observed_at"]) > _parse_time(indicator["window_end"]):
        raise P121SignalError("observed_after_window_end")
    if not str(indicator["artifact_hash"]).startswith(HASH_PREFIX):
        raise P121SignalError("invalid_indicator_artifact_hash")
    if not _sequence(indicator.get("evidence_ids")):
        raise P121SignalError("missing_indicator_evidence")
    validate_exact_zero_authority(indicator.get("authority_counters"))
    if str(indicator.get("duplicate_lineage_status", "resolved")) != "resolved":
        raise P121SignalError("unresolved_duplicate_lineage")
    if str(indicator.get("system_identity_status", "resolved")) != "resolved":
        raise P121SignalError("ambiguous_system_identity")


def indicator_non_action_reason(indicator: Mapping[str, Any]) -> str | None:
    """Return why an otherwise valid indicator must not drive action authority."""

    try:
        validate_leading_indicator(indicator)
    except P121SignalError as exc:
        return str(exc)
    if str(indicator.get("missingness_status")) != "complete":
        return "missing_indicator_data"
    if str(indicator.get("data_quality_status")) != "good":
        return "poor_data_quality"
    if str(indicator.get("source_quality", "acceptable")) not in {"acceptable", "strong"}:
        return "weak_source_quality"
    if _sequence(indicator.get("recurrence_refs")) and not bool(indicator.get("fresh_current_evidence")):
        return "recurrence_without_fresh_evidence"
    return None


def build_forecast(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a forecast horizon record with explicit calibration, expiry, and evidence requirements."""

    payload: dict[str, Any] = {
        "schema_version": P121_FORECAST_SCHEMA_VERSION,
        "forecast_id": _text(data, "forecast_id"),
        "indicator_ids": _text_list(data.get("indicator_ids")),
        "failure_mode": _text(data, "failure_mode"),
        "incident_family": _text(data, "incident_family"),
        "probability": _probability(data, "probability"),
        "calibrated_probability": _probability(data, "calibrated_probability"),
        "calibration_bucket": _text(data, "calibration_bucket"),
        "confidence_interval": _confidence_interval(data.get("confidence_interval")),
        "horizon_start": _text(data, "horizon_start"),
        "horizon_end": _text(data, "horizon_end"),
        "minimum_useful_lead_time_seconds": _positive_int(data, "minimum_useful_lead_time_seconds"),
        "forecast_created_at": _text(data, "forecast_created_at"),
        "expires_at": _text(data, "expires_at"),
        "expected_impact": _nonnegative_number(data, "expected_impact"),
        "uncertainty_reasons": _text_list(data.get("uncertainty_reasons", []), allow_empty=True),
        "ood_status": _text(data, "ood_status"),
        "abstention_status": _text(data, "abstention_status"),
        "required_evidence_ids": _text_list(data.get("required_evidence_ids")),
        "resolved_evidence_ids": _text_list(data.get("resolved_evidence_ids", []), allow_empty=True),
        "model_rule_version": _text(data, "model_rule_version"),
        "frozen_config_hash": _hash(data, "frozen_config_hash"),
        "artifact_hash": _hash(data, "artifact_hash"),
        "authority_counters": dict(data.get("authority_counters", zero_authority_counters())),
        "cutoff_at": str(data.get("cutoff_at", data.get("forecast_created_at", ""))),
        "route": str(data.get("route", "")),
    }
    validate_forecast(payload)
    payload["forecast_hash"] = stable_hash(payload)
    return payload


def validate_forecast(forecast: Mapping[str, Any]) -> None:
    """Validate the immutable forecast contract."""

    if forecast.get("schema_version") != P121_FORECAST_SCHEMA_VERSION:
        raise P121SignalError("invalid_forecast_schema")
    required = {
        "forecast_id",
        "indicator_ids",
        "failure_mode",
        "incident_family",
        "probability",
        "calibrated_probability",
        "calibration_bucket",
        "confidence_interval",
        "horizon_start",
        "horizon_end",
        "minimum_useful_lead_time_seconds",
        "forecast_created_at",
        "expires_at",
        "expected_impact",
        "ood_status",
        "abstention_status",
        "required_evidence_ids",
        "model_rule_version",
        "frozen_config_hash",
        "artifact_hash",
        "authority_counters",
    }
    _require_fields(forecast, required, "forecast")
    horizon_start = _parse_time(forecast["horizon_start"])
    horizon_end = _parse_time(forecast["horizon_end"])
    created_at = _parse_time(forecast["forecast_created_at"])
    expires_at = _parse_time(forecast["expires_at"])
    if horizon_end <= horizon_start:
        raise P121SignalError("invalid_horizon")
    if expires_at <= created_at:
        raise P121SignalError("expired_at_creation")
    if int(forecast["minimum_useful_lead_time_seconds"]) <= 0:
        raise P121SignalError("zero_useful_lead_time")
    lead_time = int((horizon_start - created_at).total_seconds())
    if lead_time < int(forecast["minimum_useful_lead_time_seconds"]):
        raise P121SignalError("negative_or_insufficient_lead_time")
    if not str(forecast["frozen_config_hash"]).startswith(HASH_PREFIX):
        raise P121SignalError("invalid_frozen_config_hash")
    if not str(forecast["artifact_hash"]).startswith(HASH_PREFIX):
        raise P121SignalError("invalid_forecast_artifact_hash")
    if not _sequence(forecast.get("required_evidence_ids")):
        raise P121SignalError("missing_required_evidence")
    validate_exact_zero_authority(forecast.get("authority_counters"))


def evaluate_intervention_eligibility(forecast: Mapping[str, Any], *, now: str) -> dict[str, Any]:
    """Decide whether a forecast can become a prevention candidate."""

    try:
        validate_forecast(forecast)
    except P121SignalError as exc:
        return _route("abstain_fail_closed", str(exc), eligible=False)
    now_dt = _parse_time(now)
    if now_dt >= _parse_time(forecast["expires_at"]):
        return _route("abstain_fail_closed", "expired_forecast", eligible=False)
    if str(forecast["calibration_bucket"]) not in ACTIONABLE_CALIBRATION_BUCKETS:
        return _route("investigate_more", "low_calibration_actioned", eligible=False)
    if str(forecast["ood_status"]) not in ACTIONABLE_OOD_STATUSES:
        return _route("abstain_fail_closed", "high_ood_actioned", eligible=False)
    if str(forecast["abstention_status"]) not in {"not_abstained", "actionable"}:
        return _route("abstain_fail_closed", "forecast_abstained", eligible=False)
    required = set(str(item) for item in _sequence(forecast.get("required_evidence_ids")))
    resolved = set(str(item) for item in _sequence(forecast.get("resolved_evidence_ids")))
    if not required <= resolved:
        return _route("investigate_more", "required_evidence_missing", eligible=False)
    return {"route": "candidate", "eligible": True, "reason": "eligible_with_evidence"}


def _route(route: str, reason: str, *, eligible: bool) -> dict[str, Any]:
    return {"route": route, "eligible": eligible, "reason": reason}


def _reject_forbidden_fields(data: Mapping[str, Any]) -> None:
    for key in data:
        if str(key) in FORBIDDEN_INDICATOR_FIELDS:
            raise P121SignalError(f"forbidden_indicator_field:{key}")


def _require_fields(data: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(str(key) for key in data))
    if missing:
        raise P121SignalError(f"missing_{label}_field:{missing[0]}")
    for key in required:
        if data.get(key) in (None, ""):
            raise P121SignalError(f"missing_{label}_field:{key}")


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P121SignalError(f"missing_{key}")
    return value


def _hash(data: Mapping[str, Any], key: str) -> str:
    value = _text(data, key)
    if not value.startswith(HASH_PREFIX):
        raise P121SignalError(f"invalid_{key}")
    return value


def _text_list(value: Any, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or (not value and not allow_empty):
        raise P121SignalError("missing_text_list")
    result = [str(item) for item in value]
    if any(not item.strip() for item in result):
        raise P121SignalError("invalid_text_list")
    return result


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise P121SignalError(f"invalid_{key}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise P121SignalError(f"invalid_{key}") from exc


def _nonnegative_number(data: Mapping[str, Any], key: str) -> float:
    value = _number(data, key)
    if value < 0.0:
        raise P121SignalError(f"invalid_{key}")
    return value


def _probability(data: Mapping[str, Any], key: str) -> float:
    value = _number(data, key)
    if not 0.0 <= value <= 1.0:
        raise P121SignalError(f"invalid_{key}")
    return value


def _positive_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise P121SignalError(f"invalid_{key}")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise P121SignalError(f"invalid_{key}") from exc
    if result <= 0:
        raise P121SignalError(f"invalid_{key}")
    return result


def _confidence_interval(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise P121SignalError("missing_confidence_interval")
    lower = float(value.get("lower", -1.0))
    upper = float(value.get("upper", -1.0))
    if not 0.0 <= lower <= upper <= 1.0:
        raise P121SignalError("invalid_confidence_interval")
    return {"lower": lower, "upper": upper}


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise P121SignalError("missing_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P121SignalError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
