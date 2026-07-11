from __future__ import annotations

from pathlib import Path

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p121_execution import P121ExecutionError, P121ExecutionStore, approve_prevention_operation, prove_p121_restart_recovery
from app.services.p121_signals import zero_authority_counters


def _envelope() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    registry = {"fixture-1": {"disposable": True, "target_class": "disposable_local_sandbox", "allowed_handlers": ["inject_latency"]}}
    envelope: dict[str, object] = {
        "operation_id": "op-1",
        "authority_level": "L3",
        "target_class": "disposable_local_sandbox",
        "fixture_id": "fixture-1",
        "handler": "inject_latency",
        "registry_hash": stable_hash(registry),
        "idempotency_key": "idem-1",
        "lease_owner": "worker-1",
        "lease_expires_at": 200,
        "approval_expires_at": 190,
        "authority_counters": zero_authority_counters(),
    }
    for name in ("forecast_hash", "evidence_hash", "counterfactual_hash", "guardrail_hash", "validation_plan_hash", "rollback_plan_hash"):
        envelope[name] = "sha256:" + name
    return envelope, registry


def test_registered_l3_executes_once_and_replays_without_effect() -> None:
    envelope, registry = _envelope()
    store = P121ExecutionStore()
    first = store.execute(envelope, registry=registry, now=100)
    replay = store.execute(envelope, registry=registry, now=100)
    assert first["effect_count"] == 1
    assert replay["effect_count"] == 1 and replay["replayed"] is True


def test_durable_store_recovers_idempotency_lease_and_hash_chain(tmp_path: Path) -> None:
    envelope, registry = _envelope()
    wal = tmp_path / "p121-execution.wal"
    first = P121ExecutionStore(wal).execute(envelope, registry=registry, now=100)
    restarted = P121ExecutionStore(wal)
    replay = restarted.execute(envelope, registry=registry, now=100)
    recovered = restarted.recover()
    assert replay["receipt_hash"] == first["receipt_hash"]
    assert replay["replayed"] is True
    assert recovered["receipt_count"] == 1
    assert recovered["lease_count"] == 1
    assert recovered["last_wal_hash"].startswith("sha256:")


def test_durable_store_detects_wal_tampering(tmp_path: Path) -> None:
    envelope, registry = _envelope()
    wal = tmp_path / "p121-execution.wal"
    P121ExecutionStore(wal).execute(envelope, registry=registry, now=100)
    wal.write_text(wal.read_text(encoding="utf-8").replace("effect_committed", "effect_committed_tampered"), encoding="utf-8")
    with pytest.raises(P121ExecutionError, match="wal_hash_chain_mismatch"):
        P121ExecutionStore(wal).recover()


def test_restart_recovery_proof_executes_partial_l3_and_rollback(tmp_path: Path) -> None:
    envelope, registry = _envelope()
    proof = prove_p121_restart_recovery(wal_path=tmp_path / "proof.wal", envelope=envelope, registry=registry, now=100)
    assert proof["point_count"] >= 13
    assert any(receipt["partial_l3_recovered"] for receipt in proof["crash_replay_receipts"].values())
    assert any(receipt["rollback_recovered"] for receipt in proof["crash_replay_receipts"].values())
    assert proof["crash_replay_receipts"]["rollback_begin"]["rollback_pending_replayed"] is True
    assert proof["wal_recovered"]["receipt_count"] == proof["point_count"]
    assert proof["wal_recovered"]["pending_rollback_count"] == 0


def test_recover_replays_interrupted_pending_rollback(tmp_path: Path) -> None:
    envelope, registry = _envelope()
    wal = tmp_path / "p121-rollback.wal"
    receipt = P121ExecutionStore(wal).execute(envelope, registry=registry, now=100)
    pending = P121ExecutionStore(wal).begin_rollback(str(envelope["idempotency_key"]), reason="crash_after_begin", now=101)
    interrupted = P121ExecutionStore(wal).recover()
    recovered = interrupted["receipts"][str(envelope["idempotency_key"])]

    assert pending["rollback_state"] == "pending"
    assert pending["replayed"] is False
    assert recovered["receipt_hash"] == receipt["receipt_hash"]
    assert recovered["rollback_recovered"] is True
    assert recovered["rollback_recovery"]["source"] == "pending_rollback_replay"
    assert interrupted["pending_rollback_count"] == 0


@pytest.mark.parametrize("mutation", [{"authority_level": "L2"}, {"target_class": "production"}, {"shell": "rm -rf /"}, {"api_key": "secret"}, {"handler": "unknown"}])
def test_execution_fails_closed_outside_registered_local_l3(mutation: dict[str, object]) -> None:
    envelope, registry = _envelope()
    envelope.update(mutation)
    assert approve_prevention_operation(envelope, registry=registry, now=100)["approved"] is False


def test_idempotency_payload_mismatch_fails_closed() -> None:
    envelope, registry = _envelope()
    store = P121ExecutionStore()
    store.execute(envelope, registry=registry, now=100)
    changed = dict(envelope)
    changed["operation_id"] = "different"
    with pytest.raises(P121ExecutionError, match="idempotency_payload_mismatch"):
        store.execute(changed, registry=registry, now=100)
