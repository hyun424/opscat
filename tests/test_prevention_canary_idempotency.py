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


def _command(**overrides: Any) -> dict[str, Any]:
    command = {
        "episode_id": "episode-idem-001",
        "candidate_hash": "sha256:candidate-a",
        "registry_hash": "sha256:registry-a",
        "cohort_fingerprint_hash": "sha256:cohort-a",
        "telemetry_window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:05:00Z"},
        "requested_action": {"type": "mock.rollback_artifact", "target": "checkout-api"},
        "idempotency_key": "idem:episode-idem-001:candidate-a:cohort-a",
    }
    command.update(overrides)
    return command


class HarnessSpy:
    def __init__(self) -> None:
        self.effects: list[str] = []

    def invoke(self, command: dict[str, Any]) -> dict[str, Any]:
        self.effects.append(command["idempotency_key"])
        return {"status": "applied", "effect_id": f"effect-{len(self.effects)}"}


def test_duplicate_delivery_returns_original_attempt() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()
    command = _command()

    first = api.acquire_or_replay_attempt(store, command, harness=harness)
    second = api.acquire_or_replay_attempt(store, command, harness=harness)

    assert len(harness.effects) == 1
    assert _get(first, "attempt_id") == _get(second, "attempt_id")
    assert _get(first, "result") == _get(second, "result")
    assert _get(second, "receipt_type") == "duplicate_replayed"
    assert _get(second, "duplicate_attempt_count") == 0


def test_duplicate_with_different_payload_same_key_rejected() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()

    first = api.acquire_or_replay_attempt(store, _command(), harness=harness)
    conflict = api.acquire_or_replay_attempt(
        store,
        _command(candidate_hash="sha256:candidate-b"),
        harness=harness,
    )

    assert _get(first, "accepted") is True
    assert _get(conflict, "accepted") is False
    assert _get(conflict, "terminal_state") == "blocked_fail_closed"
    assert _get(conflict, "conflict_reason") == "idempotency_key_payload_mismatch"
    assert len(harness.effects) == 1
    assert _get(conflict, "duplicate_attempt_count") == 0
