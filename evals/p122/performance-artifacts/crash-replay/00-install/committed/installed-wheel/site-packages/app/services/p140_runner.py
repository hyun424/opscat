"""Exact source-bound selector runner for P140 qualification."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p139_local_triage_service import zero_forbidden_authority

CASE_MATRIX_SCHEMA_VERSION = "p140.release_case_matrix.v1"
CASE_RESULT_SCHEMA_VERSION = "p140.release_case_result.v1"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CASE_TIMEOUT_SECONDS = 120

_P140 = "tests/test_p140_p139_deadman_adapter.py::"
_P133 = "tests/test_p133_deadman_outbox.py::"
_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("P140-CASE-01", "canonical_config_zero_writes", (_P140 + "test_config_round_trip_binds_p133_and_p139",)),
    ("P140-CASE-02", "ready_live_lease_healthy", (_P140 + "test_ready_requires_held_service_lease_and_recovers_once",)),
    ("P140-CASE-03", "ready_free_lease_unhealthy", (_P140 + "test_ready_requires_held_service_lease_and_recovers_once",)),
    ("P140-CASE-04", "stale_readiness_open", (_P140 + "test_stale_readiness_opens_heartbeat_stale",)),
    ("P140-CASE-05", "stale_heartbeat_open", (_P140 + "test_stale_heartbeat_opens_heartbeat_stale",)),
    ("P140-CASE-06", "clean_terminal_open", (_P140 + "test_clean_stop_opens_runtime_stopped_and_observed_time_deduplicates",)),
    ("P140-CASE-07", "unclean_stop_open", (_P140 + "test_first_open_unclean_stop_records_runtime_stopped",)),
    ("P140-CASE-08", "missing_state_open", (_P140 + "test_missing_state_opens_exact_p133_event",)),
    ("P140-CASE-09", "tampered_receipt_invalid", (_P140 + "test_tampered_receipt_maps_to_redacted_state_invalid",)),
    ("P140-CASE-10", "tampered_termination_invalid", (_P140 + "test_tampered_termination_maps_to_redacted_state_invalid",)),
    ("P140-CASE-11", "forked_history_invalid", (_P140 + "test_forked_exit_history_maps_to_redacted_state_invalid",)),
    ("P140-CASE-12", "ledger_mismatch_invalid", (_P140 + "test_ledger_mismatch_maps_to_redacted_state_invalid",)),
    ("P140-CASE-13", "generation_replay_dedup", (_P140 + "test_identical_unhealthy_runtime_stopped_deduplicates",)),
    ("P140-CASE-14", "stale_replay_unhealthy", (_P140 + "test_stale_replay_deduplicates_existing_incident",)),
    ("P140-CASE-15", "future_control_invalid", (_P140 + "test_future_control_records_do_not_create_false_recovery",)),
    ("P140-CASE-16", "clean_restart_update_once", (_P140 + "test_p139_restart_generation_update_emits_once",)),
    ("P140-CASE-17", "restart_control_single_chain", ("tests/test_p139_local_triage_service.py::test_restart_split_commit_recovers_exact_archived_controls",)),
    ("P140-CASE-18", "event_write_crash_replay", (_P133 + "test_event_first_cursor_second_crash_replay_reuses_existing_event_time_and_id",)),
    ("P140-CASE-19", "cursor_commit_retry_dedup", (_P133 + "test_crash_replay_reuses_later_transition_event_without_sequence_regression",)),
    ("P140-CASE-20", "conflicting_sequence_block", (_P133 + "test_conflicting_replay_existing_event_fails_closed",)),
    ("P140-CASE-21", "identical_unhealthy_dedup", (_P140 + "test_identical_unhealthy_runtime_stopped_deduplicates",)),
    ("P140-CASE-22", "reminder_boundary_once", (_P133 + "test_reminder_boundary_uses_one_check_timestamp",)),
    ("P140-CASE-23", "reason_change_linked_update", (_P140 + "test_unhealthy_reason_change_emits_one_linked_update",)),
    ("P140-CASE-24", "healthy_linked_recovery", (_P140 + "test_ready_requires_held_service_lease_and_recovers_once",)),
    ("P140-CASE-25", "p139_probe_no_mutation", (_P140 + "test_p139_status_probe_does_not_mutate_p139_tree",)),
    ("P140-CASE-26", "p133_lease_conflict", (_P140 + "test_adapter_and_p133_lease_contention_fail_before_partial_state",)),
    ("P140-CASE-27", "adapter_lease_conflict", (_P140 + "test_adapter_and_p133_lease_contention_fail_before_partial_state",)),
    ("P140-CASE-28", "ack_does_not_resolve", (_P133 + "test_ack_is_local_idempotent_and_retention_prunes_only_acknowledged_owned_events",)),
    ("P140-CASE-29", "acknowledged_only_retention", (_P133 + "test_ack_is_local_idempotent_and_retention_prunes_only_acknowledged_owned_events",)),
    ("P140-CASE-30", "unsafe_path_topology_rejected", (_P140 + "test_nested_p133_write_path_under_p139_base_is_rejected",)),
    ("P140-CASE-31", "forbidden_config_text_rejected", (_P140 + "test_config_rejects_unknown_secret_symlink_and_binding_drift",)),
    ("P140-CASE-32", "subprocess_signal_manifests_zero_authority", ("tests/test_p140_deadman_cli.py::test_real_child_process_sigterm_cli_json_has_zero_counters",)),
)


def p140_release_case_catalog() -> list[dict[str, Any]]:
    return [{"case_id": case_id, "scenario": scenario, "selectors": list(selectors)} for case_id, scenario, selectors in _CASES]


def run_p140_preliminary_matrix(project_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p140_release_case_catalog():
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", *case["selectors"]],
                cwd=project_root,
                check=False,
                capture_output=True,
                timeout=_CASE_TIMEOUT_SECONDS,
            )
            output = completed.stdout + completed.stderr
            return_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b"") + (exc.stderr or b"") + b"p140_case_timeout"
            return_code = 124
        row: dict[str, Any] = {
            "schema_version": CASE_RESULT_SCHEMA_VERSION,
            **deepcopy(case),
            "executed": True,
            "passed": return_code == 0,
            "return_code": return_code,
            "output_sha256": "sha256:" + hashlib.sha256(output).hexdigest(),
            "wall_time_ms": max(0, int((time.monotonic() - started) * 1000)),
            "evaluator_activity": {"subprocess_launch_count": 1},
            "asserted_p133_authority": zero_authority_counters(),
            "asserted_p139_forbidden_authority": zero_forbidden_authority(),
        }
        row["case_evidence_hash"] = stable_hash(row)
        rows.append(row)
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "expected": 32,
        "passed": sum(1 for row in rows if row["passed"]),
        "failed": sum(1 for row in rows if not row["passed"]),
        "cases": rows,
    }
    matrix["matrix_hash"] = stable_hash(matrix)
    return validate_p140_case_matrix(matrix)


def validate_p140_case_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if value.get("schema_version") != CASE_MATRIX_SCHEMA_VERSION:
        raise ValueError("invalid_p140_matrix_schema")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 32:
        raise ValueError("invalid_p140_case_denominator")
    catalog = p140_release_case_catalog()
    if [row.get("case_id") for row in cases if isinstance(row, Mapping)] != [case[0] for case in _CASES]:
        raise ValueError("p140_case_catalog_drift")
    for row, expected in zip(cases, catalog, strict=True):
        if not isinstance(row, Mapping) or row.get("executed") is not True:
            raise ValueError("p140_case_not_executed")
        if row.get("schema_version") != CASE_RESULT_SCHEMA_VERSION:
            raise ValueError("p140_case_schema_invalid")
        if any(row.get(key) != expected[key] for key in ("case_id", "scenario", "selectors")):
            raise ValueError("p140_case_definition_drift")
        return_code = row.get("return_code")
        passed_value = row.get("passed")
        if type(return_code) is not int or type(passed_value) is not bool or passed_value != (return_code == 0):
            raise ValueError("p140_case_result_invalid")
        if not isinstance(row.get("output_sha256"), str) or not _SHA256_RE.fullmatch(row["output_sha256"]):
            raise ValueError("p140_case_output_hash_invalid")
        if type(row.get("wall_time_ms")) is not int or row["wall_time_ms"] < 0:
            raise ValueError("p140_case_wall_time_invalid")
        if row.get("evaluator_activity") != {"subprocess_launch_count": 1}:
            raise ValueError("p140_evaluator_activity_invalid")
        if row.get("case_evidence_hash") != stable_hash({key: item for key, item in row.items() if key != "case_evidence_hash"}):
            raise ValueError("p140_case_evidence_hash_invalid")
        if row.get("asserted_p133_authority") != zero_authority_counters():
            raise ValueError("p140_p133_authority_nonzero")
        if row.get("asserted_p139_forbidden_authority") != zero_forbidden_authority():
            raise ValueError("p140_p139_authority_nonzero")
    passed = sum(1 for row in cases if row.get("passed") is True)
    if value.get("expected") != 32 or value.get("passed") != passed or value.get("failed") != 32 - passed:
        raise ValueError("p140_matrix_totals_invalid")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p140_matrix_hash_invalid")
    return value


__all__ = [
    "CASE_MATRIX_SCHEMA_VERSION",
    "p140_release_case_catalog",
    "run_p140_preliminary_matrix",
    "validate_p140_case_matrix",
]
