from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from app.services.p176_action_eligibility import (
    P176ActionEligibilityError,
    evaluate_action_eligibility,
)


def test_fixed_faults_map_to_bounded_human_required_actions_without_auto_approval() -> None:
    tune = evaluate_action_eligibility(
        "p176-family-11-connection_pool_exhaustion",
        {"service": "checkout-api", "pool_name": "primary", "max_connections": 80},
    )
    restart = evaluate_action_eligibility(
        "p176-family-06-retry_storm",
        {"service": "order-worker", "worker_pool": "default"},
    )
    rollback = evaluate_action_eligibility(
        "p176-family-21-canary_error_regression",
        {"service": "checkout-api", "deployment_id": "deploy-20260101", "canary_id": "canary-a"},
    )

    assert tune == {
        "schema_version": "p176.action_eligibility.v1",
        "fault_family": "p176-family-11-connection_pool_exhaustion",
        "eligible": True,
        "action": "tune_pool",
        "bounded_target": {"service": "checkout-api", "pool_name": "primary"},
        "bounded_params": {"max_connections": 80},
        "route": "human_required",
        "auto_approved": False,
        "reason": "fixed_action_requires_human_approval",
    }
    assert restart["action"] == "restart_worker"
    assert restart["bounded_target"] == {"service": "order-worker", "worker_pool": "default"}
    assert restart["bounded_params"] == {}
    assert rollback["action"] == "rollback_canary"
    assert rollback["bounded_target"] == {"service": "checkout-api", "deployment_id": "deploy-20260101", "canary_id": "canary-a"}
    assert rollback["bounded_params"] == {}
    assert all(decision["route"] == "human_required" and decision["auto_approved"] is False for decision in (tune, restart, rollback))


def test_unsupported_faults_are_never_action_eligible() -> None:
    decision = evaluate_action_eligibility("network_partition", {"service": "checkout-api"})

    assert decision == {
        "schema_version": "p176.action_eligibility.v1",
        "fault_family": "network_partition",
        "eligible": False,
        "action": None,
        "bounded_target": {},
        "bounded_params": {},
        "route": "human_required",
        "auto_approved": False,
        "reason": "unsupported_fault_family",
    }


def test_no_free_form_targets_params_or_commands_are_accepted() -> None:
    forbidden_contexts: list[Mapping[str, Any]] = [
        {"service": "checkout-api", "pool_name": "primary", "max_connections": 80, "command": "kubectl scale"},
        {"service": "checkout-api", "pool_name": "primary", "max_connections": 80, "target": "checkout-api.primary"},
        {"service": "checkout-api", "pool_name": "primary", "max_connections": 80, "sql": "alter system"},
        {"service": "checkout-api", "pool_name": "primary", "max_connections": 2000},
        {"service": "checkout-api", "pool_name": "primary", "max_connections": "80"},
        {"service": "checkout-api", "pool_name": "primary", "max_connections": 80, "auto_approved": True},
    ]
    for context in forbidden_contexts:
        with pytest.raises(P176ActionEligibilityError):
            evaluate_action_eligibility("p176-family-11-connection_pool_exhaustion", context)


def test_unknown_targets_and_missing_required_fields_fail_closed() -> None:
    with pytest.raises(P176ActionEligibilityError, match="unsupported_service"):
        evaluate_action_eligibility("p176-family-06-retry_storm", {"service": "prod-worker", "worker_pool": "default"})
    with pytest.raises(P176ActionEligibilityError, match="missing_required_context"):
        evaluate_action_eligibility(
            "p176-family-21-canary_error_regression",
            {"service": "checkout-api", "deployment_id": "deploy-20260101"},
        )

    with pytest.raises(P176ActionEligibilityError, match="service_not_affected"):
        evaluate_action_eligibility(
            "p176-family-06-retry_storm",
            {"service": "postgres-db", "worker_pool": "default"},
        )
    with pytest.raises(P176ActionEligibilityError, match="invalid_worker_pool"):
        evaluate_action_eligibility(
            "p176-family-06-retry_storm",
            {"service": "order-worker", "worker_pool": "default;rm"},
        )
