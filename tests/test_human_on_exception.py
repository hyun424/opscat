"""Human-on-exception coverage: OpsCat escalates instead of guessing."""

from __future__ import annotations

from typing import Any

from app.models.action import ActionRequest, PolicyDecision
from app.services.policy_engine import NightAutopilotConfig, PolicyContext, PolicyEngine, default_capabilities


def _create_incident(client: Any, scenario: str, *, service: str = "payment-api", environment: str = "staging", severity: str = "high") -> dict[str, Any]:
    response = client.post(
        "/webhooks/alerts/mock",
        json={
            "scenario": scenario,
            "service": service,
            "environment": environment,
            "severity": severity,
            "message": f"Human-on-exception test alert: {scenario}",
            "fingerprint": f"{service}:{scenario}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _first_action(incident: dict[str, Any]) -> dict[str, Any]:
    assert incident.get("actions"), incident
    return incident["actions"][0]


def test_low_confidence_incident_escalates_with_evidence(client: Any) -> None:
    incident = _create_incident(client, "low_confidence_ambiguous")
    action = _first_action(incident)

    assert incident["status"] == "escalated"
    assert incident["confidence"] < 0.70
    assert action["action_type"] == "human.escalate"
    assert action["policy_decision"] == "ESCALATE"
    assert len(action["evidence_ids"]) >= 2
    assert "wake" in str(action["payload"]).lower()


def test_missing_runbook_context_escalates_instead_of_guessing(client: Any) -> None:
    incident = _create_incident(client, "missing_runbook_context", service="unknown-service")
    action = _first_action(incident)
    runbook_evidence = [item for item in incident["evidence"] if item["type"] == "runbook"]

    assert incident["status"] == "escalated"
    assert action["policy_decision"] == "ESCALATE"
    assert runbook_evidence
    assert runbook_evidence[0]["evidence_metadata"]["missing_runbook"] is True
    assert "No trusted runbook" in runbook_evidence[0]["content"]


def test_protected_auth_domain_denies_dangerous_action_and_escalates(client: Any) -> None:
    incident = _create_incident(client, "protected_auth_incident", service="auth-api", environment="production", severity="critical")
    action = _first_action(incident)

    assert incident["status"] == "escalated"
    assert action["action_type"] == "production.restart_service"
    assert action["policy_decision"] == "DENY"
    assert action["risk_level"] == "prohibited"
    assert "human" in action["rationale"].lower()


def test_failed_verification_escalates_after_approved_mock_action(client: Any) -> None:
    incident = _create_incident(client, "verification_failure", environment="production")
    action = _first_action(incident)
    assert incident["status"] == "waiting_approval"
    assert action["policy_decision"] == "REQUIRE_APPROVAL"

    approved = client.post(
        f"/incidents/{incident['id']}/actions/{action['id']}/approve",
        json={"decision": "approve", "actor": "test-human", "reason": "exercise failed verification path"},
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()

    assert body["incident"]["status"] == "escalated"
    assert body["action"]["status"] == "executed"
    assert "verification failed" in str(body["incident"]["timeline"]).lower()
    assert "forced_failure" in str(body["incident"]["timeline"])


def test_night_autopilot_max_attempts_escalates_without_action(client: Any) -> None:
    response = client.post("/night-autopilot/simulate", json={"max_attempts_per_incident": 0})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["actions_taken"] == []
    assert body["escalations"]
    assert "night autopilot" in body["morning_report"].lower()
    assert "escalated" in body["morning_report"].lower()


def test_policy_escalates_unknown_action_for_manual_review() -> None:
    result = PolicyEngine().evaluate(
        ActionRequest(action_type="human.escalate", target="payment-api:production", environment="production"),
        PolicyContext(capabilities=default_capabilities(), service="payment-api", environment="production"),
    )

    assert result.decision == PolicyDecision.ESCALATE
    assert result.requires_approval is True
    assert "manual review" in result.reason


def test_policy_escalates_night_autopilot_after_max_attempts() -> None:
    result = PolicyEngine().evaluate(
        ActionRequest(action_type="mock.execute_restart_worker", target="worker:staging", environment="staging"),
        PolicyContext(
            capabilities=default_capabilities({"mock:workers:restart"}),
            service="worker",
            environment="staging",
            night_autopilot=True,
            autopilot_attempts=1,
            autopilot=NightAutopilotConfig(
                allowed_services=("worker",),
                allowed_environments=("staging",),
                allowed_actions=("mock.execute_restart_worker",),
                max_attempts_per_incident=1,
            ),
        ),
    )

    assert result.decision == PolicyDecision.ESCALATE
    assert result.requires_approval is True
