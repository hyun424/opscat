from __future__ import annotations

import json
from typing import Any

from app.models import AuditEvent


def _event_types(client: Any, incident_payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> tuple[dict[str, Any], list[str]]:
    created = client.post("/webhooks/alerts/mock?process_now=true", headers=headers or {}, json=incident_payload)
    assert created.status_code == 201, created.text
    incident = created.json()
    listed = client.get("/incidents", headers=headers or {})
    assert listed.status_code == 200
    return incident, [event["event_type"] for event in incident["timeline"]]


def test_audit_log_records_policy_execution_verification_and_report(client: Any, db_session: Any) -> None:
    incident, _ = _event_types(client, {"scenario": "payment_api_deploy_regression", "environment": "staging"})
    action_id = incident["actions"][0]["id"]

    approved = client.post("/approvals/" + action_id, json={"decision": "approve", "actor": "audit-test", "reason": "exercise audit"})
    assert approved.status_code == 200, approved.text

    events = db_session.query(AuditEvent).filter(AuditEvent.resource_id.in_([incident["id"], action_id])).all()
    event_types = {event.event_type for event in events}
    assert {
        "alert_received",
        "action_proposed",
        "policy_decision",
        "approval_granted",
        "action_executed",
        "recovery_verified",
        "report_generated",
    } <= event_types
    assert all(event.tenant_id == "demo" and event.workspace_id == "demo" for event in events)


def test_audit_log_records_rejection_and_escalation(client: Any, db_session: Any) -> None:
    low_confidence, _ = _event_types(client, {"scenario": "low_confidence_ambiguous", "environment": "staging"})
    waiting, _ = _event_types(client, {"scenario": "payment_api_deploy_regression", "environment": "staging", "idempotency_key": "audit-reject"})
    action_id = waiting["actions"][0]["id"]

    rejected = client.post("/approvals/" + action_id, json={"decision": "reject", "actor": "audit-test", "reason": "not safe"})
    assert rejected.status_code == 200, rejected.text

    events = db_session.query(AuditEvent).all()
    by_resource = {(event.resource_id, event.event_type) for event in events}
    assert (low_confidence["id"], "human_escalation_required") in by_resource
    assert (action_id, "approval_rejected") in by_resource


def test_audit_metadata_is_redacted(client: Any, db_session: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        json={
            "scenario": "payment_api_deploy_regression",
            "message": "api_key=plain-secret Bearer raw.jwt.token ops@example.com",
        },
    )
    assert created.status_code == 201, created.text

    serialized = json.dumps([event.event_metadata for event in db_session.query(AuditEvent).all()], default=str, sort_keys=True)
    assert "plain-secret" not in serialized
    assert "raw.jwt.token" not in serialized
    assert "ops@example.com" not in serialized
