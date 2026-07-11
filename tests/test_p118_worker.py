from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p118_approval import P118_APPROVAL_DECISION_SCHEMA_VERSION, empty_p118_policy_counters, p118_operation_context_hash
from app.services.p118_ledger import P118LedgerStore
from app.services.p118_operation_contract import build_operation_envelope, exact_zero_authority_counters
from app.services.p118_validation_cycle import FixtureActionAdapter, run_p118_validation_cycle
from app.services.p118_worker import P118Worker, P118WorkerError


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64


def _receipt(payload: dict[str, object], *, field: str = "receipt_hash") -> dict[str, object]:
    result = dict(payload)
    result[field] = stable_hash(result)
    return result


def _lease() -> dict[str, object]:
    return _receipt({"operation_id": "op-worker-001", "owner_id": "worker-a", "expires_at": 200, "cas_version": 0})


def _wal() -> dict[str, object]:
    return _receipt({"operation_id": "op-worker-001", "cas_version": 0, "wal_position": 0})


def _approval(*, approved: bool = True) -> dict[str, object]:
    operation = build_operation_envelope(_operation()).to_dict()
    lease = dict(operation["lease_receipt"])
    wal = _wal()
    policy_counters = empty_p118_policy_counters()
    policy_counters["approvals" if approved else "rejections"] = 1
    policy_counters["fail_closed_decisions"] = int(not approved)
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
            "approved": approved,
            "reason": "approved" if approved else "rejected",
            "policy_hash": _hash("2"),
            "operation_id": "op-worker-001",
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


def _operation() -> dict[str, object]:
    return {
        "operation_id": "op-worker-001",
        "schema_version": "p118.operation_envelope.v1",
        "p117_decision_episode_id": "episode-worker-001",
        "p117_selected_action_pack_id": "pack-local-001",
        "p115_action_pack_digest": _hash("1"),
        "fixture_target_id": "sandbox:fixture:checkout-api",
        "action_level": "L1",
        "precondition_refs": ["precondition:ready"],
        "validation_plan_ref": "validation:mock",
        "rollback_plan_ref": "rollback:mock",
        "approval_receipt": {"receipt_id": "approval", "policy_hash": _hash("2"), "verification_hash": _hash("5")},
        "lease_receipt": _lease(),
        "wal_position": 0,
        "cas_version": 0,
        "idempotency_key": "idem:worker-001",
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }


def test_worker_requires_single_owner_lease_for_bounded_state_progression(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)
    worker = P118Worker(ledger, owner_id="worker-a", lease_ttl_seconds=10, max_retries=2)

    lease = worker.acquire_lease(operation.operation_id, now=100)
    validation = run_p118_validation_cycle(
        operation=operation,
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt=_approval(),
        lease_owner_id="worker-a",
        wal_receipt=_wal(),
        cas_version=0,
        now=100,
    )
    result = worker.run_once(
        operation.operation_id,
        now=101,
        validation_result=validation,
        operation=operation,
        verification_hash=_hash("5"),
        approval_receipt=_approval(),
        lease_receipt=_lease(),
        wal_receipt=_wal(),
        cas_version=0,
    )

    assert lease.owner_id == "worker-a"
    assert result.final_state == "succeeded"
    assert result.transitions == ["verified", "approved", "prechecked", "action_attempted", "postchecked", "succeeded"]
    assert result.retry_count == 0
    assert result.authority_counter_snapshot["production_mutation"] == 0


def test_worker_rejects_takeover_before_expiry_and_stale_renewal(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)
    P118Worker(ledger, owner_id="worker-a", lease_ttl_seconds=10, max_retries=2).acquire_lease(operation.operation_id, now=100)
    worker_b = P118Worker(ledger, owner_id="worker-b", lease_ttl_seconds=10, max_retries=2)

    with pytest.raises(P118WorkerError, match="lease_takeover_before_expiry"):
        worker_b.acquire_lease(operation.operation_id, now=105)
    with pytest.raises(P118WorkerError, match="stale_lease_renewal"):
        worker_b.renew_lease(operation.operation_id, now=106)


