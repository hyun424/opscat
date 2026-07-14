"""Deterministic exact-30-case runner for P138 release qualification."""

from __future__ import annotations

import resource
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p138_observation_triage_supervisor import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RUNTIME_ACTIVITY_KEYS,
)

RELEASE_RESOURCE_USAGE_KEYS = (
    "wall_time_ms",
    "cpu_time_ms",
    "child_cpu_time_ms",
    "peak_memory_bytes",
    "wall_limit_ms",
    "cpu_limit_ms",
    "peak_memory_limit_bytes",
)
PRELIMINARY_MATRIX_SCHEMA_VERSION = "p138.canonical_matrix.v1"
CASE_RUNTIME_SCHEMA_VERSION = "p138.case_runtime.v1"
CASE_INPUT_SCHEMA_VERSION = "p138.case_input_binding.v1"
PRELIMINARY_STATUS = "p138_preliminary_matrix_frozen"
REQUIRED_CASE_COUNT = 30

REAL_BOUNDARY_CASE_IDS = frozenset(
    {
        "P138-CASE-02",
        "P138-CASE-03",
        "P138-CASE-07",
        "P138-CASE-09",
        "P138-CASE-10",
        "P138-CASE-16",
        "P138-CASE-18",
        "P138-CASE-21",
        "P138-CASE-22",
        "P138-CASE-23",
        "P138-CASE-24",
        "P138-CASE-25",
        "P138-CASE-29",
        "P138-CASE-30",
    }
)

P136_OBSERVER_BOUNDARY = "p136.observe_one_cycle"
P136_RECOVERY_BOUNDARY = "p136.recover_cycle_outcome"
PUBLISHER_BOUNDARY = "p136.publish_p136_handoff_bundle"
P137_RUNTIME_BOUNDARY = "p137.run_p137_runtime_once"
P138_ONCE_BOUNDARY = "p138.run_p138_supervisor_once"
P138_LOOP_BOUNDARY = "p138.run_p138_supervisor_loop"

RuntimeFactory = Callable[[str], Mapping[str, Any]]


class P138RunnerError(ValueError):
    """Raised when a case execution cannot prove the frozen P138 denominator."""


def _expected(
    status: str,
    *,
    error: str = "none",
    stop_reason: str = "none",
    phase_path: Sequence[str] = (),
    component_boundaries: Sequence[str] = (),
    durable_post_state: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "error": error,
        "stop_reason": stop_reason,
        "phase_path": list(phase_path),
        "component_boundaries": list(component_boundaries),
        "durable_post_state": durable_post_state,
    }


_FULL_PHASE_PATH = (
    "cycle_started",
    "p136_completed",
    "handoff_selected",
    "handoff_published",
    "p137_accepted",
    "cycle_finalized",
)
_EMPTY_PHASE_PATH = ("cycle_started", "p136_completed", "cycle_finalized")


def _row(case_id: str, scenario: str, expected: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "scenario": scenario,
        "expected": deepcopy(dict(expected)),
        "real_boundary_required": case_id in REAL_BOUNDARY_CASE_IDS,
    }


