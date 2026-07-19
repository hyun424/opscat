"""P176 split evidence ledgers for agent-visible and evaluator-only records."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any

from app.services.p147_p152_contracts import ContractError, stable_hash
from app.services.redaction import redact_value

SCHEMA_VERSION = "p176.evidence_record.v1"
LEDGERS = frozenset({"agent_visible", "evaluator_only"})
SOURCE_CLASSES = frozenset(
    {
        "metrics",
        "logs",
        "traces",
        "deploy_history",
        "host_state",
        "container_state",
        "topology",
        "dependency_health",
    }
)

_FIELDS = frozenset(
    {
        "schema_version",
        "ledger_name",
        "sequence",
        "source_class",
        "source_id",
        "observed_at",
        "received_at",
        "freshness_bound_seconds",
        "redaction_applied",
        "redaction_receipt_hash",
        "content_hash",
        "summary",
        "evaluator_context_hash",
        "previous_record_hash",
        "record_hash",
    }
)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_FORBIDDEN_AGENT_KEY_PARTS = ("ground_truth", "truth", "raw_payload", "payload", "secret", "token", "password", "authorization", "cookie")
_FORBIDDEN_AGENT_TEXT = re.compile(r"\b(Bearer\s+|api[_-]?key=|token=|secret=|password=|sk_(?:live|test)_|xox[baprs]-)", re.IGNORECASE)


class P176EvidenceError(ValueError):
    """Raised when P176 evidence fails closed."""


def append_evidence_record(
    *,
    previous: Mapping[str, Any] | None,
    ledger_name: str,
    source_class: str,
    source_id: str,
    observed_at: str,
    received_at: str,
    freshness_bound_seconds: int,
    content_hash: str,
    redaction_receipt_hash: str,
    summary: Mapping[str, Any],
    evaluator_context_hash: str | None = None,
) -> dict[str, Any]:
    if previous is not None:
        previous_value = _mapping(previous, "previous")
        if previous_value.get("ledger_name") != ledger_name:
            raise P176EvidenceError("ledger_predecessor_confusion")
        _validate_record_content(previous_value, ledger_name=ledger_name)
        sequence = _positive_int(previous_value.get("sequence"), "previous_sequence") + 1
        previous_hash = _hash(previous_value.get("record_hash"), "previous_record_hash")
    else:
        sequence = 1
        previous_hash = ""

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ledger_name": ledger_name,
        "sequence": sequence,
        "source_class": source_class,
        "source_id": source_id,
        "observed_at": observed_at,
        "received_at": received_at,
        "freshness_bound_seconds": freshness_bound_seconds,
        "redaction_applied": True,
        "redaction_receipt_hash": redaction_receipt_hash,
        "content_hash": content_hash,
        "summary": deepcopy(dict(summary)),
        "evaluator_context_hash": evaluator_context_hash,
        "previous_record_hash": previous_hash,
    }
    record["record_hash"] = _stable_hash(record)
    validate_evidence_record(record, previous=previous, ledger_name=ledger_name)
    return record


def validate_evidence_chain(
    records: Sequence[Mapping[str, Any]], *, ledger_name: str, require_all_source_classes: bool = False
) -> None:
    _ledger_name(ledger_name)
    if isinstance(records, (str, bytes, bytearray)):
        raise P176EvidenceError("invalid_records")
    if not records:
        raise P176EvidenceError("empty_evidence_chain")
    previous: Mapping[str, Any] | None = None
    seen_hashes: set[str] = set()
    for expected_sequence, record in enumerate(records, start=1):
        value = _mapping(record, "record")
        if value.get("sequence") != expected_sequence:
            raise P176EvidenceError("sequence_mismatch")
        validate_evidence_record(value, previous=previous, ledger_name=ledger_name)
        record_hash = str(value["record_hash"])
        if record_hash in seen_hashes:
            raise P176EvidenceError("replayed_record")
        seen_hashes.add(record_hash)
        previous = value
    if require_all_source_classes and {str(item["source_class"]) for item in records} != SOURCE_CLASSES:
        raise P176EvidenceError("source_class_coverage_incomplete")


def validate_evidence_record(
    record: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
    ledger_name: str | None = None,
) -> None:
    value = _mapping(record, "record")
    actual_ledger, sequence = _validate_record_content(value, ledger_name=ledger_name)

    previous_hash = value.get("previous_record_hash")
    if previous is None:
        if sequence != 1 or previous_hash != "":
            raise P176EvidenceError("genesis_record_invalid")
    else:
        previous_value = _mapping(previous, "previous")
        if previous_value.get("ledger_name") != actual_ledger:
            raise P176EvidenceError("ledger_predecessor_confusion")
        previous_ledger, previous_sequence = _validate_record_content(previous_value, ledger_name=actual_ledger)
        if previous_ledger != actual_ledger:
            raise P176EvidenceError("ledger_predecessor_confusion")
        if previous_hash != previous_value.get("record_hash"):
            raise P176EvidenceError("previous_record_hash_mismatch")
        if sequence != previous_sequence + 1:
            raise P176EvidenceError("sequence_mismatch")


def _validate_record_content(value: Mapping[str, Any], *, ledger_name: str | None = None) -> tuple[str, int]:
    if set(value) != _FIELDS or value.get("schema_version") != SCHEMA_VERSION:
        raise P176EvidenceError("invalid_evidence_schema")
    actual_ledger = _ledger_name(value.get("ledger_name"))
    if ledger_name is not None and actual_ledger != _ledger_name(ledger_name):
        raise P176EvidenceError("ledger_name_mismatch")
    sequence = _positive_int(value.get("sequence"), "sequence")
    source_class = str(value.get("source_class", ""))
    if source_class not in SOURCE_CLASSES:
        raise P176EvidenceError("unsupported_source_class")
    _nonempty_text(value.get("source_id"), "source_id")
    bound = _positive_int(value.get("freshness_bound_seconds"), "freshness_bound_seconds")
    _validate_freshness(str(value["observed_at"]), str(value["received_at"]), bound)
    if value.get("redaction_applied") is not True or not value.get("redaction_receipt_hash"):
        raise P176EvidenceError("redaction_required")
    _hash(value.get("redaction_receipt_hash"), "redaction_receipt_hash")
    _hash(value.get("content_hash"), "content_hash")
    summary = _mapping(value.get("summary"), "summary")
    if redact_value(summary) != summary:
        raise P176EvidenceError("redaction_required")
    evaluator_context_hash = value.get("evaluator_context_hash")
    if actual_ledger == "agent_visible":
        if evaluator_context_hash is not None:
            raise P176EvidenceError("agent_visible_evaluator_context_forbidden")
        _assert_agent_visible_safe(value)
    elif evaluator_context_hash is not None:
        _hash(evaluator_context_hash, "evaluator_context_hash")

    expected_hash = _stable_hash({key: item for key, item in value.items() if key != "record_hash"})
    if value.get("record_hash") != expected_hash:
        raise P176EvidenceError("record_hash_invalid")
    return actual_ledger, sequence


def _stable_hash(value: Any) -> str:
    _reject_non_finite(value)
    try:
        return stable_hash(value)
    except ContractError as exc:
        raise P176EvidenceError("evidence_not_canonical") from exc


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise P176EvidenceError("non_finite_evidence_number")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_non_finite(item)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for item in value:
            _reject_non_finite(item)


def _validate_freshness(observed_at: str, received_at: str, bound_seconds: int) -> None:
    observed = _timestamp(observed_at, "observed_at")
    received = _timestamp(received_at, "received_at")
    age = (received - observed).total_seconds()
    if age < 0:
        raise P176EvidenceError("future_observation")
    if age > bound_seconds:
        raise P176EvidenceError("stale_evidence")


def _assert_agent_visible_safe(value: Any) -> None:
    def walk(item: Any, path: tuple[str, ...]) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                key_text = str(key).lower().replace("-", "_")
                if any(part in key_text for part in _FORBIDDEN_AGENT_KEY_PARTS):
                    raise P176EvidenceError("agent_visible_forbidden_field")
                walk(child, (*path, key_text))
        elif isinstance(item, str):
            if _URL_RE.search(item):
                raise P176EvidenceError("agent_visible_url_forbidden")
            if _FORBIDDEN_AGENT_TEXT.search(item):
                raise P176EvidenceError("agent_visible_secret_forbidden")
    walk(value, ())


def _timestamp(value: str, field: str) -> datetime:
    try:
        if not value.endswith("Z"):
            raise ValueError
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P176EvidenceError(f"invalid_{field}") from exc


def _ledger_name(value: Any) -> str:
    if not isinstance(value, str) or value not in LEDGERS:
        raise P176EvidenceError("invalid_ledger_name")
    return value


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P176EvidenceError(f"invalid_{field}")
    return value


def _nonempty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P176EvidenceError(f"invalid_{field}")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P176EvidenceError(f"invalid_{field}")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P176EvidenceError(f"invalid_{field}")
    return value


__all__ = [
    "LEDGERS",
    "SCHEMA_VERSION",
    "SOURCE_CLASSES",
    "P176EvidenceError",
    "append_evidence_record",
    "validate_evidence_chain",
    "validate_evidence_record",
]
