"""P107 guardrail outcome evaluation, rollback, escalation, and repeat lockout."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

UNSAFE_GUARDRAIL_STATES = {"breached", "uncertain", "unknown", "failed", "missing"}
ROLLBACK_TERMINALS = {"rolled_back", "rollback_failed_escalated", "escalated"}


class RollbackHandler(Protocol):
    def rollback(self, attempt: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RollbackAttempt:
    attempt_id: str
    attempt_kind: str = "rollback"
    status: str = "pending"


@dataclass
class PreventionGuardrailRollback:
    rollback_handler: RollbackHandler | None = None
    _blocked_repeat_keys: set[str] = field(default_factory=set)

    def assess(self, attempt: Any, outcome: Mapping[str, Any]) -> dict[str, Any]:
        repeat_key = repeat_lock_key(attempt)
        if repeat_key in self._blocked_repeat_keys:
            return {
                "success_claimed": False,
                "terminal_state": "blocked_fail_closed",
                "effect_applied": False,
                "repeat_allowed": False,
                "repeat_after_rollback_execution_count": 0,
                "breach_without_rollback_or_escalation_count": 0,
                "non_improvement_success_claim_count": 0,
            }

        decision = evaluate_guardrail_outcome(outcome)
        if decision["safe_to_claim_success"]:
            return {
                "success_claimed": True,
                "terminal_state": "succeeded",
                "effect_applied": True,
                "repeat_allowed": True,
                "repeat_after_rollback_execution_count": 0,
                "breach_without_rollback_or_escalation_count": 0,
                "non_improvement_success_claim_count": 0,
            }

        rollback_result = self._rollback_or_escalate(attempt)
        terminal_state = str(rollback_result.get("terminal_state", rollback_result.get("status", "escalated")))
        if terminal_state not in ROLLBACK_TERMINALS:
            terminal_state = "escalated"
        self._blocked_repeat_keys.add(repeat_key)

        return {
            "success_claimed": False,
            "terminal_state": terminal_state,
            "effect_applied": True,
            "repeat_allowed": False,
            "rollback_attempt": {
                "attempt_id": f"rollback-{_value(attempt, 'attempt_id', 'unknown')}",
                "attempt_kind": "rollback",
                "status": str(rollback_result.get("status", terminal_state)),
            },
            "rollback_result": dict(rollback_result),
            "repeat_after_rollback_execution_count": 0,
            "breach_without_rollback_or_escalation_count": 0,
            "non_improvement_success_claim_count": 0,
        }

    def _rollback_or_escalate(self, attempt: Any) -> Mapping[str, Any]:
        if self.rollback_handler is None:
            return {"status": "escalated", "terminal_state": "escalated", "reason": "rollback_handler_missing"}
        result = self.rollback_handler.rollback(attempt)
        status = str(result.get("status", "failed"))
        if status == "rolled_back":
            return {"status": "rolled_back", "terminal_state": "rolled_back"}
        return {
            "status": status,
            "terminal_state": "rollback_failed_escalated",
            "reason": str(result.get("reason", "rollback_failed")),
        }


def evaluate_guardrail_outcome(outcome: Mapping[str, Any]) -> dict[str, Any]:
    telemetry_available = bool(outcome.get("telemetry_available", False))
    guardrail_status = str(outcome.get("guardrail_status", "missing")).lower()
    primary_metric_delta = outcome.get("primary_metric_delta")

    unsafe_reasons: list[str] = []
    if not telemetry_available:
        unsafe_reasons.append("telemetry_loss")
    if guardrail_status in UNSAFE_GUARDRAIL_STATES:
        unsafe_reasons.append(f"guardrail_{guardrail_status}")
    if primary_metric_delta is None:
        unsafe_reasons.append("missing_primary_metric_delta")
    elif float(primary_metric_delta) <= 0.0:
        unsafe_reasons.append("non_improvement")

    return {
        "safe_to_claim_success": not unsafe_reasons,
        "unsafe_reasons": unsafe_reasons,
        "requires_rollback_or_escalation": bool(unsafe_reasons),
    }


def repeat_lock_key(attempt: Any) -> str:
    material = {
        "episode_id": _value(attempt, "episode_id", ""),
        "capability_id": _value(attempt, "capability_id", ""),
        "cohort_hash": _value(attempt, "cohort_hash", _value(attempt, "cohort_fingerprint_hash", "")),
        "idempotency_key": _value(attempt, "idempotency_key", ""),
    }
    if not any(material.values()):
        material["attempt_id"] = _value(attempt, "attempt_id", "unknown")
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)
