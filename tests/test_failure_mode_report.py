"""P7-009 failure-mode report contracts."""

from __future__ import annotations

from typing import Any


def _create_report(client: Any, payload: dict[str, Any]) -> str:
    created = client.post("/webhooks/alerts/mock?process_now=true", json=payload)
    assert created.status_code == 201, created.text
    incident_id = created.json()["id"]
    report = client.get(f"/incidents/{incident_id}/report")
    assert report.status_code == 200, report.text
    return report.json()["report"]


def test_report_includes_failure_mode_analysis_for_low_confidence_escalation(client: Any) -> None:
    report = _create_report(
        client,
        {
            "idempotency_key": "p7-failure-mode-low-confidence",
            "scenario": "low_confidence_ambiguous",
            "environment": "staging",
            "severity": "high",
            "message": "ambiguous signal api_key=plain_secret Bearer raw.jwt.token ops@example.com",
        },
    )

    assert "## Failure Mode Analysis" in report
    assert "Uncertainty:" in report
    assert "Alternate hypotheses:" in report
    assert "Missing evidence:" in report
    assert "Blocked actions:" in report
    assert "Escalation reasons:" in report
    assert "low_confidence" in report
    assert "plain_secret" not in report
    assert "raw.jwt.token" not in report
    assert "ops@example.com" not in report
    assert "[REDACTED]" in report


def test_report_explains_policy_denied_action_failure_modes(client: Any) -> None:
    report = _create_report(
        client,
        {
            "idempotency_key": "p7-failure-mode-denied",
            "scenario": "protected_auth_incident",
            "service": "auth-api",
            "environment": "production",
            "severity": "critical",
        },
    )

    assert "## Failure Mode Analysis" in report
    assert "policy_denied_action" in report
    assert "production.restart_service" in report
    assert "Do not execute denied/prohibited action" in report
