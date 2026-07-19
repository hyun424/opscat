"""P177 evidence-seeking diagnosis trace schema with hash-chain integrity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.services.p147_p152_contracts import stable_hash

TRACE_EVENT_SCHEMA_VERSION = "p177.trace_event.v1"
TRACE_SCHEMA_VERSION = "p177.diagnosis_trace.v1"
EVENT_TYPES = frozenset({"hypothesis", "question", "tool_choice", "evidence_result", "contradiction", "revision", "stop"})
STOP_REASONS = frozenset(
    {
        "final_diagnosis",
        "abstain_missing_evidence",
        "abstain_stale_evidence",
        "abstain_contradictory_evidence",
        "escalate_low_confidence",
        "escalate_outside_tool_coverage",
        "budget_exhausted",
        "policy_violation",
    }
)


class P177TraceError(ValueError):
    """Raised when a P177 trace is incomplete or tampered."""


def append_trace_event(*, previous: Mapping[str, Any] | None, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise P177TraceError("unknown_event_type")
    previous_hash = ""
    sequence = 1
    if previous is not None:
        _validate_event(previous, expected_sequence=None, previous_hash=None)
        previous_hash = str(previous["event_hash"])
        sequence = _positive_int(previous.get("sequence"), "previous_sequence") + 1
    event: dict[str, Any] = {
        "schema_version": TRACE_EVENT_SCHEMA_VERSION,
        "sequence": sequence,
        "event_type": event_type,
        "payload": deepcopy(dict(payload)),
        "previous_event_hash": previous_hash,
    }
    payload_map = event["payload"]
    if not isinstance(payload_map, Mapping):
        raise P177TraceError("invalid_payload")
    _validate_payload(event_type, payload_map)
    event["event_hash"] = stable_hash(event)
    return event


def validate_trace_chain(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not events or isinstance(events, (str, bytes, bytearray)):
        raise P177TraceError("empty_trace")
    previous_hash = ""
    seen: set[str] = set()
    event_types: list[str] = []
    for expected_sequence, event in enumerate(events, start=1):
        _validate_event(event, expected_sequence=expected_sequence, previous_hash=previous_hash)
        event_hash = str(event["event_hash"])
        if event_hash in seen:
            raise P177TraceError("replayed_trace_event")
        seen.add(event_hash)
        event_types.append(str(event["event_type"]))
        previous_hash = event_hash
    missing = {"hypothesis", "question", "tool_choice", "evidence_result", "revision", "stop"} - set(event_types)
    if missing:
        raise P177TraceError("incomplete_trace")
    if event_types[-1] != "stop":
        raise P177TraceError("missing_terminal_stop")
    payload = events[-1]["payload"]
    if not isinstance(payload, Mapping) or payload.get("stop_reason") not in STOP_REASONS:
        raise P177TraceError("invalid_stop_reason")
    trace = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "event_count": len(events),
        "terminal_event_hash": previous_hash,
        "stop_reason": payload["stop_reason"],
    }
    trace["trace_hash"] = stable_hash(trace)
    return trace


def _validate_event(event: Mapping[str, Any], *, expected_sequence: int | None, previous_hash: str | None) -> None:
    if set(event) != {"schema_version", "sequence", "event_type", "payload", "previous_event_hash", "event_hash"}:
        raise P177TraceError("invalid_event_schema")
    if event.get("schema_version") != TRACE_EVENT_SCHEMA_VERSION:
        raise P177TraceError("invalid_event_schema")
    sequence = _positive_int(event.get("sequence"), "sequence")
    if expected_sequence is not None and sequence != expected_sequence:
        raise P177TraceError("sequence_mismatch")
    if previous_hash is not None and event.get("previous_event_hash") != previous_hash:
        raise P177TraceError("previous_event_hash_mismatch")
    event_type = str(event.get("event_type"))
    if event_type not in EVENT_TYPES:
        raise P177TraceError("unknown_event_type")
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise P177TraceError("invalid_payload")
    _validate_payload(event_type, payload)
    expected_hash = stable_hash({key: value for key, value in event.items() if key != "event_hash"})
    if event.get("event_hash") != expected_hash:
        raise P177TraceError("event_hash_invalid")


def _validate_payload(event_type: str, payload: Mapping[str, Any]) -> None:
    if event_type == "hypothesis" and (not payload.get("hypothesis_id") or not payload.get("statement")):
        raise P177TraceError("invalid_hypothesis")
    if event_type == "question" and (not payload.get("question_id") or not payload.get("text")):
        raise P177TraceError("invalid_question")
    if event_type == "tool_choice" and not payload.get("tool_id"):
        raise P177TraceError("invalid_tool_choice")
    if event_type == "evidence_result" and (not payload.get("evidence_id") or payload.get("read_only") is not True):
        raise P177TraceError("invalid_evidence_result")
    if event_type == "contradiction":
        if not payload.get("contradiction_id") or not payload.get("evidence_ids"):
            raise P177TraceError("invalid_contradiction")
    if event_type == "revision":
        uncertainty = payload.get("uncertainty")
        if not isinstance(uncertainty, int | float) or isinstance(uncertainty, bool) or not 0 <= float(uncertainty) <= 1:
            raise P177TraceError("invalid_revision")
    if event_type == "stop" and payload.get("stop_reason") not in STOP_REASONS:
        raise P177TraceError("invalid_stop_reason")


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P177TraceError(f"invalid_{field}")
    return value
