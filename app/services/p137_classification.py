"""Deterministic terminal classification contracts for P137."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_contracts import CLASSIFICATION_SCHEMA_VERSION as CONTRACT_CLASSIFICATION_SCHEMA_VERSION

CLASSIFICATION_SCHEMA_VERSION = CONTRACT_CLASSIFICATION_SCHEMA_VERSION
CLASSIFICATIONS = frozenset({"confirmed_incident", "insufficient_evidence", "benign_anomaly", "aborted_fail_closed"})
CONFIDENCE_CODES = frozenset({"evidence_sufficient", "evidence_insufficient", "benign_supported", "fail_closed"})
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "schema_version",
        "classification_id",
        "incident_id",
        "classification_sequence",
        "classification",
        "decided_at",
        "top_hypothesis_hash",
        "support_summary_hashes",
        "contradiction_summary_hashes",
        "missing_evidence_hashes",
        "confidence_code",
        "decision_reasons",
        "authority_counters",
        "runtime_activity",
        "resource_usage",
        "previous_classification_hash",
        "classification_hash",
    }
)


class P137ClassificationError(ValueError):
    """Raised when terminal classification evidence is invalid."""


def derive_classification(
    hypotheses: Sequence[Mapping[str, Any]],
    *,
    accepted_incident: bool,
    semantic_tie: bool = False,
    failure_code: str | None = None,
    classification_write_succeeded: bool = False,
    ledger_cas_succeeded: bool = False,
) -> str | None:
    """Derive one terminal label, or ``None`` when no label is authoritative."""

    if not accepted_incident:
        return None
    if failure_code is not None:
        return "aborted_fail_closed" if classification_write_succeeded and ledger_cas_succeeded else None
    if semantic_tie or not hypotheses:
        return "insufficient_evidence"
    ordered = sorted(hypotheses, key=_hypothesis_order, reverse=True)
    top = ordered[0]
    missing = _sequence(top.get("missing_evidence"), "missing_evidence")
    if any(_mapping(item, "missing_item").get("blocking") is True for item in missing):
        return "insufficient_evidence"
    support = [_mapping(item, "support_edge") for item in _sequence(top.get("support"), "support")]
    contradictions = [_mapping(item, "contradiction_edge") for item in _sequence(top.get("contradictions"), "contradictions")]
    if any(item.get("relation") == "contradicts_decisive" for item in contradictions):
        return "insufficient_evidence"
    if top.get("category") == "benign_pattern" and any(item.get("relation") == "supports_benign" for item in support):
        return "benign_anomaly"
    if top.get("category") != "benign_pattern" and any(item.get("relation") == "supports_primary" for item in support):
        return "confirmed_incident"
    return "insufficient_evidence"


def build_classification_record(
    *,
    incident_id: str,
    classification_sequence: int,
    classification: str,
    decided_at: str,
    top_hypothesis: Mapping[str, Any] | None,
    authority_counters: Mapping[str, Any],
    runtime_activity: Mapping[str, Any],
    resource_usage: Mapping[str, Any],
    previous_classification_hash: str | None = None,
    decision_reasons: Sequence[str] = (),
) -> dict[str, Any]:
    _text(incident_id, "incident_id")
    _positive_int(classification_sequence, "classification_sequence")
    if classification not in CLASSIFICATIONS:
        raise P137ClassificationError("invalid_classification")
    _text(decided_at, "decided_at")
    if previous_classification_hash is not None:
        _hash(previous_classification_hash, "previous_classification_hash")
    hypothesis = _mapping(top_hypothesis, "top_hypothesis") if top_hypothesis is not None else None
    if classification != "aborted_fail_closed" and hypothesis is None:
        raise P137ClassificationError("top_hypothesis_required")
    top_hash = str(hypothesis.get("hypothesis_hash")) if hypothesis else None
    if top_hash is not None:
        _hash(top_hash, "top_hypothesis_hash")
    support_hashes = _edge_hashes(hypothesis, "support")
    contradiction_hashes = _edge_hashes(hypothesis, "contradictions")
    missing_hashes = _missing_hashes(hypothesis)
    confidence = {
        "confirmed_incident": "evidence_sufficient",
        "insufficient_evidence": "evidence_insufficient",
        "benign_anomaly": "benign_supported",
        "aborted_fail_closed": "fail_closed",
    }[classification]
    reasons = sorted({_text(item, "decision_reason") for item in decision_reasons})
    counters = _zero_integer_map(authority_counters, "authority_counters")
    activity = _nonnegative_integer_map(runtime_activity, "runtime_activity")
    resources = _nonnegative_integer_map(resource_usage, "resource_usage")
    classification_id = stable_hash(
        {"incident_id": incident_id, "classification_sequence": classification_sequence, "classification": classification}
    )
    record: dict[str, Any] = {
        "schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "classification_id": classification_id,
        "incident_id": incident_id,
        "classification_sequence": classification_sequence,
        "classification": classification,
        "decided_at": decided_at,
        "top_hypothesis_hash": top_hash,
        "support_summary_hashes": support_hashes,
        "contradiction_summary_hashes": contradiction_hashes,
        "missing_evidence_hashes": missing_hashes,
        "confidence_code": confidence,
        "decision_reasons": reasons,
        "authority_counters": counters,
        "runtime_activity": activity,
        "resource_usage": resources,
        "previous_classification_hash": previous_classification_hash,
    }
    record["classification_hash"] = stable_hash(record)
    validate_classification_record(record, top_hypothesis=hypothesis)
    return record


def validate_classification_record(record: Mapping[str, Any], *, top_hypothesis: Mapping[str, Any] | None = None) -> None:
    value = _mapping(record, "classification")
    if set(value) != _FIELDS or value.get("schema_version") != CLASSIFICATION_SCHEMA_VERSION:
        raise P137ClassificationError("invalid_classification_fields")
    _text(value.get("classification_id"), "classification_id")
    _text(value.get("incident_id"), "incident_id")
    _positive_int(value.get("classification_sequence"), "classification_sequence")
    if value.get("classification") not in CLASSIFICATIONS:
        raise P137ClassificationError("invalid_classification")
    if value.get("confidence_code") not in CONFIDENCE_CODES:
        raise P137ClassificationError("invalid_confidence_code")
    _text(value.get("decided_at"), "decided_at")
    previous = value.get("previous_classification_hash")
    if previous is not None:
        _hash(previous, "previous_classification_hash")
    top_hash = value.get("top_hypothesis_hash")
    if top_hash is not None:
        _hash(top_hash, "top_hypothesis_hash")
    for field in ("support_summary_hashes", "contradiction_summary_hashes", "missing_evidence_hashes"):
        _hashes(_sequence(value.get(field), field), field)
    reasons = _sequence(value.get("decision_reasons"), "decision_reasons")
    if list(reasons) != sorted(set(str(item) for item in reasons)):
        raise P137ClassificationError("decision_reasons_not_canonical")
    _zero_integer_map(_mapping(value.get("authority_counters"), "authority_counters"), "authority_counters")
    _nonnegative_integer_map(_mapping(value.get("runtime_activity"), "runtime_activity"), "runtime_activity")
    _nonnegative_integer_map(_mapping(value.get("resource_usage"), "resource_usage"), "resource_usage")
    if top_hypothesis is not None:
        hypothesis = _mapping(top_hypothesis, "top_hypothesis")
        if top_hash != hypothesis.get("hypothesis_hash"):
            raise P137ClassificationError("detached_top_hypothesis")
        if list(value["support_summary_hashes"]) != _edge_hashes(hypothesis, "support"):
            raise P137ClassificationError("forged_support_summary")
        if list(value["contradiction_summary_hashes"]) != _edge_hashes(hypothesis, "contradictions"):
            raise P137ClassificationError("forged_contradiction_summary")
        if list(value["missing_evidence_hashes"]) != _missing_hashes(hypothesis):
            raise P137ClassificationError("forged_missing_evidence_summary")
    expected = stable_hash({key: item for key, item in value.items() if key != "classification_hash"})
    if value.get("classification_hash") != expected:
        raise P137ClassificationError("classification_hash_invalid")


def _hypothesis_order(value: Mapping[str, Any]) -> tuple[int, int, int, int, int, int, str]:
    score = _mapping(value.get("score"), "score")
    semantic = (
        int(score.get("rank_score", 0)),
        int(score.get("support_weight", 0)),
        -int(score.get("contradiction_weight", 0)),
        -int(score.get("missing_required_count", 0)),
        int(score.get("freshness_weight", 0)),
        int(score.get("source_diversity_weight", 0)),
    )
    return (*semantic, str(value.get("hypothesis_hash", "")))


def _edge_hashes(hypothesis: Mapping[str, Any] | None, field: str) -> list[str]:
    if hypothesis is None:
        return []
    return _hashes([_mapping(item, field).get("edge_hash") for item in _sequence(hypothesis.get(field), field)], field)


def _missing_hashes(hypothesis: Mapping[str, Any] | None) -> list[str]:
    if hypothesis is None:
        return []
    return _hashes([_mapping(item, "missing_item").get("item_hash") for item in _sequence(hypothesis.get("missing_evidence"), "missing_evidence")], "missing_evidence")


def _zero_integer_map(value: Mapping[str, Any], field: str) -> dict[str, int]:
    result = _nonnegative_integer_map(value, field)
    if any(result.values()):
        raise P137ClassificationError(f"nonzero_{field}")
    return result


def _nonnegative_integer_map(value: Mapping[str, Any], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key or isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise P137ClassificationError(f"invalid_{field}")
        result[key] = raw
    return dict(sorted(result.items()))


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137ClassificationError(f"invalid_{field}")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P137ClassificationError(f"invalid_{field}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 256:
        raise P137ClassificationError(f"invalid_{field}")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P137ClassificationError(f"invalid_{field}")
    return value


def _hashes(values: Sequence[Any], field: str) -> list[str]:
    hashes = [_hash(item, field) for item in values]
    if len(hashes) != len(set(hashes)):
        raise P137ClassificationError(f"duplicate_{field}")
    return sorted(hashes)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P137ClassificationError(f"invalid_{field}")
    return value


__all__ = [
    "CLASSIFICATIONS",
    "P137ClassificationError",
    "build_classification_record",
    "derive_classification",
    "validate_classification_record",
]
