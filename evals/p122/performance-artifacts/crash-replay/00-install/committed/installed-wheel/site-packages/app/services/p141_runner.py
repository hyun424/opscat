"""Exact source-bound selector runner for P141 qualification."""

from __future__ import annotations

import base64
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
from app.services.p121_signals import zero_authority_counters as zero_p133_authority
from app.services.p141_notification_authority import zero_notification_authority_counters

CASE_MATRIX_SCHEMA_VERSION = "p141.release_case_matrix.v1"
CASE_RESULT_SCHEMA_VERSION = "p141.release_case_result.v1"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CASE_TIMEOUT_SECONDS = 120
_RUNNER_SOURCE_PATH = Path(__file__)
_CORE = "tests/test_p141_notification_authority.py::"
_CLI = "tests/test_p141_notification_cli.py::"
_RUNNER = "tests/test_p141_runner.py::"
_RELEASE = "tests/test_p141_release_evidence.py::"

_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("P141-CASE-01", "canonical_config", (_CORE + "test_config_round_trip_is_closed_local_and_destination_only",)),
    ("P141-CASE-02", "unknown_field_rejected", (_CORE + "test_config_round_trip_is_closed_local_and_destination_only",)),
    ("P141-CASE-03", "endpoint_secret_text_rejected", (_CORE + "test_config_round_trip_is_closed_local_and_destination_only",)),
    ("P141-CASE-04", "path_symlink_hardlink_rejected", (_CORE + "test_receipt_tamper_symlink_and_budget_exhaustion_fail_closed",)),
    ("P141-CASE-05", "destination_allowlist", (_CORE + "test_config_round_trip_is_closed_local_and_destination_only",)),
    ("P141-CASE-06", "transition_allowlist", (_CORE + "test_transition_allowlist_and_chain_are_closed",)),
    ("P141-CASE-07", "opened_event", (_CORE + "test_one_event_creates_deterministic_envelopes_and_simulated_receipts_without_ack",)),
    ("P141-CASE-08", "updated_event", (_CORE + "test_all_p133_transitions_form_one_bound_chain",)),
    ("P141-CASE-09", "reminder_event", (_CORE + "test_all_p133_transitions_form_one_bound_chain",)),
    ("P141-CASE-10", "recovered_event", (_CORE + "test_all_p133_transitions_form_one_bound_chain",)),
    ("P141-CASE-11", "malformed_or_hash_drift", (_CORE + "test_tampered_p133_event_and_missing_chain_fail_closed",)),
    ("P141-CASE-12", "p133_config_drift", (_CORE + "test_cross_config_and_cross_event_replay_fail_closed",)),
    ("P141-CASE-13", "sequence_gap_or_rewind", (_CORE + "test_tampered_p133_event_and_missing_chain_fail_closed",)),
    ("P141-CASE-14", "predecessor_fork", (_CORE + "test_tampered_p133_event_and_missing_chain_fail_closed",)),
    ("P141-CASE-15", "deterministic_bytes", (_CORE + "test_replay_is_byte_identical_and_does_not_advance_attempt_counts",)),
    ("P141-CASE-16", "redacted_projection", (_CORE + "test_one_event_creates_deterministic_envelopes_and_simulated_receipts_without_ack",)),
    ("P141-CASE-17", "multi_destination", (_CORE + "test_one_event_creates_deterministic_envelopes_and_simulated_receipts_without_ack",)),
    ("P141-CASE-18", "simulated_not_delivered_or_acked", (_CORE + "test_one_event_creates_deterministic_envelopes_and_simulated_receipts_without_ack",)),
    ("P141-CASE-19", "cross_config_replay", (_CORE + "test_cross_config_and_cross_event_replay_fail_closed",)),
    ("P141-CASE-20", "cross_event_replay", (_CORE + "test_list_rejects_self_consistent_artifacts_not_backed_by_p133",)),
    ("P141-CASE-21", "envelope_tamper", (_CORE + "test_envelope_and_receipt_tamper_fail_closed",)),
    ("P141-CASE-22", "receipt_tamper", (_CORE + "test_receipt_tamper_symlink_and_budget_exhaustion_fail_closed",)),
    ("P141-CASE-23", "lease_conflict", (_CORE + "test_notification_lease_conflict_fails_before_writes",)),
    ("P141-CASE-24", "envelope_only_crash", (_CORE + "test_partial_destination_crash_and_receipt_orphan_fail_closed",)),
    ("P141-CASE-25", "receipt_before_cursor_crash", (_CORE + "test_cursor_failure_replays_existing_artifacts_without_duplication",)),
    ("P141-CASE-26", "multi_destination_partial_crash", (_CORE + "test_partial_destination_crash_and_receipt_orphan_fail_closed",)),
    ("P141-CASE-27", "batch_budget_and_free_space", (_CORE + "test_receipt_tamper_symlink_and_budget_exhaustion_fail_closed",)),
    ("P141-CASE-28", "clock_rollback", (_CORE + "test_clock_rollback_fails_closed",)),
    ("P141-CASE-29", "no_p133_ack_mutation", (_CORE + "test_cursor_cannot_skip_missing_artifact_and_p133_tree_is_byte_immutable",)),
    ("P141-CASE-30", "no_p133_event_cursor_mutation", (_CORE + "test_cursor_cannot_skip_missing_artifact_and_p133_tree_is_byte_immutable",)),
    ("P141-CASE-31", "no_external_io_surface", (_CORE + "test_notification_authority_is_distinct_from_p121_and_source_has_no_external_io",)),
    ("P141-CASE-32", "exact_zero_authority", (_CLI + "test_validate_process_and_list_commands_are_json_only",)),
    ("P141-CASE-33", "exact_catalog", (_RUNNER + "test_p141_catalog_is_exact_ordered_immutable_denominator",)),
    ("P141-CASE-34", "matrix_anti_forgery", (_RUNNER + "test_p141_matrix_rejects_skip_authority_and_hash_forgery",)),
    ("P141-CASE-35", "source_dependency_bindings", (_RELEASE + "test_p141_preliminary_and_final_evidence_bind_sources_dependencies_and_review",)),
    ("P141-CASE-36", "final_does_not_rewrite_frozen_inputs", (_RELEASE + "test_p141_final_mode_does_not_rewrite_frozen_inputs",)),
)


