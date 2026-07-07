from __future__ import annotations

from typing import Any

from app.models.action import ActionRequest
from app.services.action_service import ActionService
from app.services.action_simulator import ActionSimulator, SimulationStatus
from app.services.policy_engine import PolicyContext


def test_action_simulator_returns_bounded_effect_and_rollback_for_mock_actions() -> None:
    simulator = ActionSimulator()
    result = simulator.simulate(
        ActionRequest(
            action_type="mock.create_rollback_pr",
            target="payment-api",
            environment="staging",
            payload={"rollback_to": "deploy-41"},
        )
    )

    assert result.status == SimulationStatus.PASS
    assert result.allowed is True
    assert result.blast_radius.level.value == "workspace"
    assert "payment-api" in result.touched_resources
    assert result.rollback_path is not None
    assert result.precondition_gaps == ()
    assert "no external mutation" in result.expected_effect


def test_action_simulator_fails_closed_for_missing_preconditions_and_unknown_actions() -> None:
    simulator = ActionSimulator()

    missing_precondition = simulator.simulate(
        ActionRequest(action_type="mock.create_rollback_pr", target="payment-api", environment="staging", payload={"missing_preconditions": ["rollback_plan_present"]})
    )
    unknown = simulator.simulate(ActionRequest(action_type="unknown.provider.mutate", target="payment-api", environment="staging"))

    assert missing_precondition.status == SimulationStatus.BLOCKED
    assert missing_precondition.allowed is False
    assert "rollback_plan_present" in missing_precondition.precondition_gaps
    assert unknown.status == SimulationStatus.ESCALATE
    assert unknown.allowed is False
    assert unknown.blast_radius.level.value == "unknown"


def test_action_service_serializes_blast_radius_and_simulation_evidence() -> None:
    service = ActionService()
    record = service.propose(
        ActionRequest(action_type="report.generate", target="incident-1", payload={"evidence_ids": ["ev-1"]}),
        PolicyContext(),
    )

    data = service.serialize_record(record)

    assert data["evaluation"]["blast_radius"]["level"] == "local"
    assert data["evaluation"]["simulation"]["status"] == "pass"
    assert data["audit_context"]["blast_radius"]["level"] == "local"
    assert data["audit_context"]["simulation"]["allowed"] is True


def test_persisted_action_attempt_records_simulation_precondition(client: Any) -> None:
    created = client.post("/webhooks/alerts/mock?process_now=true", json={"scenario": "payment_api_deploy_regression", "environment": "staging"})
    assert created.status_code == 201, created.text
    action = created.json()["actions"][0]

    approved = client.post(f"/approvals/{action['id']}", json={"decision": "approve", "actor": "test", "reason": "simulation evidence"})

    assert approved.status_code == 200, approved.text
    attempt = approved.json()["action"]["execution_attempts"][0]
    simulation = attempt["precondition_result"]["simulation"]
    assert simulation["status"] == "pass"
    assert simulation["blast_radius"]["level"] == "workspace"
    assert simulation["rollback_path"]
