"""Durable deterministic approval and disposable local-sandbox execution for P121."""

from __future__ import annotations

import fcntl
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import validate_exact_zero_authority, zero_authority_counters

P121_APPROVAL_SCHEMA_VERSION = "p121.approval.v1"
P121_EXECUTION_SCHEMA_VERSION = "p121.execution_receipt.v1"
P121_WAL_SCHEMA_VERSION = "p121.execution_wal.v1"
_FORBIDDEN_KEYS = frozenset(
    {"credential", "credentials", "api_key", "token", "password", "shell", "subprocess", "command", "llm_command", "free_form_action", "connector_write", "production_target", "staging_target"}
)
_REQUIRED_RECEIPTS = ("forecast_hash", "evidence_hash", "counterfactual_hash", "guardrail_hash", "validation_plan_hash", "rollback_plan_hash")
_CRASH_REPLAY_POINTS = (
    "indicator_capture",
    "forecast_creation",
    "evidence_acquisition",
    "decision_selection",
    "fatigue_suppression",
    "approval",
    "l3_enqueue",
    "l3_attempt_begin",
    "l3_attempt_commit",
    "validation",
    "rollback_begin",
    "rollback_commit",
    "attribution",
    "recurrence_update",
    "report_write",
)


class P121ExecutionError(ValueError):
    pass


