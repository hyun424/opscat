from __future__ import annotations

from typing import Any

import pytest

from app.schemas.incidents import MockAlertRequest
from app.services.authorization import AuthorizationError
from app.services.identity_service import get_or_create_local_principal
from app.services.incident_service import create_and_investigate, decide_action, get_incident

ALPHA_HEADERS = {
    "X-OpsCat-Actor": "alpha-operator@example.com",
    "X-OpsCat-Tenant": "tenant-a",
    "X-OpsCat-Workspace": "alpha",
    "X-OpsCat-Role": "operator",
}
BETA_HEADERS = {
    "X-OpsCat-Actor": "beta-operator@example.com",
    "X-OpsCat-Tenant": "tenant-a",
    "X-OpsCat-Workspace": "beta",
    "X-OpsCat-Role": "operator",
}
VIEWER_HEADERS = {
    "X-OpsCat-Actor": "viewer@example.com",
    "X-OpsCat-Tenant": "tenant-a",
    "X-OpsCat-Workspace": "alpha",
    "X-OpsCat-Role": "viewer",
}


def _create_alpha_incident(client: Any) -> dict[str, Any]:
    created = client.post(
        "/webhooks/alerts/mock",
        headers=ALPHA_HEADERS,
        json={"scenario": "payment_bad_deploy", "environment": "production", "severity": "high"},
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_alert_payload_scope_must_match_authenticated_principal(client: Any) -> None:
    response = client.post(
        "/webhooks/alerts/mock",
        headers=ALPHA_HEADERS,
        json={"tenant_id": "tenant-a", "workspace_id": "beta", "message": "scope mismatch"},
    )

    assert response.status_code == 403
    assert "scope" in response.json()["detail"]["message"]


def test_cross_workspace_api_access_fails_before_report_or_investigation(client: Any) -> None:
    incident = _create_alpha_incident(client)
    incident_id = incident["id"]
    action_id = incident["actions"][0]["id"]

    assert client.get(f"/incidents/{incident_id}", headers=BETA_HEADERS).status_code == 404
    assert client.get(f"/incidents/{incident_id}/report", headers=BETA_HEADERS).status_code == 403
    assert client.post(f"/incidents/{incident_id}/investigate", headers=BETA_HEADERS).status_code == 403
    assert client.post(f"/approvals/{action_id}", headers=BETA_HEADERS, json={"decision": "approve"}).status_code == 403

    alpha_read = client.get(f"/incidents/{incident_id}", headers=ALPHA_HEADERS)
    assert alpha_read.status_code == 200
    assert alpha_read.json()["actions"][0]["status"] == "proposed"


def test_viewer_membership_cannot_approve_action(client: Any) -> None:
    incident = _create_alpha_incident(client)
    action_id = incident["actions"][0]["id"]

    denied = client.post(f"/approvals/{action_id}", headers=VIEWER_HEADERS, json={"decision": "approve"})

    assert denied.status_code == 403
    assert "approve" in denied.json()["detail"]["message"]


def test_service_layer_rejects_cross_workspace_access(db_session: Any) -> None:
    incident = create_and_investigate(
        db_session,
        MockAlertRequest(tenant_id="tenant-a", workspace_id="alpha", scenario="payment_bad_deploy", environment="production"),
    )
    beta = get_or_create_local_principal(
        db_session,
        email="beta-operator@example.com",
        tenant_id="tenant-a",
        workspace_id="beta",
        role="operator",
    )

    with pytest.raises(AuthorizationError):
        get_incident(db_session, incident.id, principal=beta)
    with pytest.raises(AuthorizationError):
        decide_action(
            db_session,
            incident.actions[0].id,
            decision="approve",
            actor="beta-operator@example.com",
            principal=beta,
        )
