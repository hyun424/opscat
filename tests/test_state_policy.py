import pytest

from app.models import Incident
from app.services.policy_engine import PolicyContext, PolicyEngine
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
    result = PolicyEngine().evaluate("prohibited.arbitrary_shell", PolicyContext())
    assert result.decision == "DENY"
    assert result.risk_level == "prohibited"


def test_policy_requires_approval_for_mock_pr() -> None:
    result = PolicyEngine().evaluate(
        "mock.create_rollback_pr",
        PolicyContext(environment="staging", service="payment-api"),
    )
    assert result.decision == "REQUIRE_APPROVAL"
    assert result.requires_approval is True


def test_policy_allows_night_autopilot_allowlisted_low_risk_action() -> None:
    result = PolicyEngine().evaluate(
        "mock.execute_restart_worker",
        PolicyContext(mode="night_autopilot", environment="staging", service="worker"),
    )
    assert result.decision == "ALLOW"
    assert result.requires_approval is False