_ROWS = (
    _row(
        "P138-CASE-01",
        "bootstrap",
        _expected(
            "ok",
            phase_path=("cycle_finalized",),
            component_boundaries=(P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="genesis_reconciled_without_new_publication",
        ),
    ),
    _row(
        "P138-CASE-02",
        "new_promotion",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(
                P136_OBSERVER_BOUNDARY,
                PUBLISHER_BOUNDARY,
                P137_RUNTIME_BOUNDARY,
                P138_ONCE_BOUNDARY,
            ),
            durable_post_state="new_contiguous_delta_published_accepted_finalized",
        ),
    ),
    _row(
        "P138-CASE-03",
        "zero_promotion",
        _expected(
            "ok",
            phase_path=_EMPTY_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="no_work_finalized_without_publication_or_triage",
        ),
    ),
    _row(
        "P138-CASE-04",
        "crash_cycle_started",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_RECOVERY_BOUNDARY, P136_OBSERVER_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="same_cycle_recovered_after_cycle_started",
        ),
    ),
    _row(
        "P138-CASE-05",
        "crash_p136_completed",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, P136_RECOVERY_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="stored_delta_published_once_after_p136_completed",
        ),
    ),
    _row(
        "P138-CASE-06",
        "crash_handoff_selected",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, P136_RECOVERY_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="selected_handoff_published_once_on_recovery",
        ),
    ),
    _row(
        "P138-CASE-07",
        "publisher_intent_crash",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, PUBLISHER_BOUNDARY, P136_RECOVERY_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="publisher_intent_recovered_same_sequence_once",
        ),
    ),
    _row(
        "P138-CASE-08",
        "crash_handoff_published",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="published_bytes_consumed_without_republication",
        ),
    ),
    _row(
        "P138-CASE-09",
        "p137_commit_before_p138_finalize",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="p137_membership_validated_without_replay_label",
        ),
    ),
    _row(
        "P138-CASE-10",
        "p137_lease_conflict_restart",
        _expected(
            "ok",
            error="p137:lease_conflict_then_recovered",
            phase_path=("cycle_finalized",),
            component_boundaries=(P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="sequence_retained_then_accepted_before_successor",
        ),
    ),
    _row(
        "P138-CASE-11",
        "same_sequence_fork",
        _expected(
            "failed_closed",
            error="same_sequence_bundle_fork",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="prior_p138_ledger_preserved",
        ),
    ),
    _row(
        "P138-CASE-12",
        "sequence_gap_previous_hash_break",
        _expected(
            "failed_closed",
            error="sequence_gap_or_previous_hash_break",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="no_observation_publication_or_ledger_advance",
        ),
    ),
    _row(
        "P138-CASE-13",
        "publisher_state_fixed_mismatch",
        _expected(
            "failed_closed",
            error="publisher_state_fixed_mismatch",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="component_bytes_preserved_without_calls",
        ),
    ),
    _row(
        "P138-CASE-14",
        "p138_lease_contention",
        _expected(
            "failed_closed",
            error="supervisor_lease_unavailable",
            stop_reason="lease_conflict",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="zero_component_calls_and_zero_state_writes",
        ),
    ),
    _row(
        "P138-CASE-15",
        "p136_lease_contention",
        _expected(
            "failed_closed",
            error="p136:exclusive_lease_unavailable",
            phase_path=("cycle_started",),
            component_boundaries=(P136_OBSERVER_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="no_publisher_p137_or_p138_final_advance",
        ),
    ),
    _row(
        "P138-CASE-16",
        "publisher_lease_contention",
        _expected(
            "failed_closed",
            error="publisher:publisher_lease_unavailable",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="no_sequence_p137_or_p138_final_advance",
        ),
    ),
    _row(
        "P138-CASE-17",
        "stale_p137_readiness_version",
        _expected(
            "failed_closed",
            error="p137_stale_readiness_or_version",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="current_bundle_retained",
        ),
    ),
    _row(
        "P138-CASE-18",
        "later_delta_only",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="only_later_promotion_delta_published_and_classified",
        ),
    ),
    _row(
        "P138-CASE-19",
        "signals",
        _expected(
            "stopped",
            error="signal_at_safe_boundary",
            stop_reason="sigterm",
            component_boundaries=(P138_LOOP_BOUNDARY,),
            durable_post_state="hash_bound_termination_at_safe_boundary",
        ),
    ),
    _row(
        "P138-CASE-20",
        "forbidden_secret_path_resource_guard",
        _expected(
            "failed_closed",
            error="guard_blocked_before_runtime_authority",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="no_forbidden_authority_or_sensitive_output",
        ),
    ),
    _row(
        "P138-CASE-21",
        "p136_checkpoint_promotions_before_p138_phase",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, P136_RECOVERY_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="promotion_completion_recovered_without_extra_receipt",
        ),
    ),
    _row(
        "P138-CASE-22",
        "p136_checkpoint_empty_before_p138_phase",
        _expected(
            "ok",
            phase_path=_EMPTY_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, P136_RECOVERY_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="empty_completion_recovered_without_extra_receipt_or_publish",
        ),
    ),
    _row(
        "P138-CASE-23",
        "publisher_crash_after_fixed",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, PUBLISHER_BOUNDARY, P136_RECOVERY_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="fixed_split_commit_recovered_same_sequence_once",
        ),
    ),
    _row(
        "P138-CASE-24",
        "publisher_crash_after_state",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, PUBLISHER_BOUNDARY, P136_RECOVERY_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="state_split_commit_recovered_and_stale_intent_removed",
        ),
    ),
    _row(
        "P138-CASE-25",
        "partial_non_genesis_bootstrap_reject",
        _expected(
            "failed_closed",
            error="partial_and_non_genesis_bootstrap_rejected",
            component_boundaries=(P138_ONCE_BOUNDARY,),
            durable_post_state="both_bootstrap_variants_rejected_before_new_observation",
        ),
    ),
    _row(
        "P138-CASE-26",
        "receipt_exhaustion_failure_threshold",
        _expected(
            "stopped",
            error="receipt_exhausted_and_failure_threshold",
            stop_reason="distinct_stop_labels",
            component_boundaries=(P136_RECOVERY_BOUNDARY, P138_LOOP_BOUNDARY),
            durable_post_state="no_publication_after_either_stop",
        ),
    ),
    _row(
        "P138-CASE-27",
        "max_cycle_heartbeat_cadence",
        _expected(
            "stopped",
            stop_reason="max_cycles_reached",
            component_boundaries=(P136_OBSERVER_BOUNDARY, P138_LOOP_BOUNDARY),
            durable_post_state="exact_cycle_heartbeat_and_readiness_cadence",
        ),
    ),
    _row(
        "P138-CASE-28",
        "stale_readiness_deadman_safe_signal",
        _expected(
            "stopped",
            error="stale_readiness_deadman_and_safe_signal",
            stop_reason="pre_component_safe_stop",
            component_boundaries=(P138_LOOP_BOUNDARY,),
            durable_post_state="termination_bound_to_last_valid_ledger",
        ),
    ),
    _row(
        "P138-CASE-29",
        "promotion_outcome_intent_before_checkpoint",
        _expected(
            "ok",
            phase_path=_FULL_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, P136_RECOVERY_BOUNDARY, PUBLISHER_BOUNDARY, P137_RUNTIME_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="promotion_outcome_intent_installed_checkpoint_and_published_once",
        ),
    ),
    _row(
        "P138-CASE-30",
        "empty_outcome_intent_before_checkpoint",
        _expected(
            "ok",
            phase_path=_EMPTY_PHASE_PATH,
            component_boundaries=(P136_OBSERVER_BOUNDARY, P136_RECOVERY_BOUNDARY, P138_ONCE_BOUNDARY),
            durable_post_state="empty_outcome_intent_installed_checkpoint_without_publish",
        ),
    ),
)


