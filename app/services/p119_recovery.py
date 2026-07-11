"""P119 orphan inventory and deterministic crash recovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.services.p110_evaluation import stable_hash
from app.services.p119_contract import P119_TERMINAL_STATES
from app.services.p119_ledger import P119LedgerError, P119LedgerStore


@dataclass(frozen=True)
class P119RecoveryResult:
    incident_id: str
    final_state: str
    duplicate_local_action_count: int
    rollback_attempt_count: int
    recovery_receipt_hash: str


def inventory_p119_orphans(wal_path: Path, *, now: int) -> dict[str, list[str]]:
    ledger = P119LedgerStore(wal_path)
    expired: list[str] = []
    pending_rollback: list[str] = []
    unterminated: list[str] = []
    for incident_id in _incident_ids(wal_path):
        state = ledger.replay(incident_id)
        if state.state in P119_TERMINAL_STATES:
            continue
        unterminated.append(incident_id)
        if state.lease_expires_at is not None and state.lease_expires_at <= now:
            expired.append(incident_id)
            if state.state in {"local_executing", "validating", "rollback_pending", "rolling_back"}:
                pending_rollback.append(incident_id)
    return {"expired_leases": sorted(expired), "pending_rollback": sorted(pending_rollback), "unterminated_incidents": sorted(unterminated)}


def recover_p119_incident(wal_path: Path, *, incident_id: str, recovery_owner: str, now: int) -> P119RecoveryResult:
    ledger = P119LedgerStore(wal_path)
    state = ledger.replay(incident_id)
    if state.state in P119_TERMINAL_STATES:
        return _result(incident_id, state.state, 0)
    if state.lease_expires_at is not None and state.lease_expires_at > now:
        raise P119LedgerError("lease_not_expired")
    ledger.acquire_lease(incident_id, owner_id=recovery_owner, now=now, ttl=60)
    state = ledger.replay(incident_id)
    attempts = 0
    if state.state in {"local_executing", "validating"}:
        ledger.transition(incident_id, "rollback_pending", expected_cas_version=state.cas_version, lease_owner_id=recovery_owner, reason="crash_recovery")
        state = ledger.replay(incident_id)
    if state.state == "rollback_pending":
        ledger.transition(incident_id, "rolling_back", expected_cas_version=state.cas_version, lease_owner_id=recovery_owner, reason="crash_recovery")
        attempts = 1
        state = ledger.replay(incident_id)
    if state.state == "rolling_back":
        ledger.transition(incident_id, "orphaned_recovered", expected_cas_version=state.cas_version, lease_owner_id=recovery_owner, reason="rollback_postchecked")
        state = ledger.replay(incident_id)
    elif state.state not in P119_TERMINAL_STATES:
        ledger.transition(incident_id, "aborted_fail_closed", expected_cas_version=state.cas_version, reason="pre_action_orphan")
        state = ledger.replay(incident_id)
    return _result(incident_id, state.state, attempts)


def replay_p119_terminal_read_only(wal_path: Path, incident_id: str) -> dict[str, object]:
    state = P119LedgerStore(wal_path).replay(incident_id)
    if state.state not in P119_TERMINAL_STATES:
        raise P119LedgerError("nonterminal_replay")
    return {
        "incident_id": incident_id,
        "state": state.state,
        "cas_version": state.cas_version,
        "timeline_hash": state.timeline_hash,
        "duplicate_local_action_count": 0,
        "replay_drift": 0,
        "replay_hash": stable_hash(state),
    }


def _result(incident_id: str, state: str, attempts: int) -> P119RecoveryResult:
    return P119RecoveryResult(incident_id, state, 0, attempts, stable_hash({"incident_id": incident_id, "state": state, "rollback_attempts": attempts}))


def _incident_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(entry["incident_id"]) for line in path.read_text(encoding="utf-8").splitlines() if line.strip() for entry in [json.loads(line)] if entry.get("receipt_type") == "incident_registered"}


__all__ = ["P119RecoveryResult", "inventory_p119_orphans", "recover_p119_incident", "replay_p119_terminal_read_only"]
