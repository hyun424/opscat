from __future__ import annotations

from app.services.p119_war_room import P119WarRoomTimeline, build_p119_escalation


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def test_timeline_is_hash_chained_replayable_and_redacted() -> None:
    timeline = P119WarRoomTimeline("incident-001")
    timeline.append("incident_detected", {"state": "detected", "secret": "do-not-show", "note": "restart production"}, timestamp=1)
    timeline.append("evidence_received", {"evidence": ["metric:cpu"], "replay_ref": _hash("1")}, timestamp=2)
    view = timeline.read_model()
    assert timeline.verify() is True
    assert timeline.events[0]["payload"]["secret"] == "[REDACTED]"
    assert timeline.events[0]["payload"]["note"] == "[REDACTED]"
    assert view["event_count"] == 2


def test_timeline_tampering_is_detected_and_escalation_contains_required_context() -> None:
    timeline = P119WarRoomTimeline("incident-002")
    timeline.append("escalated", {"risk": "uncertain"}, timestamp=1)
    timeline.events[0]["payload"]["risk"] = "changed"
    assert timeline.verify() is False
    escalation = build_p119_escalation(
        incident_id="incident-002",
        missing_evidence=["dependency"],
        contradictions=["c1"],
        risk="utility crosses zero",
        validation_status="ambiguous",
        rollback_status="not_started",
        budget_snapshot={"evidence": 0},
        timeline_ref=_hash("2"),
        replay_ref=_hash("3"),
    )
    assert escalation["missing_evidence"] == ["dependency"]
    assert escalation["authority_counter_snapshot"]["production_mutation"] == 0
