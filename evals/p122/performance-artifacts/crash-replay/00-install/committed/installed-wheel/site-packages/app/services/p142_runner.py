"""Exact source-bound selector runner for P142 qualification."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash

CASE_MATRIX_SCHEMA_VERSION = "p142.release_case_matrix.v1"
CASE_RESULT_SCHEMA_VERSION = "p142.release_case_result.v1"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CASE_TIMEOUT_SECONDS = 120
_RUNNER_SOURCE_PATH = Path(__file__)
_CORE = "tests/test_p142_loopback_transport_lab.py::"
_CLI = "tests/test_p142_loopback_cli.py::"
_RUNNER = "tests/test_p142_runner.py::"
_RELEASE = "tests/test_p142_release_evidence.py::"
_COUNTER_MARKER_PREFIX = "P142_CASE_COUNTERS="

FORBIDDEN_NON_TRANSPORT_COUNTER_KEYS: tuple[str, ...] = (
    "credential_read_count",
    "environment_read_count",
    "dns_socket_call_count",
    "proxy_use_count",
    "tls_handshake_count",
    "authentication_attempt_count",
    "redirect_follow_count",
    "provider_sdk_call_count",
    "non_loopback_socket_attempt_count",
    "external_message_send_count",
    "ticket_creation_count",
    "p133_ack_write_count",
    "approval_count",
    "subprocess_shell_count",
    "arbitrary_command_execution_count",
    "action_execution_count",
    "remediation_execution_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
    "authority_escape_count",
)

ALLOWED_TRANSPORT_COUNTER_KEYS: tuple[str, ...] = (
    "loopback_socket_attempt_count",
    "loopback_request_commit_count",
    "loopback_request_byte_count",
    "loopback_complete_response_count",
    "loopback_response_byte_count",
    "loopback_retry_count",
    "loopback_transport_failure_count",
    "loopback_http_2xx_count",
    "loopback_http_3xx_count",
    "loopback_http_4xx_count",
    "loopback_http_5xx_count",
)

_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("P142-CASE-01", "canonical_config", (_CORE + "test_config_accepts_closed_numeric_loopback_routes",)),
    ("P142-CASE-02", "unknown_and_forbidden_fields_rejected", (_CORE + "test_config_rejects_unknown_and_authority_bearing_fields",)),
    ("P142-CASE-03", "hostname_dns_and_localhost_rejected", (_CORE + "test_config_rejects_hostname_dns_and_localhost_targets",)),
    ("P142-CASE-04", "non_loopback_numeric_rejected", (_CORE + "test_config_rejects_non_loopback_numeric_targets",)),
    ("P142-CASE-05", "proxy_env_tls_auth_rejected", (_CORE + "test_config_rejects_proxy_env_tls_auth_and_credentials",)),
    ("P142-CASE-06", "redirect_command_action_rejected", (_CORE + "test_config_rejects_redirect_command_action_and_mutation_surfaces",)),
    ("P142-CASE-07", "path_symlink_hardlink_rejected", (_CORE + "test_path_symlink_hardlink_and_overlap_fail_closed",)),
    ("P142-CASE-08", "budget_profile_bounds", (_CORE + "test_config_enforces_time_body_response_and_artifact_budgets",)),
    ("P142-CASE-09", "p141_envelope_opened_bound", (_CORE + "test_valid_p141_opened_envelope_dispatches_to_loopback",)),
    ("P142-CASE-10", "p141_envelope_updated_bound", (_CORE + "test_all_p141_transition_envelopes_bind_before_dispatch",)),
    ("P142-CASE-11", "p141_envelope_reminder_bound", (_CORE + "test_all_p141_transition_envelopes_bind_before_dispatch",)),
    ("P142-CASE-12", "p141_envelope_recovered_bound", (_CORE + "test_all_p141_transition_envelopes_bind_before_dispatch",)),
    ("P142-CASE-13", "p141_hash_or_receipt_drift", (_CORE + "test_p141_hash_receipt_and_cursor_drift_fail_closed",)),
    ("P142-CASE-14", "p141_cross_config_or_fork", (_CORE + "test_p141_cross_config_rewind_gap_and_fork_fail_closed",)),
    ("P142-CASE-15", "p141_p133_reader_lease_only_immutability", (_CORE + "test_p141_and_p133_artifacts_are_immutable_except_exact_public_reader_leases",)),
    ("P142-CASE-16", "loopback_ipv4_dispatch", (_CORE + "test_real_ipv4_loopback_http_dispatch_writes_receipt",)),
    ("P142-CASE-17", "loopback_ipv6_dispatch", (_CORE + "test_real_ipv6_loopback_http_dispatch_writes_receipt",)),
    ("P142-CASE-18", "socket_before_validation_blocked", (_CORE + "test_socket_cannot_open_before_numeric_loopback_validation",)),
    ("P142-CASE-19", "dns_env_proxy_patched_zero", (_CORE + "test_dns_env_proxy_and_provider_entrypoints_are_never_called",)),
    ("P142-CASE-20", "redirects_not_followed", (_CORE + "test_redirect_response_is_recorded_not_followed",)),
    ("P142-CASE-21", "response_body_budget", (_CORE + "test_response_body_budget_and_truncation_are_bounded",)),
    ("P142-CASE-22", "timeout_budget", (_CORE + "test_connect_response_body_and_total_timeouts_fail_closed",)),
    ("P142-CASE-23", "malformed_response", (_CORE + "test_malformed_loopback_response_records_bounded_failure",)),
    ("P142-CASE-24", "deterministic_dispatch_identity", (_CORE + "test_dispatch_and_attempt_ids_are_deterministic",)),
    ("P142-CASE-25", "byte_identical_replay_no_socket", (_CORE + "test_completed_replay_is_byte_identical_and_opens_no_socket",)),
    ("P142-CASE-26", "pre_socket_failures_retry_bounded", (_CORE + "test_only_pre_socket_connection_failures_advance_to_next_ordinal",)),
    ("P142-CASE-27", "complete_statuses_terminal", (_CORE + "test_complete_http_statuses_never_retry_after_request_commit",)),
    ("P142-CASE-28", "retry_after_seconds_advisory", (_CORE + "test_retry_after_seconds_is_bounded_advisory_without_post_commit_wait",)),
    ("P142-CASE-29", "retry_after_imf_fixdate", (_CORE + "test_retry_after_imf_fixdate_uses_injected_utc_ceiling_and_monotonic_budget",)),
    ("P142-CASE-30", "invalid_retry_after_rejected", (_CORE + "test_obsolete_ambiguous_non_utc_and_excessive_retry_after_is_rejected",)),
    ("P142-CASE-31", "durable_attempt_journal_recovery", (_CORE + "test_attempt_journal_phases_recover_without_replaying_request_committed",)),
    ("P142-CASE-32", "lease_conflict", (_CORE + "test_loopback_transport_lease_conflict_fails_before_dispatch",)),
    ("P142-CASE-33", "cursor_requires_receipts", (_CORE + "test_cursor_advances_only_after_all_receipts_are_durable",)),
    ("P142-CASE-34", "artifact_budget_and_free_space", (_CORE + "test_artifact_count_total_bytes_and_free_space_fail_before_writes",)),
    ("P142-CASE-35", "fsync_replace_failures", (_CORE + "test_temp_write_fsync_replace_and_directory_fsync_failures_preserve_prior_state",)),
    ("P142-CASE-36", "signal_and_clock_safety", (_CLI + "test_run_stops_on_signal_and_rejects_clock_rollback",)),
    ("P142-CASE-37", "no_p133_ack_or_p141_mutation", (_CORE + "test_no_p133_ack_and_no_p141_mutation_authority",)),
    ("P142-CASE-38", "no_action_remediation_mutation", (_CORE + "test_action_remediation_and_mutation_entrypoints_are_never_called",)),
    ("P142-CASE-39", "exact_zero_non_transport_authority", (_CLI + "test_cli_outputs_exact_zero_non_transport_authority_counters",)),
    ("P142-CASE-40", "no_subprocess_or_command_runtime", (_CORE + "test_runtime_source_and_valid_paths_do_not_use_commands_or_subprocesses",)),
    ("P142-CASE-41", "exact_catalog", (_RUNNER + "test_p142_catalog_is_exact_ordered_immutable_denominator",)),
    ("P142-CASE-42", "matrix_anti_forgery", (_RUNNER + "test_p142_matrix_rejects_skip_authority_activity_hash_and_boolean_forgery",)),
    ("P142-CASE-43", "source_dependency_bindings", (_RELEASE + "test_p142_preliminary_and_final_evidence_bind_sources_p141_dependency_and_review",)),
    ("P142-CASE-44", "final_does_not_rewrite_frozen_inputs", (_RELEASE + "test_p142_final_mode_does_not_rewrite_frozen_inputs",)),
)

TRANSPORT_ACTIVE_CASE_IDS: frozenset[str] = frozenset(
    {
        "P142-CASE-09",
        "P142-CASE-10",
        "P142-CASE-11",
        "P142-CASE-12",
        "P142-CASE-15",
        "P142-CASE-16",
        "P142-CASE-17",
        "P142-CASE-19",
        "P142-CASE-20",
        "P142-CASE-21",
        "P142-CASE-22",
        "P142-CASE-23",
        "P142-CASE-25",
        "P142-CASE-26",
        "P142-CASE-27",
        "P142-CASE-28",
        "P142-CASE-33",
        "P142-CASE-37",
        "P142-CASE-38",
        "P142-CASE-40",
    }
)

TRANSPORT_ACTIVE_SELECTORS: frozenset[str] = frozenset(
    selector
    for case_id, _scenario, selectors in _CASES
    if case_id in TRANSPORT_ACTIVE_CASE_IDS
    for selector in selectors
)


def zero_forbidden_non_transport_counters() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_NON_TRANSPORT_COUNTER_KEYS}


def zero_allowed_transport_counters() -> dict[str, int]:
    return {key: 0 for key in ALLOWED_TRANSPORT_COUNTER_KEYS}


def p142_release_case_catalog() -> list[dict[str, Any]]:
    return [{"case_id": case_id, "scenario": scenario, "selectors": list(selectors)} for case_id, scenario, selectors in _CASES]


def current_p142_runner_source_hash() -> str:
    return "sha256:" + hashlib.sha256(_RUNNER_SOURCE_PATH.read_bytes()).hexdigest()


def p142_case_execution_provenance(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runner": "run_p142_preliminary_matrix",
        "runner_source_sha256": current_p142_runner_source_hash(),
        "command_argv": ["python", "-m", "pytest", "-q", "-s", *case["selectors"]],
        "captured_streams": "stdout_plus_stderr",
        "timeout_seconds": _CASE_TIMEOUT_SECONDS,
    }


def run_p142_preliminary_matrix(project_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p142_release_case_catalog():
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-s", *case["selectors"]],
                cwd=project_root,
                check=False,
                capture_output=True,
                timeout=_CASE_TIMEOUT_SECONDS,
            )
            output = completed.stdout + completed.stderr
            return_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b"") + (exc.stderr or b"") + b"p142_case_timeout"
            return_code = 124
        row = build_p142_case_result(
            case,
            return_code=return_code,
            output=output,
            wall_time_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
        rows.append(row)
    return validate_p142_case_matrix(build_p142_case_matrix(rows))


def build_p142_case_result(
    case: Mapping[str, Any],
    *,
    return_code: int,
    output: bytes,
    wall_time_ms: int,
    forbidden_counters: Mapping[str, Any] | None = None,
    transport_counters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "schema_version": CASE_RESULT_SCHEMA_VERSION,
        **deepcopy(dict(case)),
        "executed": True,
        "passed": return_code == 0,
        "return_code": return_code,
        "output_sha256": "sha256:" + hashlib.sha256(output).hexdigest(),
        "captured_output_b64": base64.b64encode(output).decode("ascii"),
        "wall_time_ms": wall_time_ms,
        "evaluator_activity": {"subprocess_launch_count": 1},
        "execution_provenance": p142_case_execution_provenance(case),
        "forbidden_non_transport_authority_counters": dict(forbidden_counters or zero_forbidden_non_transport_counters()),
        "allowed_transport_activity_counters": _case_transport_counters(case, output, transport_counters),
    }
    row["case_evidence_hash"] = stable_hash(row)
    return row


def build_p142_case_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "runner_source_sha256": current_p142_runner_source_hash(),
        "catalog_hash": stable_hash(p142_release_case_catalog()),
        "expected": 44,
        "passed": sum(1 for row in rows if row.get("passed") is True),
        "failed": sum(1 for row in rows if row.get("passed") is not True),
        "forbidden_non_transport_authority_counters": zero_forbidden_non_transport_counters(),
        "allowed_transport_activity_counters": _sum_transport_counters(rows),
        "cases": rows,
    }
    matrix["transcript_manifest_hash"] = stable_hash(
        [{"case_id": row["case_id"], "output_sha256": row["output_sha256"], "return_code": row["return_code"]} for row in rows]
    )
    matrix["matrix_hash"] = stable_hash(matrix)
    return matrix


def validate_p142_case_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if value.get("schema_version") != CASE_MATRIX_SCHEMA_VERSION:
        raise ValueError("invalid_p142_matrix_schema")
    if value.get("runner_source_sha256") != current_p142_runner_source_hash():
        raise ValueError("p142_runner_source_drift")
    if value.get("catalog_hash") != stable_hash(p142_release_case_catalog()):
        raise ValueError("p142_catalog_hash_invalid")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 44:
        raise ValueError("invalid_p142_case_denominator")
    catalog = p142_release_case_catalog()
    if [row.get("case_id") for row in cases if isinstance(row, Mapping)] != [case[0] for case in _CASES]:
        raise ValueError("p142_case_catalog_drift")
    for row, expected in zip(cases, catalog, strict=True):
        _validate_case_row(row, expected)
    passed = sum(1 for row in cases if row.get("passed") is True)
    if value.get("expected") != 44 or value.get("passed") != passed or value.get("failed") != 44 - passed:
        raise ValueError("p142_matrix_totals_invalid")
    if not _is_exact_zero_forbidden_map(value.get("forbidden_non_transport_authority_counters")):
        raise ValueError("p142_matrix_forbidden_authority_nonzero")
    expected_transport = _sum_transport_counters(cases)
    if not _is_valid_transport_map(value.get("allowed_transport_activity_counters")) or value["allowed_transport_activity_counters"] != expected_transport:
        raise ValueError("p142_matrix_transport_activity_invalid")
    expected_transcript_manifest = stable_hash(
        [{"case_id": row["case_id"], "output_sha256": row["output_sha256"], "return_code": row["return_code"]} for row in cases]
    )
    if value.get("transcript_manifest_hash") != expected_transcript_manifest:
        raise ValueError("p142_transcript_manifest_invalid")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p142_matrix_hash_invalid")
    return value


def _validate_case_row(row: Any, expected: Mapping[str, Any]) -> None:
    if not isinstance(row, Mapping) or row.get("executed") is not True:
        raise ValueError("p142_case_not_executed")
    if row.get("schema_version") != CASE_RESULT_SCHEMA_VERSION:
        raise ValueError("p142_case_schema_invalid")
    if any(row.get(key) != expected[key] for key in ("case_id", "scenario", "selectors")):
        raise ValueError("p142_case_definition_drift")
    return_code = row.get("return_code")
    passed_value = row.get("passed")
    if type(return_code) is not int or type(passed_value) is not bool or passed_value != (return_code == 0):
        raise ValueError("p142_case_result_invalid")
    if not isinstance(row.get("output_sha256"), str) or not _SHA256_RE.fullmatch(row["output_sha256"]):
        raise ValueError("p142_case_output_hash_invalid")
    encoded_output = row.get("captured_output_b64")
    if not isinstance(encoded_output, str) or len(encoded_output) > 5_592_408:
        raise ValueError("p142_case_output_transcript_invalid")
    try:
        transcript = base64.b64decode(encoded_output, validate=True)
    except ValueError as exc:
        raise ValueError("p142_case_output_transcript_invalid") from exc
    if row["output_sha256"] != "sha256:" + hashlib.sha256(transcript).hexdigest():
        raise ValueError("p142_case_output_transcript_hash_invalid")
    if type(row.get("wall_time_ms")) is not int or row["wall_time_ms"] < 0:
        raise ValueError("p142_case_wall_time_invalid")
    if row.get("evaluator_activity") != {"subprocess_launch_count": 1}:
        raise ValueError("p142_evaluator_activity_invalid")
    if row.get("execution_provenance") != p142_case_execution_provenance(expected):
        raise ValueError("p142_execution_provenance_invalid")
    if not _is_exact_zero_forbidden_map(row.get("forbidden_non_transport_authority_counters")):
        raise ValueError("p142_forbidden_authority_nonzero")
    if not _is_valid_transport_map(row.get("allowed_transport_activity_counters")):
        raise ValueError("p142_transport_activity_invalid")
    transport_active = _is_transport_active_case(expected)
    counters = row["allowed_transport_activity_counters"]
    marker_counters = _parse_case_counter_marker(transcript)
    if transport_active:
        if marker_counters is None:
            raise ValueError("p142_transport_counter_marker_missing")
        if counters != marker_counters:
            raise ValueError("p142_transport_counter_marker_mismatch")
        _validate_transport_active_counters(counters)
    else:
        if marker_counters is not None and marker_counters != zero_allowed_transport_counters():
            raise ValueError("p142_inactive_transport_counter_forgery")
        if counters != zero_allowed_transport_counters():
            raise ValueError("p142_inactive_transport_counter_forgery")
    if row.get("case_evidence_hash") != stable_hash({key: item for key, item in row.items() if key != "case_evidence_hash"}):
        raise ValueError("p142_case_evidence_hash_invalid")


def _sum_transport_counters(rows: list[Any]) -> dict[str, int]:
    totals = zero_allowed_transport_counters()
    for row in rows:
        counters = row.get("allowed_transport_activity_counters") if isinstance(row, Mapping) else None
        if not isinstance(counters, Mapping):
            continue
        for key in ALLOWED_TRANSPORT_COUNTER_KEYS:
            value = counters.get(key)
            if type(value) is int:
                totals[key] += value
    return totals


def _is_exact_zero_forbidden_map(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == set(FORBIDDEN_NON_TRANSPORT_COUNTER_KEYS)
        and all(type(value[key]) is int and value[key] == 0 for key in FORBIDDEN_NON_TRANSPORT_COUNTER_KEYS)
    )


def _is_valid_transport_map(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == set(ALLOWED_TRANSPORT_COUNTER_KEYS)
        and all(type(value[key]) is int and value[key] >= 0 and value[key] <= 10_000_000 for key in ALLOWED_TRANSPORT_COUNTER_KEYS)
    )


def _case_transport_counters(
    case: Mapping[str, Any], output: bytes, transport_counters: Mapping[str, Any] | None
) -> dict[str, int]:
    if transport_counters is not None:
        return dict(transport_counters)
    marker_counters = _parse_case_counter_marker(output)
    if marker_counters is not None:
        return marker_counters
    if _is_transport_active_case(case):
        raise ValueError("p142_transport_counter_marker_missing")
    return zero_allowed_transport_counters()


def _parse_case_counter_marker(output: bytes) -> dict[str, int] | None:
    try:
        text = output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("p142_case_output_transcript_invalid") from exc
    markers = [line.removeprefix(_COUNTER_MARKER_PREFIX) for line in text.splitlines() if line.startswith(_COUNTER_MARKER_PREFIX)]
    if not markers:
        return None
    if len(markers) != 1:
        raise ValueError("p142_transport_counter_marker_ambiguous")
    raw = markers[0]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("p142_transport_counter_marker_invalid") from exc
    if not _is_valid_transport_map(parsed):
        raise ValueError("p142_transport_counter_marker_invalid")
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    if raw != canonical:
        raise ValueError("p142_transport_counter_marker_noncanonical")
    return dict(parsed)


def _is_transport_active_case(case: Mapping[str, Any]) -> bool:
    selectors = case.get("selectors")
    return (
        case.get("case_id") in TRANSPORT_ACTIVE_CASE_IDS
        and isinstance(selectors, list)
        and bool(selectors)
        and all(selector in TRANSPORT_ACTIVE_SELECTORS for selector in selectors)
    )


def _validate_transport_active_counters(counters: Mapping[str, int]) -> None:
    attempts = counters["loopback_socket_attempt_count"]
    commits = counters["loopback_request_commit_count"]
    complete = counters["loopback_complete_response_count"]
    failures = counters["loopback_transport_failure_count"]
    statuses = (
        counters["loopback_http_2xx_count"]
        + counters["loopback_http_3xx_count"]
        + counters["loopback_http_4xx_count"]
        + counters["loopback_http_5xx_count"]
    )
    if attempts <= 0:
        raise ValueError("p142_transport_active_without_socket_attempt")
    if commits > attempts or complete > commits or statuses != complete or failures > attempts:
        raise ValueError("p142_transport_counter_totals_impossible")
    if counters["loopback_request_byte_count"] <= 0 and commits > 0:
        raise ValueError("p142_transport_counter_totals_impossible")
    if counters["loopback_response_byte_count"] > 0 and complete == 0:
        raise ValueError("p142_transport_counter_totals_impossible")


__all__ = [
    "ALLOWED_TRANSPORT_COUNTER_KEYS",
    "CASE_MATRIX_SCHEMA_VERSION",
    "FORBIDDEN_NON_TRANSPORT_COUNTER_KEYS",
    "TRANSPORT_ACTIVE_CASE_IDS",
    "TRANSPORT_ACTIVE_SELECTORS",
    "build_p142_case_matrix",
    "build_p142_case_result",
    "current_p142_runner_source_hash",
    "p142_case_execution_provenance",
    "p142_release_case_catalog",
    "run_p142_preliminary_matrix",
    "validate_p142_case_matrix",
    "zero_allowed_transport_counters",
    "zero_forbidden_non_transport_counters",
]
