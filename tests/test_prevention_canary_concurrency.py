from __future__ import annotations

import importlib
import threading
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
        "episode_id": "episode-concurrency-001",
        "candidate_hash": "sha256:candidate-a",
        "registry_hash": "sha256:registry-a",
        "cohort_fingerprint_hash": "sha256:cohort-a",
        "telemetry_window": {"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:05:00Z"},
        "requested_action": {"type": "mock.rollback_artifact", "target": "checkout-api"},
        "idempotency_key": "idem:episode-concurrency-001:candidate-a:cohort-a",
    }
    command.update(overrides)
    return command


class HarnessSpy:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.effects: list[str] = []

    def invoke(self, command: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.effects.append(command["idempotency_key"])
            return {"status": "applied", "effect_id": f"effect-{len(self.effects)}"}


def test_concurrent_duplicate_creates_one_attempt() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()
    command = _command()
    barrier = threading.Barrier(8)
    results: list[Any] = []

    def worker() -> None:
        barrier.wait(timeout=5)
        results.append(api.acquire_or_replay_attempt(store, command, harness=harness))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 8
    assert len(harness.effects) == 1
    assert {_get(result, "attempt_id") for result in results} == {_get(results[0], "attempt_id")}
    assert sum(1 for result in results if _get(result, "receipt_type") == "lock_winner") == 1
    assert all(_get(result, "concurrent_duplicate_action_count") == 0 for result in results)


def test_multi_writer_collision_uses_sequence_parent_hash_cas() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()
    expected_sequence = 1
    expected_parent_hash = store.current_head_hash()

    first = api.cas_append_attempt_intent(
        store,
        _command(idempotency_key="idem:collision-a"),
        expected_sequence=expected_sequence,
        expected_parent_hash=expected_parent_hash,
        harness=harness,
    )
    second = api.cas_append_attempt_intent(
        store,
        _command(idempotency_key="idem:collision-b"),
        expected_sequence=expected_sequence,
        expected_parent_hash=expected_parent_hash,
        harness=harness,
    )

    assert sorted([_get(first, "cas_winner"), _get(second, "cas_winner")]) == [False, True]
    assert sum(1 for result in (first, second) if _get(result, "effect_applied")) == 1
    assert len(harness.effects) == 1
    loser = second if _get(first, "cas_winner") else first
    assert _get(loser, "terminal_state") in {"blocked_fail_closed", "duplicate_or_conflict_recorded"}


def test_unique_idempotency_index_rejects_conflicting_payload() -> None:
    api = _api()
    store = api.InMemoryDurableIdempotencyStore()
    harness = HarnessSpy()

    accepted = api.acquire_or_replay_attempt(store, _command(), harness=harness)
    conflict = api.acquire_or_replay_attempt(
        store,
        _command(candidate_hash="sha256:different-candidate"),
        harness=harness,
    )

    assert _get(accepted, "accepted") is True
    assert _get(conflict, "accepted") is False
    assert _get(conflict, "conflict_reason") == "idempotency_key_payload_mismatch"
    assert len(harness.effects) == 1
