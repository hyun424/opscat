from __future__ import annotations

from typing import Any

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


def test_operator_inbox_renders_workspace_scoped_incidents(client: Any) -> None:
    alpha = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "dash-alpha", "scenario": "payment_bad_deploy", "message": "alpha dashboard incident"},
    )
    beta = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=BETA_HEADERS,
        json={"idempotency_key": "dash-beta", "scenario": "payment_bad_deploy", "message": "beta hidden incident"},
    )
    assert alpha.status_code == 201
    assert beta.status_code == 201

    page = client.get("/operator", headers=ALPHA_HEADERS)

    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    html = page.text
    assert "OpsCat Operator" in html
    assert alpha.json()["id"] in html
    assert "alpha dashboard incident" in html
    assert beta.json()["id"] not in html
    assert "beta hidden incident" not in html


def test_operator_detail_renders_reasoning_attempts_and_approval_affordance(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "dash-detail", "scenario": "payment_bad_deploy"},
    )
    assert created.status_code == 201
    incident = created.json()
    action = incident["actions"][0]
    client.post(f"/approvals/{action['id']}", headers=ALPHA_HEADERS, json={"decision": "approve", "reason": "dashboard attempt"})

    page = client.get(f"/operator/incidents/{incident['id']}", headers=ALPHA_HEADERS)

    assert page.status_code == 200
    html = page.text
    assert incident["id"] in html
    assert "Evidence" in html
    assert "Timeline" in html
    assert "Actions" in html
    assert "Execution attempts" in html
    assert "Report" in html
    assert "Approve" in html or "approval_granted" in html


def test_operator_detail_respects_workspace_scope(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "dash-scope", "scenario": "payment_bad_deploy"},
    )
    assert created.status_code == 201

    hidden = client.get(f"/operator/incidents/{created.json()['id']}", headers=BETA_HEADERS)

    assert hidden.status_code == 404
