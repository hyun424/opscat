from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.incidents import MockAlertRequest
from app.services.incident_service import create_and_investigate
from app.services.war_room_service import build_war_room


def _serialized(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def test_war_room_read_model_has_required_shape_redaction_and_deterministic_order(db_session: Session) -> None:
    incident = create_and_investigate(
        db_session,
        MockAlertRequest(
            idempotency_key="p8-war-room-shape",
            scenario="payment_bad_deploy",
            service="payment-api",
            environment="staging",
            message="5xx spike after deploy api_key=raw-secret Bearer raw.jwt.token ops@example.com",
        ),
    )

    first = build_war_room(incident)
    second = build_war_room(incident)

    assert _serialized(first) == _serialized(second)
    assert first["incident_id"] == incident.id
    assert first["tenant_id"] == incident.tenant_id
    assert first["workspace_id"] == incident.workspace_id
    assert first["status"] == incident.status
    assert set(first) >= {
        "impact",
        "timeline",
        "current_hypothesis",
        "root_cause_candidates",
        "evidence",
        "missing_evidence",
        "proposed_action",
        "policy_decision",
        "blast_radius",
        "simulation",
        "memory_matches",
        "reliability_gates",
        "human_questions",
        "reliability_score",
        "local_mock_only",
    }
    assert first["local_mock_only"] is True
    assert first["impact"] == {"service": "payment-api", "environment": "staging", "severity": "high"}
    assert [candidate["rank"] for candidate in first["root_cause_candidates"]] == [1, 2, 3]
    assert len(first["root_cause_candidates"]) == 3
    assert first["evidence"]
    assert first["timeline"]
    assert first["proposed_action"]["action_type"].startswith("mock.")
    assert first["policy_decision"]["decision"] in {"ALLOW", "REQUIRE_APPROVAL", "DENY", "ESCALATE"}
    assert first["blast_radius"]["scope"] in {"local", "service", "workspace", "tenant", "global", "unknown", "prohibited"}
    assert first["simulation"]["status"] in {"passed", "pass", "blocked", "escalate"}
    assert first["reliability_gates"]["hard_policy_blocked"] is False
    assert first["reliability_score"]["score"] >= 0

    serialized = _serialized(first)
    assert "raw-secret" not in serialized
    assert "raw.jwt.token" not in serialized
    assert "ops@example.com" not in serialized
    assert "[REDACTED]" in serialized


def test_war_room_handles_empty_incident_without_provider_network_or_shell_calls(monkeypatch: Any) -> None:
    from app.models import Incident

    def forbidden_call(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("war-room read model must not call network or shell surfaces")

    monkeypatch.setattr("socket.socket", forbidden_call)
    monkeypatch.setattr("subprocess.run", forbidden_call)
    incident = Incident(
        id="empty-p8",
        tenant_id="tenant-a",
        workspace_id="alpha",
        alert_fingerprint="empty",
        source="mock_alert",
        status="new",
        service="worker",
        environment="staging",
        severity="warning",
        alert_payload={"scenario": "empty"},
        summary="Waiting for local/mock evidence",
    )

    room = build_war_room(incident)

    assert room["local_mock_only"] is True
    assert room["evidence"] == []
    assert room["proposed_action"] is None
    assert room["policy_decision"]["decision"] == "not_recorded"
    assert room["human_questions"]
