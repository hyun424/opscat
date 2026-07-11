"""P119 P117/P115/P118-bound selection and deterministic approval handoff."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p117_selector import P117_DECISION_SCHEMA_VERSION
from app.services.p118_action_pack_verifier import P118ActionPackVerificationError, verify_signed_action_pack
from app.services.p118_approval import decide_p118_approval
from app.services.p118_operation_contract import (
    build_operation_envelope,
)
from app.services.p118_operation_contract import (
    exact_zero_authority_counters as p118_zero_counters,
)
from app.services.p119_contract import (
    P119ContractError,
    exact_zero_authority_counters,
    reject_authority_boundary,
    validate_exact_zero_authority_counters,
)

P119_NON_ACTION_LABELS = frozenset({"no_action", "investigate_more", "escalate", "abstain"})
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class P119SelectionError(ValueError):
    """Raised when action selection or approval fails closed."""


@dataclass(frozen=True)
class P119SelectionOutcome:
    outcome: str
    selected_label: str
    selected_action_pack_id: str | None
    approval_receipt: Mapping[str, Any] | None
    operation_envelope: Mapping[str, Any] | None
    escalation_payload: Mapping[str, Any] | None
    reason: str
    authority_counter_snapshot: Mapping[str, int]
    outcome_hash: str


def approve_p119_selection(
    *,
    p117_decision: Mapping[str, Any],
    frozen_action_manifest: Mapping[str, Mapping[str, Any]],
    policy_hash: str,
    target_fixture_id: str,
    budget_snapshot: Mapping[str, Any],
    timeline_refs: Sequence[str],
    now: int,
    signer_secrets: Mapping[str, str],
) -> P119SelectionOutcome:
    reject_authority_boundary(p117_decision)
    validate_exact_zero_authority_counters(exact_zero_authority_counters())
    if p117_decision.get("schema_version") != P117_DECISION_SCHEMA_VERSION:
        raise P119SelectionError("invalid_p117_decision_schema")
    label = _required_text(p117_decision, "selected_label")
    if label in P119_NON_ACTION_LABELS:
        return _non_action_outcome(label, p117_decision, budget_snapshot, timeline_refs, reason=label)
    if label != "act":
        raise P119SelectionError(f"unknown_p117_label:{label}")
    selected_id = _required_text(p117_decision, "selected_action_pack_id")
    pack = frozen_action_manifest.get(selected_id)
    if pack is None:
        raise P119SelectionError("invented_action_id")
    try:
        verification = _verify_pack(
            pack,
            decision=p117_decision,
            selected_id=selected_id,
            target_fixture_id=target_fixture_id,
            signer_secrets=signer_secrets,
            now=now,
        )
    except P119ContractError as exc:
        raise P119SelectionError(str(exc)) from exc
    if policy_hash != str(pack.get("policy_hash")):
        return _escalation(label, selected_id, "policy_hash_mismatch", p117_decision, budget_snapshot, timeline_refs)
    if pack.get("permanently_human_authorized") is True:
        return _escalation(label, selected_id, "human_authorization_required", p117_decision, budget_snapshot, timeline_refs)
    if pack.get("contraindications_resolved") is not True:
        return _escalation(label, selected_id, "contraindication_present", p117_decision, budget_snapshot, timeline_refs)
    operation_id = f"p119-op:{selected_id}"
    lease = _receipt(
        {
            "operation_id": operation_id,
            "owner_id": "p119-local-worker",
            "expires_at": verification.expires_at,
            "cas_version": 0,
        }
    )
    wal = _receipt({"operation_id": operation_id, "receipt_type": "operation_registered", "cas_version": 0, "wal_position": 0})
    operation_data = {
        "operation_id": operation_id,
        "schema_version": "p118.operation_envelope.v1",
        "p117_decision_episode_id": _required_text(p117_decision, "decision_episode_id"),
        "p117_selected_action_pack_id": selected_id,
        "p115_action_pack_digest": verification.pack_digest,
        "fixture_target_id": target_fixture_id,
        "action_level": str(pack["allowed_level"]),
        "precondition_refs": [str(item) for item in _required_sequence(pack.get("prerequisite_receipts"), "missing_prerequisite_receipts")],
        "validation_plan_ref": str(_mapping(_mapping(pack.get("p115_pack")).get("validation_query")).get("plan_id", "")),
        "rollback_plan_ref": str(_mapping(_mapping(pack.get("p115_pack")).get("rollback_plan")).get("plan_id", "")),
        "approval_receipt": {"policy_hash": policy_hash, "verification_hash": verification.verification_hash},
        "lease_receipt": lease,
        "wal_position": 0,
        "cas_version": 0,
        "idempotency_key": f"idem:p119:{selected_id}:{verification.verification_hash}",
        "authority_counter_snapshot": p118_zero_counters(),
    }
    approval_operation = build_operation_envelope(operation_data)
    approval = decide_p118_approval(
        operation=approval_operation,
        verification=verification,
        policy_hash=policy_hash,
        now=now,
        lease_receipt=lease,
        wal_receipt=wal,
        cas_version=0,
    ).to_dict()
    operation_data["approval_receipt"] = approval
    operation = build_operation_envelope(operation_data).to_dict()
    return _outcome("approved", label, selected_id, approval, operation, None, "approved")


def _verify_pack(
    pack: Mapping[str, Any],
    *,
    decision: Mapping[str, Any],
    selected_id: str,
    target_fixture_id: str,
    signer_secrets: Mapping[str, str],
    now: int,
) -> Any:
    reject_authority_boundary(pack)
    p115_pack = _mapping(pack.get("p115_pack"))
    p117_ref = _mapping(pack.get("p117_action_pack_ref"))
    if not p115_pack or not p117_ref:
        raise P119SelectionError("missing_real_p115_p117_binding")
    if pack.get("revoked") is True:
        raise P119SelectionError("revoked_action_pack")
    expires_at = pack.get("verification_expires_at")
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise P119SelectionError("stale_action_pack")
    level = str(pack.get("allowed_level", ""))
    if not level.startswith("L") or not level[1:].isdigit() or int(level[1:]) > 3:
        raise P119SelectionError("action_level_above_l3")
    if pack.get("fixture_target_id") != target_fixture_id or not target_fixture_id.startswith(("local:fixture:", "mock:fixture:", "sandbox:fixture:")):
        raise P119SelectionError("fixture_target_mismatch")
    if not _mapping(p115_pack.get("validation_query")).get("plan_id"):
        raise P119SelectionError("missing_validation_plan")
    if not _mapping(p115_pack.get("rollback_plan")).get("plan_id"):
        raise P119SelectionError("missing_rollback_plan")
    _required_sequence(pack.get("prerequisite_receipts"), "missing_prerequisite_receipts")
    validate_exact_zero_authority_counters(pack.get("authority_counter_snapshot"))
    try:
        return verify_signed_action_pack(
            p115_pack,
            p117_decision_output=decision,
            p117_action_pack_ref=p117_ref,
            signer_secrets=signer_secrets,
            revoked_digests={str(p117_ref.get("pack_hash"))} if pack.get("revoked") is True else set(),
            now=now,
            verification_expires_at=expires_at,
        )
    except P118ActionPackVerificationError as exc:
        raise P119SelectionError(str(exc)) from exc


def _non_action_outcome(label: str, decision: Mapping[str, Any], budget: Mapping[str, Any], timeline_refs: Sequence[str], *, reason: str) -> P119SelectionOutcome:
    escalation = None
    outcome = label
    if label in {"investigate_more", "escalate", "abstain"}:
        escalation = _payload(decision, budget, timeline_refs, reason)
        outcome = "escalated" if label in {"escalate", "abstain"} else "investigate_more"
    return _outcome(outcome, label, None, None, None, escalation, reason)


def _escalation(label: str, selected_id: str, reason: str, decision: Mapping[str, Any], budget: Mapping[str, Any], timeline_refs: Sequence[str]) -> P119SelectionOutcome:
    payload = _payload(decision, budget, timeline_refs, reason)
    payload = {**payload, "selected_action_pack_id": selected_id}
    return _outcome("escalated", label, selected_id, None, None, payload, reason)


def _payload(decision: Mapping[str, Any], budget: Mapping[str, Any], timeline_refs: Sequence[str], reason: str) -> dict[str, Any]:
    payload = {
        "schema_version": "p119.local_escalation_payload.v1",
        "decision_episode_id": _required_text(decision, "decision_episode_id"),
        "selected_label": _required_text(decision, "selected_label"),
        "blocked_reason": reason,
        "missing_evidence": list(decision.get("requested_evidence_classes", [])) if isinstance(decision.get("requested_evidence_classes", []), Sequence) else [],
        "contradictions": list(decision.get("contradiction_set_ids", [])) if isinstance(decision.get("contradiction_set_ids", []), Sequence) else [],
        "budget_snapshot": dict(budget),
        "timeline_refs": sorted(str(item) for item in timeline_refs),
        "recommended_human_decision": "review_local_mock_metadata",
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
    payload["payload_hash"] = stable_hash(payload)
    return payload


def _outcome(
    outcome: str,
    label: str,
    selected_id: str | None,
    approval: Mapping[str, Any] | None,
    operation: Mapping[str, Any] | None,
    escalation: Mapping[str, Any] | None,
    reason: str,
) -> P119SelectionOutcome:
    base: dict[str, Any] = {
        "outcome": outcome,
        "selected_label": label,
        "selected_action_pack_id": selected_id,
        "approval_receipt": dict(approval) if approval is not None else None,
        "operation_envelope": dict(operation) if operation is not None else None,
        "escalation_payload": dict(escalation) if escalation is not None else None,
        "reason": reason,
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
    return P119SelectionOutcome(
        outcome=outcome,
        selected_label=label,
        selected_action_pack_id=selected_id,
        approval_receipt=approval,
        operation_envelope=operation,
        escalation_payload=escalation,
        reason=reason,
        authority_counter_snapshot=exact_zero_authority_counters(),
        outcome_hash=stable_hash(base),
    )


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P119SelectionError(f"missing_{key}")
    return value.strip()


def _required_sequence(value: Any, error: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P119SelectionError(error)
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["receipt_hash"] = stable_hash(result)
    return result
