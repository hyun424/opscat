"""P107 adversarial canary fixture matrix evaluation.

This module is intentionally pure and local. It loads/scans committed fixture
content only and produces deterministic evidence for the P107 release lane.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CANONICAL_FIXTURE_PATH = Path("evals/prevention/p107_canary_cases.json")
SCHEMA_VERSION = "p107.canary_fixture_matrix.v1"
REQUIRED_FIXTURE_IDS = tuple(f"A{index:02d}" for index in range(1, 15))
REQUIRED_EVIDENCE_GATES = frozenset(
    {
        "p106_gate_recomputed",
        "cohort_fingerprints_equalized",
        "policy_preflight_passed",
        "local_mock_adapter_only",
        "primary_metric_window_met",
        "guardrail_window_met",
        "rollback_or_escalation_verified",
        "idempotency_replay_verified",
        "no_release_replay_as_recovery",
        "zero_authority_counters",
    }
)
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
REQUIRED_METRIC_GATES = {
    "duplicate_attempt_count": 0,
    "crash_resume_duplicate_count": 0,
    "concurrent_duplicate_action_count": 0,
    "stale_or_forged_executed_count": 0,
    "policy_flip_executed_count": 0,
    "cohort_escape_accepted_count": 0,
    "telemetry_loss_success_claim_count": 0,
    "breach_without_rollback_or_escalation_count": 0,
    "non_improvement_success_claim_count": 0,
    "rollback_success_rate": 1.0,
    "repeat_after_rollback_execution_count": 0,
    "deterministic_replay": True,
    "tamper_rejected": True,
    "reorder_rejected": True,
    "sequence_gap_rejected": True,
    "tail_truncation_rejected": True,
    "partial_record_rejected": True,
    "duplicate_parent_fork_rejected": True,
    "non_terminal_episode_rejected": True,
    "append_after_terminal_rejected": True,
    "impossible_transition_rejected": True,
    "expected_terminal_head_hash_matched": True,
    "recovery_replay_valid_prefix_resumable": True,
    "recovery_replay_duplicate_effect_count": 0,
    "release_replay_gate_rejects_non_terminal": True,
    "auth_enabled": False,
    "credential_read_count": 0,
    "production_adapter_call_count": 0,
    "production_mutation_count": 0,
    "shell_execution_count": 0,
    "network_call_count": 0,
    "cloud_mutation_count": 0,
    "database_mutation_count": 0,
    "static_authority_boundary_passed": True,
    "runtime_authority_sentinel_passed": True,
    "canonical_p106_gate_recomputed": True,
    "caller_supplied_p107_gate_eligible_used": False,
    "p106_unlocked": False,
}
ALLOWED_TERMINAL_STATES = {"succeeded", "rolled_back", "escalated", "blocked_fail_closed"}


def load_prevention_canary_fixture_matrix(path: str | Path = CANONICAL_FIXTURE_PATH) -> dict[str, Any]:
    fixture_path = Path(path)
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def evaluate_prevention_canary_fixture_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    fixtures = list(matrix.get("fixtures", [])) if isinstance(matrix.get("fixtures"), list) else []
    fixture_ids = [str(fixture.get("fixture_id", "")) for fixture in fixtures if isinstance(fixture, Mapping)]
    seen_ids = set(fixture_ids)
    missing_fixture_ids = [fixture_id for fixture_id in REQUIRED_FIXTURE_IDS if fixture_id not in seen_ids]
    unexpected_fixture_ids = [fixture_id for fixture_id in fixture_ids if fixture_id not in REQUIRED_FIXTURE_IDS]
    duplicate_fixture_ids = sorted({fixture_id for fixture_id in fixture_ids if fixture_ids.count(fixture_id) > 1})

    failed_gates_by_fixture: dict[str, list[str]] = {}
    replay_separation_failures: list[str] = []
    authority_counter_failures: dict[str, dict[str, Any]] = {}
    terminal_state_failures: dict[str, str] = {}
    command_failures: dict[str, list[str]] = {}

    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            continue
        fixture_id = str(fixture.get("fixture_id", ""))
        gates = fixture.get("evidence_gates")
        failed_gates = _failed_evidence_gates(gates)
        if failed_gates:
            failed_gates_by_fixture[fixture_id] = failed_gates

        if fixture.get("recovery_replay_hash") == fixture.get("release_replay_hash"):
            replay_separation_failures.append(fixture_id)

        nonzero_counters = _nonzero_authority_counters(fixture.get("authority_counters"))
        if nonzero_counters:
            authority_counter_failures[fixture_id] = nonzero_counters

        terminal_state = str(fixture.get("expected_terminal_state", ""))
        if terminal_state not in ALLOWED_TERMINAL_STATES:
            terminal_state_failures[fixture_id] = terminal_state

        command_errors = _command_errors(fixture)
        if command_errors:
            command_failures[fixture_id] = command_errors

    metric_gate_failures = _metric_gate_failures(matrix.get("metric_gates"))
    schema_valid = matrix.get("schema_version") == SCHEMA_VERSION
    exact_order = fixture_ids == list(REQUIRED_FIXTURE_IDS)
    accepted = (
        schema_valid
        and exact_order
        and not missing_fixture_ids
        and not unexpected_fixture_ids
        and not duplicate_fixture_ids
        and not failed_gates_by_fixture
        and not replay_separation_failures
        and not authority_counter_failures
        and not terminal_state_failures
        and not command_failures
        and not metric_gate_failures
    )

    return {
        "accepted": accepted,
        "schema_version": matrix.get("schema_version"),
        "fixture_ids": fixture_ids,
        "required_fixture_ids": list(REQUIRED_FIXTURE_IDS),
        "missing_fixture_ids": missing_fixture_ids,
        "unexpected_fixture_ids": unexpected_fixture_ids,
        "duplicate_fixture_ids": duplicate_fixture_ids,
        "failed_gates_by_fixture": failed_gates_by_fixture,
        "replay_separation_failures": replay_separation_failures,
        "authority_counter_failures": authority_counter_failures,
        "terminal_state_failures": terminal_state_failures,
        "command_failures": command_failures,
        "metric_gate_failures": metric_gate_failures,
        "required_evidence_gates": sorted(REQUIRED_EVIDENCE_GATES),
        "required_metric_gates": dict(REQUIRED_METRIC_GATES),
        "matrix_hash": stable_hash(matrix),
        "matrix_source_path": str(matrix.get("source_path") or CANONICAL_FIXTURE_PATH),
        "zero_authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
        "static_authority_boundary_passed": metric_gate_failures.get("static_authority_boundary_passed") is None,
        "runtime_authority_sentinel_passed": metric_gate_failures.get("runtime_authority_sentinel_passed") is None,
    }


def build_fixture_matrix_evidence(matrix: Mapping[str, Any]) -> dict[str, Any]:
    result = evaluate_prevention_canary_fixture_matrix(matrix)
    return {
        "schema_version": "p107.canary_evidence.v1",
        "fixture_path": str(result["matrix_source_path"]),
        "fixture_ids": result["fixture_ids"],
        "accepted": result["accepted"],
        "matrix_hash": result["matrix_hash"],
        "evidence_gates": {gate: gate not in _all_failed_gates(result["failed_gates_by_fixture"]) for gate in sorted(REQUIRED_EVIDENCE_GATES)},
        "metric_gates": {key: result["metric_gate_failures"].get(key) is None for key in REQUIRED_METRIC_GATES},
        "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
        "static_authority_boundary_passed": result["static_authority_boundary_passed"],
        "runtime_authority_sentinel_passed": result["runtime_authority_sentinel_passed"],
        "reasons": _reasons(result),
        "result": result,
    }


def stable_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _failed_evidence_gates(gates: Any) -> list[str]:
    if not isinstance(gates, Mapping):
        return sorted(REQUIRED_EVIDENCE_GATES)
    failed = [gate for gate in REQUIRED_EVIDENCE_GATES if gates.get(gate) is not True]
    extra = [str(gate) for gate in gates if gate not in REQUIRED_EVIDENCE_GATES]
    return sorted(failed + extra)


def _nonzero_authority_counters(counters: Any) -> dict[str, Any]:
    if not isinstance(counters, Mapping):
        return dict(ZERO_AUTHORITY_COUNTERS)
    failures: dict[str, Any] = {}
    for key, expected in ZERO_AUTHORITY_COUNTERS.items():
        if counters.get(key) != expected:
            failures[key] = counters.get(key)
    for key, value in counters.items():
        if key not in ZERO_AUTHORITY_COUNTERS:
            failures[str(key)] = value
    return failures


def _metric_gate_failures(metric_gates: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(metric_gates, Mapping):
        return {key: {"expected": expected, "actual": None} for key, expected in REQUIRED_METRIC_GATES.items()}
    failures = {}
    for key, expected in REQUIRED_METRIC_GATES.items():
        actual = metric_gates.get(key)
        if actual != expected:
            failures[key] = {"expected": expected, "actual": actual}
    return failures


def _command_errors(fixture: Mapping[str, Any]) -> list[str]:
    fixture_id = str(fixture.get("fixture_id", ""))
    command = fixture.get("command")
    errors: list[str] = []
    if not isinstance(command, Mapping):
        return ["missing_command"]
    if command.get("fixture_id") != fixture_id:
        errors.append("fixture_id_mismatch")
    if command.get("adapter") != "local_mock":
        errors.append("adapter_not_local_mock")
    return errors


def _all_failed_gates(failed_by_fixture: Mapping[str, list[str]]) -> set[str]:
    failed: set[str] = set()
    for gates in failed_by_fixture.values():
        failed.update(gates)
    return failed


def _reasons(result: Mapping[str, Any]) -> list[str]:
    reasons = []
    if not result.get("accepted"):
        for key in (
            "missing_fixture_ids",
            "unexpected_fixture_ids",
            "duplicate_fixture_ids",
            "failed_gates_by_fixture",
            "replay_separation_failures",
            "authority_counter_failures",
            "terminal_state_failures",
            "command_failures",
            "metric_gate_failures",
        ):
            value = result.get(key)
            if value:
                reasons.append(f"{key}:{value}")
    return reasons
