from __future__ import annotations

from app.services.p119_contract import build_incident_envelope, exact_zero_authority_counters
from app.services.p119_ledger import P119LedgerStore
from app.services.p119_recovery import inventory_p119_orphans, recover_p119_incident, replay_p119_terminal_read_only


def _incident():  # type: ignore[no-untyped-def]
    return build_incident_envelope(
        {
            "incident_id": "incident-crash-001",
            "schema_version": "p119.incident_envelope.v1",
            "alert_fingerprint": "alert:checkout:latency",
            "fixture_id": "local:fixture:checkout-api",
            "state": "detected",
            "wal_position": 0,
            "cas_version": 0,
            "idempotency_key": "idem:crash-001",
            "budget_snapshot": {"incident_wall_clock_budget": 30},
            "timeline_hash": "sha256:" + "1" * 64,
            "replay_refs": ["replay:crash-001"],
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }
    )


def test_post_action_crash_takes_recovery_lease_rolls_back_and_replays_read_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "p119.jsonl"
    ledger = P119LedgerStore(path)
    incident = _incident()
    ledger.register_incident(incident)
    ledger.acquire_lease(incident.incident_id, owner_id="worker-a", now=10, ttl=10)
    for state in ("triage_started", "diagnosing", "selection_pending", "approval_pending", "approved", "local_execution_pending", "local_executing"):
        current = ledger.replay(incident.incident_id)
        ledger.transition(incident.incident_id, state, expected_cas_version=current.cas_version, lease_owner_id="worker-a")
    inventory = inventory_p119_orphans(path, now=21)
    result = recover_p119_incident(path, incident_id=incident.incident_id, recovery_owner="recovery-worker", now=21)
    before = path.read_text(encoding="utf-8")
    replay = replay_p119_terminal_read_only(path, incident.incident_id)
    assert inventory["pending_rollback"] == [incident.incident_id]
    assert result.final_state == "orphaned_recovered"
    assert result.rollback_attempt_count == 1 and result.duplicate_local_action_count == 0
    assert replay["replay_drift"] == 0 and path.read_text(encoding="utf-8") == before