def test_worker_can_take_over_after_expiry_and_rejects_unowned_execution(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)
    P118Worker(ledger, owner_id="worker-a", lease_ttl_seconds=10, max_retries=2).acquire_lease(operation.operation_id, now=100)
    worker_b = P118Worker(ledger, owner_id="worker-b", lease_ttl_seconds=10, max_retries=2)

    lease = worker_b.acquire_lease(operation.operation_id, now=111)

    assert lease.owner_id == "worker-b"
    assert lease.receipt_type == "lease_takeover"
    with pytest.raises(P118WorkerError, match="worker_without_owner_receipt"):
        P118Worker(ledger, owner_id="worker-c", lease_ttl_seconds=10, max_retries=2).run_once(
            operation.operation_id,
            now=112,
            validation_result=run_p118_validation_cycle(
                operation=operation,
                adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
                approval_receipt=_approval(),
                lease_owner_id="worker-a",
                wal_receipt=_wal(),
                cas_version=0,
                now=100,
            ),
            operation=operation,
            verification_hash=_hash("5"),
            approval_receipt=_approval(),
            lease_receipt=_lease(),
            wal_receipt=_wal(),
            cas_version=0,
        )


def test_worker_rejects_optimistic_success_without_measured_validation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)
    worker = P118Worker(ledger, owner_id="worker-a", lease_ttl_seconds=10, max_retries=2)
    worker.acquire_lease(operation.operation_id, now=100)
    failed = run_p118_validation_cycle(
        operation=operation,
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt=_approval(approved=False),
        lease_owner_id="worker-a",
        wal_receipt=_wal(),
        cas_version=0,
        now=100,
    )
    with pytest.raises(P118WorkerError, match="qualified_terminal_validation_required"):
        worker.run_once(
            operation.operation_id,
            now=101,
            validation_result=failed,
            operation=operation,
            verification_hash=_hash("5"),
            approval_receipt=_approval(),
            lease_receipt=_lease(),
            wal_receipt=_wal(),
            cas_version=0,
        )


def test_worker_rejects_forged_hash_prefix_approval_receipt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)
    worker = P118Worker(ledger, owner_id="worker-a", lease_ttl_seconds=10, max_retries=2)
    worker.acquire_lease(operation.operation_id, now=100)
    validation = run_p118_validation_cycle(
        operation=operation,
        adapter=FixtureActionAdapter(before={"healthy": False}, after={"healthy": True}, rollback_after={"healthy": False}),
        approval_receipt=_approval(),
        lease_owner_id="worker-a",
        wal_receipt=_wal(),
        cas_version=0,
        now=100,
    )

    with pytest.raises(P118WorkerError, match="missing_verification_or_approval_binding"):
        worker.run_once(
            operation.operation_id,
            now=101,
            validation_result=validation,
            operation=operation,
            verification_hash=_hash("5"),
            approval_receipt={**_approval(), "decision_hash": _hash("3")},
            lease_receipt=_lease(),
            wal_receipt=_wal(),
            cas_version=0,
        )


def test_expired_lease_takeover_is_atomic_under_contention(tmp_path) -> None:  # type: ignore[no-untyped-def]
    wal_path = tmp_path / "p118-ledger.jsonl"
    ledger = P118LedgerStore(wal_path)
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)
    ledger.record_lease(operation.operation_id, owner_id="worker-a", expires_at=90, receipt_type="lease_acquired")

    def acquire(owner: str) -> str:
        try:
            P118Worker(P118LedgerStore(wal_path), owner_id=owner, lease_ttl_seconds=10, max_retries=2).acquire_lease(operation.operation_id, now=100)
            return "acquired"
        except (P118WorkerError, ValueError):
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(acquire, ("worker-b", "worker-c")))
    assert outcomes.count("acquired") == 1
    assert outcomes.count("rejected") == 1
