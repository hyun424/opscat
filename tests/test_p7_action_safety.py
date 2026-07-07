from __future__ import annotations

from app.models.action import ActionRequest
from app.services.action_simulator import ActionSimulator
from app.services.blast_radius import BlastRadiusEngine
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.self_critique_service import SelfCritiqueService


def test_blast_radius_blocks_unknown_shell_and_allows_bounded_reversible_mock_action() -> None:
    engine = BlastRadiusEngine()

    unknown = engine.evaluate(ActionRequest(action_type="shell.execute", target="prod", environment="production", payload={"command": "rm -rf /"}))
    assert unknown.allowed is False
    assert unknown.scope == "prohibited"
    assert unknown.requires_human_approval is True

    bounded = engine.evaluate(ActionRequest(action_type="mock.execute_restart_worker", target="worker:staging", environment="staging"))
    assert bounded.allowed is True
    assert bounded.scope in {"local", "service"}
    assert bounded.rollback_available is True


def test_action_simulator_is_required_for_mutating_actions() -> None:
    simulator = ActionSimulator()

    result = simulator.simulate(ActionRequest(action_type="mock.create_rollback_pr", target="payment-api:staging", environment="staging", payload={"to_version": "v1.41.3"}))
    assert result.ok is True
    assert result.rollback_path
    assert "mock repository" in result.touched_resources[0]

    failed = simulator.simulate(ActionRequest(action_type="cloud.delete_resource", target="prod-db", environment="production"))
    assert failed.ok is False
    assert failed.precondition_gaps


def test_self_critique_gate_rejects_weak_or_conflicting_action_before_policy() -> None:
    critique = SelfCritiqueService().critique(
        confidence=0.92,
        evidence_count=1,
        alternate_causes=["external outage"],
        contradictions=["deploy marker is stale"],
        action_type="mock.create_rollback_pr",
    )

    assert critique.blocks_auto_action is True
    assert critique.ambiguity == "high"
    assert critique.missing_evidence


def test_night_autopilot_policy_v2_requires_reliability_gates() -> None:
    request = ActionRequest(action_type="mock.execute_restart_worker", target="worker:staging", environment="staging")
    allowed = PolicyEngine().evaluate(
        request,
        PolicyContext(
            mode="night_autopilot",
            service="worker",
            environment="staging",
            confidence=0.88,
            blast_radius_scope="service",
            reversible=True,
            simulation_status="passed",
            memory_failed_action_warning=False,
        ),
    )
    assert allowed.decision == "ALLOW"

    blocked = PolicyEngine().evaluate(
        request,
        PolicyContext(
            mode="night_autopilot",
            service="worker",
            environment="staging",
            confidence=0.88,
            blast_radius_scope="service",
            reversible=True,
            simulation_status="failed",
            memory_failed_action_warning=False,
        ),
    )
    assert blocked.decision in {"ESCALATE", "REQUIRE_APPROVAL"}
