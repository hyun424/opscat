"""Fail-closed release evidence for the P131 always-on monitor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS

P131_RELEASE_SCHEMA_VERSION = "p131.release_evidence.v1"
P131_READY_STATUS = "p131_always_on_monitor_qualified"
P131_BLOCKED_STATUS = "p131_blocked"


class P131ReleaseEvidenceError(ValueError):
    """Raised when P131 release evidence is stale, malformed, or unsafe."""


def build_p131_release_evidence(runtime_report: Mapping[str, Any], watchdog_matrix: Mapping[str, Any]) -> dict[str, Any]:
    """Bind runtime and dead-man evidence to explicit promotion gates."""

    final_state = _mapping(runtime_report.get("final_state"))
    authority = _mapping(final_state.get("authority"))
    counters = _mapping(authority.get("counters"))
    totals = _mapping(final_state.get("totals"))
    canary = _mapping(final_state.get("canary"))
    stages = _mapping(canary.get("last_stages"))
    first_run = _mapping(runtime_report.get("first_run"))
    restart_run = _mapping(runtime_report.get("restart_run"))
    watchdog_cases = _mapping(watchdog_matrix.get("cases"))

    gates = {
        "scheduler_cadence_contract_observed": runtime_report.get("sleep_intervals_seconds") == [60.0],
        "real_time_bounded_scheduler_smoke": runtime_report.get("real_time_bounded_smoke_passed") is True,
        "restart_resumed_exactly_once": _exact_int(final_state.get("resume_count"), 1),
        "restart_no_loss_or_duplicate_acceptance": (
            _exact_int(first_run.get("accepted_observation_count"), 1)
            and _exact_int(restart_run.get("accepted_observation_count"), 1)
            and _exact_int(final_state.get("accepted_observation_count"), 2)
            and _exact_int(final_state.get("duplicate_observation_count"), 0)
        ),
        "heartbeat_current": _mapping(watchdog_cases.get("current")).get("healthy") is True,
        "missing_state_detected": _mapping(watchdog_cases.get("missing")).get("reason") == "state_missing",
        "stale_heartbeat_detected": _mapping(watchdog_cases.get("stale")).get("reason") == "heartbeat_stale",
        "tampered_state_detected": _mapping(watchdog_cases.get("tampered")).get("reason") == "state_hash_invalid",
        "synthetic_canary_contract_passed": (
            canary.get("last_result") == "passed"
            and type(canary.get("success_count")) is int
            and int(canary.get("success_count", 0)) > 0
            and _exact_int(canary.get("failure_count"), 0)
            and _exact_int(canary.get("action_execution_count"), 0)
            and stages.get("serialization_round_trip_passed") is True
            and stages.get("signal_detection_passed") is True
            and stages.get("policy_no_action_passed") is True
        ),
        "ready_with_fresh_source": final_state.get("ready") is True,
        "exact_zero_authority": (
            authority.get("exact_zero") is True
            and set(counters) == set(P121_AUTHORITY_COUNTER_KEYS)
            and all(type(counters.get(key)) is int and counters.get(key) == 0 for key in P121_AUTHORITY_COUNTER_KEYS)
        ),
        "zero_action_and_network_execution": _exact_int(totals.get("action_execution_count"), 0)
        and _exact_int(totals.get("network_call_count"), 0),
        "static_boundary_no_forbidden_capabilities": _mapping(runtime_report.get("static_boundary")).get("forbidden_matches") == [],
        "runtime_report_self_hash_current": runtime_report.get("runtime_report_hash")
        == stable_hash({key: value for key, value in runtime_report.items() if key != "runtime_report_hash"}),
        "watchdog_matrix_self_hash_current": watchdog_matrix.get("watchdog_matrix_hash")
        == stable_hash({key: value for key, value in watchdog_matrix.items() if key != "watchdog_matrix_hash"}),
    }
    passed = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P131_RELEASE_SCHEMA_VERSION,
        "release_id": "P131-always-on-monitor",
        "release_status": P131_READY_STATUS if passed else P131_BLOCKED_STATUS,
        "product_claim": "Credential-free local JSONL monitoring has a tested scheduler contract, restart-safe checkpoints, self-monitoring, and an independent watchdog.",
        "public_limitation": (
            "Local read-only telemetry only; no direct live connector, authentication, credentials, subprocess, remediation, staging mutation, "
            "production mutation, production autonomy, or operator replacement is claimed."
        ),
        "gates": gates,
        "runtime_report_hash": stable_hash(runtime_report),
        "watchdog_matrix_hash": stable_hash(watchdog_matrix),
        "authority": {"counters": dict(counters), "exact_zero": authority.get("exact_zero") is True},
        "reasons": [f"{name} failed closed" for name, value in gates.items() if not value],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p131_release_evidence(
    evidence: Mapping[str, Any],
    *,
    runtime_report: Mapping[str, Any],
    watchdog_matrix: Mapping[str, Any],
) -> None:
    """Reject non-current, blocked, or internally inconsistent evidence."""

    if evidence.get("schema_version") != P131_RELEASE_SCHEMA_VERSION:
        raise P131ReleaseEvidenceError("invalid_release_schema")
    claimed_hash = evidence.get("release_evidence_hash")
    unsigned = {key: value for key, value in evidence.items() if key != "release_evidence_hash"}
    if claimed_hash != stable_hash(unsigned):
        raise P131ReleaseEvidenceError("release_evidence_hash_invalid")
    gates = _mapping(evidence.get("gates"))
    if not gates or not all(value is True for value in gates.values()):
        raise P131ReleaseEvidenceError("release_gate_failed")
    if evidence.get("release_status") != P131_READY_STATUS:
        raise P131ReleaseEvidenceError("release_status_blocked")
    authority = _mapping(evidence.get("authority"))
    if authority.get("exact_zero") is not True:
        raise P131ReleaseEvidenceError("authority_not_exact_zero")
    counters = _mapping(authority.get("counters"))
    if set(counters) != set(P121_AUTHORITY_COUNTER_KEYS) or any(type(counters.get(key)) is not int or counters.get(key) != 0 for key in P121_AUTHORITY_COUNTER_KEYS):
        raise P131ReleaseEvidenceError("authority_not_exact_zero")
    if evidence.get("runtime_report_hash") != stable_hash(runtime_report):
        raise P131ReleaseEvidenceError("runtime_report_binding_invalid")
    if evidence.get("watchdog_matrix_hash") != stable_hash(watchdog_matrix):
        raise P131ReleaseEvidenceError("watchdog_matrix_binding_invalid")
    rebuilt = build_p131_release_evidence(runtime_report, watchdog_matrix)
    if dict(evidence) != rebuilt:
        raise P131ReleaseEvidenceError("release_evidence_semantic_mismatch")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected
