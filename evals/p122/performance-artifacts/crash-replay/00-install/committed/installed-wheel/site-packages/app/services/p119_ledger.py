"""Append-only P119 incident WAL with CAS, idempotency, leases, and replay."""

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
from app.services.p119_contract import (
    P119_TERMINAL_STATES,
    P119IncidentEnvelope,
    build_timeline_event,
    exact_zero_authority_counters,
    legal_transition,
)

_LEASE_REQUIRED_TO_ENTER = frozenset({"local_execution_pending", "local_executing", "validating", "rollback_pending", "rolling_back", "learning", "recovered", "orphaned_recovered"})


class P119LedgerError(ValueError):
    """Raised when P119 ledger invariants fail closed."""


@dataclass(frozen=True)
class P119LedgerReceipt:
    receipt_type: str
    incident_id: str
    state: str
    cas_version: int
    wal_position: int
    receipt_hash: str
    previous_hash: str
    timeline_hash: str
    lease_owner_id: str | None = None


@dataclass(frozen=True)
class P119IncidentState:
    incident_id: str
    alert_fingerprint: str
    fixture_id: str
    state: str
    cas_version: int
    idempotency_key: str
    payload_hash: str
    timeline_hash: str
    authority_counter_snapshot: Mapping[str, int]
    lease_owner_id: str | None = None
    lease_expires_at: int | None = None


