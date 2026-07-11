"""P120 read-only telemetry normalization contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p120_governance import P120GovernanceError, validate_exact_zero_authority, zero_authority_counters

NORMALIZATION_VERSION = "p120.telemetry_normalization.v1"
READ_ONLY_CONTRACT_SCHEMA_VERSION = "p120.read_only_importer_contract.v1"
SUPPORTED_SCHEMAS = frozenset({"prometheus", "datadog", "sentry", "log_event", "trace_span", "topology", "deploy_marker"})
SUPPORTED_MODALITIES = frozenset({"metric", "log", "trace", "event", "topology", "deploy_config", "validation", "rollback", "outcome"})
ALLOWED_EVIDENCE_STATES = frozenset({"valid", "missing_evidence", "contradiction", "ood", "investigate_more", "abstain", "escalate", "fail_closed"})


class P120NormalizationError(ValueError):
    """Raised when telemetry normalization fails closed."""


def normalize_telemetry_record(raw: Mapping[str, Any], *, source_schema: str, ingestion_time: str, authority_counters: Mapping[str, int] | None = None) -> dict[str, Any]:
    """Normalize heterogeneous read-only telemetry into a canonical envelope."""

    if source_schema not in SUPPORTED_SCHEMAS:
        return _fail_closed(raw, source_schema=source_schema, ingestion_time=ingestion_time, reason="unsupported_modality")
    counters = dict(authority_counters or zero_authority_counters())
    try:
        validate_exact_zero_authority(counters)
        parsed = _parse_schema(raw, source_schema)
        _validate_required_common(parsed)
        state_reasons = _state_reasons(parsed, ingestion_time=ingestion_time)
        state = _state_from_reasons(state_reasons)
        envelope = _canonical_envelope(parsed, raw=raw, source_schema=source_schema, ingestion_time=ingestion_time, counters=counters, evidence_state=state, state_reasons=state_reasons)
        validate_normalized_record(envelope)
        return envelope
    except (P120GovernanceError, P120NormalizationError, KeyError, TypeError, ValueError) as exc:
        return _fail_closed(raw, source_schema=source_schema, ingestion_time=ingestion_time, reason=str(exc), counters=counters)


def validate_normalized_record(record: Mapping[str, Any]) -> None:
    """Require denominator-visible canonical fields and exact-zero authority."""

    required = {
        "telemetry_record_id",
        "source_id",
        "system_id",
        "service_id",
        "entity_ref",
        "modality",
        "observed_at",
        "ingested_at",
        "window",
        "signal_name",
        "value",
        "unit",
        "severity",
        "labels",
        "topology_refs",
        "deploy_config_refs",
        "redaction_receipt",
        "normalization_version",
        "source_hash",
        "authority_counters",
        "evidence_state",
        "denominator_visible",
        "raw_ref",
    }
    missing = sorted(required - set(str(key) for key in record))
    if missing:
        raise P120NormalizationError(f"missing_normalized_field:{missing[0]}")
    if record.get("normalization_version") != NORMALIZATION_VERSION:
        raise P120NormalizationError("invalid_normalization_version")
    if str(record.get("modality")) not in SUPPORTED_MODALITIES:
        raise P120NormalizationError("unsupported_modality_hidden")
    if str(record.get("evidence_state")) not in ALLOWED_EVIDENCE_STATES:
        raise P120NormalizationError("invalid_evidence_state")
    if record.get("denominator_visible") is not True:
        raise P120NormalizationError("telemetry_dropped_from_denominator")
    if record.get("redaction_receipt") in (None, ""):
        raise P120NormalizationError("missing_redaction_receipt")
    validate_exact_zero_authority(record.get("authority_counters"))


def build_read_only_importer_contract(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a read-only local/imported telemetry contract."""

    supported_schemas = _text_list(data, "supported_schemas")
    mutation_surfaces = _text_list({**data, "mutation_surfaces": data.get("mutation_surfaces", [])}, "mutation_surfaces", allow_empty=True)
    ingestion_loss_rate = float(data.get("ingestion_loss_rate", 0.0))
    payload: dict[str, Any] = {
        "schema_version": READ_ONLY_CONTRACT_SCHEMA_VERSION,
        "connector_id": _text(data, "connector_id"),
        "source_kind": _text(data, "source_kind"),
        "supported_schemas": supported_schemas,
        "requires_credentials": bool(data.get("requires_credentials")),
        "live_connector_calls": int(data.get("live_connector_calls", 0)),
        "write_endpoints_reachable": bool(data.get("write_endpoints_reachable")),
        "mutation_surfaces": mutation_surfaces,
        "ingestion_loss_rate": ingestion_loss_rate,
        "authority_counters": dict(data.get("authority_counters", zero_authority_counters())),
    }
    if payload["source_kind"] not in {"local_fixture", "curated_benchmark", "imported_read_only_snapshot"}:
        raise P120NormalizationError("invalid_read_only_source_kind")
    if any(schema not in SUPPORTED_SCHEMAS for schema in payload["supported_schemas"]):
        raise P120NormalizationError("unsupported_contract_schema")
    if payload["requires_credentials"]:
        raise P120NormalizationError("credential_required_connector")
    if payload["live_connector_calls"] != 0:
        raise P120NormalizationError("live_connector_call_present")
    if payload["write_endpoints_reachable"] or payload["mutation_surfaces"]:
        raise P120NormalizationError("write_endpoint_reachable")
    if payload["ingestion_loss_rate"] > 0.001:
        raise P120NormalizationError("ingestion_loss_above_threshold")
    validate_exact_zero_authority(payload["authority_counters"])
    payload["contract_hash"] = stable_hash(payload)
    return payload


