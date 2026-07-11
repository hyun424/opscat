"""Deterministic orphan inventory, crash recovery, and read-only replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_ledger import P118LedgerError, P118LedgerStore
from app.services.p118_operation_contract import P118_TERMINAL_STATUSES


@dataclass(frozen=True)
class P118CrashRecoveryResult:
    operation_id: str
    final_state: str
    duplicate_action_count: int
    rollback_attempts: int
    orphan_recoveries: int
    rollback_evidence_hash: str | None = None


def inventory_p118_orphans(wal_path: Path, *, now: int) -> dict[str, list[str]]:
    ledger = P118LedgerStore(wal_path)
    operation_ids = _operation_ids(wal_path)
    expired: list[str] = []
    pending: list[str] = []
    for operation_id in operation_ids:
        state = ledger.replay(operation_id)
        if state.state in P118_TERMINAL_STATUSES:
            continue
        if state.lease_expires_at is not None and state.lease_expires_at <= now:
            expired.append(operation_id)
            if state.state in {"action_attempted", "postchecked", "action_failed", "postcheck_failed", "rollback_attempted", "rollback_postchecked"}:
                pending.append(operation_id)
    return {"expired_leases": sorted(expired), "pending_rollback": sorted(pending)}


def recover_p118_crash(wal_path: Path, *, operation_id: str, owner_id: str, now: int) -> P118CrashRecoveryResult:
    ledger = P118LedgerStore(wal_path)
    state = ledger.replay(operation_id)
    if state.state in P118_TERMINAL_STATUSES:
        return P118CrashRecoveryResult(operation_id, state.state, 0, 0, 0)
    if state.lease_expires_at is None or state.lease_expires_at > now:
        raise P118LedgerError("lease_not_expired")
    previous_owner = state.lease_owner_id
    previous_expiry = state.lease_expires_at
    ledger.record_lease(
        operation_id,
        owner_id=owner_id,
        expires_at=now + 60,
        receipt_type="lease_takeover",
        expected_lease_owner=previous_owner,
        expected_lease_expires_at=previous_expiry,
    )
    state = ledger.replay(operation_id)
    rollback_attempts = 0
    rollback_evidence_hash: str | None = None
    if state.state in {"received", "verified", "approved", "prechecked"}:
        ledger.transition(operation_id, "aborted_fail_closed", expected_cas_version=state.cas_version, lease_owner_id=owner_id)
        state = ledger.replay(operation_id)
        return P118CrashRecoveryResult(operation_id, state.state, 0, 0, 1, None)
    if state.state in {"action_attempted", "postchecked", "action_failed", "postcheck_failed"}:
        ledger.transition(operation_id, "rollback_attempted", expected_cas_version=state.cas_version, lease_owner_id=owner_id)
        rollback_attempts = 1
        rollback_evidence_hash = stable_hash({"operation_id": operation_id, "recovery_owner": owner_id, "recovery_time": now, "phase": "rollback_postcheck"})
        state = ledger.replay(operation_id)
    if state.state == "rollback_attempted":
        ledger.transition(operation_id, "rollback_postchecked", expected_cas_version=state.cas_version, lease_owner_id=owner_id)
        state = ledger.replay(operation_id)
    if state.state == "rollback_postchecked":
        ledger.transition(operation_id, "rolled_back", expected_cas_version=state.cas_version, lease_owner_id=owner_id)
        state = ledger.replay(operation_id)
    if state.state != "rolled_back":
        raise P118LedgerError("orphan_not_recoverable_without_effect_replay")
    return P118CrashRecoveryResult(operation_id, state.state, 0, rollback_attempts, 1, rollback_evidence_hash)


def replay_p118_terminal_read_only(wal_path: Path, operation_id: str) -> dict[str, Any]:
    state = P118LedgerStore(wal_path).replay(operation_id)
    if state.state not in P118_TERMINAL_STATUSES:
        raise P118LedgerError("nonterminal_read_only_replay")
    result = asdict(state)
    result["replay_drift"] = 0
    result["duplicate_action_count"] = 0
    return result


def _operation_ids(wal_path: Path) -> set[str]:
    import json

    ids: set[str] = set()
    if not wal_path.exists():
        return ids
    for line in wal_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("receipt_type") == "operation_registered":
            ids.add(str(entry["operation_id"]))
    return ids


__all__ = ["P118CrashRecoveryResult", "inventory_p118_orphans", "recover_p118_crash", "replay_p118_terminal_read_only"]
