from __future__ import annotations

from app.services.p118_crash_recovery import inventory_p118_orphans, recover_p118_crash, replay_p118_terminal_read_only
from app.services.p118_ledger import P118LedgerStore
from app.services.p118_operation_contract import P118OperationEnvelope, build_operation_envelope, exact_zero_authority_counters


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64


def _operation() -> P118OperationEnvelope:
    return build_operation_envelope(
        {
            "operation_id": "op-crash-007",
            "schema_version": "p118.operation_envelope.v1",
            "p117_decision_episode_id": "episode-crash-007",
            "p117_selected_action_pack_id": "pack-local-007",
            "p115_action_pack_digest": _hash("1"),
            "fixture_target_id": "sandbox:fixture:checkout-api",
            "action_level": "L1",
            "precondition_refs": ["precondition:ready"],
            "validation_plan_ref": "validation:mock",
            "rollback_plan_ref": "rollback:mock",
            "approval_receipt": {"receipt_id": "approval", "policy_hash": _hash("2")},
            "lease_receipt": {"receipt_id": "lease", "owner_id": "worker-a"},
            "wal_position": 0,
            "cas_version": 0,
            "idempotency_key": "idem:crash-007",
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }
    )


def test_crash_recovery_inventories_orphans_and_rolls_forward_to_recoverable_terminal(tmp_path) -> None:  # type: ignore[no-untyped-def]
    wal_path = tmp_path / "p118.jsonl"
    ledger = P118LedgerStore(wal_path)
    operation = _operation()
    ledger.register_operation(operation)
    ledger.record_lease("op-crash-007", owner_id="worker-a", expires_at=90, receipt_type="lease_acquired")
    ledger.transition("op-crash-007", "verified", expected_cas_version=0, lease_owner_id="worker-a")
    ledger.transition("op-crash-007", "approved", expected_cas_version=1, lease_owner_id="worker-a")
    ledger.transition("op-crash-007", "prechecked", expected_cas_version=2, lease_owner_id="worker-a")
    ledger.transition("op-crash-007", "action_attempted", expected_cas_version=3, lease_owner_id="worker-a")

    inventory = inventory_p118_orphans(wal_path, now=100)
    recovery = recover_p118_crash(wal_path, operation_id="op-crash-007", owner_id="recovery-worker", now=100)

    assert inventory["expired_leases"] == ["op-crash-007"]
    assert inventory["pending_rollback"] == ["op-crash-007"]
    assert recovery.final_state == "rolled_back"
    assert recovery.duplicate_action_count == 0
    assert recovery.rollback_attempts == 1
    assert recovery.orphan_recoveries == 1
    assert recovery.rollback_evidence_hash is not None


def test_terminal_replay_is_read_only_stable_and_does_not_duplicate_effects(tmp_path) -> None:  # type: ignore[no-untyped-def]
    wal_path = tmp_path / "p118.jsonl"
    ledger = P118LedgerStore(wal_path)
    operation = _operation()
    ledger.register_operation(operation)
    ledger.record_lease("op-crash-007", owner_id="worker-a", expires_at=200, receipt_type="lease_acquired")
    for state in ("verified", "approved", "prechecked", "action_attempted", "postchecked", "succeeded"):
        current = ledger.replay("op-crash-007")
        ledger.transition("op-crash-007", state, expected_cas_version=current.cas_version, lease_owner_id="worker-a")
    before = wal_path.read_text(encoding="utf-8")

    first = replay_p118_terminal_read_only(wal_path, "op-crash-007")
    second = replay_p118_terminal_read_only(wal_path, "op-crash-007")

    assert first == second
    assert first["replay_drift"] == 0
    assert first["duplicate_action_count"] == 0
    assert wal_path.read_text(encoding="utf-8") == before
