from __future__ import annotations

import importlib
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_policy_preflight")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention policy preflight module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _allowed_context() -> dict[str, Any]:
    return {
        "episode_id": "episode-policy-001",
        "candidate_hash": "sha256:candidate",
        "registry_hash": "sha256:registry-a",
        "expected_registry_hash": "sha256:registry-a",
        "cohort_fingerprint_hash": "sha256:cohort",
        "action_request": {
            "action_type": "mock.rollback_artifact",
            "target": "checkout-api",
            "environment": "local",
            "payload": {"service": "checkout-api"},
        },
        "policy_context": {
            "service": "checkout-api",
            "environment": "local",
            "severity": "medium",
            "confidence": 0.96,
            "evidence_count": 4,
            "blast_radius_scope": "local",
            "rollback_available": True,
            "simulation_passed": True,
            "simulation_status": "passed",
            "conflicting_signals": False,
            "known_ambiguity": False,
        },
    }


class RecordingAuditStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class HarnessSpy:
    def __init__(self) -> None:
        self.attempt_count = 0

    def invoke(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.attempt_count += 1
        return {"status": "applied"}


def test_immediate_policy_recheck_occurs_before_wal_intent() -> None:
    calls: list[str] = []
    audit = RecordingAuditStore()

    def safety_gate(case: dict[str, Any]) -> dict[str, Any]:
        calls.append("policy_recheck")
        assert case["registry_hash_parity"] is True
        return {"passed": True, "route": "observe", "reasons": [], "execution_enabled": False}

    result = _api().run_policy_preflight(
        _allowed_context(),
        evaluate_preventive_safety_gate=safety_gate,
        audit_store=audit,
        on_wal_intent=lambda _event: calls.append("wal_intent_appended"),
    )

    assert _get(result, "allowed") is True
    assert calls == ["policy_recheck", "wal_intent_appended"]
    assert _get(result, "policy_recheck_hash", "").startswith("sha256:")
    assert audit.events[-1]["state"] == "policy_rechecked"
    assert audit.events[-1]["policy_recheck_hash"] == _get(result, "policy_recheck_hash")


def test_policy_flip_at_preflight_blocks_attempt() -> None:
    audit = RecordingAuditStore()
    harness = HarnessSpy()

    def safety_gate(_case: dict[str, Any]) -> dict[str, Any]:
        return {"passed": False, "route": "blocked_fail_closed", "reasons": ["policy flipped"], "execution_enabled": False}

    result = _api().run_policy_preflight(
        _allowed_context(),
        evaluate_preventive_safety_gate=safety_gate,
        audit_store=audit,
        harness=harness,
    )

    assert _get(result, "allowed") is False
    assert _get(result, "terminal_state") == "blocked_fail_closed"
    assert _get(result, "policy_flip_executed_count") == 0
    assert not [event for event in audit.events if event.get("state") == "wal_intent_appended"]
    assert harness.attempt_count == 0


@pytest.mark.parametrize("registry_hash", ["sha256:registry-b", None])
def test_preflight_rejects_missing_or_changed_registry_hash(registry_hash: str | None) -> None:
    context = _allowed_context()
    context["registry_hash"] = registry_hash

    result = _api().run_policy_preflight(context, audit_store=RecordingAuditStore(), harness=HarnessSpy())

    assert _get(result, "allowed") is False
    assert _get(result, "terminal_state") == "blocked_fail_closed"
    assert "registry" in " ".join(_get(result, "reasons", []))


@pytest.mark.parametrize(
    "override",
    [
        {"confidence": 0.42},
        {"known_ambiguity": True},
        {"conflicting_signals": True},
        {"environment": "production"},
        {"rollback_available": False},
        {"simulation_passed": False, "simulation_status": "failed"},
    ],
)
def test_preflight_rejects_confidence_drop_ambiguity_conflict_or_prod_environment(override: dict[str, Any]) -> None:
    context = _allowed_context()
    context["policy_context"].update(override)
    if "environment" in override:
        context["action_request"]["environment"] = override["environment"]

    result = _api().run_policy_preflight(context, audit_store=RecordingAuditStore(), harness=HarnessSpy())

    assert _get(result, "allowed") is False
    assert _get(result, "terminal_state") == "blocked_fail_closed"
    assert _get(result, "attempt_allowed") is False
