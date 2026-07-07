from __future__ import annotations

from typing import Any

from tests.test_operator_dashboard import ALPHA_HEADERS, BETA_HEADERS


def test_war_room_api_returns_redacted_operator_read_model(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={
            "idempotency_key": "war-room-api-redaction",
            "scenario": "payment_bad_deploy",
            "message": "war room incident api_key=plain-secret ops@example.com",
        },
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    response = client.get(f"/incidents/{incident_id}/war-room", headers=ALPHA_HEADERS)

    assert response.status_code == 200
    body = response.json()["war_room"]
    assert body["incident_id"] == incident_id
    assert body["tenant_id"] == ALPHA_HEADERS["X-OpsCat-Tenant"]
    assert body["workspace_id"] == ALPHA_HEADERS["X-OpsCat-Workspace"]
    assert body["summary"]
    assert body["impact"]["service"] == "payment-api"
    assert body["evidence"]
    assert body["timeline"]
    assert body["hypotheses"]
    assert body["policy_gates"]
    assert "score" in body["reliability_score"]
    assert body["runbook_critique"]["fit"]
    assert body["human_questions"]
    assert body["why_not_auto_execute"]
    serialized = response.text
    assert "plain-secret" not in serialized
    assert "ops@example.com" not in serialized
    assert "[REDACTED]" in serialized


def test_war_room_api_hides_other_workspace_incident(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "war-room-api-scope", "scenario": "payment_bad_deploy"},
    )
    assert created.status_code == 201

    hidden = client.get(f"/incidents/{created.json()['id']}/war-room", headers=BETA_HEADERS)

    assert hidden.status_code == 404


def test_war_room_api_missing_incident_is_404(client: Any) -> None:
    response = client.get("/incidents/missing-war-room/war-room", headers=ALPHA_HEADERS)

    assert response.status_code == 404
