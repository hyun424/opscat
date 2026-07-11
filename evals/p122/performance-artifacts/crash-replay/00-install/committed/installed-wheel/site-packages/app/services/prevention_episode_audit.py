"""Immutable P107 prevention audit records, WAL helpers, and replay."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.prevention_state_machine import (
    TERMINAL_STATES,
    PreventionStateMachine,
    PreventionStateTransitionError,
)

GENESIS_HASH = "GENESIS"
ZERO_AUTHORITY_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "production_adapter_calls": 0,
    "production_mutations": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "cloud_calls": 0,
    "db_mutations": 0,
}


@dataclass(frozen=True)
class PreventionEpisode:
    episode_id: str
    selected_candidate_hash: str
    canonical_p106_evidence_hash: str
    p105_p106_prerequisite_identity: str
    registry_hash: str
    cohort_scope: Mapping[str, Any]
    telemetry_window: Mapping[str, Any]
    created_at: str
    sequence: int = 1
    state: str = "received"
    parent_hash: str = GENESIS_HASH
    expected_terminal_head_hash: str | None = None


@dataclass(frozen=True)
class PreventiveActionAttempt:
    episode_id: str
    attempt_id: str
    sequence: int
    state: str
    selected_candidate_hash: str
    canonical_p106_evidence_hash: str
    registry_hash: str
    policy_recheck_hash: str
    cohort_fingerprint_hash: str
    idempotency_key: str
    treatment_control_fingerprints: Mapping[str, Any]
    authority_counters: Mapping[str, int]
    parent_hash: str
    occurred_at: str
    expected_terminal_head_hash: str | None = None
    p105_p106_prerequisite_identity: str | None = None
    cohort_scope: Mapping[str, Any] = field(default_factory=dict)
    telemetry_window: Mapping[str, Any] = field(default_factory=dict)
    result: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreventionAuditReplay:
    deterministic_replay: bool
    replay_hash: str
    report_input_model: Mapping[str, Any]
    terminal_state: str
    head_hash: str
    record_count: int


class PreventionAuditError(ValueError):
    """Raised when an audit append or replay violates P107 invariants."""


def canonical_record_bytes(record: Any) -> bytes:
    """Return stable ASCII JSON bytes for a record-like object."""

    payload = _record_payload(record)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


class JsonlPreventionAuditStore:
    """Append-only JSONL store for local/mock P107 audit evidence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.flush_count = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, record: Any) -> str:
        existing = _read_jsonl_records(self.path, allow_empty=True)
        payload = _record_payload(record)
        _prepare_payload_for_append(payload, existing)
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            self.flush_count += 1
        return str(payload["record_hash"])


def record_prevention_attempt_with_wal(
    store: JsonlPreventionAuditStore,
    episode: PreventionEpisode,
    attempt: PreventiveActionAttempt,
    harness: Any,
) -> Mapping[str, Any]:
    """Append and flush attempt intent before invoking the local/mock harness."""

    if not _read_jsonl_records(store.path, allow_empty=True):
        parent = store.append(episode)
        if attempt.parent_hash != parent:
            attempt = dataclasses.replace(attempt, parent_hash=parent)
    intent_hash = store.append(attempt)
    result = harness.invoke(attempt.idempotency_key)
    return {"intent_hash": intent_hash, "effect": result}


def record_prevention_rollback_with_wal(
    store: JsonlPreventionAuditStore,
    episode: PreventionEpisode,
    rollback_attempt: PreventiveActionAttempt,
    rollbacker: Any,
) -> Mapping[str, Any]:
    """Append and flush rollback intent before invoking the local/mock rollbacker."""

    if not _read_jsonl_records(store.path, allow_empty=True):
        parent = store.append(episode)
        if rollback_attempt.parent_hash != parent:
            rollback_attempt = dataclasses.replace(rollback_attempt, parent_hash=parent)
    intent_hash = store.append(rollback_attempt)
    result = rollbacker.rollback(rollback_attempt.idempotency_key)
    return {"intent_hash": intent_hash, "rollback": result}


