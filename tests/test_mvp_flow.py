from fastapi.testclient import TestClient


def test_mock_alert_to_approval_execution_report_flow(client: TestClient) -> None:
    response = client.post(
        "/webhooks/alerts/mock?process_now=true",
        json={
            "scenario": "payment_api_deploy_regression",
            "environment": "staging",
            "severity": "high",
            "message": "Payment API timeout spike",
        },
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["status"] == "waiting_approval"
    assert incident["service"] == "payment-api"
    assert len(incident["evidence"]) >= 4
    assert incident["actions"][0]["policy_decision"] == "REQUIRE_APPROVAL"
    assert incident["actions"][0]["risk_level"] == "medium"
    assert len(incident["actions"][0]["evidence_ids"]) >= 2

    action_id = incident["actions"][0]["id"]
    approved = client.post(
        f"/approvals/{action_id}",
        json={"decision": "approve", "actor": "test-oncall", "reason": "safe mock action"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["incident"]["status"] == "resolved"
    assert body["action"]["status"] == "executed"
    assert body["action"]["execution_result"]["ok"] is True
    assert body["report"] is not None

    report = client.get(f"/incidents/{incident['id']}/report")
    assert report.status_code == 200
    assert "Incident Report" in report.json()["report"]
    report_text = report.json()["report"]
    assert "mock.create_rollback_pr" in report_text
    assert "Simulation" in report_text
    assert "Blast radius: workspace" in report_text


def test_reject_approval_escalates(client: TestClient) -> None:
    incident = client.post("/webhooks/alerts/mock?process_now=true", json={}).json()
    action_id = incident["actions"][0]["id"]
    rejected = client.post(
        f"/approvals/{action_id}",
        json={"decision": "reject", "actor": "test-oncall", "reason": "not during freeze"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["incident"]["status"] == "escalated"
    assert rejected.json()["action"]["status"] == "rejected"


def test_night_autopilot_simulation_executes_allowlisted_low_risk_action(client: TestClient) -> None:
    response = client.post("/night-autopilot/simulate", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "simulated"
    assert body["incidents_detected"] == 1
    assert len(body["actions_taken"]) == 1
    assert body["escalations"] == []
    assert "Night Autopilot Morning Report" in body["morning_report"]
