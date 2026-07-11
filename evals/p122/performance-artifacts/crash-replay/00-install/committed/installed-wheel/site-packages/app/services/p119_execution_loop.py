"""P119 local closed-loop execution handoff built on P118 receipts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_approval import validate_p118_approval_decision_receipt, validate_p118_receipt_self_hash
from app.services.p118_ledger import P118LedgerStore
from app.services.p118_operation_contract import P118OperationEnvelope, exact_zero_authority_counters
from app.services.p118_validation_cycle import FixtureActionAdapter, run_p118_validation_cycle
from app.services.p118_worker import P118Worker, P118WorkerError


@dataclass(frozen=True)
class P119ExecutionResult:
    operation_id: str
    execution_status: str
    recovery_eligible: bool
    recovery_blockers: tuple[str, ...]
    duplicate_action_count: int
    validation_receipt_hash: str
    authority_counter_snapshot: Mapping[str, int]


def execute_p119_local_loop(
    *,
    operation: P118OperationEnvelope,
    adapter: FixtureActionAdapter,
    approval_receipt: Mapping[str, Any],
    verification_hash: str,
    lease_receipt: Mapping[str, Any],
    wal_receipt: Mapping[str, Any],
    cas_version: int,
    wal_path: Path,
    now: int,
) -> P119ExecutionResult:
    owner = str(lease_receipt.get("owner_id", ""))
    operation_payload = operation.to_dict()
    if (
        approval_receipt.get("approved") is not True
        or not validate_p118_approval_decision_receipt(
            approval_receipt,
            operation=operation.to_dict(),
            verification_hash=verification_hash,
            lease_receipt=lease_receipt,
            wal_receipt=wal_receipt,
            cas_version=cas_version,
            now=now,
        )
        or not verification_hash.startswith("sha256:")
        or approval_receipt.get("operation_id") != operation.operation_id
        or approval_receipt.get("verification_hash") != verification_hash
        or lease_receipt.get("operation_id") != operation.operation_id
        or wal_receipt.get("operation_id") != operation.operation_id
        or lease_receipt.get("cas_version") != cas_version
        or wal_receipt.get("cas_version") != cas_version
        or not validate_p118_receipt_self_hash(lease_receipt)
        or not validate_p118_receipt_self_hash(wal_receipt)
        or not owner
        or dict(approval_receipt) != operation_payload.get("approval_receipt")
        or dict(lease_receipt) != operation_payload.get("lease_receipt")
    ):
        return _blocked(operation.operation_id, "missing_or_unbound_execution_receipt")
    validation = run_p118_validation_cycle(
        operation=operation,
        adapter=adapter,
        approval_receipt=approval_receipt,
        lease_owner_id=owner,
        wal_receipt=wal_receipt,
        cas_version=cas_version,
        now=now,
    )
    if validation.final_status not in {"succeeded", "rolled_back"}:
        return _blocked(operation.operation_id, validation.final_status)
    ledger = P118LedgerStore(wal_path)
    ledger.register_operation(operation)
    ledger.record_lease(
        operation.operation_id,
        owner_id=owner,
        expires_at=int(lease_receipt.get("expires_at", now + 60)),
        receipt_type="lease_acquired",
    )
    worker = P118Worker(ledger, owner_id=owner, lease_ttl_seconds=60, max_retries=0)
    try:
        result = worker.run_once(
            operation.operation_id,
            now=now,
            validation_result=validation,
            operation=operation,
            verification_hash=verification_hash,
            approval_receipt=dict(approval_receipt),
            lease_receipt=dict(lease_receipt),
            wal_receipt=dict(wal_receipt),
            cas_version=cas_version,
        )
    except P118WorkerError as exc:
        return _blocked(operation.operation_id, f"worker_fail_closed:{exc}")
    receipt_hash = stable_hash(validation.to_dict())
    blockers = ("causal_attribution_pending", "recurrence_window_pending") if result.final_state == "succeeded" else ("rollback_is_not_action_success",)
    return P119ExecutionResult(
        operation_id=operation.operation_id,
        execution_status=result.final_state,
        recovery_eligible=False,
        recovery_blockers=blockers,
        duplicate_action_count=0,
        validation_receipt_hash=receipt_hash,
        authority_counter_snapshot=exact_zero_authority_counters(),
    )


def _blocked(operation_id: str, reason: str) -> P119ExecutionResult:
    return P119ExecutionResult(
        operation_id=operation_id,
        execution_status="aborted_fail_closed",
        recovery_eligible=False,
        recovery_blockers=(reason,),
        duplicate_action_count=0,
        validation_receipt_hash=stable_hash({"operation_id": operation_id, "reason": reason}),
        authority_counter_snapshot=exact_zero_authority_counters(),
    )


__all__ = ["P119ExecutionResult", "execute_p119_local_loop"]