def p138_release_case_matrix() -> list[dict[str, Any]]:
    """Return a defensive copy of the immutable P138 release denominator."""

    return deepcopy(list(_ROWS))


def run_p138_preliminary_matrix(
    output_dir: Path,
    *,
    runtime_factory: RuntimeFactory,
    evaluator_overhead_activity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute and freeze all 30 cases; no final review is consumed here."""

    rows = p138_release_case_matrix()
    expected_ids = [f"P138-CASE-{index:02d}" for index in range(1, 31)]
    if [row["case_id"] for row in rows] != expected_ids:
        raise P138RunnerError("case_denominator_drift")
    cases: list[dict[str, Any]] = []
    case_inputs: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row["case_id"])
        runtime = _validated_runtime(runtime_factory(case_id), case_id=case_id)
        case_input = _case_input_binding(runtime)
        case_inputs.append(case_input)
        cases.append(_execute_case(row, runtime, output_dir=output_dir))
    if any(case["status"] != "passed" for case in cases):
        failed = [case["case_id"] for case in cases if case["status"] != "passed"]
        raise P138RunnerError(f"release_case_failed:{','.join(failed)}")

    forbidden = _aggregate_counter(cases, "forbidden_authority", FORBIDDEN_AUTHORITY_KEYS)
    expected_forbidden = _aggregate_counter(cases, "expected_forbidden_authority", FORBIDDEN_AUTHORITY_KEYS)
    runtime_activity = _aggregate_counter(cases, "runtime_activity", RUNTIME_ACTIVITY_KEYS)
    expected_runtime = _aggregate_counter(cases, "expected_runtime_activity", RUNTIME_ACTIVITY_KEYS)
    evaluator_cases = _aggregate_counter(cases, "evaluator_activity", EVALUATOR_ACTIVITY_KEYS)
    expected_evaluator_cases = _aggregate_counter(cases, "expected_evaluator_activity", EVALUATOR_ACTIVITY_KEYS)
    overhead = _exact_counter_map(
        evaluator_overhead_activity or _zero(EVALUATOR_ACTIVITY_KEYS),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_evaluator_overhead_activity",
    )
    evaluator_activity = _sum_maps(evaluator_cases, overhead)
    expected_evaluator = _sum_maps(expected_evaluator_cases, overhead)
    resource_usage = _aggregate_resources(cases, "resource_usage")
    expected_resource_usage = _resource_budget()
    matrix: dict[str, Any] = {
        "schema_version": PRELIMINARY_MATRIX_SCHEMA_VERSION,
        "status": PRELIMINARY_STATUS,
        "cases": cases,
        "case_inputs": case_inputs,
        "totals": {"expected": REQUIRED_CASE_COUNT, "passed": REQUIRED_CASE_COUNT, "failed": 0},
        "forbidden_authority": forbidden,
        "expected_forbidden_authority": expected_forbidden,
        "runtime_activity": runtime_activity,
        "expected_runtime_activity": expected_runtime,
        "evaluator_activity": evaluator_activity,
        "expected_evaluator_activity": expected_evaluator,
        "evaluator_overhead_activity": overhead,
        "expected_evaluator_overhead_activity": deepcopy(overhead),
        "resource_usage": resource_usage,
        "expected_resource_usage": expected_resource_usage,
        "matrix_hash": stable_hash(cases),
        "case_input_hash": stable_hash(case_inputs),
        "case_config_hash": stable_hash(
            [
                {
                    "case_id": item["case_id"],
                    "input_profile_hash": stable_hash(item["bindings"]["input_profile"]),
                }
                for item in case_inputs
            ]
        ),
        "case_evidence_hash": stable_hash([case["case_evidence_hash"] for case in cases]),
    }
    return matrix


def _validated_runtime(value: Mapping[str, Any], *, case_id: str) -> dict[str, Any]:
    runtime = _mapping(value, "case_runtime")
    expected_fields = {
        "schema_version",
        "case_id",
        "input_profile",
        "expected_runtime_activity",
        "expected_forbidden_authority",
        "expected_evaluator_activity",
        "expected_resource_usage",
        "execute",
    }
    if set(runtime) != expected_fields or runtime.get("schema_version") != CASE_RUNTIME_SCHEMA_VERSION:
        raise P138RunnerError("invalid_case_runtime_fields")
    if runtime.get("case_id") != case_id:
        raise P138RunnerError("case_runtime_id_mismatch")
    _mapping(runtime.get("input_profile"), "input_profile")
    _exact_counter_map(runtime.get("expected_runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_expected_runtime_activity")
    _exact_counter_map(
        runtime.get("expected_forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_expected_forbidden_authority",
        require_zero=True,
    )
    _exact_counter_map(runtime.get("expected_evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_expected_evaluator_activity")
    _validate_resource_budget(runtime.get("expected_resource_usage"))
    if not callable(runtime.get("execute")):
        raise P138RunnerError("case_executor_must_be_callable")
    return deepcopy(dict(runtime))


def _execute_case(
    row: Mapping[str, Any],
    runtime: Mapping[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    executor = runtime.get("execute")
    if not callable(executor):
        raise P138RunnerError("case_executor_must_be_callable")
    started_wall = time.monotonic()
    started_self = resource.getrusage(resource.RUSAGE_SELF)
    started_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    observed = _mapping(executor(), "case_observation")
    measured = _resource_usage(started_wall, started_self, started_children)
    expected_fields = {
        "status",
        "error",
        "stop_reason",
        "phase_path",
        "component_boundaries",
        "durable_post_state",
        "runtime_activity",
        "forbidden_authority",
        "evaluator_activity",
        "resource_usage",
        "execution_source",
    }
    if set(observed) != expected_fields:
        raise P138RunnerError("invalid_case_observation_fields")
    case_id = str(row["case_id"])
    expected = deepcopy(dict(_mapping(row.get("expected"), "case_expected")))
    actual = {
        "status": _text(observed.get("status"), "observed_status"),
        "error": _text(observed.get("error"), "observed_error"),
        "stop_reason": _text(observed.get("stop_reason"), "observed_stop_reason"),
        "phase_path": _text_sequence(observed.get("phase_path"), "observed_phase_path"),
        "component_boundaries": _text_sequence(observed.get("component_boundaries"), "observed_component_boundaries"),
        "durable_post_state": _text(observed.get("durable_post_state"), "observed_durable_post_state"),
    }
    for key in ("status", "error", "stop_reason", "durable_post_state"):
        if actual[key] != expected[key]:
            raise P138RunnerError(f"observed_{key}_mismatch:{case_id}")
    if actual["phase_path"] != expected["phase_path"]:
        raise P138RunnerError(f"observed_phase_path_mismatch:{case_id}")
    if actual["component_boundaries"] != expected["component_boundaries"]:
        raise P138RunnerError(f"observed_component_boundaries_mismatch:{case_id}")

    runtime_activity = _exact_counter_map(observed.get("runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_observed_runtime_activity")
    expected_runtime = _exact_counter_map(runtime.get("expected_runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_expected_runtime_activity")
    if runtime_activity != expected_runtime:
        raise P138RunnerError(f"observed_runtime_activity_mismatch:{case_id}")
    forbidden = _exact_counter_map(observed.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_observed_forbidden_authority", require_zero=True)
    expected_forbidden = _exact_counter_map(runtime.get("expected_forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_expected_forbidden_authority", require_zero=True)
    if forbidden != expected_forbidden:
        raise P138RunnerError(f"observed_forbidden_authority_mismatch:{case_id}")
    evaluator = _exact_counter_map(observed.get("evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_observed_evaluator_activity")
    expected_evaluator = _exact_counter_map(runtime.get("expected_evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_expected_evaluator_activity")
    if evaluator != expected_evaluator:
        raise P138RunnerError(f"observed_evaluator_activity_mismatch:{case_id}")
    _exact_resource_map(observed.get("resource_usage"), "invalid_observed_resource_usage")
    expected_resources = _validate_resource_budget(runtime.get("expected_resource_usage"))
    if not _resource_within_budget(measured, expected_resources):
        raise P138RunnerError(f"observed_resource_budget_exceeded:{case_id}")
    evidence = {
        "executed": True,
        "execution_source": _text(observed.get("execution_source"), "execution_source"),
        "output_dir_ref_hash": stable_hash(Path(output_dir).as_posix()),
        "runtime_activity": runtime_activity,
        "expected_runtime_activity": expected_runtime,
        "forbidden_authority": forbidden,
        "expected_forbidden_authority": expected_forbidden,
        "evaluator_activity": evaluator,
        "expected_evaluator_activity": expected_evaluator,
        "resource_usage": measured,
        "expected_resource_usage": expected_resources,
    }
    case: dict[str, Any] = {
        "case_id": case_id,
        "scenario": str(row["scenario"]),
        "expected": expected,
        "actual": actual,
        "status": "passed",
        "real_boundary": bool(row["real_boundary_required"]),
        "evidence": evidence,
    }
    case["case_evidence_hash"] = stable_hash(case)
    return case


def _case_input_binding(runtime: Mapping[str, Any]) -> dict[str, Any]:
    bindings = {str(key): _input_descriptor(value) for key, value in sorted(runtime.items()) if key not in {"schema_version", "case_id"}}
    result = {
        "schema_version": CASE_INPUT_SCHEMA_VERSION,
        "case_id": str(runtime["case_id"]),
        "bindings": bindings,
    }
    result["runtime_input_hash"] = stable_hash(bindings)
    return result


def _input_descriptor(value: Any) -> Any:
    if isinstance(value, Path):
        return {"kind": "path", "name": value.name, "path_ref_hash": stable_hash(value.as_posix())}
    if isinstance(value, bytes):
        return {"kind": "bytes", "byte_count": len(value), "content_hash": stable_hash(value.hex())}
    if callable(value):
        state = getattr(value, "__dict__", {})
        return {
            "kind": "callable",
            "identity": _callable_identity(value),
            "state": _input_descriptor(state),
        }
    if isinstance(value, Mapping):
        return {str(key): _input_descriptor(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_input_descriptor(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise P138RunnerError(f"unsupported_case_input_type:{type(value).__name__}")


def _callable_identity(value: Callable[..., Any]) -> str:
    module = getattr(value, "__module__", type(value).__module__)
    qualname = getattr(value, "__qualname__", type(value).__qualname__)
    return f"{module}.{qualname}"


def _resource_usage(started_wall: float, started_self: Any, started_children: Any) -> dict[str, int]:
    current_self = resource.getrusage(resource.RUSAGE_SELF)
    current_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "wall_time_ms": max(0, int((time.monotonic() - started_wall) * 1000)),
        "cpu_time_ms": max(0, int(((current_self.ru_utime + current_self.ru_stime) - (started_self.ru_utime + started_self.ru_stime)) * 1000)),
        "child_cpu_time_ms": max(0, int(((current_children.ru_utime + current_children.ru_stime) - (started_children.ru_utime + started_children.ru_stime)) * 1000)),
        "peak_memory_bytes": max(0, _normalized_peak_rss_bytes(current_self) - _normalized_peak_rss_bytes(started_self)),
        "wall_limit_ms": 30_000,
        "cpu_limit_ms": 15_000,
        "peak_memory_limit_bytes": 134_217_728,
    }


def _normalized_peak_rss_bytes(usage: Any) -> int:
    value = int(getattr(usage, "ru_maxrss", 0))
    return value if value > 10_000_000 else value * 1024


def _resource_budget() -> dict[str, int]:
    return {
        "wall_time_ms": 0,
        "cpu_time_ms": 0,
        "child_cpu_time_ms": 0,
        "peak_memory_bytes": 0,
        "wall_limit_ms": 30_000,
        "cpu_limit_ms": 15_000,
        "peak_memory_limit_bytes": 134_217_728,
    }


def _validate_resource_budget(value: Any) -> dict[str, int]:
    result = _exact_resource_map(value, "invalid_expected_resource_usage")
    if any(result[key] != 0 for key in ("wall_time_ms", "cpu_time_ms", "child_cpu_time_ms", "peak_memory_bytes")):
        raise P138RunnerError("invalid_expected_resource_measurements")
    if result != _resource_budget():
        raise P138RunnerError("invalid_expected_resource_limits")
    return result


def _resource_within_budget(observed: Mapping[str, int], budget: Mapping[str, int]) -> bool:
    return (
        observed["wall_time_ms"] <= budget["wall_limit_ms"]
        and observed["cpu_time_ms"] + observed["child_cpu_time_ms"] <= budget["cpu_limit_ms"]
        and observed["peak_memory_bytes"] <= budget["peak_memory_limit_bytes"]
        and all(observed[key] == budget[key] for key in ("wall_limit_ms", "cpu_limit_ms", "peak_memory_limit_bytes"))
    )


def _aggregate_counter(cases: Sequence[Mapping[str, Any]], field: str, keys: Sequence[str]) -> dict[str, int]:
    result = _zero(keys)
    for case in cases:
        evidence = _mapping(case.get("evidence"), "case_evidence")
        current = _exact_counter_map(evidence.get(field), keys, f"invalid_case_{field}", require_zero=field.endswith("forbidden_authority"))
        result = _sum_maps(result, current)
    return result


def _aggregate_resources(cases: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    result = _resource_budget()
    for key in ("wall_time_ms", "cpu_time_ms", "child_cpu_time_ms", "peak_memory_bytes"):
        result[key] = sum(_exact_resource_map(_mapping(case.get("evidence"), "case_evidence").get(field), f"invalid_case_{field}")[key] for case in cases)
    return result


def _exact_counter_map(value: Any, keys: Sequence[str], error: str, *, require_zero: bool = False) -> dict[str, int]:
    raw = _mapping(value, "counter_map")
    if set(raw) != set(keys):
        raise P138RunnerError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = raw[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P138RunnerError(error)
        if require_zero and item != 0:
            raise P138RunnerError("forbidden_authority_nonzero")
        result[key] = item
    return result


def _exact_resource_map(value: Any, error: str) -> dict[str, int]:
    return _exact_counter_map(value, RELEASE_RESOURCE_USAGE_KEYS, error)


def _sum_maps(left: Mapping[str, int], right: Mapping[str, int]) -> dict[str, int]:
    if set(left) != set(right):
        raise P138RunnerError("counter_key_mismatch")
    return {key: left[key] + right[key] for key in left}


def _zero(keys: Sequence[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P138RunnerError(f"invalid_{label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise P138RunnerError(f"invalid_{label}")
    return value


def _text_sequence(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P138RunnerError(f"invalid_{label}")
    return [_text(item, label) for item in value]


__all__ = [
    "CASE_INPUT_SCHEMA_VERSION",
    "CASE_RUNTIME_SCHEMA_VERSION",
    "PRELIMINARY_MATRIX_SCHEMA_VERSION",
    "PRELIMINARY_STATUS",
    "P138RunnerError",
    "REAL_BOUNDARY_CASE_IDS",
    "RELEASE_RESOURCE_USAGE_KEYS",
    "p138_release_case_matrix",
    "run_p138_preliminary_matrix",
]