def _parse_schema(raw: Mapping[str, Any], source_schema: str) -> dict[str, Any]:
    if source_schema == "prometheus":
        return {
            **_base(raw),
            "modality": "metric",
            "signal_name": raw.get("metric", raw.get("__name__", "")),
            "value": raw.get("value", 1),
            "unit": raw.get("unit"),
            "observed_at": raw.get("timestamp"),
            "window": raw.get("window", {"start": raw.get("timestamp"), "end": raw.get("timestamp")}),
            "labels": dict(_mapping(raw.get("labels"))),
        }
    if source_schema == "datadog":
        return {
            **_base(raw),
            "modality": "metric",
            "signal_name": raw.get("metric_name", raw.get("metric", "")),
            "value": raw.get("point", raw.get("value")),
            "unit": raw.get("unit"),
            "observed_at": raw.get("ts", raw.get("timestamp")),
            "window": raw.get("window", {"start": raw.get("ts", raw.get("timestamp")), "end": raw.get("ts", raw.get("timestamp"))}),
            "labels": dict(_mapping(raw.get("tags"))),
        }
    if source_schema == "sentry":
        return {
            **_base(raw),
            "modality": "event",
            "signal_name": raw.get("title", raw.get("event_id", "")),
            "value": raw.get("count", 1),
            "unit": raw.get("unit", "event"),
            "severity": raw.get("level", raw.get("severity", "unknown")),
            "observed_at": raw.get("last_seen", raw.get("timestamp")),
            "window": raw.get("window", {"start": raw.get("first_seen", raw.get("timestamp")), "end": raw.get("last_seen", raw.get("timestamp"))}),
            "labels": dict(_mapping(raw.get("tags"))),
        }
    if source_schema == "log_event":
        return {
            **_base(raw),
            "modality": "log",
            "signal_name": raw.get("template", raw.get("message", "")),
            "value": raw.get("value", 1),
            "unit": raw.get("unit", "line"),
            "observed_at": raw.get("timestamp"),
            "window": raw.get("window", {"start": raw.get("timestamp"), "end": raw.get("timestamp")}),
            "labels": dict(_mapping(raw.get("fields"))),
        }
    if source_schema == "trace_span":
        return {
            **_base(raw),
            "modality": "trace",
            "signal_name": raw.get("operation", raw.get("span_name", "")),
            "value": raw.get("duration_ms"),
            "unit": raw.get("unit", "ms"),
            "observed_at": raw.get("start_time"),
            "window": raw.get("window", {"start": raw.get("start_time"), "end": raw.get("end_time", raw.get("start_time"))}),
            "labels": dict(_mapping(raw.get("attributes"))),
        }
    if source_schema == "topology":
        return {
            **_base(raw),
            "modality": "topology",
            "signal_name": raw.get("edge_type", "topology"),
            "value": raw.get("edge_count"),
            "unit": raw.get("unit", "graph"),
            "observed_at": raw.get("timestamp"),
            "window": raw.get("window", {"start": raw.get("timestamp"), "end": raw.get("timestamp")}),
            "labels": dict(_mapping(raw.get("labels"))),
        }
    return {
        **_base(raw),
        "modality": "deploy_config",
        "signal_name": raw.get("marker", raw.get("change_id", "")),
        "value": raw.get("version"),
        "unit": raw.get("unit", "marker"),
        "observed_at": raw.get("timestamp"),
        "window": raw.get("window", {"start": raw.get("timestamp"), "end": raw.get("timestamp")}),
        "labels": dict(_mapping(raw.get("labels"))),
    }


