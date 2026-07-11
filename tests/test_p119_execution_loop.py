from __future__ import annotations

from app.services.p110_evaluation import stable_hash
from app.services.p118_approval import P118_APPROVAL_DECISION_SCHEMA_VERSION, empty_p118_policy_counters, p118_operation_context_hash
from app.services.p118_operation_contract import build_operation_envelope, exact_zero_authority_counters
from app.services.p118_validation_cycle import FixtureActionAdapter
from app.services.p119_execution_loop import execute_p119_local_loop


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def _receipt(payload: dict[str, object], *, field: str = "receipt_hash") -> dict[str, object]:
    result = dict(payload)
    result[field] = stable_hash(result)
    return result


def _lease() -> dict[str, object]:
    return _receipt({"operation_id": "p119-op-001", "owner_id": "worker-a", "expires_at": 200, "cas_version": 0})


def _wal() -> dict[str, object]:
    return _receipt({"operation_id": "p119-op-001", "receipt_type": "operation_registered", "cas_version": 0, "wal_position": 0})


def _approval(*, approved: bool = True) -> dict[str, object]:
    operation = _base_operation({"policy_hash": _hash("2"), "verification_hash": _hash("3")}).to_dict()
    policy_counters = empty_p118_policy_counters()
    policy_counters["approvals" if approved else "rejections"] = 1
    policy_counters["fail_closed_decisions"] = int(not approved)
    counters = exact_zero_authority_counters()
    context = {
        "operation_context_hash": p118_operation_context_hash(operation),
        "verification_hash": _hash("3"),
        "verification_expires_at": 200,
        "policy_hash": _hash("2"),
        "lease_expires_at": 200,
        "lease_receipt_hash": _lease()["receipt_hash"],
        "wal_receipt_hash": _wal()["receipt_hash"],
        "wal_position": 0,
        "cas_version": 0,
        "decided_at": 100,
        "counters": counters,
        "policy_counters": policy_counters,
    }
    return _receipt(
        {
            "schema_version": P118_APPROVAL_DECISION_SCHEMA_VERSION,
            "approved": approved,
            "reason": "approved" if approved else "rejected",
            "policy_hash": _hash("2"),
            "operation_id": "p119-op-001",
            "verification_hash": _hash("3"),
            "verification_expires_at": 200,
            "lease_expires_at": 200,
            "lease_receipt_hash": _lease()["receipt_hash"],
            "wal_receipt_hash": _wal()["receipt_hash"],
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


def _base_operation(approval_receipt):  # type: ignore[no-untyped-def]
    return build_operation_envelope(
        {
            "operation_id": "p119-op-001",
            "schema_version": "p118.operation_envelope.v1",
            "p117_decision_episode_id": "episode-001",
            "p117_selected_action_pack_id": "pack-001",
            "p115_action_pack_digest": _hash("1"),
            "fixture_target_id": "mock:fixture:checkout",
            "action_level": "L2",
            "precondition_refs": ["ready"],
            "validation_plan_ref": "validation:mock",
            "rollback_plan_ref": "rollback:mock",
            "approval_receipt": approval_receipt,
            "lease_receipt": _lease(),
            "wal_position": 0,
            "cas_version": 0,
            "idempotency_key": "idem:p119-op-001",
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }
    )


def _operation():  # type: ignore[no-untyped-def]
    return _base_operation(_approval())


def _run(tmp_path, adapter, approved=True):  # type: ignore[no-untyped-def]
    return execute_p119_local_loop(
        operation=_operation(),
        adapter=adapter,
        approval_receipt=_approval(approved=approved),
        verification_hash=_hash("3"),
        lease_receipt=_lease(),
        wal_receipt=_wal(),
        cas_version=0,
        wal_path=tmp_path / "wal.jsonl",
        now=100,
    )


def test_success_is_measured_but_not_recovered_until_attribution_and_recurrence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = _run(tmp_path, FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}))
    assert result.execution_status == "succeeded"
    assert result.recovery_eligible is False
    assert result.recovery_blockers == ("causal_attribution_pending", "recurrence_window_pending")
    assert result.duplicate_action_count == 0


def test_failed_postcheck_rolls_back_and_never_gets_action_success_credit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = _run(tmp_path, FixtureActionAdapter(before={"healthy": False}, after={"healthy": False}, rollback_after={"healthy": False}))
    assert result.execution_status == "rolled_back"
    assert result.recovery_blockers == ("rollback_is_not_action_success",)


def test_missing_approval_fails_closed_without_action(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = _run(tmp_path, FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}), approved=False)
    assert result.execution_status == "aborted_fail_closed"
    assert result.duplicate_action_count == 0


def test_forged_hash_prefix_receipt_fails_closed_without_action(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result = execute_p119_local_loop(
        operation=_operation(),
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt={**_approval(), "decision_hash": _hash("2")},
        verification_hash=_hash("3"),
        lease_receipt=_lease(),
        wal_receipt=_wal(),
        cas_version=0,
        wal_path=tmp_path / "wal.jsonl",
        now=100,
    )
    assert result.execution_status == "aborted_fail_closed"
    assert result.duplicate_action_count == 0
