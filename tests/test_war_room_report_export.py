from __future__ import annotations

from typing import Any

from tests.test_operator_dashboard import ALPHA_HEADERS


def test_incident_report_exports_redacted_war_room_sections(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={
            "idempotency_key": "war-room-report-export",
            "scenario": "payment_bad_deploy",
            "message": "report export api_key=plain-secret ops@example.com",
        },
    )
    assert created.status_code == 201
    incident = created.json()

    response = client.get(f"/incidents/{incident['id']}/report", headers=ALPHA_HEADERS)

    assert response.status_code == 200
    report = response.json()["report"]
    for section in [
        "# War Room Report:",
        "## Incident Summary",
        "## Impact",
        "## Timeline",
        "## Evidence",
        "## Hypotheses",
        "## Reliability Score",
        "## Policy Gates",
        "## Runbook Critique",
        "## Human Questions",
        "## Final Decision",
        "## Incident Report:",
    ]:
        assert section in report
    assert "plain-secret" not in report
    assert "ops@example.com" not in report
    assert "[REDACTED]" in report


def test_war_room_report_is_deterministic_for_same_incident(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "war-room-report-deterministic", "scenario": "payment_bad_deploy"},
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    first = client.get(f"/incidents/{incident_id}/report", headers=ALPHA_HEADERS).json()["report"]
    second = client.get(f"/incidents/{incident_id}/report", headers=ALPHA_HEADERS).json()["report"]

    assert first == second
