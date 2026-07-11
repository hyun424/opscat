"""P121 evidence-before-action forecasting guard contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121SignalError, validate_exact_zero_authority, zero_authority_counters

P121_EVIDENCE_SCHEMA_VERSION = "p121.evidence_receipt.v1"
P121_DECISION_SCHEMA_VERSION = "p121.prevention_decision.v1"
ALLOWED_EVIDENCE_SOURCE_KINDS = frozenset({"local_fixture", "mock_read_only", "sandbox_snapshot", "frozen_telemetry_snapshot"})
ALLOWED_ROUTES = frozenset({"prevent_l1_recommend", "prevent_l2_dry_run", "prevent_l3_local_sandbox", "investigate_more", "no_action", "escalate", "abstain_fail_closed"})
PREVENTIVE_ROUTES = frozenset({"prevent_l1_recommend", "prevent_l2_dry_run", "prevent_l3_local_sandbox", "escalate"})
NON_ACTION_ROUTES = frozenset({"investigate_more", "no_action", "abstain_fail_closed"})


class P121EvidenceError(ValueError):
    """Raised when evidence-before-action contracts fail closed."""


def build_evidence_receipt(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a local/mock read-only, hash-bound evidence receipt."""

    payload: dict[str, Any] = {
        "schema_version": P121_EVIDENCE_SCHEMA_VERSION,
        "evidence_id": _text(data, "evidence_id"),
        "source_ref": _text(data, "source_ref"),
        "source_kind": _text(data, "source_kind"),
        "taxonomy_version": _text(data, "taxonomy_version"),
        "artifact_hash": _hash(data, "artifact_hash"),
        "observed_at": _text(data, "observed_at"),
        "cutoff_at": _text(data, "cutoff_at"),
        "collected_at": _text(data, "collected_at"),
        "staleness_seconds": _nonnegative_int(data, "staleness_seconds"),
        "max_staleness_seconds": _nonnegative_int(data, "max_staleness_seconds"),
        "contradiction_status": _text(data, "contradiction_status"),
        "post_intervention": bool(data.get("post_intervention", False)),
        "denominator_visible": bool(data.get("denominator_visible", True)),
        "authority_counters": dict(data.get("authority_counters", zero_authority_counters())),
    }
    validate_evidence_receipt(payload)
    payload["evidence_hash"] = stable_hash(payload)
    return payload


def validate_evidence_receipt(receipt: Mapping[str, Any]) -> None:
    """Reject stale, nonlocal, post-cutoff, contradictory, or unhashable evidence."""

    if receipt.get("schema_version") != P121_EVIDENCE_SCHEMA_VERSION:
        raise P121EvidenceError("invalid_evidence_schema")
    required = {
        "evidence_id",
        "source_ref",
        "source_kind",
        "taxonomy_version",
        "artifact_hash",
        "observed_at",
        "cutoff_at",
        "collected_at",
        "staleness_seconds",
        "max_staleness_seconds",
        "contradiction_status",
        "denominator_visible",
        "authority_counters",
    }
    _require_fields(receipt, required, "evidence")
    if str(receipt["source_kind"]) not in ALLOWED_EVIDENCE_SOURCE_KINDS:
        raise P121EvidenceError("nonlocal_evidence")
    if not str(receipt["artifact_hash"]).startswith("sha256:"):
        raise P121EvidenceError("unhashable_evidence")
    if _parse_time(receipt["observed_at"]) > _parse_time(receipt["cutoff_at"]):
        raise P121EvidenceError("post_cutoff_evidence")
    if _parse_time(receipt["collected_at"]) < _parse_time(receipt["observed_at"]):
        raise P121EvidenceError("evidence_collected_before_observation")
    if int(receipt["staleness_seconds"]) > int(receipt["max_staleness_seconds"]):
        raise P121EvidenceError("stale_evidence")
    if str(receipt["contradiction_status"]) != "none":
        raise P121EvidenceError("contradictory_evidence")
    if receipt.get("post_intervention") is True:
        raise P121EvidenceError("post_intervention_evidence")
    if receipt.get("denominator_visible") is not True:
        raise P121EvidenceError("evidence_not_denominator_visible")
    try:
        validate_exact_zero_authority(receipt.get("authority_counters"))
    except P121SignalError as exc:
        raise P121EvidenceError(str(exc)) from exc


