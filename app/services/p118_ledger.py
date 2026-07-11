"""Append-only local WAL, CAS, idempotency, and replay ledger for P118."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_operation_contract import P118_TERMINAL_STATUSES, P118OperationEnvelope, exact_zero_authority_counters

_LEGAL_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "received": frozenset({"verified", "rejected", "expired", "aborted_fail_closed"}),
    "verified": frozenset({"approved", "rejected", "aborted_fail_closed"}),
    "approved": frozenset({"prechecked", "precheck_failed", "aborted_fail_closed"}),
    "prechecked": frozenset({"action_attempted", "validation_failed", "aborted_fail_closed"}),
    "action_attempted": frozenset({"postchecked", "action_failed", "postcheck_failed", "rollback_attempted", "aborted_fail_closed"}),
    "postchecked": frozenset({"succeeded", "postcheck_failed", "rollback_attempted"}),
    "precheck_failed": frozenset({"rejected"}),
    "action_failed": frozenset({"rollback_attempted", "rollback_failed"}),
    "postcheck_failed": frozenset({"rollback_attempted", "rollback_failed"}),
    "rollback_attempted": frozenset({"rollback_postchecked", "rollback_failed"}),
    "rollback_postchecked": frozenset({"rolled_back", "rollback_failed"}),
}


class P118LedgerError(ValueError):
    """Raised when WAL, CAS, idempotency, or replay invariants fail closed."""


@dataclass(frozen=True)
class P118LedgerReceipt:
    receipt_type: str
    operation_id: str
    state: str
    cas_version: int
    wal_position: int
    receipt_hash: str
    previous_hash: str
    duplicate_action_count: int
    lease_owner_id: str | None = None


@dataclass(frozen=True)
class P118OperationState:
    operation_id: str
    state: str
    cas_version: int
    idempotency_key: str
    payload_hash: str
    authority_counter_snapshot: Mapping[str, int]
    duplicate_action_count: int
    lease_owner_id: str | None = None
    lease_expires_at: int | None = None


class P118LedgerStore:
    def __init__(self, wal_path: Path) -> None:
        self.wal_path = wal_path
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries = self._load_entries()

    def register_operation(self, operation: P118OperationEnvelope) -> P118LedgerReceipt:
        payload = operation.to_dict()
        payload_hash = stable_hash(_idempotency_payload(payload))
        return self._receipt_from_entry(
            self._append(
                operation.operation_id,
                receipt_type="operation_registered",
                state="received",
                cas_version=0,
                lease_owner_id=None,
                payload={
                    "operation": payload,
                    "idempotency_key": operation.idempotency_key,
                    "payload_hash": payload_hash,
                    "authority_counter_snapshot": payload["authority_counter_snapshot"],
                    "duplicate_action_count": 0,
                    "lease_owner_id": str(_mapping(payload.get("lease_receipt")).get("owner_id", "")) or None,
                },
                register_idempotency_key=operation.idempotency_key,
                register_payload_hash=payload_hash,
            )
        )

    def transition(
        self,
        operation_id: str,
        next_state: str,
        *,
        expected_cas_version: int,
        lease_owner_id: str | None,
        evidence_receipt: Mapping[str, Any] | None = None,
    ) -> P118LedgerReceipt:
        state = self.replay(operation_id)
        if state.state in P118_TERMINAL_STATUSES:
            raise P118LedgerError("terminal_state_reopened")
        if expected_cas_version != state.cas_version:
            raise P118LedgerError("cas_conflict")
        if not lease_owner_id or state.lease_owner_id != lease_owner_id:
            raise P118LedgerError("lease_owner_mismatch")
        if next_state not in _LEGAL_TRANSITIONS.get(state.state, frozenset()):
            raise P118LedgerError("illegal_state_transition")
        return self._receipt_from_entry(
            self._append(
                operation_id,
                receipt_type="state_transition",
                state=next_state,
                cas_version=state.cas_version + 1,
                lease_owner_id=lease_owner_id,
                payload={
                    "from_state": state.state,
                    "to_state": next_state,
                    "duplicate_action_count": 0,
                    "evidence_receipt": dict(evidence_receipt or {}),
                },
                expected_prior_cas=expected_cas_version,
                expected_prior_state=state.state,
                expected_owner=lease_owner_id,
            )
        )

    def record_lease(
        self,
        operation_id: str,
        *,
        owner_id: str,
        expires_at: int,
        receipt_type: str,
        expected_lease_owner: str | None = None,
        expected_lease_expires_at: int | None = None,
    ) -> P118LedgerReceipt:
        state = self.replay(operation_id)
        return self._receipt_from_entry(
            self._append(
                operation_id,
                receipt_type=receipt_type,
                state=state.state,
                cas_version=state.cas_version,
                lease_owner_id=owner_id,
                payload={"lease_expires_at": expires_at, "duplicate_action_count": 0},
                expected_lease_owner=expected_lease_owner,
                expected_lease_expires_at=expected_lease_expires_at,
            )
        )

    def replay(self, operation_id: str) -> P118OperationState:
        if not self.verify_hash_chain():
            raise P118LedgerError("wal_hash_chain_break")
        state: P118OperationState | None = None
        for entry in self._entries:
            if entry["operation_id"] != operation_id:
                continue
            payload = entry["payload"]
            if entry["receipt_type"] == "operation_registered":
                state = P118OperationState(
                    operation_id=operation_id,
                    state="received",
                    cas_version=0,
                    idempotency_key=str(payload["idempotency_key"]),
                    payload_hash=str(payload["payload_hash"]),
                    authority_counter_snapshot=dict(payload["authority_counter_snapshot"]),
                    duplicate_action_count=0,
                    lease_owner_id=str(payload["lease_owner_id"]) if payload.get("lease_owner_id") else None,
                )
            elif state is None:
                continue
            elif entry["receipt_type"] == "state_transition":
                state = P118OperationState(
                    operation_id=state.operation_id,
                    state=str(entry["state"]),
                    cas_version=int(entry["cas_version"]),
                    idempotency_key=state.idempotency_key,
                    payload_hash=state.payload_hash,
                    authority_counter_snapshot=state.authority_counter_snapshot,
                    duplicate_action_count=0,
                    lease_owner_id=entry.get("lease_owner_id") if entry.get("lease_owner_id") is not None else state.lease_owner_id,
                    lease_expires_at=state.lease_expires_at,
                )
            elif str(entry["receipt_type"]).startswith("lease_"):
                state = P118OperationState(
                    operation_id=state.operation_id,
                    state=state.state,
                    cas_version=state.cas_version,
                    idempotency_key=state.idempotency_key,
                    payload_hash=state.payload_hash,
                    authority_counter_snapshot=state.authority_counter_snapshot,
                    duplicate_action_count=0,
                    lease_owner_id=str(entry["lease_owner_id"]),
                    lease_expires_at=int(payload["lease_expires_at"]),
                )
        if state is None:
            raise P118LedgerError("unknown_operation")
        return state

    def verify_hash_chain(self) -> bool:
        previous = ""
        seen_positions: set[int] = set()
        for index, entry in enumerate(self._entries):
            if entry.get("wal_position") in seen_positions or entry.get("wal_position") != index:
                return False
            seen_positions.add(int(entry["wal_position"]))
            if entry.get("previous_hash") != previous:
                return False
            receipt_hash = str(entry.get("receipt_hash", ""))
            expected = stable_hash({key: value for key, value in entry.items() if key != "receipt_hash"})
            if receipt_hash != expected:
                return False
            previous = receipt_hash
        return True

    def _state_by_idempotency_key(self, idempotency_key: str) -> P118OperationState | None:
        operation_ids = [str(entry["operation_id"]) for entry in self._entries if entry["receipt_type"] == "operation_registered" and entry["payload"]["idempotency_key"] == idempotency_key]
        if not operation_ids:
            return None
        return self.replay(operation_ids[-1])

    def _append(
        self,
        operation_id: str,
        *,
        receipt_type: str,
        state: str,
        cas_version: int,
        lease_owner_id: str | None,
        payload: Mapping[str, Any],
        expected_prior_cas: int | None = None,
        expected_prior_state: str | None = None,
        expected_owner: str | None = None,
        expected_lease_owner: str | None = None,
        expected_lease_expires_at: int | None = None,
        register_idempotency_key: str | None = None,
        register_payload_hash: str | None = None,
    ) -> dict[str, Any]:
        with self._exclusive_lock():
            self._entries = self._load_entries()
            if not self.verify_hash_chain():
                raise P118LedgerError("wal_hash_chain_break")
            if register_idempotency_key is not None:
                existing = self._state_by_idempotency_key(register_idempotency_key)
                if existing is not None:
                    if existing.payload_hash != register_payload_hash:
                        raise P118LedgerError("idempotency_key_payload_mismatch")
                    operation_id = existing.operation_id
                    receipt_type = "idempotent_replay"
                    state = existing.state
                    cas_version = existing.cas_version
                    lease_owner_id = existing.lease_owner_id
                    payload = {"duplicate_action_count": 0}
            if expected_prior_cas is not None:
                current = self.replay(operation_id)
                if current.cas_version != expected_prior_cas:
                    raise P118LedgerError("cas_conflict")
                if expected_prior_state is not None and current.state != expected_prior_state:
                    raise P118LedgerError("state_changed_during_cas")
                if expected_owner is not None and current.lease_owner_id != expected_owner:
                    raise P118LedgerError("lease_owner_mismatch")
            if expected_lease_owner is not None or expected_lease_expires_at is not None:
                current = self.replay(operation_id)
                if current.lease_owner_id != expected_lease_owner or current.lease_expires_at != expected_lease_expires_at:
                    raise P118LedgerError("lease_changed_during_acquire")
            previous_hash = str(self._entries[-1]["receipt_hash"]) if self._entries else ""
            entry: dict[str, Any] = {
                "wal_position": len(self._entries),
                "previous_hash": previous_hash,
                "operation_id": operation_id,
                "receipt_type": receipt_type,
                "state": state,
                "cas_version": cas_version,
                "lease_owner_id": lease_owner_id,
                "authority_counter_snapshot": exact_zero_authority_counters(),
                "payload": dict(payload),
            }
            entry["receipt_hash"] = stable_hash(entry)
            line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
            descriptor = os.open(self.wal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, line.encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._entries.append(entry)
        return entry

    @contextmanager
    def _exclusive_lock(self):  # type: ignore[no-untyped-def]
        lock_path = self.wal_path.with_suffix(self.wal_path.suffix + ".lock")
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _load_entries(self) -> list[dict[str, Any]]:
        if not self.wal_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.wal_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    raise P118LedgerError("invalid_wal_entry")
                entries.append(entry)
        return entries

    def _receipt_from_entry(self, entry: Mapping[str, Any]) -> P118LedgerReceipt:
        return P118LedgerReceipt(
            receipt_type=str(entry["receipt_type"]),
            operation_id=str(entry["operation_id"]),
            state=str(entry["state"]),
            cas_version=int(entry["cas_version"]),
            wal_position=int(entry["wal_position"]),
            receipt_hash=str(entry["receipt_hash"]),
            previous_hash=str(entry["previous_hash"]),
            duplicate_action_count=int(_payload_value(entry, "duplicate_action_count", 0)),
            lease_owner_id=str(entry["lease_owner_id"]) if entry.get("lease_owner_id") is not None else None,
        )


def _idempotency_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "operation_id": payload["operation_id"],
        "p117_selected_action_pack_id": payload["p117_selected_action_pack_id"],
        "p115_action_pack_digest": payload["p115_action_pack_digest"],
        "fixture_target_id": payload["fixture_target_id"],
        "precondition_hash": stable_hash(payload["precondition_refs"]),
        "payload_hash": payload["envelope_hash"],
    }


def _payload_value(entry: Mapping[str, Any], key: str, default: Any) -> Any:
    payload = entry.get("payload")
    if isinstance(payload, Mapping):
        return payload.get(key, default)
    return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
