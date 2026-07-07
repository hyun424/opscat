from __future__ import annotations

from typing import Any


def test_failed_post_action_verification_escalates_with_verification_evidence(client: Any) -> None:
    created = client.post("/webhooks/alerts/mock?process_now=true", json={"scenario": "verification_failure", "environment": "staging"})
    assert created.status_code == 201
    action = created.json()["actions"][0]

    approved = client.post(f"/approvals/{action['id']}", json={"decision": "approve", "actor": "test", "reason": "verify failure"})
    assert approved.status_code == 200, approved.text
    incident = approved.json()["incident"]

    assert incident["status"] == "escalated"
    assert any(event["event_type"] == "recovery_verified" for event in incident["timeline"])
    assert any(attempt["post_check_result"].get("recovered") is False for attempt in approved.json()["action"]["execution_attempts"])