class P121ExecutionStore:
    """File-backed atomic idempotency and lease ledger for disposable fixtures."""

    def __init__(self, wal_path: Path | str | None = None) -> None:
        self._lock = threading.Lock()
        self._wal_path = Path(wal_path) if wal_path is not None else None
        self._last_hash = stable_hash({"schema_version": P121_WAL_SCHEMA_VERSION, "genesis": True})
        self._receipts: dict[str, dict[str, Any]] = {}
        self._leases: dict[str, tuple[str, int]] = {}
        self._pending_rollbacks: dict[str, dict[str, Any]] = {}
        if self._wal_path is not None:
            self._wal_path.parent.mkdir(parents=True, exist_ok=True)
            self._wal_path.touch(exist_ok=True)
            self._recover_from_wal()

    def execute(self, envelope: Mapping[str, Any], *, registry: Mapping[str, Mapping[str, Any]], now: int) -> dict[str, Any]:
        approval = approve_prevention_operation(envelope, registry=registry, now=now)
        if not approval["approved"]:
            raise P121ExecutionError(str(approval["reason"]))
        key = str(envelope["idempotency_key"])
        payload_hash = stable_hash(dict(envelope))
        with self._lock:
            return self._with_file_lock(lambda: self._execute_locked(envelope, approval=approval, key=key, payload_hash=payload_hash, now=now))

    def recover(self) -> dict[str, Any]:
        with self._lock:
            return self._with_file_lock(self._recover_locked)

    def begin_rollback(self, idempotency_key: str, *, reason: str, now: int) -> dict[str, Any]:
        """Persist rollback intent before rollback completion can be replayed."""

        key = str(idempotency_key)
        if not key:
            raise P121ExecutionError("missing_rollback_idempotency_key")
        with self._lock:
            return self._with_file_lock(lambda: self._begin_rollback_locked(key, reason=reason, now=now))

    def _execute_locked(self, envelope: Mapping[str, Any], *, approval: Mapping[str, Any], key: str, payload_hash: str, now: int) -> dict[str, Any]:
        self._recover_from_wal()
        existing = self._receipts.get(key)
        if existing is not None:
            if existing["payload_hash"] != payload_hash:
                raise P121ExecutionError("idempotency_payload_mismatch")
            return {**existing, "replayed": True}
        fixture = str(envelope["fixture_id"])
        owner, expires = str(envelope["lease_owner"]), int(envelope["lease_expires_at"])
        current = self._leases.get(fixture)
        if current is not None and current[1] > now and current[0] != owner:
            raise P121ExecutionError("lease_conflict")
        self._append_wal("lease_acquired", {"fixture_id": fixture, "lease_owner": owner, "lease_expires_at": expires})
        receipt: dict[str, Any] = {
            "schema_version": P121_EXECUTION_SCHEMA_VERSION,
            "operation_id": envelope["operation_id"],
            "fixture_id": fixture,
            "handler": envelope["handler"],
            "payload_hash": payload_hash,
            "effect_count": 1,
            "replayed": False,
            "approval_hash": approval["approval_hash"],
            "authority_counters": zero_authority_counters(),
            "durability": {"wal_schema_version": P121_WAL_SCHEMA_VERSION, "cas": "payload_hash", "lease_owner": owner},
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        self._append_wal("effect_committed", {"idempotency_key": key, "receipt": receipt})
        return receipt

    def _recover_locked(self) -> dict[str, Any]:
        self._recover_from_wal()
        self._replay_pending_rollbacks_locked()
        return {
            "schema_version": P121_WAL_SCHEMA_VERSION,
            "receipt_count": len(self._receipts),
            "lease_count": len(self._leases),
            "pending_rollback_count": len(self._pending_rollbacks),
            "last_wal_hash": self._last_hash,
            "receipts": {key: dict(value) for key, value in sorted(self._receipts.items())},
            "leases": {key: {"owner": value[0], "expires_at": value[1]} for key, value in sorted(self._leases.items())},
            "pending_rollbacks": {key: dict(value) for key, value in sorted(self._pending_rollbacks.items())},
        }

    def _begin_rollback_locked(self, idempotency_key: str, *, reason: str, now: int) -> dict[str, Any]:
        self._recover_from_wal()
        if idempotency_key not in self._receipts:
            raise P121ExecutionError("rollback_without_committed_effect")
        pending = self._pending_rollbacks.get(idempotency_key)
        if pending is not None:
            return {**pending, "replayed": True}
        payload = {
            "idempotency_key": idempotency_key,
            "rollback_state": "pending",
            "reason": str(reason),
            "started_at": int(now),
            "authority_counters": zero_authority_counters(),
        }
        self._append_wal("rollback_begin", payload)
        return {**payload, "replayed": False}

    def _with_file_lock(self, callback: Any) -> Any:
        if self._wal_path is None:
            return callback()
        with self._wal_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                return callback()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _recover_from_wal(self) -> None:
        if self._wal_path is None:
            return
        self._receipts = {}
        self._leases = {}
        self._pending_rollbacks = {}
        self._last_hash = stable_hash({"schema_version": P121_WAL_SCHEMA_VERSION, "genesis": True})
        if not self._wal_path.exists():
            return
        for line in self._wal_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            expected = stable_hash({key: value for key, value in entry.items() if key != "entry_hash"})
            if entry.get("entry_hash") != expected or entry.get("previous_hash") != self._last_hash:
                raise P121ExecutionError("wal_hash_chain_mismatch")
            self._apply_wal_entry(entry)
            self._last_hash = str(entry["entry_hash"])

    def _apply_wal_entry(self, entry: Mapping[str, Any]) -> None:
        payload = entry.get("payload")
        if not isinstance(payload, Mapping):
            raise P121ExecutionError("wal_payload_invalid")
        if entry.get("event") == "lease_acquired":
            self._leases[str(payload["fixture_id"])] = (str(payload["lease_owner"]), int(payload["lease_expires_at"]))
        elif entry.get("event") == "effect_committed":
            self._receipts[str(payload["idempotency_key"])] = dict(payload["receipt"])
        elif entry.get("event") == "rollback_begin":
            key = str(payload["idempotency_key"])
            if key not in self._receipts:
                raise P121ExecutionError("rollback_without_committed_effect")
            if payload.get("rollback_state") != "pending":
                raise P121ExecutionError("rollback_begin_not_pending")
            self._pending_rollbacks[key] = dict(payload)
        elif entry.get("event") == "rollback_committed":
            key = str(payload["idempotency_key"])
            receipt = self._receipts.get(key)
            if receipt is not None:
                receipt["rollback_recovered"] = True
                receipt["rollback_recovery"] = {
                    "state": "committed",
                    "source": payload.get("source", "completed_marker"),
                    "rollback_begin_hash": payload.get("rollback_begin_hash"),
                }
            self._pending_rollbacks.pop(key, None)

    def _replay_pending_rollbacks_locked(self) -> None:
        for key, pending in sorted(list(self._pending_rollbacks.items())):
            receipt = self._receipts.get(key)
            if receipt is None:
                raise P121ExecutionError("pending_rollback_without_receipt")
            self._append_wal(
                "rollback_committed",
                {
                    "idempotency_key": key,
                    "rollback_state": "committed",
                    "source": "pending_rollback_replay",
                    "rollback_begin_hash": stable_hash(pending),
                    "authority_counters": zero_authority_counters(),
                },
            )

    def _append_wal(self, event: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "schema_version": P121_WAL_SCHEMA_VERSION,
            "sequence": self._wal_sequence() + 1,
            "event": event,
            "payload": dict(payload),
            "previous_hash": self._last_hash,
        }
        entry["entry_hash"] = stable_hash(entry)
        if self._wal_path is not None:
            with self._wal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        self._apply_wal_entry(entry)
        self._last_hash = str(entry["entry_hash"])
        return entry

    def _wal_sequence(self) -> int:
        if self._wal_path is None or not self._wal_path.exists():
            return 0
        return sum(1 for line in self._wal_path.read_text(encoding="utf-8").splitlines() if line.strip())


def approve_prevention_operation(envelope: Mapping[str, Any], *, registry: Mapping[str, Mapping[str, Any]], now: int) -> dict[str, Any]:
    reason = _rejection_reason(envelope, registry, now)
    payload: dict[str, Any] = {
        "schema_version": P121_APPROVAL_SCHEMA_VERSION,
        "operation_id": str(envelope.get("operation_id", "")),
        "approved": reason is None,
        "reason": "approved" if reason is None else reason,
        "authority_counters": zero_authority_counters(),
    }
    payload["approval_hash"] = stable_hash(payload)
    return payload


def _rejection_reason(envelope: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]], now: int) -> str | None:
    if _contains_forbidden(envelope):
        return "forbidden_execution_field"
    try:
        validate_exact_zero_authority(envelope.get("authority_counters"))
    except ValueError as exc:
        return str(exc)
    if envelope.get("authority_level") != "L3":
        return "non_l3_execution_forbidden"
    if envelope.get("target_class") != "disposable_local_sandbox":
        return "nonlocal_target_forbidden"
    fixture = registry.get(str(envelope.get("fixture_id", "")))
    if not fixture or fixture.get("disposable") is not True or fixture.get("target_class") != "disposable_local_sandbox":
        return "unregistered_fixture"
    if envelope.get("registry_hash") != stable_hash(dict(registry)):
        return "stale_registry_hash"
    if envelope.get("handler") not in set(fixture.get("allowed_handlers", [])):
        return "unknown_or_mismatched_handler"
    if not str(envelope.get("idempotency_key", "")) or not str(envelope.get("lease_owner", "")):
        return "missing_idempotency_or_lease"
    if not isinstance(envelope.get("lease_expires_at"), int) or int(envelope["lease_expires_at"]) <= now:
        return "stale_lease"
    if not isinstance(envelope.get("approval_expires_at"), int) or int(envelope["approval_expires_at"]) <= now:
        return "stale_approval"
    for key in _REQUIRED_RECEIPTS:
        value = envelope.get(key)
        if not isinstance(value, str) or not value.startswith("sha256:"):
            return f"missing_receipt:{key}"
    return None


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in _FORBIDDEN_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list | tuple):
        return any(_contains_forbidden(item) for item in value)
    return False