def _base(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "telemetry_record_id": raw.get("telemetry_record_id", raw.get("id", "")),
        "source_id": raw.get("source_id", ""),
        "system_id": raw.get("system_id", ""),
        "service_id": raw.get("service_id", raw.get("service", "")),
        "entity_ref": raw.get("entity_ref", raw.get("host", raw.get("service", ""))),
        "severity": raw.get("severity", "unknown"),
        "topology_refs": list(_sequence(raw.get("topology_refs"))),
        "deploy_config_refs": list(_sequence(raw.get("deploy_config_refs"))),
        "redaction_receipt": raw.get("redaction_receipt", ""),
        "timestamp_uncertainty_ms": raw.get("timestamp_uncertainty_ms"),
        "clock_skew_ms": raw.get("clock_skew_ms"),
        "duplicate_of": raw.get("duplicate_of"),
        "arrival_order": raw.get("arrival_order"),
        "expected_order": raw.get("expected_order"),
        "contradicts": list(_sequence(raw.get("contradicts"))),
    }


def _canonical_envelope(
    parsed: Mapping[str, Any],
    *,
    raw: Mapping[str, Any],
    source_schema: str,
    ingestion_time: str,
    counters: Mapping[str, int],
    evidence_state: str,
    state_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "telemetry_record_id": str(parsed["telemetry_record_id"]),
        "source_id": str(parsed["source_id"]),
        "system_id": str(parsed["system_id"]),
        "service_id": str(parsed["service_id"]),
        "entity_ref": str(parsed["entity_ref"]),
        "modality": str(parsed["modality"]),
        "observed_at": str(parsed["observed_at"]),
        "ingested_at": ingestion_time,
        "window": dict(_mapping(parsed["window"])),
        "signal_name": str(parsed["signal_name"]),
        "value": parsed["value"],
        "unit": parsed["unit"],
        "severity": str(parsed.get("severity", "unknown")),
        "labels": dict(_mapping(parsed.get("labels"))),
        "topology_refs": list(_sequence(parsed.get("topology_refs"))),
        "deploy_config_refs": list(_sequence(parsed.get("deploy_config_refs"))),
        "redaction_receipt": str(parsed["redaction_receipt"]),
        "normalization_version": NORMALIZATION_VERSION,
        "source_hash": stable_hash(raw),
        "authority_counters": dict(counters),
        "evidence_state": evidence_state,
        "state_reasons": list(state_reasons),
        "denominator_visible": True,
        "source_schema": source_schema,
        "raw_ref": {"source_hash": stable_hash(raw), "record_id": str(parsed["telemetry_record_id"])},
    }


def _validate_required_common(parsed: Mapping[str, Any]) -> None:
    for key in ("telemetry_record_id", "source_id", "system_id", "service_id", "entity_ref", "modality", "observed_at", "window", "signal_name", "unit", "redaction_receipt"):
        value = parsed.get(key)
        if value in (None, ""):
            raise P120NormalizationError(f"missing_{key}")
    if parsed.get("value") is None:
        raise P120NormalizationError("nullable_metric_preserved")
    if str(parsed["modality"]) not in SUPPORTED_MODALITIES:
        raise P120NormalizationError("unsupported_modality_hidden")


