from __future__ import annotations

from app.models.action import ActionRequest, ActionStatus
from app.services.action_service import ActionService
from app.services.action_simulator import ActionSimulator
from app.services.policy_engine import PolicyContext, default_capabilities


def test_action_simulator_returns_bounded_mock_effects() -> None:
    simulation = ActionSimulator().simulate(ActionRequest(action_type="mock.create_incident_ticket", target="payment-api", payload={"title": "x"}))

    assert simulation.success is True
    assert simulation.touched_resources == ["mock-ticket:payment-api"]
    assert simulation.rollback_path
    assert simulation.residual_risks


def test_action_service_refuses_execution_without_successful_simulation() -> None:
    service = ActionService()
    context = PolicyContext(capabilities=default_capabilities({"mock:workers:restart"}), service="worker", environment="local", night_autopilot=True)
    record = service.propose(ActionRequest(action_type="mock.execute_restart_worker", target="worker:local"), context)
    result = service.execute(record.id, context)

    assert result.status == ActionStatus.EXECUTED
    assert result.output["simulation"]["success"] is True

    unknown = service.propose(ActionRequest(action_type="made.up.action", target="unknown"), context)
    blocked = service.execute(unknown.id, context)
    assert blocked.status == ActionStatus.FAILED
    assert "not executable" in blocked.message
