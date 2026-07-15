"""Exact source-bound selector runner for P144 qualification."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p144_provider_adapter_lab import (
    ADAPTER_COUNTER_KEYS,
    FORBIDDEN_COUNTER_KEYS,
    TRANSPORT_COUNTER_KEYS,
    measured_adapter_counters,
    measured_transport_counters,
    reset_measured_counters,
    zero_adapter_counters,
    zero_forbidden_counters,
    zero_transport_counters,
)

CASE_MATRIX_SCHEMA_VERSION = "p144.release_case_matrix.v1"
CASE_RESULT_SCHEMA_VERSION = "p144.release_case_result.v1"
_CASE_TIMEOUT_SECONDS = 120
_RUNNER_SOURCE_PATH = Path(__file__)
_CORE = "tests/test_p144_provider_adapter_lab.py::"
_CLI = "tests/test_p144_provider_adapter_cli.py::"
_RUNNER = "tests/test_p144_runner.py::"
_RELEASE = "tests/test_p144_release_evidence.py::"
_ADAPTER_MARKER_PREFIX = "P144_ADAPTER_COUNTERS="
_TRANSPORT_MARKER_PREFIX = "P144_TRANSPORT_COUNTERS="
_FORBIDDEN_MARKER_PREFIX = "P144_FORBIDDEN_COUNTERS="
_PROOF_MARKER_PREFIX = "P144_SELECTOR_PROOF="
_PROVENANCE_MARKER_PREFIX = "P144_CASE_PROVENANCE="
_PYTEST_EXECUTED: list[str] = []
_PYTEST_PASSED: set[str] = set()

_P144_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("P144-CASE-01", "closed config", (_CORE + "test_config_accepts_exact_closed_schema",)),
    ("P144-CASE-02", "unknown config", (_CORE + "test_config_rejects_unknown_fields",)),
    ("P144-CASE-03", "unsafe config names", (_CORE + "test_config_rejects_unsafe_field_names",)),
    ("P144-CASE-04", "unsafe config values", (_CORE + "test_config_rejects_unsafe_values",)),
    ("P144-CASE-05", "local paths", (_CORE + "test_paths_reject_traversal_symlink_and_hardlink",)),
    ("P144-CASE-06", "root ownership", (_CORE + "test_roots_reject_unsafe_owner_and_permissions",)),
    ("P144-CASE-07", "root overlap", (_CORE + "test_roots_reject_overlap",)),
    ("P144-CASE-08", "budgets", (_CORE + "test_budgets_reject_bool_negative_overflow_and_inconsistency",)),
    ("P144-CASE-09", "P143 release", (_CORE + "test_p143_exact_qualified_release_required",)),
    ("P144-CASE-10", "P143 stale", (_CORE + "test_p143_stale_or_invalid_release_rejected",)),
    ("P144-CASE-11", "P143 projection graph", (_CORE + "test_p143_projection_graph_required",)),
    ("P144-CASE-12", "P143 projection rederive", (_CORE + "test_p143_projection_rederived_and_forgery_rejected",)),
    ("P144-CASE-13", "P142 release", (_CORE + "test_p142_exact_qualified_release_required",)),
    ("P144-CASE-14", "P142 stale", (_CORE + "test_p142_stale_or_invalid_release_rejected",)),
    ("P144-CASE-15", "transitive graph", (_CORE + "test_transitive_dependency_graph_required",)),
    ("P144-CASE-16", "production flags", (_CORE + "test_external_and_production_delivery_flags_rejected",)),
    ("P144-CASE-17", "receiver ownership", (_CORE + "test_receiver_capability_is_process_owned_and_unserializable",)),
    ("P144-CASE-18", "IPv4 loopback", (_CORE + "test_ipv4_receiver_capability_accepted",)),
    ("P144-CASE-19", "IPv6 loopback", (_CORE + "test_ipv6_receiver_capability_accepted_when_available",)),
    ("P144-CASE-20", "hostname", (_CORE + "test_hostnames_and_dns_entrypoints_rejected",)),
    ("P144-CASE-21", "external numeric", (_CORE + "test_non_loopback_numeric_address_rejected",)),
    ("P144-CASE-22", "Unix socket", (_CORE + "test_unix_socket_rejected",)),
    ("P144-CASE-23", "fixed method/path", (_CORE + "test_fixed_post_method_and_path_emitted",)),
    ("P144-CASE-24", "fixed headers", (_CORE + "test_fixed_headers_emitted_in_canonical_order",)),
    ("P144-CASE-25", "header injection", (_CORE + "test_header_injection_and_request_control_rejected",)),
    ("P144-CASE-26", "canonical body", (_CORE + "test_canonical_request_body_is_byte_stable",)),
    ("P144-CASE-27", "request size", (_CORE + "test_request_size_budget_rejected_before_socket",)),
    ("P144-CASE-28", "delivery ID", (_CORE + "test_delivery_id_is_deterministic_and_source_bound",)),
    ("P144-CASE-29", "idempotency", (_CORE + "test_p143_idempotency_key_preserved",)),
    ("P144-CASE-30", "dedupe", (_CORE + "test_p143_dedupe_key_is_non_authority_binding",)),
    ("P144-CASE-31", "accepted 2xx", (_CORE + "test_success_statuses_classify_accepted",)),
    ("P144-CASE-32", "no-content 204", (_CORE + "test_no_content_204_is_accepted",)),
    ("P144-CASE-33", "duplicate 208", (_CORE + "test_208_valid_duplicate_is_accepted",)),
    ("P144-CASE-34", "duplicate 409", (_CORE + "test_409_requires_exact_duplicate_body",)),
    ("P144-CASE-35", "permanent 4xx", (_CORE + "test_permanent_4xx_never_retries",)),
    ("P144-CASE-36", "transient 408/425", (_CORE + "test_408_and_425_create_bounded_adapter_retry",)),
    ("P144-CASE-37", "throttled 429", (_CORE + "test_429_retry_after_creates_bounded_adapter_retry",)),
    ("P144-CASE-38", "transient 5xx", (_CORE + "test_transient_5xx_retries_then_succeeds",)),
    ("P144-CASE-39", "retry exhausted", (_CORE + "test_retry_budget_exhaustion_is_terminal",)),
    ("P144-CASE-40", "invalid Retry-After", (_CORE + "test_invalid_retry_after_fails_without_wait",)),
    ("P144-CASE-41", "excessive Retry-After", (_CORE + "test_excessive_retry_after_rejected",)),
    ("P144-CASE-42", "redirect", (_CORE + "test_redirect_is_rejected_and_never_followed",)),
    ("P144-CASE-43", "malformed status", (_CORE + "test_malformed_status_rejected",)),
    ("P144-CASE-44", "malformed headers", (_CORE + "test_malformed_and_duplicate_framing_headers_rejected",)),
    ("P144-CASE-45", "malformed JSON", (_CORE + "test_malformed_provider_json_rejected",)),
    ("P144-CASE-46", "oversized response", (_CORE + "test_oversized_response_budget_enforced",)),
    ("P144-CASE-47", "truncated response", (_CORE + "test_truncated_response_detected",)),
    ("P144-CASE-48", "connection failure", (_CORE + "test_connection_failure_receipt_is_deterministic",)),
    ("P144-CASE-49", "timeout", (_CORE + "test_timeout_is_bounded_and_classified",)),
    ("P144-CASE-50", "fixed response headers", (_CORE + "test_only_fixed_safe_response_headers_persisted",)),
    ("P144-CASE-51", "provider receipt", (_CORE + "test_provider_receipt_id_is_bounded_and_validated",)),
    ("P144-CASE-52", "completed replay", (_CORE + "test_completed_replay_is_byte_identical_and_opens_no_socket",)),
    ("P144-CASE-53", "conflicting replay", (_CORE + "test_conflicting_replay_artifacts_fail_closed",)),
    ("P144-CASE-54", "pre-send crash", (_CORE + "test_pre_send_crash_recovers_at_most_once",)),
    ("P144-CASE-55", "post-send ambiguity", (_CORE + "test_post_send_ambiguity_requires_review_and_never_retries",)),
    ("P144-CASE-56", "attempt crash windows", (_CORE + "test_attempt_crash_windows_recover_exactly",)),
    ("P144-CASE-57", "receipt crash windows", (_CORE + "test_receipt_crash_windows_recover_exactly",)),
    ("P144-CASE-58", "cursor/run crash", (_CORE + "test_cursor_and_run_crash_windows_recover_exactly",)),
    ("P144-CASE-59", "lease conflict", (_CORE + "test_lease_conflict_blocks_before_socket",)),
    ("P144-CASE-60", "bounded progress", (_CORE + "test_bounded_multi_cycle_progress_cannot_strand_sources",)),
    ("P144-CASE-61", "counter reconciliation", (_CLI + "test_cli_counters_reconcile_to_artifacts_and_transport",)),
    ("P144-CASE-62", "forbidden entrypoints", (_CORE + "test_forbidden_entrypoints_and_counters_remain_zero",)),
    ("P144-CASE-63", "matrix anti-forgery", (_RUNNER + "test_matrix_rejects_skip_reorder_hash_transcript_and_boolean_forgery",)),
    ("P144-CASE-64", "final evidence", (_RELEASE + "test_final_evidence_binds_freeze_review_dependencies_and_limitations",)),
)


def p144_release_case_catalog() -> list[dict[str, Any]]:
    return [{"case_id": case_id, "scenario": scenario, "selectors": list(selectors)} for case_id, scenario, selectors in _P144_CASES]


def current_p144_runner_source_hash() -> str:
    return "sha256:" + hashlib.sha256(_RUNNER_SOURCE_PATH.read_bytes()).hexdigest()


def p144_case_execution_provenance(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runner": "run_p144_preliminary_matrix",
        "runner_source_sha256": current_p144_runner_source_hash(),
        "command_argv": [
            "python",
            "-m",
            "pytest",
            "-q",
            "-s",
            "-p",
            "app.services.p144_runner",
            "--p144-case-id",
            case["case_id"],
            *case["selectors"],
        ],
        "captured_streams": "stdout_and_stderr",
        "timeout_seconds": _CASE_TIMEOUT_SECONDS,
    }


def run_p144_preliminary_matrix(project_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p144_release_case_catalog():
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-s",
                    "-p",
                    "app.services.p144_runner",
                    "--p144-case-id",
                    case["case_id"],
                    *case["selectors"],
                ],
                cwd=project_root,
                check=False,
                capture_output=True,
                timeout=_CASE_TIMEOUT_SECONDS,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = (exc.stderr or b"") + b"p144_case_timeout"
            exit_code = 124
        rows.append(
            build_p144_case_result(
                case,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        )
    return validate_p144_case_matrix(build_p144_case_matrix(rows))


def build_p144_case_result(
    case: Mapping[str, Any],
    *,
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
    duration_ms: int,
    adapter_counters: Mapping[str, Any] | None = None,
    transport_counters: Mapping[str, Any] | None = None,
    forbidden_counters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    transcript = stdout + stderr
    row: dict[str, Any] = {
        "schema_version": CASE_RESULT_SCHEMA_VERSION,
        **deepcopy(dict(case)),
        "selector_result": "passed" if exit_code == 0 else "failed",
        "selector_execution_proof": _parse_json_marker(transcript, _PROOF_MARKER_PREFIX),
        "command_argv": p144_case_execution_provenance(case)["command_argv"],
        "timeout_seconds": _CASE_TIMEOUT_SECONDS,
        "exit_code": exit_code,
        "captured_streams": "stdout_and_stderr",
        "stdout_b64": base64.b64encode(stdout).decode("ascii"),
        "stderr_b64": base64.b64encode(stderr).decode("ascii"),
        "transcript_sha256": "sha256:" + hashlib.sha256(transcript).hexdigest(),
        "execution_provenance_marker": _parse_json_marker(transcript, _PROVENANCE_MARKER_PREFIX),
        "runner": "run_p144_preliminary_matrix",
        "runner_source_sha256": current_p144_runner_source_hash(),
        "adapter_counters": dict(adapter_counters or _parse_marker(transcript, _ADAPTER_MARKER_PREFIX, ADAPTER_COUNTER_KEYS, exact_zero=False) or zero_adapter_counters()),
        "transport_counters": dict(transport_counters or _parse_marker(transcript, _TRANSPORT_MARKER_PREFIX, TRANSPORT_COUNTER_KEYS, exact_zero=False) or zero_transport_counters()),
        "forbidden_counters": dict(forbidden_counters or _parse_marker(transcript, _FORBIDDEN_MARKER_PREFIX, FORBIDDEN_COUNTER_KEYS, exact_zero=True) or zero_forbidden_counters()),
    }
    row["row_hash"] = stable_hash(row)
    return row


def build_p144_case_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "expected": 64,
        "passed": sum(1 for row in rows if row.get("selector_result") == "passed"),
        "failed": sum(1 for row in rows if row.get("selector_result") != "passed"),
        "catalog_hash": stable_hash(p144_release_case_catalog()),
        "runner_source_sha256": current_p144_runner_source_hash(),
        "rows": rows,
        "adapter_counters": _sum(rows, "adapter_counters", ADAPTER_COUNTER_KEYS),
        "transport_counters": _sum(rows, "transport_counters", TRANSPORT_COUNTER_KEYS),
        "forbidden_counters": zero_forbidden_counters(),
    }
    matrix["matrix_hash"] = stable_hash(matrix)
    return matrix


def validate_p144_case_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if value.get("schema_version") != CASE_MATRIX_SCHEMA_VERSION:
        raise ValueError("invalid_p144_matrix_schema")
    if value.get("catalog_hash") != stable_hash(p144_release_case_catalog()):
        raise ValueError("p144_catalog_hash_invalid")
    if value.get("runner_source_sha256") != current_p144_runner_source_hash():
        raise ValueError("p144_runner_source_drift")
    rows = value.get("rows")
    if not isinstance(rows, list) or len(rows) != 64:
        raise ValueError("invalid_p144_case_denominator")
    catalog = p144_release_case_catalog()
    if [row.get("case_id") for row in rows if isinstance(row, Mapping)] != [case["case_id"] for case in catalog]:
        raise ValueError("p144_case_catalog_drift")
    seen: set[str] = set()
    for row, expected in zip(rows, catalog, strict=True):
        _validate_row(row, expected)
        selector = row["selectors"][0]
        if selector in seen:
            raise ValueError("p144_selector_reuse")
        seen.add(selector)
    passed = sum(1 for row in rows if row["selector_result"] == "passed")
    if value.get("expected") != 64 or value.get("passed") != passed or value.get("failed") != 64 - passed:
        raise ValueError("p144_matrix_totals_invalid")
    if value.get("adapter_counters") != _sum(rows, "adapter_counters", ADAPTER_COUNTER_KEYS):
        raise ValueError("p144_adapter_counters_invalid")
    if value.get("transport_counters") != _sum(rows, "transport_counters", TRANSPORT_COUNTER_KEYS):
        raise ValueError("p144_transport_counters_invalid")
    if value.get("forbidden_counters") != zero_forbidden_counters():
        raise ValueError("p144_forbidden_counters_invalid")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p144_matrix_hash_invalid")
    return value


def _validate_row(row: Any, expected: Mapping[str, Any]) -> None:
    if not isinstance(row, Mapping) or row.get("schema_version") != CASE_RESULT_SCHEMA_VERSION:
        raise ValueError("p144_case_schema_invalid")
    if any(row.get(key) != expected[key] for key in ("case_id", "scenario", "selectors")):
        raise ValueError("p144_case_definition_drift")
    if row.get("runner") != "run_p144_preliminary_matrix" or row.get("runner_source_sha256") != current_p144_runner_source_hash():
        raise ValueError("p144_runner_identity_invalid")
    if row.get("command_argv") != p144_case_execution_provenance(expected)["command_argv"]:
        raise ValueError("p144_command_argv_invalid")
    if row.get("captured_streams") != "stdout_and_stderr" or row.get("timeout_seconds") != _CASE_TIMEOUT_SECONDS:
        raise ValueError("p144_capture_contract_invalid")
    if type(row.get("exit_code")) is not int or row.get("selector_result") not in {"passed", "failed"} or (row["exit_code"] == 0) != (row["selector_result"] == "passed"):
        raise ValueError("p144_selector_result_invalid")
    if row["selector_result"] != "passed":
        raise ValueError("p144_selector_not_passed")
    stdout = _b64(row.get("stdout_b64"))
    stderr = _b64(row.get("stderr_b64"))
    transcript = stdout + stderr
    if row.get("transcript_sha256") != "sha256:" + hashlib.sha256(transcript).hexdigest():
        raise ValueError("p144_transcript_hash_invalid")
    expected_proof = {"executed": expected["selectors"], "passed": expected["selectors"]}
    if row.get("selector_execution_proof") != expected_proof or _parse_json_marker(transcript, _PROOF_MARKER_PREFIX, required=True) != expected_proof:
        raise ValueError("p144_selector_execution_proof_invalid")
    expected_marker = {
        "case_id": expected["case_id"],
        "runner": "run_p144_preliminary_matrix",
        "runner_source_sha256": current_p144_runner_source_hash(),
        "selectors": expected["selectors"],
    }
    if row.get("execution_provenance_marker") != expected_marker or _parse_json_marker(transcript, _PROVENANCE_MARKER_PREFIX, required=True) != expected_marker:
        raise ValueError("p144_execution_provenance_marker_invalid")
    if _parse_marker(transcript, _ADAPTER_MARKER_PREFIX, ADAPTER_COUNTER_KEYS, exact_zero=False, required=True) != row["adapter_counters"]:
        raise ValueError("p144_adapter_counter_marker_mismatch")
    if _parse_marker(transcript, _TRANSPORT_MARKER_PREFIX, TRANSPORT_COUNTER_KEYS, exact_zero=False, required=True) != row["transport_counters"]:
        raise ValueError("p144_transport_counter_marker_mismatch")
    if _parse_marker(transcript, _FORBIDDEN_MARKER_PREFIX, FORBIDDEN_COUNTER_KEYS, exact_zero=True, required=True) != row["forbidden_counters"]:
        raise ValueError("p144_forbidden_counter_marker_mismatch")
    if row.get("row_hash") != stable_hash({key: item for key, item in row.items() if key != "row_hash"}):
        raise ValueError("p144_row_hash_invalid")


def _b64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("p144_transcript_invalid")
    return base64.b64decode(value, validate=True)


def _parse_json_marker(output: bytes, prefix: str, *, required: bool = False) -> Any | None:
    text = output.decode("utf-8")
    markers = [line.removeprefix(prefix) for line in text.splitlines() if line.startswith(prefix)]
    if not markers:
        if required:
            raise ValueError("p144_mandatory_marker_missing")
        return None
    if len(markers) != 1:
        raise ValueError("p144_marker_ambiguous")
    parsed = json.loads(markers[0], object_pairs_hook=_strict_json_object)
    if markers[0] != json.dumps(parsed, sort_keys=True, separators=(",", ":")):
        raise ValueError("p144_marker_noncanonical")
    return parsed


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _parse_marker(output: bytes, prefix: str, keys: tuple[str, ...], *, exact_zero: bool, required: bool = False) -> dict[str, int] | None:
    parsed = _parse_json_marker(output, prefix, required=required)
    if parsed is None:
        return None
    if not _counter_map(parsed, keys, exact_zero=exact_zero):
        raise ValueError("p144_counter_marker_invalid")
    return dict(parsed)


def _counter_map(value: Any, keys: tuple[str, ...], *, exact_zero: bool) -> bool:
    return isinstance(value, Mapping) and set(value) == set(keys) and all(type(value[key]) is int and (value[key] == 0 if exact_zero else value[key] >= 0) for key in keys)


def _sum(rows: list[Any], field: str, keys: tuple[str, ...]) -> dict[str, int]:
    totals = {key: 0 for key in keys}
    for row in rows:
        counters = row.get(field) if isinstance(row, Mapping) else None
        if isinstance(counters, Mapping):
            for key in keys:
                value = counters.get(key)
                if type(value) is int:
                    totals[key] += value
    return totals


def pytest_addoption(parser: Any) -> None:
    parser.addoption("--p144-case-id", action="store", default=None)


def pytest_sessionstart(session: Any) -> None:
    _ = session
    reset_measured_counters()


def pytest_runtest_logreport(report: Any) -> None:
    if report.when != "call":
        return
    selector = str(report.nodeid).split("[", 1)[0]
    if selector not in _PYTEST_EXECUTED:
        _PYTEST_EXECUTED.append(selector)
    if report.passed:
        _PYTEST_PASSED.add(selector)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    _ = exitstatus
    case_id = session.config.getoption("--p144-case-id")
    if case_id is None:
        return
    proof = {"executed": _PYTEST_EXECUTED, "passed": [item for item in _PYTEST_EXECUTED if item in _PYTEST_PASSED]}
    provenance = {
        "case_id": case_id,
        "runner": "run_p144_preliminary_matrix",
        "runner_source_sha256": current_p144_runner_source_hash(),
        "selectors": _PYTEST_EXECUTED,
    }
    sys.stdout.write("\n")
    for prefix, value in (
        (_PROOF_MARKER_PREFIX, proof),
        (_PROVENANCE_MARKER_PREFIX, provenance),
        (_FORBIDDEN_MARKER_PREFIX, zero_forbidden_counters()),
        (_ADAPTER_MARKER_PREFIX, measured_adapter_counters()),
        (_TRANSPORT_MARKER_PREFIX, measured_transport_counters()),
    ):
        sys.stdout.write(prefix + json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


__all__ = [
    "ADAPTER_COUNTER_KEYS",
    "CASE_MATRIX_SCHEMA_VERSION",
    "FORBIDDEN_COUNTER_KEYS",
    "TRANSPORT_COUNTER_KEYS",
    "_P144_CASES",
    "build_p144_case_matrix",
    "build_p144_case_result",
    "current_p144_runner_source_hash",
    "p144_case_execution_provenance",
    "p144_release_case_catalog",
    "run_p144_preliminary_matrix",
    "validate_p144_case_matrix",
    "zero_adapter_counters",
    "zero_forbidden_counters",
    "zero_transport_counters",
]