class P119LedgerStore:
    def __init__(self, wal_path: Path) -> None:
        self.wal_path = wal_path
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries = self._load_entries()

    def register_incident(self, incident: P119IncidentEnvelope) -> P119LedgerReceipt:
        payload = incident.to_dict()
        return self._receipt_from_entry(
            self._append(
                incident.incident_id,
                receipt_type="incident_registered",
                state=incident.state,
                cas_version=incident.cas_version,
                lease_owner_id=None,
                timeline_event_type="incident_detected",
                payload={"incident": payload},
                register_idempotency_key=incident.idempotency_key,
                register_payload_hash=incident.payload_hash,
            )
        )

    def transition(self, incident_id: str, next_state: str, *, expected_cas_version: int, lease_owner_id: str | None = None, reason: str = "state_transition") -> P119LedgerReceipt:
        state = self.replay(incident_id)
        if state.state in P119_TERMINAL_STATES:
            raise P119LedgerError("terminal_state_reopened")
        if expected_cas_version != state.cas_version:
            raise P119LedgerError("cas_conflict")
        if not legal_transition(state.state, next_state):
            self._append(
                incident_id,
                receipt_type="illegal_transition_fail_closed",
                state="aborted_fail_closed",
                cas_version=state.cas_version + 1,
                lease_owner_id=state.lease_owner_id,
                timeline_event_type="transition_rejected_fail_closed",
                payload={"from_state": state.state, "attempted_state": next_state, "reason": "illegal_state_transition"},
                expected_prior_cas=expected_cas_version,
                expected_prior_state=state.state,
            )
            raise P119LedgerError("illegal_state_transition")
        if next_state in _LEASE_REQUIRED_TO_ENTER and (not lease_owner_id or state.lease_owner_id != lease_owner_id):
            raise P119LedgerError("lease_owner_mismatch")
        return self._receipt_from_entry(
            self._append(
                incident_id,
                receipt_type="state_transition",
                state=next_state,
                cas_version=state.cas_version + 1,
                lease_owner_id=state.lease_owner_id,
                timeline_event_type=_event_type_for(next_state),
                payload={"from_state": state.state, "to_state": next_state, "reason": reason},
                expected_prior_cas=expected_cas_version,
                expected_prior_state=state.state,
            )
        )

    def acquire_lease(self, incident_id: str, *, owner_id: str, now: int, ttl: int) -> P119LedgerReceipt:
        if not owner_id:
            raise P119LedgerError("missing_lease_owner")
        state = self.replay(incident_id)
        if state.lease_owner_id and state.lease_expires_at is not None and state.lease_expires_at > now and state.lease_owner_id != owner_id:
            raise P119LedgerError("lease_split_brain")
        return self._receipt_from_entry(
            self._append(
                incident_id,
                receipt_type="lease_acquired",
                state=state.state,
                cas_version=state.cas_version,
                lease_owner_id=owner_id,
                timeline_event_type="lease_acquired",
                payload={"owner_id": owner_id, "lease_expires_at": now + ttl},
                expected_lease_owner=state.lease_owner_id,
                expected_lease_expires_at=state.lease_expires_at,
            )
        )

    def replay(self, incident_id: str) -> P119IncidentState:
        if not self.verify_hash_chain():
            raise P119LedgerError("wal_hash_chain_break")
        state: P119IncidentState | None = None
        for entry in self._entries:
            if entry["incident_id"] != incident_id:
                continue
            payload = _mapping(entry.get("payload"))
            if entry["receipt_type"] == "incident_registered":
                incident = _mapping(payload.get("incident"))
                state = P119IncidentState(
                    incident_id=incident_id,
                    alert_fingerprint=str(incident["alert_fingerprint"]),
                    fixture_id=str(incident["fixture_id"]),
                    state=str(entry["state"]),
                    cas_version=int(entry["cas_version"]),
                    idempotency_key=str(incident["idempotency_key"]),
                    payload_hash=str(incident["payload_hash"]),
                    timeline_hash=str(entry["timeline_hash"]),
                    authority_counter_snapshot=dict(incident["authority_counter_snapshot"]),
                )
            elif state is None:
                continue
            elif entry["receipt_type"] in {"state_transition", "illegal_transition_fail_closed", "idempotency_conflict_fail_closed"}:
                state = P119IncidentState(
                    incident_id=state.incident_id,
                    alert_fingerprint=state.alert_fingerprint,
                    fixture_id=state.fixture_id,
                    state=str(entry["state"]),
                    cas_version=int(entry["cas_version"]),
                    idempotency_key=state.idempotency_key,
                    payload_hash=state.payload_hash,
                    timeline_hash=str(entry["timeline_hash"]),
                    authority_counter_snapshot=state.authority_counter_snapshot,
                    lease_owner_id=state.lease_owner_id,
                    lease_expires_at=state.lease_expires_at,
                )
            elif entry["receipt_type"] == "lease_acquired":
                state = P119IncidentState(
                    incident_id=state.incident_id,
                    alert_fingerprint=state.alert_fingerprint,
                    fixture_id=state.fixture_id,
                    state=state.state,
                    cas_version=state.cas_version,
                    idempotency_key=state.idempotency_key,
                    payload_hash=state.payload_hash,
                    timeline_hash=str(entry["timeline_hash"]),
                    authority_counter_snapshot=state.authority_counter_snapshot,
                    lease_owner_id=str(entry["lease_owner_id"]),
                    lease_expires_at=int(payload["lease_expires_at"]),
                )
        if state is None:
            raise P119LedgerError("unknown_incident")
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
            expected = stable_hash({key: value for key, value in entry.items() if key != "receipt_hash"})
            if entry.get("receipt_hash") != expected:
                return False
            previous = str(entry["receipt_hash"])
        return True

    def _state_by_idempotency_key(self, idempotency_key: str) -> P119IncidentState | None:
        incident_ids = [
            str(entry["incident_id"])
            for entry in self._entries
            if entry["receipt_type"] == "incident_registered" and _mapping(_mapping(entry["payload"]).get("incident")).get("idempotency_key") == idempotency_key
        ]
        if not incident_ids:
            return None
        return self.replay(incident_ids[-1])

    def _append(
        self,
        incident_id: str,
        *,
        receipt_type: str,
        state: str,
        cas_version: int,
        lease_owner_id: str | None,
        timeline_event_type: str,
        payload: Mapping[str, Any],
        expected_prior_cas: int | None = None,
        expected_prior_state: str | None = None,
        expected_lease_owner: str | None = None,
        expected_lease_expires_at: int | None = None,
        register_idempotency_key: str | None = None,
        register_payload_hash: str | None = None,
    ) -> dict[str, Any]:
        raise_after_append: str | None = None
        with self._exclusive_lock():
            self._entries = self._load_entries()
            if not self.verify_hash_chain():
                raise P119LedgerError("wal_hash_chain_break")
            if register_idempotency_key is not None:
                existing = self._state_by_idempotency_key(register_idempotency_key)
                if existing is not None:
                    if existing.payload_hash != register_payload_hash:
                        incident_id = existing.incident_id
                        receipt_type = "idempotency_conflict_fail_closed"
                        state = "aborted_fail_closed"
                        cas_version = existing.cas_version + 1
                        lease_owner_id = existing.lease_owner_id
                        timeline_event_type = "transition_rejected_fail_closed"
                        payload = {"reason": "idempotency_key_payload_mismatch"}
                        raise_after_append = "idempotency_key_payload_mismatch"
                    else:
                        incident_id = existing.incident_id
                        receipt_type = "idempotent_replay"
                        state = existing.state
                        cas_version = existing.cas_version
                        lease_owner_id = existing.lease_owner_id
                        timeline_event_type = "dedupe_or_correlation_decision"
                        payload = {"reason": "duplicate_idempotency_key"}
            state_before = state
            if expected_prior_cas is not None:
                current = self.replay(incident_id)
                if current.cas_version != expected_prior_cas:
                    raise P119LedgerError("cas_conflict")
                if expected_prior_state is not None and current.state != expected_prior_state:
                    raise P119LedgerError("state_changed_during_cas")
                state_before = current.state
            if expected_lease_owner is not None or expected_lease_expires_at is not None:
                current = self.replay(incident_id)
                if current.lease_owner_id != expected_lease_owner or current.lease_expires_at != expected_lease_expires_at:
                    raise P119LedgerError("lease_changed_during_acquire")
            previous_hash = str(self._entries[-1]["receipt_hash"]) if self._entries else ""
            previous_timeline_hash = str(self._entries[-1]["timeline_hash"]) if self._entries else ""
            event = build_timeline_event(
                incident_id=incident_id,
                event_type=timeline_event_type,
                state_before=state_before,
                state_after=state,
                timestamp=len(self._entries),
                actor_type="p119_local_contract",
                payload=payload,
                previous_hash=previous_timeline_hash,
                budget_snapshot={"receipt_count": len(self._entries) + 1},
                authority_counter_snapshot=exact_zero_authority_counters(),
            )
            entry: dict[str, Any] = {
                "wal_position": len(self._entries),
                "previous_hash": previous_hash,
                "incident_id": incident_id,
                "receipt_type": receipt_type,
                "state": state,
                "cas_version": cas_version,
                "lease_owner_id": lease_owner_id,
                "authority_counter_snapshot": exact_zero_authority_counters(),
                "timeline_hash": event["current_hash"],
                "timeline_event": event,
                "payload": dict(payload),
            }
            entry["receipt_hash"] = stable_hash(entry)
            descriptor = os.open(self.wal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, (json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._entries.append(entry)
        if raise_after_append is not None:
            raise P119LedgerError(raise_after_append)
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
                    raise P119LedgerError("invalid_wal_entry")
                entries.append(entry)
        return entries

    def _receipt_from_entry(self, entry: Mapping[str, Any]) -> P119LedgerReceipt:
        return P119LedgerReceipt(
            receipt_type=str(entry["receipt_type"]),
            incident_id=str(entry["incident_id"]),
            state=str(entry["state"]),
            cas_version=int(entry["cas_version"]),
            wal_position=int(entry["wal_position"]),
            receipt_hash=str(entry["receipt_hash"]),
            previous_hash=str(entry["previous_hash"]),
            timeline_hash=str(entry["timeline_hash"]),
            lease_owner_id=str(entry["lease_owner_id"]) if entry.get("lease_owner_id") is not None else None,
        )


def _event_type_for(state: str) -> str:
    return {
        "triage_started": "triage_started",
        "diagnosing": "evidence_packet_bound",
        "evidence_acquiring": "evidence_acquisition_requested",
        "selection_pending": "decision_selected",
        "approval_pending": "approval_requested",
        "approved": "approval_granted",
        "local_execution_pending": "operation_enqueued",
        "local_executing": "local_action_attempted",
        "validating": "validation_started",
        "rollback_pending": "validation_failed",
        "rolling_back": "rollback_started",
        "learning": "learning_record_written",
        "recovered": "incident_terminalized",
        "escalated": "human_escalation_required",
        "expired": "incident_terminalized",
        "orphaned_recovered": "orphan_inventory_recorded",
        "aborted_fail_closed": "transition_rejected_fail_closed",
    }.get(state, "authority_counter_snapshot")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
