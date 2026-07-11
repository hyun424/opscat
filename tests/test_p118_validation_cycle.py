from __future__ import annotations

from app.services.p110_evaluation import stable_hash
from app.services.p118_approval import P118_APPROVAL_DECISION_SCHEMA_VERSION, empty_p118_policy_counters, p118_operation_context_hash
from app.services.p118_operation_contract import P118OperationEnvelope, build_operation_envelope, exact_zero_authority_counters
from app.services.p118_validation_cycle import FixtureActionAdapter, run_p118_validation_cycle


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64


def _receipt(payload: dict[str, object], *, field: str = "receipt_hash") -> dict[str, object]:
    result = dict(payload)
    result[field] = stable_hash(result)
    return result


def _approval() -> dict[str, object]:
    operation = _operation().to_dict()
    lease = dict(operation["lease_receipt"])
    wal = _receipt({"operation_id": "op-validation-006", "cas_version": 0, "wal_position": 0})
    policy_counters = empty_p118_policy_counters()
    policy_counters["approvals"] = 1
    counters = exact_zero_authority_counters()
    context = {
        "operation_context_hash": p118_operation_context_hash(operation),
        "verification_hash": _hash("5"),
        "verification_expires_at": 200,
        "policy_hash": _hash("2"),
        "lease_expires_at": 200,
        "lease_receipt_hash": lease["receipt_hash"],
        "wal_receipt_hash": wal["receipt_hash"],
        "wal_position": 0,
        "cas_version": 0,
        "decided_at": 100,
        "counters": counters,
        "policy_counters": policy_counters,
    }
    return _receipt(
        {
            "schema_version": P118_APPROVAL_DECISION_SCHEMA_VERSION,
            "approved": True,
            "reason": "approved",
            "policy_hash": _hash("2"),
            "operation_id": "op-validation-006",
            "verification_hash": _hash("5"),
            "verification_expires_at": 200,
            "lease_expires_at": 200,
            "lease_receipt_hash": lease["receipt_hash"],
            "wal_receipt_hash": wal["receipt_hash"],
            "wal_position": 0,
            "cas_version": 0,
            "decided_at": 100,
            "operation_context_hash": context["operation_context_hash"],
            "approval_context_hash": stable_hash(context),
            "counters": counters,
            "policy_counters": policy_counters,
            "authority_counter_snapshot": counters,
            "nonlocal_authority_zero": True,
        },
        field="decision_hash",
    )


def _operation() -> P118OperationEnvelope:
    lease = _receipt({"operation_id": "op-validation-006", "owner_id": "worker-a", "expires_at": 200, "cas_version": 0})
    return build_operation_envelope(
        {
            "operation_id": "op-validation-006",
            "schema_version": "p118.operation_envelope.v1",
            "p117_decision_episode_id": "episode-validation-006",
            "p117_selected_action_pack_id": "pack-local-006",
            "p115_action_pack_digest": _hash("1"),
            "fixture_target_id": "mock:fixture:checkout-api",
            "action_level": "L2",
            "precondition_refs": ["precondition:ready"],
            "validation_plan_ref": "validation:mock",
            "rollback_plan_ref": "rollback:mock",
            "approval_receipt": {"receipt_id": "approval", "policy_hash": _hash("2"), "verification_hash": _hash("5")},
            "lease_receipt": lease,
            "wal_position": 0,
            "cas_version": 0,
            "idempotency_key": "idem:validation-006",
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }
    )


def test_validation_cycle_requires_measured_pre_post_evidence_before_success() -> None:
    result = run_p118_validation_cycle(
        operation=_operation(),
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt=_approval(),
        lease_owner_id="worker-a",
        wal_receipt=_receipt({"operation_id": "op-validation-006", "cas_version": 0, "wal_position": 0}),
        cas_version=0,
        now=100,
    )

    assert result.final_status == "succeeded"
    assert result.optimistic_success_count == 0
    assert result.missing_postcheck_success_count == 0
    assert result.rollback_without_evidence_count == 0
    assert result.precheck_evidence_hash is not None
    assert result.precheck_evidence_hash.startswith("sha256:")
    assert result.postcheck_evidence_hash is not None
    assert result.postcheck_evidence_hash.startswith("sha256:")
    assert result.rollback_evidence_hash is None
    assert result.authority_counter_snapshot["production_mutation"] == 0


def test_validation_cycle_rolls_back_with_evidence_on_postcheck_failure() -> None:
    result = run_p118_validation_cycle(
        operation=_operation(),
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": False}, rollback_after={"healthy": False}),
        approval_receipt=_approval(),
        lease_owner_id="worker-a",
        wal_receipt=_receipt({"operation_id": "op-validation-006", "cas_version": 0, "wal_position": 0}),
        cas_version=0,
        now=100,
    )

    assert result.final_status == "rolled_back"
    assert result.rollback_attempt_count == 1
    assert result.rollback_evidence_hash is not None
    assert result.rollback_without_evidence_count == 0


def test_validation_cycle_surfaces_rollback_failure_and_rejects_unsafe_probe() -> None:
    rollback_failed = run_p118_validation_cycle(
        operation=_operation(),
        adapter=FixtureActionAdapter(before={"healthy": True}, after={"healthy": False}, rollback_after={"healthy": True}),
        approval_receipt=_approval(),
        lease_owner_id="worker-a",
        wal_receipt=_receipt({"operation_id": "op-validation-006", "cas_version": 0, "wal_position": 0}),
        cas_version=0,
        now=100,
    )
    unsafe = run_p118_validation_cycle(
        operation=_operation(),
        adapter=FixtureActionAdapter(before={"target": "production"}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt=_approval(),
        lease_owner_id="worker-a",
        wal_receipt=_receipt({"operation_id": "op-validation-006", "cas_version": 0, "wal_position": 0}),
        cas_version=0,
        now=100,
    )

    assert rollback_failed.final_status == "rollback_failed"
    assert rollback_failed.rollback_failure_visible is True
    assert unsafe.final_status == "aborted_fail_closed"
    assert unsafe.authority_counter_snapshot["production_mutation"] == 0


def test_validation_cycle_rejects_forged_hash_prefix_receipts() -> None:
    forged_approval = {**_approval(), "decision_hash": _hash("3")}
    forged_wal = {**_receipt({"operation_id": "op-validation-006", "cas_version": 0, "wal_position": 0}), "receipt_hash": _hash("4")}

    approval_result = run_p118_validation_cycle(
        operation=_operation(),
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt=forged_approval,
        lease_owner_id="worker-a",
        wal_receipt=_receipt({"operation_id": "op-validation-006", "cas_version": 0, "wal_position": 0}),
        cas_version=0,
        now=100,
    )
    wal_result = run_p118_validation_cycle(
        operation=_operation(),
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt=_approval(),
        lease_owner_id="worker-a",
        wal_receipt=forged_wal,
        cas_version=0,
        now=100,
    )

    assert approval_result.final_status == "aborted_fail_closed"
    assert wal_result.final_status == "aborted_fail_closed"
