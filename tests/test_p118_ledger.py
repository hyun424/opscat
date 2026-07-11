from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.p118_ledger import P118LedgerError, P118LedgerStore
from app.services.p118_operation_contract import build_operation_envelope, exact_zero_authority_counters


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64


def _operation(operation_id: str = "op-ledger-001") -> dict[str, object]:
    return {
        "operation_id": operation_id,
        "schema_version": "p118.operation_envelope.v1",
        "p117_decision_episode_id": "episode-ledger-001",
        "p117_selected_action_pack_id": "pack-local-001",
        "p115_action_pack_digest": _hash("1"),
        "fixture_target_id": "mock:fixture:checkout-api",
        "action_level": "L2",
        "precondition_refs": ["precondition:ready"],
        "validation_plan_ref": "validation:mock",
        "rollback_plan_ref": "rollback:mock",
        "approval_receipt": {"receipt_id": "approval"},
        "lease_receipt": {"receipt_id": "lease", "owner_id": "worker-a"},
        "wal_position": 0,
        "cas_version": 0,
        "idempotency_key": "idem:ledger-001",
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }


def test_ledger_registers_idempotently_and_replays_hash_chained_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())

    first = ledger.register_operation(operation)
    duplicate = ledger.register_operation(operation)
    verified = ledger.transition(operation.operation_id, "verified", expected_cas_version=0, lease_owner_id="worker-a")
    approved = ledger.transition(operation.operation_id, "approved", expected_cas_version=1, lease_owner_id="worker-a")

    replayed = ledger.replay(operation.operation_id)

    assert first.receipt_type == "operation_registered"
    assert duplicate.receipt_type == "idempotent_replay"
    assert duplicate.duplicate_action_count == 0
    assert verified.cas_version == 1
    assert approved.cas_version == 2
    assert replayed.state == "approved"
    assert replayed.cas_version == 2
    assert replayed.duplicate_action_count == 0
    assert ledger.verify_hash_chain() is True


def test_ledger_fails_closed_for_conflicting_idempotency_and_stale_cas(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)

    conflicting_payload = _operation(operation_id="op-ledger-002")
    conflicting_payload["idempotency_key"] = operation.idempotency_key
    conflicting_payload["fixture_target_id"] = "mock:fixture:other-service"

    with pytest.raises(P118LedgerError, match="idempotency_key_payload_mismatch"):
        ledger.register_operation(build_operation_envelope(conflicting_payload))
    with pytest.raises(P118LedgerError, match="cas_conflict"):
        ledger.transition(operation.operation_id, "verified", expected_cas_version=3, lease_owner_id="worker-a")
    with pytest.raises(P118LedgerError, match="lease_owner_mismatch"):
        ledger.transition(operation.operation_id, "verified", expected_cas_version=0, lease_owner_id="worker-b")


def test_ledger_rejects_illegal_transitions_and_terminal_reopen(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P118LedgerStore(tmp_path / "p118-ledger.jsonl")
    operation = build_operation_envelope(_operation())
    ledger.register_operation(operation)

    with pytest.raises(P118LedgerError, match="illegal_state_transition"):
        ledger.transition(operation.operation_id, "action_attempted", expected_cas_version=0, lease_owner_id="worker-a")

    ledger.transition(operation.operation_id, "verified", expected_cas_version=0, lease_owner_id="worker-a")
    ledger.transition(operation.operation_id, "approved", expected_cas_version=1, lease_owner_id="worker-a")
    ledger.transition(operation.operation_id, "prechecked", expected_cas_version=2, lease_owner_id="worker-a")
    ledger.transition(operation.operation_id, "action_attempted", expected_cas_version=3, lease_owner_id="worker-a")
    ledger.transition(operation.operation_id, "postchecked", expected_cas_version=4, lease_owner_id="worker-a")
    ledger.transition(operation.operation_id, "succeeded", expected_cas_version=5, lease_owner_id="worker-a")

    with pytest.raises(P118LedgerError, match="terminal_state_reopened"):
        ledger.transition(operation.operation_id, "verified", expected_cas_version=6, lease_owner_id="worker-a")


def test_concurrent_registration_has_one_atomic_operation_record(tmp_path) -> None:  # type: ignore[no-untyped-def]
    wal_path = tmp_path / "p118-ledger.jsonl"
    operation = build_operation_envelope(_operation())

    def register() -> str:
        return P118LedgerStore(wal_path).register_operation(operation).receipt_type

    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(lambda _: register(), range(8)))

    assert receipts.count("operation_registered") == 1
    assert receipts.count("idempotent_replay") == 7
    assert P118LedgerStore(wal_path).verify_hash_chain() is True
