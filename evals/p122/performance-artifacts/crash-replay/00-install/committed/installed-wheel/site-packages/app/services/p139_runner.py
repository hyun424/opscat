"""Source-bound exact-case runner for P139 release qualification."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p139_local_triage_service import zero_forbidden_authority

CASE_MATRIX_SCHEMA_VERSION = "p139.release_case_matrix.v1"
CASE_RESULT_SCHEMA_VERSION = "p139.release_case_result.v1"

_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("P139-CASE-01", "canonical_bundle_validation_zero_writes", ("tests/test_p139_local_triage_service.py::test_bundle_round_trip_and_rejects_secret_or_callable",)),
    (
        "P139-CASE-02",
        "genesis_service_exact_max_cycle_stop",
        (
            "tests/test_p139_local_triage_service.py::test_service_runs_to_clean_stop_with_zero_authority",
            "tests/test_p138_observation_triage_supervisor.py::test_loop_propagates_each_cycle_time_into_p136_and_publisher_inputs",
        ),
    ),
    ("P139-CASE-03", "zero_promotion_suppresses_downstream", ("tests/test_p138_observation_triage_supervisor.py::test_real_zero_work_suppresses_publisher_and_p137",)),
    ("P139-CASE-04", "promotion_published_and_accepted_once", ("tests/test_p138_observation_triage_supervisor.py::test_real_new_promotion_runs_p136_publisher_and_p137_once",)),
    (
        "P139-CASE-05",
        "clean_restart_receipt_chain",
        (
            "tests/test_p139_local_triage_service.py::test_clean_restart_rolls_controls_and_extends_receipt_chain",
            "tests/test_p138_observation_triage_supervisor.py::test_loop_propagates_each_cycle_time_into_p136_and_publisher_inputs",
        ),
    ),
    ("P139-CASE-06", "terminal_control_rollover_avoids_stale_stop", ("tests/test_p139_local_triage_service.py::test_clean_restart_rolls_controls_and_extends_receipt_chain",)),
    ("P139-CASE-07", "rollover_split_commits_recover_once", ("tests/test_p139_local_triage_service.py::test_restart_split_commit_recovers_exact_archived_controls",)),
    ("P139-CASE-08", "cycle_started_recovery_once", ("tests/test_p138_observation_triage_supervisor.py::test_restart_through_every_phase_boundary_publishes_and_triages_once",)),
    (
        "P139-CASE-09",
        "p136_or_publisher_intent_recovery_once",
        (
            "tests/test_p138_observation_triage_supervisor.py::test_supervisor_recovers_real_publisher_split_crashes_exactly_once",
            "tests/test_p138_observation_triage_supervisor.py::test_p136_empty_same_cycle_recovery_consumes_no_second_receipt",
        ),
    ),
    ("P139-CASE-10", "service_lease_contention_zero_inner_writes", ("tests/test_p139_service_cli.py::test_service_lease_conflict_fails_before_inner_state",)),
    ("P139-CASE-11", "p138_lease_contention_no_success_receipt", ("tests/test_p138_observation_triage_supervisor.py::test_nonblocking_p138_lease_precedes_all_state_and_component_work",)),
    ("P139-CASE-12", "p136_lease_contention_preserves_heads", ("tests/test_p138_observation_triage_supervisor.py::test_p136_empty_same_cycle_recovery_consumes_no_second_receipt",)),
    (
        "P139-CASE-13",
        "publisher_lease_contention_preserves_bundle",
        ("tests/test_p138_observation_triage_supervisor.py::test_publisher_snapshot_lease_conflict_precedes_observation_and_phase_writes",),
    ),
    ("P139-CASE-14", "p137_lease_contention_retains_handoff", ("tests/test_p138_observation_triage_supervisor.py::test_p137_lease_conflict_retains_current_bundle_until_restart",)),
    ("P139-CASE-15", "stale_readiness_blocks_observation", ("tests/test_p138_observation_triage_supervisor.py::test_loop_stale_readiness_deadman_and_safe_signal_stop_before_components",)),
    ("P139-CASE-16", "stale_heartbeat_blocks_observation", ("tests/test_p138_observation_triage_supervisor.py::test_loop_stale_readiness_deadman_and_safe_signal_stop_before_components",)),
    ("P139-CASE-17", "tampered_controls_blocked", ("tests/test_p139_service_cli.py::test_tampered_exit_receipt_and_termination_block_status",)),
    ("P139-CASE-18", "tampered_terminal_receipt_blocked", ("tests/test_p139_service_cli.py::test_tampered_exit_receipt_and_termination_block_status",)),
    (
        "P139-CASE-19",
        "forked_or_gapped_history_blocked",
        (
            "tests/test_p139_service_cli.py::test_exit_history_retention_preserves_current_and_predecessor",
            "tests/test_p138_observation_triage_supervisor.py::test_ledger_validation_and_startup_reject_recomputed_non_genesis_fork",
        ),
    ),
    ("P139-CASE-20", "bundle_symlink_or_nonregular_rejected", ("tests/test_p139_local_triage_service.py::test_bundle_and_runtime_paths_reject_symlinks",)),
    ("P139-CASE-21", "bundle_framing_and_size_rejected", ("tests/test_p139_service_cli.py::test_bundle_framing_and_release_drift_fail_closed",)),
    ("P139-CASE-22", "unsafe_or_overlapping_paths_rejected", ("tests/test_p139_service_cli.py::test_path_authority_is_explicit_relative_and_nonoverlapping",)),
    ("P139-CASE-23", "unknown_callable_url_or_secret_rejected", ("tests/test_p139_local_triage_service.py::test_bundle_round_trip_and_rejects_secret_or_callable",)),
    ("P139-CASE-24", "p138_release_drift_rejected", ("tests/test_p139_service_cli.py::test_bundle_framing_and_release_drift_fail_closed",)),
    ("P139-CASE-25", "transitive_dependency_drift_rejected", ("tests/test_p138_observation_triage_supervisor.py::test_real_p137_release_validator_rejects_fabricated_minimal_evidence",)),
    ("P139-CASE-26", "signals_stop_at_safe_cycle_boundary", ("tests/test_p139_local_triage_service.py::test_signal_controller_stops_before_a_new_cycle_with_bound_receipt",)),
    ("P139-CASE-27", "ready_requires_live_lease_and_no_writes", ("tests/test_p139_local_triage_service.py::test_status_reports_ready_only_with_held_lease_and_matching_heartbeat",)),
    (
        "P139-CASE-28",
        "status_classifies_terminal_states",
        ("tests/test_p139_local_triage_service.py::test_status_requires_live_service_lease_for_ready", "tests/test_p139_local_triage_service.py::test_service_runs_to_clean_stop_with_zero_authority"),
    ),
    ("P139-CASE-29", "systemd_hardening_exact", ("tests/test_p139_service_cli.py::test_deployment_manifests_enforce_no_network_and_least_privilege",)),
    ("P139-CASE-30", "compose_hardening_exact", ("tests/test_p139_service_cli.py::test_deployment_manifests_enforce_no_network_and_least_privilege",)),
    ("P139-CASE-31", "subprocess_clean_run_restart_status", ("tests/test_p139_local_triage_service.py::test_real_subprocess_validate_run_restart_and_status",)),
    ("P139-CASE-32", "subprocess_forced_stop_restart_no_duplicate", ("tests/test_p139_local_triage_service.py::test_real_subprocess_sigterm_then_restart_has_one_receipt_successor",)),
)


def p139_release_case_catalog() -> list[dict[str, Any]]:
    return [{"case_id": case_id, "scenario": scenario, "selectors": list(selectors)} for case_id, scenario, selectors in _CASES]


def run_p139_preliminary_matrix(project_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p139_release_case_catalog():
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *case["selectors"]],
            cwd=project_root,
            check=False,
            capture_output=True,
        )
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        output = completed.stdout + completed.stderr
        row: dict[str, Any] = {
            "schema_version": CASE_RESULT_SCHEMA_VERSION,
            **deepcopy(case),
            "executed": True,
            "passed": completed.returncode == 0,
            "return_code": completed.returncode,
            "output_sha256": "sha256:" + hashlib.sha256(output).hexdigest(),
            "wall_time_ms": elapsed_ms,
            "evaluator_activity": {"subprocess_launch_count": 1},
            "asserted_runtime_forbidden_authority": zero_forbidden_authority(),
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
    return validate_p139_case_matrix(matrix)


def validate_p139_case_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if value.get("schema_version") != CASE_MATRIX_SCHEMA_VERSION:
        raise ValueError("invalid_p139_matrix_schema")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 32:
        raise ValueError("invalid_p139_case_denominator")
    expected_ids = [case[0] for case in _CASES]
    if [row.get("case_id") for row in cases if isinstance(row, Mapping)] != expected_ids:
        raise ValueError("p139_case_catalog_drift")
    for row in cases:
        if not isinstance(row, Mapping) or row.get("executed") is not True:
            raise ValueError("p139_case_not_executed")
        if row.get("case_evidence_hash") != stable_hash({key: item for key, item in row.items() if key != "case_evidence_hash"}):
            raise ValueError("p139_case_evidence_hash_invalid")
        authority = row.get("asserted_runtime_forbidden_authority")
        if authority != zero_forbidden_authority():
            raise ValueError("p139_runtime_authority_nonzero")
    passed = sum(1 for row in cases if row.get("passed") is True)
    if value.get("expected") != 32 or value.get("passed") != passed or value.get("failed") != 32 - passed:
        raise ValueError("p139_matrix_totals_invalid")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p139_matrix_hash_invalid")
    return value


__all__ = [
    "CASE_MATRIX_SCHEMA_VERSION",
    "p139_release_case_catalog",
    "run_p139_preliminary_matrix",
    "validate_p139_case_matrix",
]