def p141_release_case_catalog() -> list[dict[str, Any]]:
    return [{"case_id": case_id, "scenario": scenario, "selectors": list(selectors)} for case_id, scenario, selectors in _CASES]


def current_p141_runner_source_hash() -> str:
    return "sha256:" + hashlib.sha256(_RUNNER_SOURCE_PATH.read_bytes()).hexdigest()


def p141_case_execution_provenance(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runner": "run_p141_preliminary_matrix",
        "runner_source_sha256": current_p141_runner_source_hash(),
        "command_argv": ["python", "-m", "pytest", "-q", *case["selectors"]],
        "captured_streams": "stdout_plus_stderr",
        "timeout_seconds": _CASE_TIMEOUT_SECONDS,
    }


def run_p141_preliminary_matrix(project_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p141_release_case_catalog():
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
            output = (exc.stdout or b"") + (exc.stderr or b"") + b"p141_case_timeout"
            return_code = 124
        row: dict[str, Any] = {
            "schema_version": CASE_RESULT_SCHEMA_VERSION,
            **deepcopy(case),
            "executed": True,
            "passed": return_code == 0,
            "return_code": return_code,
            "output_sha256": "sha256:" + hashlib.sha256(output).hexdigest(),
            "captured_output_b64": base64.b64encode(output).decode("ascii"),
            "wall_time_ms": max(0, int((time.monotonic() - started) * 1000)),
            "evaluator_activity": {"subprocess_launch_count": 1},
            "execution_provenance": p141_case_execution_provenance(case),
            "asserted_p133_authority": zero_p133_authority(),
            "asserted_p141_authority": zero_notification_authority_counters(),
        }
        row["case_evidence_hash"] = stable_hash(row)
        rows.append(row)
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "runner_source_sha256": current_p141_runner_source_hash(),
        "catalog_hash": stable_hash(p141_release_case_catalog()),
        "expected": 36,
        "passed": sum(1 for row in rows if row["passed"]),
        "failed": sum(1 for row in rows if not row["passed"]),
        "cases": rows,
    }
    matrix["transcript_manifest_hash"] = stable_hash(
        [{"case_id": row["case_id"], "output_sha256": row["output_sha256"], "return_code": row["return_code"]} for row in rows]
    )
    matrix["matrix_hash"] = stable_hash(matrix)
    return validate_p141_case_matrix(matrix)


