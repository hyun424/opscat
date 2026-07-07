from __future__ import annotations

from app.models.action import ActionRequest
from app.services.policy_engine import PolicyContext, PolicyEngine, evaluate_policy


def test_policy_exposes_p6_route_model_for_auto_approval_human_and_blocked() -> None:
    engine = PolicyEngine()

    auto = engine.evaluate(ActionRequest(action_type="mock.get_error_context", target="payment-api"), PolicyContext())
    approval = engine.evaluate(ActionRequest(action_type="mock.create_rollback_pr", target="payment-api", environment="staging"), PolicyContext())
    blocked = evaluate_policy({"action_type": "arbitrary_shell", "environment": "production", "approved": True})
    human = engine.evaluate(ActionRequest(action_type="unknown.provider.action", target="payment-api"), PolicyContext())

    assert auto.route.value == "auto_execute"
    assert approval.route.value == "approval_required"
    assert blocked.route.value == "blocked"
    assert human.route.value == "human_required"
