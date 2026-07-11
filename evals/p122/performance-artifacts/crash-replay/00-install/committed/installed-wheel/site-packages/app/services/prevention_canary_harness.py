"""Deterministic local/mock P107 prevention canary harness."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.services.prevention_authority_sentinel import (
    PreventionAuthoritySentinel,
)

REGISTERED_LOCAL_MOCK_HANDLERS = {
    "mock.create_rollback_artifact": "preventive.mock.rollback_pr",
    "mock.rollback_artifact": "preventive.mock.rollback_pr",
    "mock.create_local_report": "preventive.mock.report",
}

FORBIDDEN_ACTION_MARKERS = (
    "shell",
    "secret",
    "credential",
    "database",
    "db.",
    "cloud",
    "production",
    "external",
    "adapter",
    "network",
    "http",
)


@dataclass
class PreventionCanaryHarness:
    sentinel: PreventionAuthoritySentinel = field(default_factory=PreventionAuthoritySentinel)
    _effects_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)

    def execute(self, action: Mapping[str, Any]) -> dict[str, Any]:
        idempotency_key = str(action.get("idempotency_key", "")).strip()
        action_type = str(action.get("action_type", "")).strip()
        capability_id = str(action.get("capability_id", "")).strip()
        payload = _mapping(action.get("payload"))

        if not idempotency_key:
            return self._blocked(action_type, "missing_idempotency_key")

        existing = self._effects_by_key.get(idempotency_key)
        if existing is not None:
            replay = dict(existing)
            replay["receipt_type"] = "duplicate_replayed"
            replay["duplicate_effect_count"] = 0
            replay["authority_counters"] = self.sentinel.snapshot()
            return replay

        blocked_reason = self._blocked_reason(action_type, capability_id)
        if blocked_reason:
            result = self._blocked(action_type, blocked_reason)
            result["idempotency_key"] = idempotency_key
            return result

        effect_hash = _stable_hash(
            {
                "action_type": action_type,
                "capability_id": capability_id,
                "idempotency_key": idempotency_key,
                "payload": payload,
            }
        )
        attempt_id = f"p107-attempt-{effect_hash.removeprefix('sha256:')[:16]}"
        result = {
            "accepted": True,
            "status": "applied",
            "terminal_state": "succeeded",
            "attempt_id": attempt_id,
            "idempotency_key": idempotency_key,
            "action_type": action_type,
            "capability_id": capability_id,
            "effect_applied": True,
            "effect_hash": effect_hash,
            "effect_record": self._effect_record(action_type, payload, effect_hash),
            "duplicate_effect_count": 0,
            "authority_counters": self.sentinel.snapshot(),
        }
        self._effects_by_key[idempotency_key] = dict(result)
        return dict(result)

    def _blocked_reason(self, action_type: str, capability_id: str) -> str | None:
        lowered = action_type.lower()
        if any(marker in lowered for marker in FORBIDDEN_ACTION_MARKERS):
            return "forbidden_action_marker"
        expected_capability = REGISTERED_LOCAL_MOCK_HANDLERS.get(action_type)
        if expected_capability is None:
            return "unknown_local_mock_handler"
        if capability_id != expected_capability:
            return "capability_registry_mismatch"
        return None

    def _blocked(self, action_type: str, reason: str) -> dict[str, Any]:
        return {
            "accepted": False,
            "status": "blocked_fail_closed",
            "terminal_state": "blocked_fail_closed",
            "action_type": action_type,
            "blocked_reason": reason,
            "effect_applied": False,
            "duplicate_effect_count": 0,
            "authority_counters": self.sentinel.snapshot(),
        }

    def _effect_record(self, action_type: str, payload: Mapping[str, Any], effect_hash: str) -> dict[str, Any]:
        service = str(payload.get("service", "unknown"))
        if action_type in {"mock.create_rollback_artifact", "mock.rollback_artifact"}:
            return {
                "kind": "local_mock_rollback_artifact",
                "service": service,
                "artifact_hash": effect_hash,
                "external_pr_created": False,
                "rollback_executed": False,
            }
        return {
            "kind": "local_mock_report",
            "service": service,
            "report_hash": effect_hash,
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stable_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
