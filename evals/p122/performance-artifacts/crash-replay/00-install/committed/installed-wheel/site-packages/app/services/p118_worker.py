"""Bounded local P118 worker lease and state-transition loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.p118_approval import validate_p118_approval_decision_receipt
from app.services.p118_ledger import P118LedgerStore
from app.services.p118_operation_contract import P118_AUTHORITY_COUNTER_KEYS, P118OperationEnvelope
from app.services.p118_validation_cycle import P118ValidationCycleResult


class P118WorkerError(ValueError):
    """Raised when a P118 worker cannot prove ownership or bounded progress."""


@dataclass(frozen=True)
class P118LeaseReceipt:
    receipt_type: str
    operation_id: str
    owner_id: str
    expires_at: int
    cas_version: int


@dataclass(frozen=True)
class P118WorkerResult:
    operation_id: str
    final_state: str
    transitions: list[str]
    retry_count: int
    authority_counter_snapshot: dict[str, int]


class P118Worker:
    def __init__(self, ledger: P118LedgerStore, *, owner_id: str, lease_ttl_seconds: int, max_retries: int) -> None:
        if lease_ttl_seconds <= 0:
            raise P118WorkerError("invalid_lease_ttl")
        if max_retries < 0:
            raise P118WorkerError("invalid_retry_limit")
        self.ledger = ledger
        self.owner_id = owner_id
        self.lease_ttl_seconds = lease_ttl_seconds
        self.max_retries = max_retries

    def acquire_lease(self, operation_id: str, *, now: int) -> P118LeaseReceipt:
        state = self.ledger.replay(operation_id)
        receipt_type = "lease_acquired"
        if state.lease_owner_id is not None and state.lease_owner_id != self.owner_id:
            if state.lease_expires_at is None or now <= state.lease_expires_at:
                raise P118WorkerError("lease_takeover_before_expiry")
            receipt_type = "lease_takeover"
        receipt = self.ledger.record_lease(
            operation_id,
            owner_id=self.owner_id,
            expires_at=now + self.lease_ttl_seconds,
            receipt_type=receipt_type,
            expected_lease_owner=state.lease_owner_id,
            expected_lease_expires_at=state.lease_expires_at,
        )
        return P118LeaseReceipt(receipt_type=receipt.receipt_type, operation_id=operation_id, owner_id=self.owner_id, expires_at=now + self.lease_ttl_seconds, cas_version=receipt.cas_version)

    def renew_lease(self, operation_id: str, *, now: int) -> P118LeaseReceipt:
        state = self.ledger.replay(operation_id)
        if state.lease_owner_id != self.owner_id:
            raise P118WorkerError("stale_lease_renewal")
        receipt = self.ledger.record_lease(
            operation_id,
            owner_id=self.owner_id,
            expires_at=now + self.lease_ttl_seconds,
            receipt_type="lease_renewed",
            expected_lease_owner=state.lease_owner_id,
            expected_lease_expires_at=state.lease_expires_at,
        )
        return P118LeaseReceipt(receipt_type=receipt.receipt_type, operation_id=operation_id, owner_id=self.owner_id, expires_at=now + self.lease_ttl_seconds, cas_version=receipt.cas_version)

    def run_once(
        self,
        operation_id: str,
        *,
        now: int,
        validation_result: P118ValidationCycleResult,
        operation: P118OperationEnvelope,
        verification_hash: str,
        approval_receipt: dict[str, Any],
        lease_receipt: dict[str, Any],
        wal_receipt: dict[str, Any],
        cas_version: int,
    ) -> P118WorkerResult:
        state = self.ledger.replay(operation_id)
        if state.lease_owner_id != self.owner_id or state.lease_expires_at is None or now > state.lease_expires_at:
            raise P118WorkerError("worker_without_owner_receipt")
        if not verification_hash.startswith("sha256:") or not validate_p118_approval_decision_receipt(
            approval_receipt,
            operation=operation.to_dict(),
            verification_hash=verification_hash,
            lease_receipt=lease_receipt,
            wal_receipt=wal_receipt,
            cas_version=cas_version,
            now=now,
        ):
            raise P118WorkerError("missing_verification_or_approval_binding")
        if approval_receipt.get("operation_id") != operation_id or approval_receipt.get("verification_hash") != verification_hash:
            raise P118WorkerError("unbound_approval_receipt")
        approval_decision_hash = str(approval_receipt["decision_hash"])
        if validation_result.final_status == "succeeded":
            if validation_result.precheck_evidence_hash is None or validation_result.postcheck_evidence_hash is None:
                raise P118WorkerError("measured_validation_required")
            path: tuple[str, ...] = ("verified", "approved", "prechecked", "action_attempted", "postchecked", "succeeded")
        elif validation_result.final_status == "rolled_back":
            if validation_result.rollback_evidence_hash is None:
                raise P118WorkerError("rollback_evidence_required")
            path = ("verified", "approved", "prechecked", "action_attempted", "rollback_attempted", "rollback_postchecked", "rolled_back")
        else:
            raise P118WorkerError("qualified_terminal_validation_required")
        transitions: list[str] = []
        evidence_by_state: dict[str, dict[str, Any]] = {
            "verified": {"verification_hash": verification_hash},
            "approved": {"approval_decision_hash": approval_decision_hash},
            "prechecked": {"precheck_evidence_hash": validation_result.precheck_evidence_hash},
            "action_attempted": {"validation_cycle_bound": True},
            "postchecked": {"postcheck_evidence_hash": validation_result.postcheck_evidence_hash},
            "succeeded": {"postcheck_evidence_hash": validation_result.postcheck_evidence_hash},
            "rollback_attempted": {"rollback_evidence_hash": validation_result.rollback_evidence_hash},
            "rollback_postchecked": {"rollback_evidence_hash": validation_result.rollback_evidence_hash},
            "rolled_back": {"rollback_evidence_hash": validation_result.rollback_evidence_hash},
        }
        for next_state in path:
            current = self.ledger.replay(operation_id)
            receipt = self.ledger.transition(
                operation_id,
                next_state,
                expected_cas_version=current.cas_version,
                lease_owner_id=self.owner_id,
                evidence_receipt=evidence_by_state[next_state],
            )
            transitions.append(receipt.state)
        final = self.ledger.replay(operation_id)
        counters = {key: int(final.authority_counter_snapshot.get(key, 0)) for key in P118_AUTHORITY_COUNTER_KEYS}
        if any(counters.values()):
            raise P118WorkerError("authority_counter_drift")
        return P118WorkerResult(operation_id=operation_id, final_state=final.state, transitions=transitions, retry_count=0, authority_counter_snapshot=counters)

    def retry_receipt(self, operation_id: str, *, reason: str, attempt: int) -> dict[str, Any]:
        if attempt > self.max_retries:
            raise P118WorkerError("retry_limit_exceeded")
        state = self.ledger.replay(operation_id)
        if state.lease_owner_id != self.owner_id:
            raise P118WorkerError("worker_without_owner_receipt")
        return {"operation_id": operation_id, "owner_id": self.owner_id, "reason": reason, "attempt": attempt, "max_retries": self.max_retries}
