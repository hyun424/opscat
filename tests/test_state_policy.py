import pytest

from app.models import Incident
from app.models.action import ActionRequest, PolicyDecision, RiskLevel
from app.services.policy_engine import (
    NightAutopilotConfig,
    PolicyContext,
    PolicyEngine,
    default_capabilities,
)
from app.services.state_machine import InvalidStateTransition, transition_incident


def test_state_machine_rejects_invalid_transition() -> None:
    incident = Incident(service="payment-api", environment="staging", severity="high", status="new")
    with pytest.raises(InvalidStateTransition):
        transition_incident(incident, "resolved")


def test_state_machine_allows_ordered_transition() -> None:
    incident = Incident(service="payment-api", environment="staging", severity="high", status="new")
    event = transition_incident(incident, "queued", actor="system")
    assert incident.status == "queued"
    assert event.event_metadata["to"] == "queued"


def test_policy_blocks_prohibited_actions() -> None:
    result = PolicyEngine().evaluate(
        ActionRequest(action_type="shell.execute", target="host", payload={"cmd": "rm -rf /"}),
        PolicyContext(),
    )
    assert result.decision == PolicyDecision.DENY
    assert result.risk_level == RiskLevel.PROHIBITED


def test_policy_requires_approval_for_mock_pr() -> None:
    result = PolicyEngine().evaluate(
        ActionRequest(
            action_type="mock.create_rollback_pr",
            target="payment-api",
            environment="staging",
        ),
        PolicyContext(
            capabilities=default_capabilities({"mock:pull_requests:write"}),
            environment="staging",
            service="payment-api",
        ),
    )
    assert result.decision == PolicyDecision.REQUIRE_APPROVAL
    assert result.requires_approval is True


def test_policy_allows_night_autopilot_allowlisted_low_risk_action() -> None:
    result = PolicyEngine().evaluate(
        ActionRequest(
            action_type="mock.execute_restart_worker",
            target="worker:staging",
            environment="staging",
        ),
        PolicyContext(
            capabilities=default_capabilities({"mock:workers:restart"}),
            environment="staging",
            service="worker",
            night_autopilot=True,
            autopilot=NightAutopilotConfig(
                allowed_services=("worker",),
                allowed_environments=("staging",),
                allowed_actions=("mock.execute_restart_worker",),
            ),
        ),
    )
    assert result.decision == PolicyDecision.ALLOW
    assert result.requires_approval is False
