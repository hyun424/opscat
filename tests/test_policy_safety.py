"""Safety tests for OpsCat policy/risk behavior."""

from __future__ import annotations

import importlib
from typing import Any

import pytest


@pytest.fixture(scope="session")
def policy_module() -> Any:
    candidates = ["app.services.policy_engine", "app.policy_engine", "app.models.policy"]
    for name in candidates:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    pytest.skip("policy engine module is not implemented yet")


def _policy_decision(policy_module: Any, action: dict[str, Any]) -> str:
    if hasattr(policy_module, "evaluate_policy"):
        result = policy_module.evaluate_policy(action)
    elif hasattr(policy_module, "PolicyEngine"):
        result = policy_module.PolicyEngine().evaluate(action)
    else:
        pytest.skip("policy module does not expose evaluate_policy or PolicyEngine.evaluate yet")

    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return str(result.get("decision"))
    decision = getattr(result, "decision", result)
    return getattr(decision, "value", str(decision))


@pytest.mark.parametrize(
    "action_type,payload",
    [
        ("production_rollback", {"environment": "production", "service": "payment-api"}),
        ("database_mutation", {"sql": "DELETE FROM payments"}),
        ("arbitrary_shell", {"command": "rm -rf /"}),
        ("cloud_delete", {"resource": "prod-db"}),
        ("secret_access", {"secret_name": "STRIPE_KEY"}),
    ],
)
def test_dangerous_actions_are_denied_by_default(
    policy_module: Any,
    action_type: str,
    payload: dict[str, Any],
) -> None:
    decision = _policy_decision(
        policy_module,
        {
            "action_type": action_type,
            "risk_level": "high",
            "environment": payload.get("environment", "production"),
            "payload": payload,
            "approved": False,
        },
    )
    assert decision == "DENY"


def test_mock_rollback_pr_requires_approval(policy_module: Any) -> None:
    decision = _policy_decision(
        policy_module,
        {
            "action_type": "mock.create_rollback_pr",
            "risk_level": "medium",
            "environment": "production",
            "payload": {"service": "payment-api", "candidate_deploy": "deploy-42"},
            "approved": False,
        },
    )
    assert decision == "REQUIRE_APPROVAL"


def test_read_only_context_tools_are_allowed(policy_module: Any) -> None:
    decision = _policy_decision(
        policy_module,
        {
            "action_type": "mock.get_error_context",
            "risk_level": "read_only",
            "environment": "production",
            "payload": {"scenario": "payment_bad_deploy"},
            "approved": False,
        },
    )
    assert decision == "ALLOW"
