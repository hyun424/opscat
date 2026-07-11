"""Deterministic fail-closed approval policy for P118 fixture operations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_action_pack_verifier import P118ActionPackVerificationResult
from app.services.p118_operation_contract import P118_AUTHORITY_COUNTER_KEYS, P118OperationEnvelope, validate_exact_zero_authority_counters

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
P118_APPROVAL_DECISION_SCHEMA_VERSION = "p118.approval_decision.v1"
_POLICY_COUNTER_KEYS = (*P118_AUTHORITY_COUNTER_KEYS, "approvals", "rejections", "rollback_attempts", "duplicate_action_attempts", "fail_closed_decisions")


@dataclass(frozen=True)
class P118ApprovalDecision:
    approved: bool
    reason: str
    policy_hash: str
    operation_id: str
    verification_hash: str
    verification_expires_at: int
    lease_expires_at: int
    lease_receipt_hash: str
    wal_receipt_hash: str
    wal_position: int
    cas_version: int
    decided_at: int
    operation_context_hash: str
    approval_context_hash: str
    counters: Mapping[str, int]
    policy_counters: Mapping[str, int]
    authority_counter_snapshot: Mapping[str, int]
    nonlocal_authority_zero: bool
    decision_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": P118_APPROVAL_DECISION_SCHEMA_VERSION,
            "approved": self.approved,
            "reason": self.reason,
            "policy_hash": self.policy_hash,
            "operation_id": self.operation_id,
            "verification_hash": self.verification_hash,
            "verification_expires_at": self.verification_expires_at,
            "lease_expires_at": self.lease_expires_at,
            "lease_receipt_hash": self.lease_receipt_hash,
            "wal_receipt_hash": self.wal_receipt_hash,
            "wal_position": self.wal_position,
            "cas_version": self.cas_version,
            "decided_at": self.decided_at,
            "operation_context_hash": self.operation_context_hash,
            "approval_context_hash": self.approval_context_hash,
            "counters": dict(self.counters),
            "policy_counters": dict(self.policy_counters),
            "authority_counter_snapshot": dict(self.authority_counter_snapshot),
            "nonlocal_authority_zero": self.nonlocal_authority_zero,
            "decision_hash": self.decision_hash,
        }


def empty_p118_policy_counters() -> dict[str, int]:
    return {key: 0 for key in _POLICY_COUNTER_KEYS}


def decide_p118_approval(
    *,
    operation: P118OperationEnvelope,
    verification: P118ActionPackVerificationResult,
    policy_hash: str,
    now: int,
    lease_receipt: Mapping[str, Any],
    wal_receipt: Mapping[str, Any],
    cas_version: int,
    observed_counters: Mapping[str, int] | None = None,
) -> P118ApprovalDecision:
    payload = operation.to_dict()
    policy_counters = empty_p118_policy_counters()
    observed = dict(empty_p118_policy_counters() if observed_counters is None else observed_counters)
    reason = _rejection_reason(
        payload,
        verification,
        policy_hash,
        lease_receipt,
        wal_receipt,
        cas_version,
        observed,
        now,
    )
    approved = reason is None
    policy_counters.update({key: int(observed.get(key, 0)) for key in P118_AUTHORITY_COUNTER_KEYS})
    policy_counters["approvals" if approved else "rejections"] = 1
    policy_counters["fail_closed_decisions"] = int(not approved)
    nonlocal_zero = all(policy_counters[key] == 0 for key in P118_AUTHORITY_COUNTER_KEYS)
    decision_reason = "approved" if approved else str(reason)
    authority_snapshot = {key: policy_counters[key] for key in P118_AUTHORITY_COUNTER_KEYS}
    operation_context_hash = p118_operation_context_hash(payload)
    context: dict[str, Any] = {
        "operation_context_hash": operation_context_hash,
        "verification_hash": verification.verification_hash,
        "verification_expires_at": verification.expires_at,
        "policy_hash": policy_hash,
        "lease_expires_at": lease_receipt.get("expires_at"),
        "lease_receipt_hash": lease_receipt.get("receipt_hash"),
        "wal_receipt_hash": wal_receipt.get("receipt_hash"),
        "wal_position": wal_receipt.get("wal_position"),
        "cas_version": cas_version,
        "decided_at": now,
        "counters": authority_snapshot,
        "policy_counters": policy_counters,
    }
    base: dict[str, Any] = {
        "schema_version": P118_APPROVAL_DECISION_SCHEMA_VERSION,
        "approved": approved,
        "reason": decision_reason,
        "policy_hash": policy_hash,
        "operation_id": operation.operation_id,
        "verification_hash": verification.verification_hash,
        "verification_expires_at": verification.expires_at,
        "lease_expires_at": lease_receipt.get("expires_at"),
        "lease_receipt_hash": lease_receipt.get("receipt_hash"),
        "wal_receipt_hash": wal_receipt.get("receipt_hash"),
        "wal_position": wal_receipt.get("wal_position"),
        "cas_version": cas_version,
        "decided_at": now,
        "operation_context_hash": operation_context_hash,
        "approval_context_hash": stable_hash(context),
        "counters": authority_snapshot,
        "policy_counters": policy_counters,
        "authority_counter_snapshot": authority_snapshot,
        "nonlocal_authority_zero": nonlocal_zero,
    }
    return P118ApprovalDecision(
        approved=approved,
        reason=decision_reason,
        policy_hash=policy_hash,
        operation_id=operation.operation_id,
        verification_hash=verification.verification_hash,
        verification_expires_at=verification.expires_at,
        lease_expires_at=int(lease_receipt.get("expires_at", -1)),
        lease_receipt_hash=str(lease_receipt.get("receipt_hash", "")),
        wal_receipt_hash=str(wal_receipt.get("receipt_hash", "")),
        wal_position=int(wal_receipt.get("wal_position", -1)),
        cas_version=cas_version,
        decided_at=now,
        operation_context_hash=operation_context_hash,
        approval_context_hash=str(base["approval_context_hash"]),
        counters=authority_snapshot,
        policy_counters=policy_counters,
        authority_counter_snapshot=authority_snapshot,
        nonlocal_authority_zero=nonlocal_zero,
        decision_hash=stable_hash(base),
    )


def validate_p118_receipt_self_hash(receipt: Mapping[str, Any], *, field: str = "receipt_hash") -> bool:
    claimed = receipt.get(field)
    return isinstance(claimed, str) and claimed == stable_hash({key: value for key, value in receipt.items() if key != field})


def p118_operation_context_hash(operation: Mapping[str, Any]) -> str:
    return stable_hash({key: value for key, value in operation.items() if key not in {"approval_receipt", "envelope_hash"}})


def validate_p118_approval_decision_receipt(
    receipt: Mapping[str, Any],
    *,
    operation: Mapping[str, Any] | None = None,
    verification_hash: str | None = None,
    lease_receipt: Mapping[str, Any] | None = None,
    wal_receipt: Mapping[str, Any] | None = None,
    cas_version: int | None = None,
    now: int | None = None,
) -> bool:
    if receipt.get("schema_version") != P118_APPROVAL_DECISION_SCHEMA_VERSION or not validate_p118_receipt_self_hash(receipt, field="decision_hash"):
        return False
    required_hashes = ("policy_hash", "verification_hash", "lease_receipt_hash", "wal_receipt_hash", "operation_context_hash", "approval_context_hash")
    if any(not isinstance(receipt.get(field), str) or not _HASH_RE.fullmatch(str(receipt[field])) for field in required_hashes):
        return False
    required_ints = ("verification_expires_at", "lease_expires_at", "wal_position", "cas_version", "decided_at")
    if any(not isinstance(receipt.get(field), int) or isinstance(receipt.get(field), bool) for field in required_ints):
        return False
    try:
        validate_exact_zero_authority_counters(receipt.get("authority_counter_snapshot"))
    except ValueError:
        return False
    counters = receipt.get("counters")
    authority_snapshot = receipt.get("authority_counter_snapshot")
    try:
        validated_counters = validate_exact_zero_authority_counters(counters)
        validated_snapshot = validate_exact_zero_authority_counters(authority_snapshot)
    except ValueError:
        return False
    if validated_counters != validated_snapshot:
        return False
    policy_counters = receipt.get("policy_counters")
    if (
        not isinstance(policy_counters, Mapping)
        or set(policy_counters) != set(_POLICY_COUNTER_KEYS)
        or any(not isinstance(policy_counters.get(key), int) or isinstance(policy_counters.get(key), bool) for key in _POLICY_COUNTER_KEYS)
        or any(policy_counters.get(key) != 0 for key in P118_AUTHORITY_COUNTER_KEYS)
    ):
        return False
    context = {
        "operation_context_hash": receipt["operation_context_hash"],
        "verification_hash": receipt["verification_hash"],
        "verification_expires_at": receipt["verification_expires_at"],
        "policy_hash": receipt["policy_hash"],
        "lease_expires_at": receipt["lease_expires_at"],
        "lease_receipt_hash": receipt["lease_receipt_hash"],
        "wal_receipt_hash": receipt["wal_receipt_hash"],
        "wal_position": receipt["wal_position"],
        "cas_version": receipt["cas_version"],
        "decided_at": receipt["decided_at"],
        "counters": dict(validated_counters),
        "policy_counters": dict(policy_counters),
    }
    if receipt.get("approval_context_hash") != stable_hash(context):
        return False
    if operation is not None and (receipt.get("operation_id") != operation.get("operation_id") or receipt.get("operation_context_hash") != p118_operation_context_hash(operation)):
        return False
    if verification_hash is not None and receipt.get("verification_hash") != verification_hash:
        return False
    if lease_receipt is not None and (
        not validate_p118_receipt_self_hash(lease_receipt)
        or receipt.get("lease_receipt_hash") != lease_receipt.get("receipt_hash")
        or receipt.get("lease_expires_at") != lease_receipt.get("expires_at")
    ):
        return False
    if wal_receipt is not None and (
        not validate_p118_receipt_self_hash(wal_receipt)
        or receipt.get("wal_receipt_hash") != wal_receipt.get("receipt_hash")
        or receipt.get("wal_position") != wal_receipt.get("wal_position")
    ):
        return False
    if cas_version is not None and receipt.get("cas_version") != cas_version:
        return False
    return now is None or (int(receipt["verification_expires_at"]) > now and int(receipt["lease_expires_at"]) > now and int(receipt["decided_at"]) <= now)


def _rejection_reason(
    operation: Mapping[str, Any],
    verification: P118ActionPackVerificationResult,
    policy_hash: str,
    lease: Mapping[str, Any],
    wal: Mapping[str, Any],
    cas_version: int,
    counters: Mapping[str, int],
    now: int,
) -> str | None:
    if not _HASH_RE.fullmatch(policy_hash):
        return "missing_policy_hash"
    unknown = sorted(set(counters) - set(_POLICY_COUNTER_KEYS))
    if unknown:
        return f"unknown_policy_counter:{unknown[0]}"
    missing = sorted(set(_POLICY_COUNTER_KEYS) - set(counters))
    if missing:
        return f"missing_policy_counter:{missing[0]}"
    for key in P118_AUTHORITY_COUNTER_KEYS:
        value = counters.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            return f"missing_authority_counter:{key}"
        if value != 0:
            return f"authority_counter_nonzero:{key}"
    if verification.accepted is not True:
        return "pack_not_verified"
    if verification.verification_hash != stable_hash({key: value for key, value in verification.to_dict().items() if key != "verification_hash"}):
        return "invalid_verification_self_hash"
    if verification.expires_at <= now:
        return "stale_pack_verification"
    if verification.p117_decision_episode_id != operation.get("p117_decision_episode_id"):
        return "p117_decision_episode_mismatch"
    if verification.action_pack_id != operation.get("p117_selected_action_pack_id"):
        return "verified_pack_id_mismatch"
    if verification.pack_digest != operation.get("p115_action_pack_digest"):
        return "verified_pack_digest_mismatch"
    expected_owner = str(_mapping(operation.get("lease_receipt")).get("owner_id", ""))
    if not expected_owner or lease.get("owner_id") != expected_owner:
        return "lease_owner_mismatch"
    if lease.get("operation_id") != operation.get("operation_id"):
        return "lease_operation_mismatch"
    if not isinstance(lease.get("expires_at"), int) or int(lease["expires_at"]) <= now:
        return "stale_lease_receipt"
    if lease.get("cas_version") != cas_version:
        return "lease_cas_mismatch"
    if not validate_p118_receipt_self_hash(lease):
        return "invalid_lease_receipt"
    if not validate_p118_receipt_self_hash(wal):
        return "invalid_wal_receipt"
    if wal.get("operation_id") != operation.get("operation_id"):
        return "wal_operation_mismatch"
    if wal.get("cas_version") != cas_version:
        return "wal_cas_mismatch"
    if int(wal.get("wal_position", -1)) < int(operation.get("wal_position", 0)):
        return "stale_wal_receipt"
    if cas_version != int(operation.get("cas_version", -1)):
        return "stale_cas_version"
    if not operation.get("validation_plan_ref"):
        return "missing_validation_plan"
    if not operation.get("rollback_plan_ref"):
        return "missing_rollback_plan"
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "P118_APPROVAL_DECISION_SCHEMA_VERSION",
    "P118ApprovalDecision",
    "decide_p118_approval",
    "empty_p118_policy_counters",
    "p118_operation_context_hash",
    "validate_p118_approval_decision_receipt",
    "validate_p118_receipt_self_hash",
]
