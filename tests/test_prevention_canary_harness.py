from __future__ import annotations

import importlib
from typing import Any

import pytest

ZERO_AUTHORITY_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "production_adapter_calls": 0,
    "production_mutation": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "cloud_calls": 0,
    "db_mutation": 0,
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_canary_harness")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention canary harness module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _harness(api: Any) -> Any:
    cls = getattr(api, "PreventionCanaryHarness", None)
    if cls is None:
        pytest.fail("P107 RED: expose PreventionCanaryHarness.", pytrace=False)
    return cls()


def _execute(harness: Any, action: dict[str, Any]) -> Any:
    execute = getattr(harness, "execute", None)
    if execute is None:
        pytest.fail("P107 RED: PreventionCanaryHarness must expose execute(action).", pytrace=False)
    return execute(action)


def test_harness_executes_registered_local_mock_handler_deterministically() -> None:
    harness = _harness(_api())
    action = {
        "action_type": "mock.create_rollback_artifact",
        "capability_id": "preventive.mock.rollback_pr",
        "idempotency_key": "p107-harness-safe-1",
        "payload": {"service": "checkout-api", "environment": "staging"},
    }

    first = _execute(harness, action)
    second = _execute(harness, dict(action))

    assert _get(first, "status") == "applied"
    assert _get(first, "effect_hash") == _get(second, "effect_hash")
    assert _get(first, "authority_counters") == ZERO_AUTHORITY_COUNTERS


def test_harness_rejects_unknown_handler_fail_closed() -> None:
    harness = _harness(_api())

    result = _execute(
        harness,
        {
            "action_type": "mock.unknown_prevention_action",
            "capability_id": "unknown",
            "idempotency_key": "p107-harness-unknown",
            "payload": {},
        },
    )

    assert _get(result, "status") == "blocked_fail_closed"
    assert _get(result, "effect_applied") is False
    assert _get(result, "authority_counters") == ZERO_AUTHORITY_COUNTERS


@pytest.mark.parametrize(
    "action_type",
    [
        "shell.execute",
        "secret.read",
        "database.mutate",
        "cloud.delete_resource",
        "production.rollback",
        "external.adapter.invoke",
    ],
)
def test_harness_rejects_forbidden_action_markers_without_side_effect(action_type: str) -> None:
    harness = _harness(_api())

    result = _execute(
        harness,
        {
            "action_type": action_type,
            "capability_id": "preventive.mock.rollback_pr",
            "idempotency_key": f"p107-forbidden-{action_type}",
            "payload": {"service": "checkout-api"},
        },
    )

    assert _get(result, "status") == "blocked_fail_closed"
    assert _get(result, "effect_applied") is False
    assert _get(result, "authority_counters") == ZERO_AUTHORITY_COUNTERS


def test_harness_effect_lookup_is_idempotent_by_key() -> None:
    harness = _harness(_api())
    action = {
        "action_type": "mock.create_local_report",
        "capability_id": "preventive.mock.report",
        "idempotency_key": "p107-harness-idempotent",
        "payload": {"service": "checkout-api", "report": "canary"},
    }

    first = _execute(harness, action)
    second = _execute(harness, dict(action))

    assert _get(first, "attempt_id") == _get(second, "attempt_id")
    assert _get(first, "effect_hash") == _get(second, "effect_hash")
    assert _get(second, "duplicate_effect_count") == 0
