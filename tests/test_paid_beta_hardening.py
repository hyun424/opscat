from typing import Any

from app.services.redaction import redact_text


def test_mock_alert_idempotency_groups_duplicate_webhook(client: Any) -> None:
    payload = {
        "idempotency_key": "alert-123",
        "scenario": "payment_api_deploy_regression",
        "service": "payment-api",
        "environment": "staging",
        "severity": "high",
        "message": "Payment failed token=secret-token user@example.com",
    }

    first = client.post("/webhooks/alerts/mock", json=payload)
    second = client.post("/webhooks/alerts/mock", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    first_body = first.json()
    second_body = second.json()
    assert second_body["id"] == first_body["id"]
    assert second_body["alert_fingerprint"] == first_body["alert_fingerprint"]
    assert "secret-token" not in second_body["summary"]
    assert "user@example.com" not in second_body["summary"]

    listed = client.get("/incidents")
    matching = [item for item in listed.json() if item["alert_fingerprint"] == first_body["alert_fingerprint"]]
    assert len(matching) == 1


def test_workspace_header_scopes_incident_access_and_status(client: Any) -> None:
    alpha_headers = {"X-OpsCat-Workspace": "alpha"}
    beta_headers = {"X-OpsCat-Workspace": "beta"}

    created = client.post(
        "/webhooks/alerts/mock",
        headers=alpha_headers,
        json={"idempotency_key": "alpha-alert", "message": "alpha incident"},
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]
    assert created.json()["workspace_id"] == "alpha"

    assert client.get(f"/incidents/{incident_id}", headers=alpha_headers).status_code == 200
    hidden = client.get(f"/incidents/{incident_id}", headers=beta_headers)
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["workspace_id"] == "beta"

    alpha_status = client.get("/status", headers=alpha_headers)
    beta_status = client.get("/status", headers=beta_headers)
    assert alpha_status.status_code == 200
    assert alpha_status.json()["workspace_id"] == "alpha"
    assert sum(alpha_status.json()["incident_counts"].values()) >= 1
    assert beta_status.json()["workspace_id"] == "beta"
    assert beta_status.json()["incident_counts"] == {}


def test_redaction_removes_common_secret_and_pii_patterns() -> None:
    redacted = redact_text("api_key=abc123 bearer token.value user@example.com")
    assert "abc123" not in redacted
    assert "token.value" not in redacted
    assert "user@example.com" not in redacted
    assert "[REDACTED]" in redacted
