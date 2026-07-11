"""Measured, fail-closed validation and rollback cycle for P118 fixtures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_approval import validate_p118_approval_decision_receipt, validate_p118_receipt_self_hash
from app.services.p118_operation_contract import (
    P118ContractError,
    P118OperationEnvelope,
    exact_zero_authority_counters,
    reject_authority_boundary,
)


@dataclass(frozen=True)
class FixtureActionAdapter:
    """A deterministic adapter that exposes observations without side effects."""

    before: Mapping[str, Any]
    after: Mapping[str, Any]
    rollback_after: Mapping[str, Any]
    validation_plan_ref: str = "validation:mock"
    rollback_plan_ref: str = "rollback:mock"


@dataclass(frozen=True)
class P118ValidationCycleResult:
    final_status: str
    optimistic_success_count: int
    missing_postcheck_success_count: int
    rollback_without_evidence_count: int
    precheck_evidence_hash: str | None
    postcheck_evidence_hash: str | None
    rollback_evidence_hash: str | None
    rollback_attempt_count: int
    rollback_failure_visible: bool
    authority_counter_snapshot: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_status": self.final_status,
            "optimistic_success_count": self.optimistic_success_count,
            "missing_postcheck_success_count": self.missing_postcheck_success_count,
            "rollback_without_evidence_count": self.rollback_without_evidence_count,
            "precheck_evidence_hash": self.precheck_evidence_hash,
            "postcheck_evidence_hash": self.postcheck_evidence_hash,
            "rollback_evidence_hash": self.rollback_evidence_hash,
            "rollback_attempt_count": self.rollback_attempt_count,
            "rollback_failure_visible": self.rollback_failure_visible,
            "authority_counter_snapshot": dict(self.authority_counter_snapshot),
        }


def run_p118_validation_cycle(
    *,
    operation: P118OperationEnvelope,
    adapter: FixtureActionAdapter,
    approval_receipt: Mapping[str, Any],
    lease_owner_id: str,
    wal_receipt: Mapping[str, Any],
    cas_version: int,
    now: int,
) -> P118ValidationCycleResult:
    counters = exact_zero_authority_counters()
    try:
        payload = operation.to_dict()
        reject_authority_boundary(adapter.before)
        reject_authority_boundary(adapter.after)
        reject_authority_boundary(adapter.rollback_after)
        if approval_receipt.get("approved") is not True:
            raise P118ContractError("operation_not_approved")
        if not validate_p118_approval_decision_receipt(
            approval_receipt,
            operation=payload,
            verification_hash=str(_mapping(payload.get("approval_receipt")).get("verification_hash", "")),
            lease_receipt=_mapping(payload.get("lease_receipt")),
            wal_receipt=wal_receipt,
            cas_version=cas_version,
            now=now,
        ):
            raise P118ContractError("invalid_approval_receipt")
        if approval_receipt.get("operation_id") != payload.get("operation_id"):
            raise P118ContractError("approval_operation_mismatch")
        if approval_receipt.get("verification_hash") != payload.get("approval_receipt", {}).get("verification_hash"):
            raise P118ContractError("approval_verification_mismatch")
        if approval_receipt.get("policy_hash") != payload.get("approval_receipt", {}).get("policy_hash"):
            raise P118ContractError("approval_policy_mismatch")
        owner = payload.get("lease_receipt", {}).get("owner_id")
        if owner != lease_owner_id:
            raise P118ContractError("lease_owner_mismatch")
        if payload.get("lease_receipt", {}).get("operation_id") != payload.get("operation_id"):
            raise P118ContractError("lease_operation_mismatch")
        if payload.get("lease_receipt", {}).get("cas_version") != cas_version:
            raise P118ContractError("lease_cas_mismatch")
        if not validate_p118_receipt_self_hash(payload.get("lease_receipt", {})):
            raise P118ContractError("invalid_lease_receipt")
        if not validate_p118_receipt_self_hash(wal_receipt):
            raise P118ContractError("invalid_wal_receipt")
        if wal_receipt.get("operation_id") != payload.get("operation_id"):
            raise P118ContractError("wal_operation_mismatch")
        if wal_receipt.get("cas_version") != cas_version:
            raise P118ContractError("wal_cas_mismatch")
        if wal_receipt.get("wal_position") != payload.get("wal_position"):
            raise P118ContractError("wal_position_mismatch")
        if cas_version != int(payload["cas_version"]):
            raise P118ContractError("cas_conflict")
        if adapter.validation_plan_ref != payload.get("validation_plan_ref"):
            raise P118ContractError("validation_plan_mismatch")
        if adapter.rollback_plan_ref != payload.get("rollback_plan_ref"):
            raise P118ContractError("rollback_plan_mismatch")
    except (P118ContractError, AttributeError, TypeError):
        return _result("aborted_fail_closed", counters=counters)

    before = dict(adapter.before)
    after = dict(adapter.after)
    pre_hash = stable_hash({"operation_id": operation.operation_id, "phase": "precheck", "observation": before})
    post_hash = stable_hash({"operation_id": operation.operation_id, "phase": "postcheck", "observation": after})

    # The qualified fixture contract models remediation as unhealthy -> healthy.
    if before.get("healthy") is False and after.get("healthy") is True:
        return _result("succeeded", counters=counters, pre_hash=pre_hash, post_hash=post_hash)

    rollback = dict(adapter.rollback_after)
    rollback_hash = stable_hash({"operation_id": operation.operation_id, "phase": "rollback_postcheck", "observation": rollback})
    rollback_restored_safe_baseline = before.get("healthy") is False and rollback.get("healthy") is False
    status = "rolled_back" if rollback_restored_safe_baseline else "rollback_failed"
    return _result(
        status,
        counters=counters,
        pre_hash=pre_hash,
        post_hash=post_hash,
        rollback_hash=rollback_hash,
        rollback_attempts=1,
        rollback_failure=status == "rollback_failed",
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _result(
    status: str,
    *,
    counters: Mapping[str, int],
    pre_hash: str | None = None,
    post_hash: str | None = None,
    rollback_hash: str | None = None,
    rollback_attempts: int = 0,
    rollback_failure: bool = False,
) -> P118ValidationCycleResult:
    return P118ValidationCycleResult(
        final_status=status,
        optimistic_success_count=0,
        missing_postcheck_success_count=0,
        rollback_without_evidence_count=0,
        precheck_evidence_hash=pre_hash,
        postcheck_evidence_hash=post_hash,
        rollback_evidence_hash=rollback_hash,
        rollback_attempt_count=rollback_attempts,
        rollback_failure_visible=rollback_failure,
        authority_counter_snapshot=dict(counters),
    )


__all__ = ["FixtureActionAdapter", "P118ValidationCycleResult", "run_p118_validation_cycle"]
