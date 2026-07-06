"""API contract tests for the local OpsCat MVP."""

from __future__ import annotations

from typing import Any

from tests.conftest import (
    REQUIRED_ENDPOINTS,
    assert_no_external_credentials_required,
    route_fingerprint,
)


def test_required_mvp_routes_are_registered(app: Any) -> None:
    registered = route_fingerprint(app)
    missing = {name: route for name, route in REQUIRED_ENDPOINTS.items() if route not in registered}
    assert not missing, f"Missing MVP API routes: {missing}"


def test_health_endpoint_is_local_and_ok(client: Any) -> None:
    assert_no_external_credentials_required()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") in {"ok", "healthy"}
    assert body.get("service", "opscat") == "opscat"


def test_payment_bad_deploy_happy_path_contract(client: Any) -> None:
    alert = {
        "scenario": "payment_bad_deploy",
        "source": "mock",
        "service": "payment-api",
        "environment": "production",
        "severity": "high",
        "title": "Payment API error spike after deploy",
        "fingerprint": "payment-api:checkout-timeout:v42",
    }

    created = client.post("/webhooks/alerts/mock", json=alert)
    assert created.status_code in {200, 201, 202}, created.text
    incident = created.json()
    incident_id = incident.get("id") or incident.get("incident_id")
    assert incident_id, incident
    assert incident.get("service") == "payment-api"
    assert incident.get("environment") == "production"

    analysis = incident
    assert analysis.get("summary")
    assert analysis.get("actions"), analysis
    assert len(analysis.get("evidence", [])) >= 2

    evidence_ids = set()
    for hypothesis in analysis.get("hypotheses", []):
        evidence_ids.update(hypothesis.get("supporting_evidence_ids", []))
    assert len(evidence_ids) >= 2, "top recommendation must be backed by at least two evidence items"

    recommended = analysis.get("recommended_action") or analysis.get("action")
    assert recommended, analysis
    assert recommended.get("risk_level") in {"low", "medium", "high", "prohibited"}
    assert recommended.get("post_checks"), "actions must define post-checks before execution"
    assert len(recommended.get("evidence_ids", [])) >= 2

    listed = client.get("/incidents")
    assert listed.status_code == 200
    assert any(item.get("id") == incident_id for item in listed.json())
