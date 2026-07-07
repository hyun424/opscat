from __future__ import annotations

from app.models.action import ActionRequest, PolicyDecision
from app.services.policy_engine import PolicyContext, PolicyEngine, default_capabilities


def test_night_autopilot_v2_requires_confidence_blast_radius_simulation_and_memory() -> None:
    engine = PolicyEngine()
    request = ActionRequest(action_type="mock.execute_restart_worker", target="worker:staging", environment="staging")
    base = PolicyContext(
        capabilities=default_capabilities({"mock:workers:restart"}),
        service="worker",
        environment="staging",
        night_autopilot=True,
        confidence=0.91,
        simulation_passed=True,
        blast_radius_scope="service",
        rollback_available=True,
    )

    assert engine.evaluate(request, base).decision == PolicyDecision.ALLOW
    assert engine.evaluate(request, PolicyContext(**{**base.__dict__, "confidence": 0.5})).decision == PolicyDecision.ESCALATE
    assert engine.evaluate(request, PolicyContext(**{**base.__dict__, "simulation_passed": False})).decision == PolicyDecision.ESCALATE
    assert engine.evaluate(request, PolicyContext(**{**base.__dict__, "failed_memory_warning": True})).decision == PolicyDecision.ESCALATE
