"""P117 contradiction ledger and deterministic fallback semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash

P117_CONTRADICTION_LEDGER_SCHEMA_VERSION = "p117.contradiction_ledger.v1"
P117_CONTRADICTION_FALLBACK_SCHEMA_VERSION = "p117.contradiction_fallback.v1"

CONTRADICTION_KINDS = frozenset(
    {
        "p114_hypothesis_conflict",
        "timestamp_conflict",
        "source_conflict",
        "prerequisite_conflict",
        "contraindication_conflict",
        "p116_seed_disagreement",
        "natural_recovery_ambiguity",
        "calibration_drift",
    }
)


class P117ContradictionError(ValueError):
    """Raised when contradiction evidence is malformed or suppressible."""


@dataclass(frozen=True)
class P117ContradictionLedger:
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P117ContradictionError("invalid_ledger_payload")
        return thawed


@dataclass(frozen=True)
class P117ContradictionFallback:
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P117ContradictionError("invalid_fallback_payload")
        return thawed


def build_contradiction_ledger(items: Sequence[Mapping[str, Any]]) -> P117ContradictionLedger:
    if not items:
        raise P117ContradictionError("missing_contradictions")
    contradictions = [_normalize_contradiction(item) for item in items]
    max_severity = max(float(item["severity"]) for item in contradictions)
    payload: dict[str, Any] = {
        "schema_version": P117_CONTRADICTION_LEDGER_SCHEMA_VERSION,
        "contradictions": contradictions,
        "max_severity": max_severity,
        "contradiction_suppression_count": 0,
    }
    payload["ledger_hash"] = stable_hash(payload)
    return P117ContradictionLedger(P117_CONTRADICTION_LEDGER_SCHEMA_VERSION, payload)


def decide_contradiction_fallback(ledger: P117ContradictionLedger, *, abstain_threshold: float = 0.8, investigate_threshold: float = 0.4) -> P117ContradictionFallback:
    payload = ledger.to_dict()
    contradictions = payload["contradictions"]
    triggered = [item for item in contradictions if float(item["severity"]) >= investigate_threshold]
    selected_label = "act"
    fallback_reason = None
    changed_decision = False
    if any(float(item["severity"]) >= abstain_threshold for item in contradictions):
        selected_label = "abstain"
        fallback_reason = "contradiction_threshold_exceeded"
        changed_decision = True
    elif triggered:
        selected_label = "investigate_more"
        fallback_reason = "contradiction_requires_evidence"
        changed_decision = True
    result: dict[str, Any] = {
        "schema_version": P117_CONTRADICTION_FALLBACK_SCHEMA_VERSION,
        "selected_label": selected_label,
        "fallback_reason": fallback_reason,
        "contradiction_set_ids": [str(item["contradiction_id"]) for item in triggered],
        "changed_decision": changed_decision,
        "contradiction_suppression_count": 0,
        "ledger_hash": payload["ledger_hash"],
    }
    result["fallback_hash"] = stable_hash(result)
    return P117ContradictionFallback(P117_CONTRADICTION_FALLBACK_SCHEMA_VERSION, result)


def _normalize_contradiction(item: Mapping[str, Any]) -> dict[str, Any]:
    kind = _required_text(item, "kind")
    if kind not in CONTRADICTION_KINDS:
        raise P117ContradictionError(f"unknown_contradiction_kind:{kind}")
    action_ids = _required_text_sequence(item.get("affected_action_pack_ids"), "missing_affected_action_pack_ids")
    evidence_ids = _required_text_sequence(item.get("affected_evidence_ids"), "missing_affected_evidence_ids")
    severity = item.get("severity")
    if not isinstance(severity, int | float) or isinstance(severity, bool) or not 0 <= float(severity) <= 1:
        raise P117ContradictionError("invalid_severity")
    description = _required_text(item, "description")
    normalized = {
        "kind": kind,
        "affected_action_pack_ids": sorted(action_ids),
        "affected_evidence_ids": sorted(evidence_ids),
        "severity": float(severity),
        "description": description,
    }
    normalized["contradiction_id"] = stable_hash(normalized)
    return normalized


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P117ContradictionError(f"missing_{key}")
    return value.strip()


def _required_text_sequence(value: Any, error: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P117ContradictionError(error)
    result = [item for item in value if isinstance(item, str) and item]
    if len(result) != len(value) or len(result) != len(set(result)):
        raise P117ContradictionError(error)
    return result


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
