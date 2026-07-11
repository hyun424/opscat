from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.p119_contract import build_incident_envelope, exact_zero_authority_counters
from app.services.p119_ledger import P119LedgerError, P119LedgerStore


def test_p119_ledger_replays_hash_chained_cas_state_and_idempotency(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P119LedgerStore(tmp_path / "p119.jsonl")
    incident = build_incident_envelope(_incident())

    first = ledger.register_incident(incident)
    duplicate = ledger.register_incident(incident)
    triage = ledger.transition(incident.incident_id, "triage_started", expected_cas_version=0)
    diagnosing = ledger.transition(incident.incident_id, "diagnosing", expected_cas_version=1)

    replayed = ledger.replay(incident.incident_id)
    assert first.receipt_type == "incident_registered"
    assert duplicate.receipt_type == "idempotent_replay"
    assert triage.cas_version == 1
    assert diagnosing.cas_version == 2
    assert replayed.state == "diagnosing"
    assert replayed.cas_version == 2
    assert ledger.verify_hash_chain() is True


def test_p119_ledger_fails_closed_for_conflicting_idempotency_stale_cas_and_illegal_transition(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = P119LedgerStore(tmp_path / "p119.jsonl")
    ledger.register_incident(build_incident_envelope(_incident()))

    conflict = _incident("inc-p119-002")
    conflict["idempotency_key"] = "idem:p119:001"
    conflict["alert_fingerprint"] = "alert:other"
    with pytest.raises(P119LedgerError, match="idempotency_key_payload_mismatch"):
        ledger.register_incident(build_incident_envelope(conflict))

    state = ledger.replay("inc-p119-001")
    assert state.state == "aborted_fail_closed"
    with pytest.raises(P119LedgerError, match="terminal_state_reopened"):
        ledger.transition("inc-p119-001", "triage_started", expected_cas_version=state.cas_version)

    other = build_incident_envelope(_incident("inc-p119-003", idem="idem:p119:003"))
    ledger.register_incident(other)
    with pytest.raises(P119LedgerError, match="cas_conflict"):
        ledger.transition(other.incident_id, "triage_started", expected_cas_version=9)
    with pytest.raises(P119LedgerError, match="illegal_state_transition"):
        ledger.transition(other.incident_id, "local_executing", expected_cas_version=0)
    assert ledger.replay(other.incident_id).state == "aborted_fail_closed"


def test_p119_ledger_requires_single_owner_lease_for_execution_and_detects_hash_tamper(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "p119.jsonl"
    ledger = P119LedgerStore(path)
    incident = build_incident_envelope(_incident())
    ledger.register_incident(incident)
    ledger.transition(incident.incident_id, "triage_started", expected_cas_version=0)
    ledger.transition(incident.incident_id, "diagnosing", expected_cas_version=1)
    ledger.transition(incident.incident_id, "selection_pending", expected_cas_version=2)
    ledger.transition(incident.incident_id, "approval_pending", expected_cas_version=3)
    ledger.transition(incident.incident_id, "approved", expected_cas_version=4)

    with pytest.raises(P119LedgerError, match="lease_owner_mismatch"):
        ledger.transition(incident.incident_id, "local_execution_pending", expected_cas_version=5, lease_owner_id="worker-a")
    ledger.acquire_lease(incident.incident_id, owner_id="worker-a", now=10, ttl=5)
    with pytest.raises(P119LedgerError, match="lease_split_brain"):
        ledger.acquire_lease(incident.incident_id, owner_id="worker-b", now=11, ttl=5)
    receipt = ledger.transition(incident.incident_id, "local_execution_pending", expected_cas_version=5, lease_owner_id="worker-a")
    assert receipt.state == "local_execution_pending"

    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[-1])
    tampered["state"] = "recovered"
    lines[-1] = json.dumps(tampered, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert P119LedgerStore(path).verify_hash_chain() is False


def test_p119_registration_and_expired_lease_takeover_are_atomic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "p119.jsonl"
    incident = build_incident_envelope(_incident())

    def register(_: int) -> str:
        return P119LedgerStore(path).register_incident(incident).receipt_type

    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(register, range(8)))
    assert receipts.count("incident_registered") == 1 and receipts.count("idempotent_replay") == 7
    P119LedgerStore(path).acquire_lease(incident.incident_id, owner_id="old", now=1, ttl=1)

    def acquire(owner: str) -> str:
        try:
            P119LedgerStore(path).acquire_lease(incident.incident_id, owner_id=owner, now=3, ttl=10)
            return "acquired"
        except P119LedgerError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(acquire, ("a", "b")))
    assert outcomes.count("acquired") == 1 and outcomes.count("rejected") == 1


def _incident(incident_id: str = "inc-p119-001", *, idem: str = "idem:p119:001") -> dict[str, object]:
    return {
        "incident_id": incident_id,
        "schema_version": "p119.incident_envelope.v1",
        "alert_fingerprint": f"alert:{incident_id}",
        "fixture_id": "local:fixture:checkout-api",
        "state": "detected",
        "wal_position": 0,
        "cas_version": 0,
        "idempotency_key": idem,
        "budget_snapshot": {"incident_wall_clock_budget": 30, "evidence_attempts_remaining": 2},
        "timeline_hash": "sha256:" + "a" * 64,
        "replay_refs": ["replay:p119:001"],
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