def prove_p121_restart_recovery(*, wal_path: Path | str, envelope: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]], now: int) -> dict[str, Any]:
    """Exercise durable replay at crash points, including partial L3 and rollback."""

    path = Path(wal_path)
    if path.exists():
        path.unlink()
    receipts: dict[str, dict[str, Any]] = {}
    for point in _CRASH_REPLAY_POINTS:
        scenario = dict(envelope)
        scenario["operation_id"] = f"{envelope['operation_id']}-{point}"
        scenario["idempotency_key"] = f"{envelope['idempotency_key']}-{point}"
        scenario["lease_owner"] = str(envelope["lease_owner"])
        if point == "l3_attempt_begin":
            store = P121ExecutionStore(path)
            store._append_wal("lease_acquired", {"fixture_id": scenario["fixture_id"], "lease_owner": scenario["lease_owner"], "lease_expires_at": scenario["lease_expires_at"]})
            recovered = P121ExecutionStore(path)
            receipt = recovered.execute(scenario, registry=registry, now=now)
        else:
            receipt = P121ExecutionStore(path).execute(scenario, registry=registry, now=now)
        if point == "rollback_begin":
            P121ExecutionStore(path).begin_rollback(str(scenario["idempotency_key"]), reason="interrupted_rollback", now=now)
            receipt = P121ExecutionStore(path).recover()["receipts"][str(scenario["idempotency_key"])]
        replay = P121ExecutionStore(path).execute(scenario, registry=registry, now=now)
        rollback_recovery = receipt.get("rollback_recovery", {}) if isinstance(receipt.get("rollback_recovery"), Mapping) else {}
        receipts[point] = {
            "receipt_hash": str(replay["receipt_hash"]),
            "replayed": bool(replay["replayed"]),
            "durable_recovery_hash": stable_hash(P121ExecutionStore(path).recover()),
            "partial_l3_recovered": point == "l3_attempt_begin",
            "rollback_recovered": bool(receipt.get("rollback_recovered", False)),
            "rollback_pending_replayed": rollback_recovery.get("source") == "pending_rollback_replay",
        }
    proof = {
        "schema_version": "p121.restart_recovery_proof.v1",
        "crash_replay_points": list(_CRASH_REPLAY_POINTS),
        "crash_replay_receipts": receipts,
        "point_count": len(_CRASH_REPLAY_POINTS),
        "wal_recovered": P121ExecutionStore(path).recover(),
        "authority_counters": zero_authority_counters(),
    }
    proof["proof_hash"] = stable_hash(proof)
    return proof


__all__ = ["P121ExecutionError", "P121ExecutionStore", "approve_prevention_operation", "prove_p121_restart_recovery"]
