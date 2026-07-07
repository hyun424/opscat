from __future__ import annotations

from typing import Any


def test_action_attempt_records_dry_run_rollback_and_policy_metadata(client: Any) -> None:
    created = client.post("/webhooks/alerts/mock?process_now=true", json={"scenario": "payment_api_deploy_regression", "environment": "staging"})
    assert created.status_code == 201, created.text
    action = created.json()["actions"][0]

    approved = client.post(f"/approvals/{action['id']}", json={"decision": "approve", "actor": "test", "reason": "metadata check"})
    assert approved.status_code == 200, approved.text
    attempts = approved.json()["action"]["execution_attempts"]

    assert attempts
    preconditions = attempts[0]["precondition_result"]
    assert "dry_run_payload" in preconditions
    assert preconditions["rollback_metadata"]["required"] is True
    assert preconditions["policy_decision_id"].startswith("ALLOW:")
