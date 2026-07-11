"""Immediate P107 preventive policy preflight recheck."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from app.services.preventive_safety_gate import evaluate_preventive_safety_gate as _shared_safety_gate

SafetyGate = Callable[[dict[str, Any]], Any]


def run_policy_preflight(
    context: Mapping[str, Any],
    *,
    evaluate_preventive_safety_gate: SafetyGate | None = None,
    audit_store: Any | None = None,
    harness: Any | None = None,
    on_wal_intent: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    del harness
    reasons = _local_rejection_reasons(context)
    if reasons:
        return _blocked(reasons, audit_store=audit_store)

    gate_input = _gate_input(context)
    evaluator = evaluate_preventive_safety_gate or _shared_safety_gate
    gate_result = _to_mapping(evaluator(gate_input))
    policy_hash = _sha256(gate_result)
    _append(audit_store, {"state": "policy_rechecked", "policy_recheck_hash": policy_hash, "result": gate_result})

    if not bool(gate_result.get("passed")):
        reasons = [str(item) for item in gate_result.get("reasons", [])] or ["policy recheck failed"]
        return {
            "allowed": False,
            "attempt_allowed": False,
            "terminal_state": "blocked_fail_closed",
            "reasons": reasons,
            "policy_recheck_hash": policy_hash,
            "policy_flip_executed_count": 0,
        }

    if on_wal_intent is not None:
        on_wal_intent({"state": "wal_intent_appended", "policy_recheck_hash": policy_hash})

    return {
        "allowed": True,
        "attempt_allowed": True,
        "terminal_state": None,
        "reasons": [],
        "policy_recheck_hash": policy_hash,
        "policy_flip_executed_count": 0,
    }


def _gate_input(context: Mapping[str, Any]) -> dict[str, Any]:
    request = context.get("action_request")
    policy_context = context.get("policy_context")
    request_map = request if isinstance(request, Mapping) else {}
    policy_map = policy_context if isinstance(policy_context, Mapping) else {}
    return {
        "action_type": request_map.get("action_type"),
        "target": request_map.get("target"),
        "environment": request_map.get("environment", policy_map.get("environment")),
        "payload": request_map.get("payload", {}),
        "service": policy_map.get("service", request_map.get("target")),
        "severity": policy_map.get("severity", "medium"),
        "confidence": policy_map.get("confidence"),
        "evidence_count": policy_map.get("evidence_count", 0),
        "blast_radius_scope": policy_map.get("blast_radius_scope"),
        "rollback_available": policy_map.get("rollback_available"),
        "simulation_passed": policy_map.get("simulation_passed"),
        "simulation_status": policy_map.get("simulation_status"),
        "conflicting_signals": policy_map.get("conflicting_signals", False),
        "known_ambiguity": policy_map.get("known_ambiguity", False),
        "registry_hash_parity": context.get("registry_hash") == context.get("expected_registry_hash"),
    }


def _local_rejection_reasons(context: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    registry_hash = context.get("registry_hash")
    if not registry_hash or registry_hash != context.get("expected_registry_hash"):
        reasons.append("registry hash parity failed")

    request = context.get("action_request")
    policy_context = context.get("policy_context")
    request_map = request if isinstance(request, Mapping) else {}
    policy_map = policy_context if isinstance(policy_context, Mapping) else {}
    environment = str(request_map.get("environment", policy_map.get("environment", ""))).lower()
    if environment in {"prod", "production"}:
        reasons.append("production-like environment is not eligible")
    if _float(policy_map.get("confidence")) < 0.8:
        reasons.append("confidence dropped below threshold")
    if policy_map.get("known_ambiguity"):
        reasons.append("known ambiguity appeared")
    if policy_map.get("conflicting_signals"):
        reasons.append("conflicting evidence appeared")
    if policy_map.get("rollback_available") is not True:
        reasons.append("rollback unavailable")
    if policy_map.get("simulation_passed") is not True:
        reasons.append("simulation failed")
    return reasons


def _blocked(reasons: list[str], *, audit_store: Any | None) -> dict[str, Any]:
    event = {"state": "blocked_fail_closed", "reasons": reasons}
    _append(audit_store, event)
    return {
        "allowed": False,
        "attempt_allowed": False,
        "terminal_state": "blocked_fail_closed",
        "reasons": reasons,
        "policy_flip_executed_count": 0,
    }


def _append(audit_store: Any | None, event: dict[str, Any]) -> None:
    if audit_store is not None:
        audit_store.append(event)


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if is_dataclass(value):
        return asdict(cast(Any, value))
    return dict(value)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
