from __future__ import annotations

from typing import Any

from app.models import ActionExecutionAttempt, Incident


def _create_process_now_incident(client: Any, *, scenario: str = "payment_bad_deploy") -> dict[str, Any]:
    response = client.post(
        "/webhooks/alerts/mock?process_now=true",
        json={"idempotency_key": f"attempt-{scenario}", "scenario": scenario, "environment": "staging"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["actions"], body
    return body


def test_approval_execution_persists_immutable_attempt_with_post_check(client: Any, db_session: Any) -> None:
    incident = _create_process_now_incident(client)
    action = incident["actions"][0]

    approved = client.post(
        f"/approvals/{action['id']}",
        json={"decision": "approve", "reason": "attempt regression"},
    )

    assert approved.status_code == 200, approved.text
    attempts = db_session.query(ActionExecutionAttempt).all()
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.action_id == action["id"]
    assert attempt.incident_id == incident["id"]
    assert attempt.status == "succeeded"
    assert attempt.attempt_number == 1
    assert attempt.precondition_result["ok"] is True
    assert attempt.execution_result["ok"] is True
    assert attempt.post_check_result["recovered"] is True
    assert attempt.retry_eligible is False
    body_action = approved.json()["action"]
    assert body_action["execution_attempts"][0]["id"] == attempt.id


def test_failed_post_check_attempt_escalates_with_attempt_metadata(client: Any, db_session: Any) -> None:
    incident = _create_process_now_incident(client, scenario="verification_failure")
    action = incident["actions"][0]

    approved = client.post(
        f"/approvals/{action['id']}",
        json={"decision": "approve", "reason": "force verification failure"},
    )

    assert approved.status_code == 200, approved.text
    attempt = db_session.query(ActionExecutionAttempt).one()
    assert attempt.status == "post_check_failed"
    assert attempt.retry_eligible is True
    assert attempt.failure_class == "post_check_failed"
    assert "sk-live" not in repr(attempt.execution_result) + repr(attempt.post_check_result)
    refreshed = db_session.query(Incident).filter(Incident.id == incident["id"]).one()
    assert refreshed.status == "escalated"
    assert any(event.event_type == "human_escalation_required" for event in refreshed.timeline)
