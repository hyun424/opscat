from __future__ import annotations

import pytest

from app.services.p119_contract import P119ContractError, build_incident_envelope, build_timeline_event, exact_zero_authority_counters


def test_incident_contract_accepts_complete_local_schema_and_hashes_timeline() -> None:
    incident = build_incident_envelope(_incident())
    event = build_timeline_event(
        incident_id=incident.incident_id,
        event_type="incident_detected",
        state_before="detected",
        state_after="detected",
        timestamp=1,
        actor_type="local_detector",
        payload={"source_artifact_refs": ["fixture:alert"]},
        previous_hash="",
        budget_snapshot={"incident_wall_clock_budget": 30},
    )

    payload = incident.to_dict()
    assert payload["schema_version"] == "p119.incident_envelope.v1"
    assert payload["authority_counter_snapshot"] == exact_zero_authority_counters()
    assert payload["payload_hash"].startswith("sha256:")
    assert event["current_hash"].startswith("sha256:")
    assert event["authority_counter_snapshot"] == exact_zero_authority_counters()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.pop("incident_id"), "missing_incident_id"),
        (lambda payload: payload.__setitem__("schema_version", "p119.incident_envelope.v2"), "unsupported_schema_version"),
        (lambda payload: payload.__setitem__("state", "invented"), "unknown_state"),
        (lambda payload: payload.__setitem__("state", "recovered"), "missing_terminal_status"),
        (lambda payload: payload["authority_counter_snapshot"].__setitem__("production_mutation_count", 1), "authority_counter_nonzero:production_mutation_count"),
        (lambda payload: payload.__setitem__("target", "production checkout"), "forbidden_authority_text"),
        (lambda payload: payload.__setitem__("shell_text", "echo unsafe"), "forbidden_authority_field:shell_text"),
    ],
)
def test_incident_contract_red_cases_fail_closed(mutate: object, message: str) -> None:
    payload = _incident()
    mutate(payload)  # type: ignore[operator]

    with pytest.raises(P119ContractError, match=message):
        build_incident_envelope(payload)


def _incident() -> dict[str, object]:
    return {
        "incident_id": "inc-p119-001",
        "schema_version": "p119.incident_envelope.v1",
        "alert_fingerprint": "alert:checkout:latency",
        "fixture_id": "local:fixture:checkout-api",
        "state": "detected",
        "wal_position": 0,
        "cas_version": 0,
        "idempotency_key": "idem:p119:001",
        "budget_snapshot": {"incident_wall_clock_budget": 30, "evidence_attempts_remaining": 2},
        "timeline_hash": "sha256:" + "a" * 64,
        "replay_refs": ["replay:p119:001"],
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