def _state_reasons(parsed: Mapping[str, Any], *, ingestion_time: str) -> list[str]:
    reasons: list[str] = []
    if parsed.get("timestamp_uncertainty_ms") not in (None, 0):
        reasons.append("timestamp_uncertainty_visible")
    if abs(int(parsed.get("clock_skew_ms") or 0)) > 300_000:
        reasons.append("timestamp_skew_visible")
    observed = _parse_time(str(parsed.get("observed_at")))
    ingested = _parse_time(ingestion_time)
    if observed is not None and ingested is not None:
        delay_seconds = (ingested - observed).total_seconds()
        if delay_seconds > 86_400:
            reasons.append("stale_record")
        elif delay_seconds > 900:
            reasons.append("delayed_record_visible")
    if parsed.get("duplicate_of"):
        reasons.append("duplicate_record_visible")
    arrival_order = parsed.get("arrival_order")
    expected_order = parsed.get("expected_order")
    if isinstance(arrival_order, int) and isinstance(expected_order, int) and arrival_order < expected_order:
        reasons.append("reorder_visible")
    if parsed.get("contradicts"):
        reasons.append("contradictory_telemetry_visible")
    return reasons


def _state_from_reasons(reasons: Sequence[str]) -> str:
    if any(reason in reasons for reason in ("stale_record", "contradictory_telemetry_visible")):
        return "contradiction" if "contradictory_telemetry_visible" in reasons else "fail_closed"
    if reasons:
        return "investigate_more"
    return "valid"


def _fail_closed(raw: Mapping[str, Any], *, source_schema: str, ingestion_time: str, reason: str, counters: Mapping[str, int] | None = None) -> dict[str, Any]:
    safe_counters = dict(counters or zero_authority_counters())
    try:
        validate_exact_zero_authority(safe_counters)
    except P120GovernanceError:
        safe_counters = zero_authority_counters()
        reason = "authority_drift_visible"
    return {
        "telemetry_record_id": str(raw.get("telemetry_record_id", raw.get("id", "malformed"))),
        "source_id": str(raw.get("source_id", "unknown")),
        "system_id": str(raw.get("system_id", "unknown")),
        "service_id": str(raw.get("service_id", raw.get("service", "unknown"))),
        "entity_ref": str(raw.get("entity_ref", "unknown")),
        "modality": "event",
        "observed_at": str(raw.get("timestamp", ingestion_time)),
        "ingested_at": ingestion_time,
        "window": dict(_mapping(raw.get("window"))) or {"start": str(raw.get("timestamp", ingestion_time)), "end": str(raw.get("timestamp", ingestion_time))},
        "signal_name": "malformed_telemetry",
        "value": None,
        "unit": "unknown",
        "severity": "error",
        "labels": {},
        "topology_refs": [],
        "deploy_config_refs": [],
        "redaction_receipt": str(raw.get("redaction_receipt", "missing")),
        "normalization_version": NORMALIZATION_VERSION,
        "source_hash": stable_hash(raw),
        "authority_counters": safe_counters,
        "evidence_state": "fail_closed",
        "state_reasons": [reason],
        "denominator_visible": True,
        "source_schema": source_schema,
        "raw_ref": {"source_hash": stable_hash(raw), "record_id": str(raw.get("telemetry_record_id", raw.get("id", "malformed")))},
    }


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P120NormalizationError(f"missing_{key}")
    return value


def _text_list(data: Mapping[str, Any], key: str, *, allow_empty: bool = False) -> list[str]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or (not allow_empty and not value):
        raise P120NormalizationError(f"missing_{key}")
    result = [str(item) for item in value]
    if any(not item.strip() for item in result):
        raise P120NormalizationError(f"invalid_{key}")
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


__all__ = [
    "NORMALIZATION_VERSION",
    "P120NormalizationError",
    "READ_ONLY_CONTRACT_SCHEMA_VERSION",
    "build_read_only_importer_contract",
    "normalize_telemetry_record",
    "validate_normalized_record",
]