def build_prevention_decision(data: Mapping[str, Any], evidence_receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a route decision that cannot bypass evidence-before-action."""

    route = _text(data, "route")
    required_evidence_ids = _text_list(data.get("required_evidence_ids", []), allow_empty=route in NON_ACTION_ROUTES or route in PREVENTIVE_ROUTES)
    provided_ids = [str(receipt.get("evidence_id", "")) for receipt in evidence_receipts]
    payload: dict[str, Any] = {
        "schema_version": P121_DECISION_SCHEMA_VERSION,
        "decision_id": _text(data, "decision_id"),
        "forecast_id": _text(data, "forecast_id"),
        "route": route,
        "required_evidence_ids": required_evidence_ids,
        "evidence_ids": provided_ids,
        "reason": str(data.get("reason", "")),
        "release_blocker": False,
        "authority_counters": dict(data.get("authority_counters", zero_authority_counters())),
    }
    missing_or_invalid = evidence_gaps(required_evidence_ids, evidence_receipts)
    if route in PREVENTIVE_ROUTES and not required_evidence_ids:
        missing_or_invalid.append("evidence_bypass_intervention")
    if route in PREVENTIVE_ROUTES and missing_or_invalid:
        payload["route"] = "abstain_fail_closed" if "evidence_bypass_intervention" in missing_or_invalid else "investigate_more"
        payload["reason"] = ",".join(missing_or_invalid)
        payload["release_blocker"] = "evidence_bypass_intervention" in missing_or_invalid
    validate_prevention_decision(payload)
    payload["decision_hash"] = stable_hash(payload)
    return payload


def evidence_gaps(required_evidence_ids: Sequence[str], evidence_receipts: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return missing or invalid evidence reasons while keeping every gap visible."""

    gaps: list[str] = []
    by_id: dict[str, Mapping[str, Any]] = {}
    for raw_receipt in evidence_receipts:
        receipt = raw_receipt
        if receipt.get("schema_version") != P121_EVIDENCE_SCHEMA_VERSION:
            try:
                receipt = build_evidence_receipt(receipt)
            except P121EvidenceError as exc:
                gaps.append(str(exc))
                if raw_receipt.get("evidence_id"):
                    by_id[str(raw_receipt.get("evidence_id"))] = raw_receipt
                continue
        evidence_id = str(receipt.get("evidence_id", ""))
        try:
            validate_evidence_receipt(receipt)
        except P121EvidenceError as exc:
            gaps.append(str(exc))
        if evidence_id:
            by_id[evidence_id] = receipt
    for evidence_id in required_evidence_ids:
        if evidence_id not in by_id:
            gaps.append("missing_required_evidence")
    return sorted(set(gaps))


def validate_prevention_decision(decision: Mapping[str, Any]) -> None:
    """Validate that preventive routes carry evidence or fail closed explicitly."""

    if decision.get("schema_version") != P121_DECISION_SCHEMA_VERSION:
        raise P121EvidenceError("invalid_decision_schema")
    route = str(decision.get("route", ""))
    if route not in ALLOWED_ROUTES:
        raise P121EvidenceError("invalid_prevention_route")
    required = _sequence(decision.get("required_evidence_ids"))
    provided = set(str(item) for item in _sequence(decision.get("evidence_ids")))
    if route in PREVENTIVE_ROUTES and (not required or not set(str(item) for item in required) <= provided):
        raise P121EvidenceError("evidence_bypass_intervention")
    if route in NON_ACTION_ROUTES and not str(decision.get("reason", "")).strip():
        raise P121EvidenceError("missing_non_action_reason")
    try:
        validate_exact_zero_authority(decision.get("authority_counters"))
    except P121SignalError as exc:
        raise P121EvidenceError(str(exc)) from exc


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P121EvidenceError(f"missing_{key}")
    return value


def _hash(data: Mapping[str, Any], key: str) -> str:
    value = _text(data, key)
    if not value.startswith("sha256:"):
        raise P121EvidenceError(f"invalid_{key}")
    return value


def _text_list(value: Any, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or (not value and not allow_empty):
        raise P121EvidenceError("missing_text_list")
    result = [str(item) for item in value]
    if any(not item.strip() for item in result):
        raise P121EvidenceError("invalid_text_list")
    return result


def _nonnegative_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if value is None or isinstance(value, bool):
        raise P121EvidenceError(f"invalid_{key}")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise P121EvidenceError(f"invalid_{key}") from exc
    if result < 0:
        raise P121EvidenceError(f"invalid_{key}")
    return result


def _require_fields(data: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(str(key) for key in data))
    if missing:
        raise P121EvidenceError(f"missing_{label}_field:{missing[0]}")
    for key in required:
        if data.get(key) in (None, ""):
            raise P121EvidenceError(f"missing_{label}_field:{key}")


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise P121EvidenceError("missing_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P121EvidenceError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
