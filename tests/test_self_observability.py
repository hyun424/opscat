"""Self-observability metrics for OpsCat as an agentic operations system."""

from __future__ import annotations

import json
from typing import Any

from app.connectors.base import ConnectorCallRequest
from app.services.connector_service import ConnectorService
from app.services.identity_service import get_or_create_local_principal
from app.services.workflow_service import process_next_workflow_job
from tests.test_operator_dashboard import ALPHA_HEADERS, BETA_HEADERS

SECRET_MARKERS = ("sk_live_", "fixture-token", "Authorization", "customer@example.com")


def test_metrics_endpoint_reports_scoped_agent_operations_without_secrets(client: Any, db_session: Any) -> None:
    queued = client.post(
        "/webhooks/alerts/mock",
        headers=ALPHA_HEADERS,
        json={
            "idempotency_key": "metrics-queued",
            "scenario": "worker_queue_backlog",
            "message": "metrics queued incident token=sk_live_should_not_leak customer@example.com",
        },
    )
    investigated = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "metrics-investigated", "scenario": "payment_bad_deploy"},
    )
    beta = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=BETA_HEADERS,
        json={"idempotency_key": "metrics-beta-hidden", "scenario": "payment_bad_deploy"},
    )
    assert queued.status_code == 202
    assert investigated.status_code == 201
    assert beta.status_code == 201

    processed = process_next_workflow_job(db_session, worker_id="metrics-test")
    assert processed is not None
    db_session.commit()

    principal = get_or_create_local_principal(
        db_session,
        email=ALPHA_HEADERS["X-OpsCat-Actor"],
        tenant_id=ALPHA_HEADERS["X-OpsCat-Tenant"],
        workspace_id=ALPHA_HEADERS["X-OpsCat-Workspace"],
        role=ALPHA_HEADERS["X-OpsCat-Role"],
    )
    ConnectorService().call(
        db_session,
        principal,
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="issues.read",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            incident_id=investigated.json()["id"],
            idempotency_key="metrics-missing-secret",
            payload={"provider_mode": "real", "project": "checkout-api", "Authorization": "fixture-token"},
        ),
    )
    db_session.commit()

    response = client.get("/metrics", headers=ALPHA_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "local-mock"
    assert payload["tenant_id"] == "tenant-a"
    assert payload["workspace_id"] == "alpha"
    assert payload["incidents"]["created"] >= 2
    assert payload["workflow_jobs"]["processed"] >= 1
    assert payload["actions"]["proposed"] >= 2
    assert payload["connector_failures"] >= 1
    assert payload["escalations"] >= 1
    assert payload["evals"]["connector_scenarios_registered"] >= 11
    assert "generated_at" in payload

    rendered = json.dumps(payload, sort_keys=True)
    assert all(marker not in rendered for marker in SECRET_MARKERS)
    assert "metrics-beta-hidden" not in rendered
