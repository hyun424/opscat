"""Regression tests for OpsCat's human-on-exception/no-silent-failure contract."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.loop import AgentLoop
from app.models import ActionProposal, Incident
from app.models.action import ActionRequest, PolicyDecision, PolicyEvaluation, RiskLevel
from app.schemas.incidents import MockAlertRequest
from app.services import incident_service
from app.services.incident_service import create_mock_incident, decide_action
from app.services.night_autopilot import simulate_night_autopilot
from app.services.policy_engine import PolicyContext


def test_protected_domain_approval_includes_human_wake_payload(client: Any) -> None:
    response = client.post(
        "/webhooks/alerts/mock",
        json={
            "scenario": "payment_bad_deploy",
            "source": "mock",
            "service": "payment-api",
            "environment": "production",
            "severity": "high",
            "title": "Payment API error spike after deploy",
            "fingerprint": "payment-api:checkout-timeout:v42",
        },
    )

    assert response.status_code in {200, 201, 202}, response.text
    incident = response.json()
    assert incident["status"] == "waiting_approval"
    action = incident["actions"][0]
    assert action["policy_decision"] == "REQUIRE_APPROVAL"
    assert action["escalation_required"] is True
    payload = action["escalation_payload"]
    assert payload["wake_human"] is True
    assert payload["escalation_decision"] == "wake_human"
    assert "protected_domain_or_high_impact" in payload["triggers"]
    assert payload["affected_service"] == "payment-api"
    assert payload["evidence_collected"]
    assert payload["actions_blocked"][0]["action_type"] == "mock.create_rollback_pr"
    assert payload["links"]["incident"].startswith("local://incidents/")
    assert any(event["event_type"] == "human_escalation_required" for event in incident["timeline"])


def test_policy_denial_escalates_with_blocked_action_payload(db_session: Session) -> None:
    class DenyAllPolicy:
        def evaluate(
            self,
            request: ActionRequest,
            context: PolicyContext | None = None,
        ) -> PolicyEvaluation:
            return PolicyEvaluation(
                decision=PolicyDecision.DENY,
                risk_level=RiskLevel.PROHIBITED,
                requires_approval=False,
                reason="test policy denies useful remediation",
            )

    incident = create_mock_incident(
        db_session,
        MockAlertRequest(service="demo-service", environment="staging", severity="medium"),
    )

    action = AgentLoop(policy_engine=DenyAllPolicy()).investigate(db_session, incident)  # type: ignore[arg-type]
    db_session.flush()

    assert incident.status == "escalated"
    assert action.status == "denied"
    assert action.escalation_required is True
    assert action.escalation_payload is not None
    assert "policy_denied_action" in action.escalation_payload["triggers"]
    assert action.escalation_payload["actions_blocked"][0]["policy_decision"] == "DENY"
    recorded = db_session.query(Incident).filter(Incident.id == incident.id).one()
    assert any(event.event_type == "human_escalation_required" for event in recorded.timeline)


def test_failed_post_check_escalates_instead_of_silent_success(
    db_session: Session,
    monkeypatch: Any,
) -> None:
    incident = create_mock_incident(
        db_session,
        MockAlertRequest(
            service="payment-api",
            environment="production",
            severity="high",
            scenario="payment_bad_deploy",
        ),
    )
    action = AgentLoop().investigate(db_session, incident)
    db_session.commit()

    def failed_recovery(_incident: Incident, _action: ActionProposal) -> dict[str, object]:
        return {
            "recovered": False,
            "message": "Mock post-check still sees elevated error rate.",
            "output": {"error_rate_delta": "+12%"},
            "verification": {"recovery_signal": "fail"},
        }

    monkeypatch.setattr(incident_service, "verify_recovery", failed_recovery)

    action, updated, report = decide_action(
        db_session,
        action.id,
        decision="approve",
        actor="oncall@example.com",
        reason="test failed verification path",
    )

    assert updated.status == "escalated"
    assert report is not None
    assert action.status == "executed"
    assert action.escalation_required is True
    assert action.escalation_payload is not None
    assert action.escalation_payload["trigger"] == "post_check_failed"
    assert action.escalation_payload["verification"]["recovered"] is False
    assert any(event.event_type == "human_escalation_required" for event in updated.timeline)


def test_night_autopilot_max_attempts_escalates_with_wake_payload(db_session: Session) -> None:
    from app.schemas.incidents import NightAutopilotConfig

    result = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(max_attempts_per_incident=0),
    )

    assert result.actions_taken == []
    assert result.escalations
    payload = result.escalations[0]
    assert payload["wake_human"] is True
    assert payload["trigger"] == "max_attempts_reached"
    assert payload["recommended_next_action"].startswith("Wake the configured on-call contact")
