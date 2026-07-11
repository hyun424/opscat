"""In-memory P107 durable idempotency and CAS semantics for local tests."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from typing import Any


class InMemoryDurableIdempotencyStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: list[dict[str, Any]] = []
        self._attempts_by_key: dict[str, dict[str, Any]] = {}
        self._invalid_replay = False
        self._partial_or_truncated = False

    def current_head_hash(self) -> str:
        with self._lock:
            if not self._records:
                return "sha256:genesis"
            return str(self._records[-1]["record_hash"])

    def next_sequence(self) -> int:
        with self._lock:
            return len(self._records) + 1

    def cas_append(self, record: Mapping[str, Any], *, expected_sequence: int, expected_parent_hash: str) -> dict[str, Any]:
        with self._lock:
            if self._partial_or_truncated or self._invalid_replay:
                return {"cas_winner": False, "terminal_state": "blocked_fail_closed", "reason": "audit_replay_invalid"}
            if expected_sequence != self.next_sequence() or expected_parent_hash != self.current_head_hash():
                return {"cas_winner": False, "terminal_state": "duplicate_or_conflict_recorded"}
            appended = dict(record)
            appended["sequence"] = expected_sequence
            appended["parent_hash"] = expected_parent_hash
            appended["record_hash"] = _hash(appended)
            self._records.append(appended)
            return {"cas_winner": True, "record": appended}

    def mark_invalid_replay(self) -> None:
        with self._lock:
            self._invalid_replay = True

    def mark_partial_or_truncated(self) -> None:
        with self._lock:
            self._partial_or_truncated = True


def acquire_or_replay_attempt(store: InMemoryDurableIdempotencyStore, command: Mapping[str, Any], *, harness: Any) -> dict[str, Any]:
    key = str(command["idempotency_key"])
    signature = _payload_signature(command)
    with store._lock:
        if store._partial_or_truncated or store._invalid_replay:
            return _blocked("audit_replay_invalid")
        existing = store._attempts_by_key.get(key)
        if existing is not None:
            if existing["payload_signature"] != signature:
                return _conflict()
            return _duplicate(existing)

        attempt_id = f"attempt-{len(store._attempts_by_key) + 1}"
        expected_sequence = store.next_sequence()
        expected_parent_hash = store.current_head_hash()
        cas = store.cas_append(
            {
                "state": "wal_intent_appended",
                "idempotency_key": key,
                "attempt_id": attempt_id,
                "payload_signature": signature,
            },
            expected_sequence=expected_sequence,
            expected_parent_hash=expected_parent_hash,
        )
        if not cas.get("cas_winner"):
            return {"accepted": False, "cas_winner": False, "effect_applied": False, "terminal_state": cas["terminal_state"]}

        result = harness.invoke(dict(command))
        result_record = {
            "state": "result_appended",
            "idempotency_key": key,
            "attempt_id": attempt_id,
            "result": result,
            "payload_signature": signature,
            "effect_observed": True,
        }
        store.cas_append(result_record, expected_sequence=store.next_sequence(), expected_parent_hash=store.current_head_hash())
        attempt = {
            "accepted": True,
            "attempt_id": attempt_id,
            "idempotency_key": key,
            "payload_signature": signature,
            "result": result,
            "receipt_type": "lock_winner",
            "terminal_state": "succeeded",
        }
        store._attempts_by_key[key] = attempt
        return _with_zero_counters(attempt)


def cas_append_attempt_intent(
    store: InMemoryDurableIdempotencyStore,
    command: Mapping[str, Any],
    *,
    expected_sequence: int,
    expected_parent_hash: str,
    harness: Any,
) -> dict[str, Any]:
    key = str(command["idempotency_key"])
    signature = _payload_signature(command)
    with store._lock:
        existing = store._attempts_by_key.get(key)
        if existing is not None:
            if existing["payload_signature"] != signature:
                return _conflict() | {"cas_winner": False, "effect_applied": False}
            return _duplicate(existing) | {"cas_winner": False, "effect_applied": False}

        attempt_id = f"attempt-{len(store._attempts_by_key) + 1}"
        cas = store.cas_append(
            {
                "state": "wal_intent_appended",
                "idempotency_key": key,
                "attempt_id": attempt_id,
                "payload_signature": signature,
            },
            expected_sequence=expected_sequence,
            expected_parent_hash=expected_parent_hash,
        )
        if not cas.get("cas_winner"):
            return {"accepted": False, "cas_winner": False, "effect_applied": False, "terminal_state": cas["terminal_state"]}

        result = harness.invoke(dict(command))
        store.cas_append(
            {
                "state": "result_appended",
                "idempotency_key": key,
                "attempt_id": attempt_id,
                "payload_signature": signature,
                "result": result,
            },
            expected_sequence=store.next_sequence(),
            expected_parent_hash=store.current_head_hash(),
        )
        attempt = {
            "accepted": True,
            "attempt_id": attempt_id,
            "idempotency_key": key,
            "payload_signature": signature,
            "result": result,
            "receipt_type": "lock_winner",
            "terminal_state": "succeeded",
        }
        store._attempts_by_key[key] = attempt
        return _with_zero_counters(attempt | {"cas_winner": True, "effect_applied": True})


def simulate_crash(
    store: InMemoryDurableIdempotencyStore,
    command: Mapping[str, Any],
    *,
    boundary: str,
    harness: Any | None = None,
) -> None:
    key = str(command["idempotency_key"])
    signature = _payload_signature(command)
    with store._lock:
        if boundary == "before_attempt_intent":
            return
        if boundary in {"partial_record", "truncated_after_intent"}:
            store.mark_partial_or_truncated()
            return

        attempt_id = f"attempt-{len(store._attempts_by_key) + 1}"
        store.cas_append(
            {
                "state": "wal_intent_appended",
                "idempotency_key": key,
                "attempt_id": attempt_id,
                "payload_signature": signature,
            },
            expected_sequence=store.next_sequence(),
            expected_parent_hash=store.current_head_hash(),
        )
        pending = {
            "accepted": True,
            "attempt_id": attempt_id,
            "idempotency_key": key,
            "payload_signature": signature,
            "receipt_type": "in_progress",
            "terminal_state": None,
        }
        store._attempts_by_key[key] = pending
        if boundary == "after_harness_effect_before_result":
            if harness is None:
                raise ValueError("harness is required for after_harness_effect_before_result")
            harness.invoke(dict(command))
            pending["effect_observed_without_result"] = True
            store.cas_append(
                {
                    "state": "attempt_effect_observed",
                    "idempotency_key": key,
                    "attempt_id": attempt_id,
                    "payload_signature": signature,
                },
                expected_sequence=store.next_sequence(),
                expected_parent_hash=store.current_head_hash(),
            )


def recover_after_crash(store: InMemoryDurableIdempotencyStore, command: Mapping[str, Any], *, harness: Any) -> dict[str, Any]:
    key = str(command["idempotency_key"])
    with store._lock:
        if store._partial_or_truncated or store._invalid_replay:
            return _blocked("audit_replay_invalid")
        existing = store._attempts_by_key.get(key)
        if existing is None:
            result = acquire_or_replay_attempt(store, command, harness=harness)
            result["resumed_from"] = "policy_rechecked"
            return result
        if existing.get("result") is not None:
            return _duplicate(existing)
        existing_effect = harness.existing_effect(key) if hasattr(harness, "existing_effect") else None
        if existing_effect is not None:
            result = existing_effect
            resumed_from = "attempt_effect_observed"
        else:
            result = harness.invoke(dict(command))
            resumed_from = "wal_intent_appended"
        store.cas_append(
            {
                "state": "result_appended",
                "idempotency_key": key,
                "attempt_id": existing["attempt_id"],
                "payload_signature": existing["payload_signature"],
                "result": result,
            },
            expected_sequence=store.next_sequence(),
            expected_parent_hash=store.current_head_hash(),
        )
        existing.update({"result": result, "receipt_type": "lock_winner", "terminal_state": "succeeded"})
        return _with_zero_counters(existing | {"resumed_from": resumed_from, "result_appended": True})


def _duplicate(existing: Mapping[str, Any]) -> dict[str, Any]:
    return _with_zero_counters(
        {
            "accepted": True,
            "attempt_id": existing["attempt_id"],
            "idempotency_key": existing["idempotency_key"],
            "result": existing.get("result"),
            "receipt_type": "duplicate_replayed",
            "terminal_state": existing.get("terminal_state"),
        }
    )


def _conflict() -> dict[str, Any]:
    return _with_zero_counters(
        {
            "accepted": False,
            "attempt_allowed": False,
            "terminal_state": "blocked_fail_closed",
            "conflict_reason": "idempotency_key_payload_mismatch",
        }
    )


def _blocked(reason: str) -> dict[str, Any]:
    return _with_zero_counters(
        {
            "accepted": False,
            "attempt_allowed": False,
            "terminal_state": "blocked_fail_closed",
            "conflict_reason": reason,
        }
    )


def _with_zero_counters(result: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(result)
    enriched.setdefault("duplicate_attempt_count", 0)
    enriched.setdefault("crash_resume_duplicate_count", 0)
    enriched.setdefault("concurrent_duplicate_action_count", 0)
    return enriched


def _payload_signature(command: Mapping[str, Any]) -> str:
    payload = {
        "episode_id": command.get("episode_id"),
        "candidate_hash": command.get("candidate_hash"),
        "registry_hash": command.get("registry_hash"),
        "cohort_fingerprint_hash": command.get("cohort_fingerprint_hash"),
        "telemetry_window": command.get("telemetry_window"),
        "requested_action": command.get("requested_action"),
    }
    return _hash(payload)


def _hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