def validate_p141_case_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if value.get("schema_version") != CASE_MATRIX_SCHEMA_VERSION:
        raise ValueError("invalid_p141_matrix_schema")
    if value.get("runner_source_sha256") != current_p141_runner_source_hash():
        raise ValueError("p141_runner_source_drift")
    if value.get("catalog_hash") != stable_hash(p141_release_case_catalog()):
        raise ValueError("p141_catalog_hash_invalid")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 36:
        raise ValueError("invalid_p141_case_denominator")
    catalog = p141_release_case_catalog()
    if [row.get("case_id") for row in cases if isinstance(row, Mapping)] != [case[0] for case in _CASES]:
        raise ValueError("p141_case_catalog_drift")
    for row, expected in zip(cases, catalog, strict=True):
        if not isinstance(row, Mapping) or row.get("executed") is not True:
            raise ValueError("p141_case_not_executed")
        if row.get("schema_version") != CASE_RESULT_SCHEMA_VERSION:
            raise ValueError("p141_case_schema_invalid")
        if any(row.get(key) != expected[key] for key in ("case_id", "scenario", "selectors")):
            raise ValueError("p141_case_definition_drift")
        return_code = row.get("return_code")
        passed_value = row.get("passed")
        if type(return_code) is not int or type(passed_value) is not bool or passed_value != (return_code == 0):
            raise ValueError("p141_case_result_invalid")
        if not isinstance(row.get("output_sha256"), str) or not _SHA256_RE.fullmatch(row["output_sha256"]):
            raise ValueError("p141_case_output_hash_invalid")
        encoded_output = row.get("captured_output_b64")
        if not isinstance(encoded_output, str) or len(encoded_output) > 5_592_408:
            raise ValueError("p141_case_output_transcript_invalid")
        try:
            transcript = base64.b64decode(encoded_output, validate=True)
        except ValueError as exc:
            raise ValueError("p141_case_output_transcript_invalid") from exc
        if row["output_sha256"] != "sha256:" + hashlib.sha256(transcript).hexdigest():
            raise ValueError("p141_case_output_transcript_hash_invalid")
        if type(row.get("wall_time_ms")) is not int or row["wall_time_ms"] < 0:
            raise ValueError("p141_case_wall_time_invalid")
        if row.get("evaluator_activity") != {"subprocess_launch_count": 1}:
            raise ValueError("p141_evaluator_activity_invalid")
        if row.get("execution_provenance") != p141_case_execution_provenance(expected):
            raise ValueError("p141_execution_provenance_invalid")
        if not _is_exact_zero_map(row.get("asserted_p133_authority"), zero_p133_authority()):
            raise ValueError("p141_p133_authority_nonzero")
        if not _is_exact_zero_map(row.get("asserted_p141_authority"), zero_notification_authority_counters()):
            raise ValueError("p141_authority_nonzero")
        if row.get("case_evidence_hash") != stable_hash({key: item for key, item in row.items() if key != "case_evidence_hash"}):
            raise ValueError("p141_case_evidence_hash_invalid")
    passed = sum(1 for row in cases if row.get("passed") is True)
    if value.get("expected") != 36 or value.get("passed") != passed or value.get("failed") != 36 - passed:
        raise ValueError("p141_matrix_totals_invalid")
    expected_transcript_manifest = stable_hash(
        [{"case_id": row["case_id"], "output_sha256": row["output_sha256"], "return_code": row["return_code"]} for row in cases]
    )
    if value.get("transcript_manifest_hash") != expected_transcript_manifest:
        raise ValueError("p141_transcript_manifest_invalid")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p141_matrix_hash_invalid")
    return value


def _is_exact_zero_map(value: Any, expected: Mapping[str, int]) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == set(expected)
        and all(type(value[key]) is int and value[key] == 0 for key in expected)
    )


__all__ = [
    "CASE_MATRIX_SCHEMA_VERSION",
    "current_p141_runner_source_hash",
    "p141_case_execution_provenance",
    "p141_release_case_catalog",
    "run_p141_preliminary_matrix",
    "validate_p141_case_matrix",
]