def replay_prevention_audit(
    store_or_path: JsonlPreventionAuditStore | str | Path,
    *,
    allow_incomplete: bool = False,
) -> PreventionAuditReplay:
    path = Path(store_or_path.path) if isinstance(store_or_path, JsonlPreventionAuditStore) else Path(store_or_path)
    records = _read_jsonl_records(path, allow_empty=False)
    machine = PreventionStateMachine()
    previous_hash = GENESIS_HASH
    seen_parents: set[str] = set()

    for index, record in enumerate(records, start=1):
        sequence = record.get("sequence")
        if sequence != index:
            reason = "sequence gap" if isinstance(sequence, int) and sequence > index else "sequence order"
            raise PreventionAuditError(f"{reason}: expected sequence {index}, got {sequence!r}")

        parent_hash = record.get("parent_hash")
        if parent_hash != previous_hash:
            if parent_hash in seen_parents:
                raise PreventionAuditError(f"duplicate-parent fork at sequence {sequence}")
            raise PreventionAuditError(f"parent/order mismatch at sequence {sequence}")
        if parent_hash in seen_parents:
            raise PreventionAuditError(f"duplicate-parent fork at sequence {sequence}")
        seen_parents.add(str(parent_hash))

        _validate_record_hash(record)
        state = str(record.get("state"))
        try:
            machine.append(state)
        except PreventionStateTransitionError as exc:
            prefix = "incomplete " if state in {"wal_intent_appended", "rollback_intent_appended"} else ""
            raise PreventionAuditError(f"{prefix}{exc}") from exc
        previous_hash = str(record["record_hash"])

    terminal_state = machine.current_state
    if terminal_state not in TERMINAL_STATES:
        if not allow_incomplete:
            raise PreventionAuditError(f"tail truncation or incomplete episode at state {terminal_state!r}")
        terminal_state = str(terminal_state)

    expected_head = records[-1].get("expected_terminal_head_hash")
    if expected_head is not None and expected_head != previous_hash:
        raise PreventionAuditError("expected terminal head hash mismatch")

    report_input_model = {
        "schema_version": "p107.audit_replay.v1",
        "record_count": len(records),
        "terminal_state": terminal_state,
        "head_hash": previous_hash,
        "records": records,
    }
    replay_hash = _sha256_json(report_input_model)
    return PreventionAuditReplay(
        deterministic_replay=True,
        replay_hash=replay_hash,
        report_input_model=report_input_model,
        terminal_state=str(terminal_state),
        head_hash=previous_hash,
        record_count=len(records),
    )


def _record_payload(record: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(record):
        if isinstance(record, type):
            raise PreventionAuditError("audit record must be an instance, not a dataclass type")
        payload = dataclasses.asdict(record)
    elif isinstance(record, Mapping):
        payload = dict(record)
    else:
        raise PreventionAuditError(f"unsupported audit record type {type(record).__name__}")
    return _freeze_jsonable(payload)


def _prepare_payload_for_append(payload: dict[str, Any], existing: list[dict[str, Any]]) -> None:
    expected_sequence = len(existing) + 1
    sequence = payload.get("sequence")
    if sequence != expected_sequence:
        raise PreventionAuditError(f"append sequence violation: expected {expected_sequence}, got {sequence!r}")
    expected_parent = existing[-1]["record_hash"] if existing else GENESIS_HASH
    if payload.get("parent_hash") != expected_parent:
        raise PreventionAuditError("append parent hash does not match current head")
    if payload.get("state") is None:
        raise PreventionAuditError("append record missing state")
    if payload.get("authority_counters") is not None and payload["authority_counters"] != ZERO_AUTHORITY_COUNTERS:
        raise PreventionAuditError("authority counters must remain exactly zero")
    if "record_hash" not in payload:
        payload["record_hash"] = _computed_record_hash(payload)


def _read_jsonl_records(path: Path, *, allow_empty: bool) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text:
        if allow_empty:
            return []
        raise PreventionAuditError("empty audit log is incomplete")
    if not text.endswith("\n"):
        raise PreventionAuditError("partial audit record at end of file")
    records = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PreventionAuditError(f"partial audit record at line {line_no}") from exc
        if not isinstance(record, dict):
            raise PreventionAuditError(f"audit record at line {line_no} is not an object")
        records.append(record)
    return records


def _validate_record_hash(record: Mapping[str, Any]) -> None:
    record_hash = record.get("record_hash")
    sequence = record.get("sequence")
    if record_hash == _computed_record_hash(record):
        return
    raise PreventionAuditError(f"tamper or hash mismatch at sequence {sequence!r}")


def _computed_record_hash(record: Mapping[str, Any]) -> str:
    payload = dict(record)
    payload.pop("record_hash", None)
    return _sha256_json(payload)


def _sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _freeze_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _freeze_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_freeze_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_freeze_jsonable(item) for item in value]
    return value
