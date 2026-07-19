"""P176 fixed action eligibility map.

This module only returns supervised eligibility decisions. It never emits shell
commands, free-form parameters, or auto-approval.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "p176.action_eligibility.v1"

_ALLOWED_SERVICES = frozenset(
    {
        "web-gateway",
        "checkout-api",
        "catalog-api",
        "order-worker",
        "event-queue",
        "notification-worker",
        "postgres-db",
        "redis-cache",
    }
)
ELIGIBLE_ACTION_BY_FAMILY = {
    "p176-family-06-retry_storm": "restart_worker",
    "p176-family-11-connection_pool_exhaustion": "tune_pool",
    "p176-family-16-queue_backlog": "restart_worker",
    "p176-family-21-canary_error_regression": "rollback_canary",
}
ELIGIBLE_SERVICES_BY_FAMILY = {
    "p176-family-06-retry_storm": frozenset({"order-worker", "notification-worker"}),
    "p176-family-11-connection_pool_exhaustion": frozenset({"checkout-api", "catalog-api", "postgres-db"}),
    "p176-family-16-queue_backlog": frozenset({"order-worker", "event-queue", "notification-worker"}),
    "p176-family-21-canary_error_regression": frozenset({"web-gateway", "checkout-api", "catalog-api"}),
}
_REQUIRED_BY_ACTION = {
    "tune_pool": frozenset({"service", "pool_name", "max_connections"}),
    "restart_worker": frozenset({"service", "worker_pool"}),
    "rollback_canary": frozenset({"service", "deployment_id", "canary_id"}),
}
_FORBIDDEN_CONTEXT_KEYS = frozenset({"command", "commands", "cmd", "target", "targets", "params", "parameters", "shell", "sql", "script", "auto_approved", "auto_approve"})
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")


class P176ActionEligibilityError(ValueError):
    """Raised when an action eligibility request fails closed."""


def evaluate_action_eligibility(fault_family: str, context: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(fault_family, str) or not fault_family:
        raise P176ActionEligibilityError("invalid_fault_family")
    context_value = _context(context)
    action = ELIGIBLE_ACTION_BY_FAMILY.get(fault_family)
    if action is None:
        return _decision(
            fault_family=fault_family,
            eligible=False,
            action=None,
            bounded_target={},
            bounded_params={},
            reason="unsupported_fault_family",
        )

    _reject_forbidden_context(context_value)
    required = _REQUIRED_BY_ACTION[action]
    if not required.issubset(context_value):
        raise P176ActionEligibilityError("missing_required_context")
    service = _bounded_text(context_value["service"], "service")
    if service not in _ALLOWED_SERVICES:
        raise P176ActionEligibilityError("unsupported_service")
    if service not in ELIGIBLE_SERVICES_BY_FAMILY[fault_family]:
        raise P176ActionEligibilityError("service_not_affected_by_fault_family")

    if action == "tune_pool":
        pool_name = _bounded_text(context_value["pool_name"], "pool_name")
        max_connections = _bounded_int(context_value["max_connections"], "max_connections", minimum=1, maximum=256)
        _exact_context_keys(context_value, required)
        bounded_target = {"service": service, "pool_name": pool_name}
        bounded_params = {"max_connections": max_connections}
    elif action == "restart_worker":
        worker_pool = _bounded_text(context_value["worker_pool"], "worker_pool")
        _exact_context_keys(context_value, required)
        bounded_target = {"service": service, "worker_pool": worker_pool}
        bounded_params = {}
    else:
        deployment_id = _bounded_text(context_value["deployment_id"], "deployment_id")
        canary_id = _bounded_text(context_value["canary_id"], "canary_id")
        _exact_context_keys(context_value, required)
        bounded_target = {"service": service, "deployment_id": deployment_id, "canary_id": canary_id}
        bounded_params = {}

    return _decision(
        fault_family=fault_family,
        eligible=True,
        action=action,
        bounded_target=bounded_target,
        bounded_params=bounded_params,
        reason="fixed_action_requires_human_approval",
    )


def _decision(
    *,
    fault_family: str,
    eligible: bool,
    action: str | None,
    bounded_target: dict[str, Any],
    bounded_params: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "fault_family": fault_family,
        "eligible": eligible,
        "action": action,
        "bounded_target": bounded_target,
        "bounded_params": bounded_params,
        "route": "human_required",
        "auto_approved": False,
        "reason": reason,
    }


def _context(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P176ActionEligibilityError("invalid_context")
    return value


def _reject_forbidden_context(context: Mapping[str, Any]) -> None:
    if any(str(key).lower() in _FORBIDDEN_CONTEXT_KEYS for key in context):
        raise P176ActionEligibilityError("free_form_context_forbidden")


def _exact_context_keys(context: Mapping[str, Any], allowed: frozenset[str]) -> None:
    if set(context) != set(allowed):
        raise P176ActionEligibilityError("unexpected_context_key")


def _bounded_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise P176ActionEligibilityError(f"invalid_{field}")
    return value


def _bounded_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise P176ActionEligibilityError(f"invalid_{field}")
    return value


__all__ = [
    "SCHEMA_VERSION",
    "ELIGIBLE_ACTION_BY_FAMILY",
    "ELIGIBLE_SERVICES_BY_FAMILY",
    "P176ActionEligibilityError",
    "evaluate_action_eligibility",
]
