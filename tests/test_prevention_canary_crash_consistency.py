from __future__ import annotations

import importlib
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_durable_idempotency")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing durable idempotency module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _command() -> dict[str, Any]:
    return {
        "episode_id": "episode-crash-001",
        "candidate_hash": "sha256:candidate-a",
        "registry_hash": "sha256:registry-a",
        "cohort_fingerprint_hash": "sha256:cohort-a",
        "telemetry_window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:05:00Z"},
        "requested_action": {"type": "mock.rollback_artifact", "target": "checkout-api"},
        "idempotency_key": "idem:episode-crash-001:candidate-a:cohort-a",
    }


class HarnessSpy:
    def __init__(self) -> None:
        self.effects_by_key: dict[str, dict[str, Any]] = {}
        self.invoke_count = 0

    def invoke(self, command: dict[str, Any]) -> dict[str, Any]:
        self.invoke_count += 1
        effect = {"status": "applied", "effect_id": f"effect-{command['idempotency_key']}"}
        self.effects_by_key[command["idempotency_key"]] = effect
        return effect

    def existing_effect(self, idempotency_key: str) -> dict[str, Any] | None:
        return self.effects_by_key.get(idempotency_key)


def test_crash_before_attempt_intent_can_retry_without_duplicate() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()
    command = _command()

    api.simulate_crash(store, command, boundary="before_attempt_intent")
    recovered = api.recover_after_crash(store, command, harness=harness)

    assert _get(recovered, "resumed_from") == "policy_rechecked"
    assert _get(recovered, "accepted") is True
    assert harness.invoke_count == 1
    assert _get(recovered, "crash_resume_duplicate_count") == 0


def test_crash_after_intent_before_harness_continues_once() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()
    command = _command()

    api.simulate_crash(store, command, boundary="after_intent_before_harness")
    recovered = api.recover_after_crash(store, command, harness=harness)
    duplicate = api.recover_after_crash(store, command, harness=harness)

    assert _get(recovered, "resumed_from") == "wal_intent_appended"
    assert _get(duplicate, "receipt_type") == "duplicate_replayed"
    assert harness.invoke_count == 1
    assert _get(duplicate, "crash_resume_duplicate_count") == 0


def test_crash_after_harness_effect_before_result_append_does_not_duplicate_effect() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()
    command = _command()

    api.simulate_crash(store, command, boundary="after_harness_effect_before_result", harness=harness)
    assert harness.invoke_count == 1

    recovered = api.recover_after_crash(store, command, harness=harness)

    assert _get(recovered, "resumed_from") == "attempt_effect_observed"
    assert _get(recovered, "result_appended") is True
    assert harness.invoke_count == 1
    assert _get(recovered, "crash_resume_duplicate_count") == 0


@pytest.mark.parametrize("boundary", ["partial_record", "truncated_after_intent"])
def test_partial_or_truncated_audit_fails_closed_without_new_effect(boundary: str) -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()
    command = _command()

    api.simulate_crash(store, command, boundary=boundary)
    recovered = api.recover_after_crash(store, command, harness=harness)

    assert _get(recovered, "accepted") is False
    assert _get(recovered, "terminal_state") == "blocked_fail_closed"
    assert _get(recovered, "attempt_allowed") is False
    assert harness.invoke_count == 0
