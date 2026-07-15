"""Exact source-bound selector runner for P143 qualification."""

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
from app.services.p143_egress_contract_lab import (
    ALLOWED_COUNTER_KEYS,
    FORBIDDEN_COUNTER_KEYS,
    measured_allowed_counters,
    reset_measured_allowed_counters,
    zero_allowed_counters,
    zero_forbidden_counters,
)

CASE_MATRIX_SCHEMA_VERSION = "p143.release_case_matrix.v1"
CASE_RESULT_SCHEMA_VERSION = "p143.release_case_result.v1"
_CASE_TIMEOUT_SECONDS = 120
_RUNNER_SOURCE_PATH = Path(__file__)
_CORE = "tests/test_p143_egress_contract_lab.py::"
_CLI = "tests/test_p143_egress_contract_cli.py::"
_RUNNER = "tests/test_p143_runner.py::"
_RELEASE = "tests/test_p143_release_evidence.py::"
_COUNTER_MARKER_PREFIX = "P143_CASE_COUNTERS="
_FORBIDDEN_MARKER_PREFIX = "P143_FORBIDDEN_COUNTERS="
_PROOF_MARKER_PREFIX = "P143_SELECTOR_PROOF="
_PROVENANCE_MARKER_PREFIX = "P143_CASE_PROVENANCE="
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PYTEST_EXECUTED: list[str] = []
_PYTEST_PASSED: set[str] = set()

_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("P143-CASE-01", "config_closed", (_CORE + "test_config_accepts_exact_closed_schema",)),
    ("P143-CASE-02", "unknown_fields", (_CORE + "test_config_rejects_unknown_fields",)),
    ("P143-CASE-03", "authority_words", (_CORE + "test_config_rejects_p143_authority_words",)),
    ("P143-CASE-04", "endpoint_url_webhook", (_CORE + "test_config_rejects_endpoint_url_and_webhook_fields",)),
    ("P143-CASE-05", "auth_token_header_secret", (_CORE + "test_config_rejects_auth_token_header_and_secret_fields",)),
    ("P143-CASE-06", "dns_proxy_tls_sdk", (_CORE + "test_config_rejects_dns_proxy_tls_and_provider_sdk_fields",)),
    ("P143-CASE-07", "paths", (_CORE + "test_paths_reject_traversal_symlink_and_hardlink",)),
    ("P143-CASE-08", "roots", (_CORE + "test_roots_reject_wrong_owner_and_writable_permissions",)),
    ("P143-CASE-09", "overlap", (_CORE + "test_roots_reject_read_write_overlap",)),
    ("P143-CASE-10", "budgets", (_CORE + "test_budgets_reject_boolean_negative_and_overflow",)),
    ("P143-CASE-11", "p142_release", (_CORE + "test_p142_exact_qualified_release_required",)),
    ("P143-CASE-12", "p142_stale", (_CORE + "test_p142_stale_release_evidence_rejected",)),
    ("P143-CASE-13", "p142_schema", (_CORE + "test_p142_receipt_schema_drift_rejected",)),
    ("P143-CASE-14", "p142_hash", (_CORE + "test_p142_receipt_hash_drift_rejected",)),
    ("P143-CASE-15", "p142_prod", (_CORE + "test_p142_production_delivered_true_rejected",)),
    ("P143-CASE-16", "p141_binding", (_CORE + "test_p141_envelope_binding_required",)),
    ("P143-CASE-17", "p141_hash", (_CORE + "test_p141_envelope_hash_drift_rejected",)),
    ("P143-CASE-18", "dependency_graph", (_CORE + "test_p133_p141_p142_dependency_graph_is_immutable",)),
    ("P143-CASE-19", "opened", (_CORE + "test_opened_transition_intent_built",)),
    ("P143-CASE-20", "updated", (_CORE + "test_updated_transition_intent_built",)),
    ("P143-CASE-21", "reminder", (_CORE + "test_reminder_transition_intent_built",)),
    ("P143-CASE-22", "recovered", (_CORE + "test_recovered_transition_intent_built",)),
    ("P143-CASE-23", "intent_id", (_CORE + "test_intent_id_is_deterministic",)),
    ("P143-CASE-24", "idempotency", (_CORE + "test_idempotency_key_is_deterministic",)),
    ("P143-CASE-25", "dedupe", (_CORE + "test_dedupe_key_is_deterministic",)),
    ("P143-CASE-26", "severity", (_CORE + "test_severity_mapping_is_closed",)),
    ("P143-CASE-27", "severity_closed", (_CORE + "test_unsupported_severity_fails_closed",)),
    ("P143-CASE-28", "truncation", (_CORE + "test_truncation_is_deterministic_and_recorded",)),
    ("P143-CASE-29", "evidence_refs", (_CORE + "test_evidence_refs_preserved_without_raw_secrets",)),
    ("P143-CASE-30", "projection_stable", (_CORE + "test_provider_neutral_projection_is_byte_stable",)),
    ("P143-CASE-31", "chat", (_CORE + "test_chat_shadow_profile_compatibility_pass",)),
    ("P143-CASE-32", "email", (_CORE + "test_email_shadow_profile_compatibility_pass",)),
    ("P143-CASE-33", "pager", (_CORE + "test_pager_shadow_profile_compatibility_pass",)),
    ("P143-CASE-34", "incident_comment", (_CORE + "test_incident_comment_shadow_profile_compatibility_pass",)),
    ("P143-CASE-35", "unsupported_channel", (_CORE + "test_unsupported_channel_fails_closed",)),
    ("P143-CASE-36", "missing_capability", (_CORE + "test_missing_required_capability_fails_closed",)),
    ("P143-CASE-37", "payload_limit", (_CORE + "test_payload_size_limit_fails_closed",)),
    ("P143-CASE-38", "evidence_limit", (_CORE + "test_evidence_reference_limit_fails_closed",)),
    ("P143-CASE-39", "retry_local", (_CORE + "test_retry_classification_is_local_evidence_only",)),
    ("P143-CASE-40", "rate_limit_manifest", (_CORE + "test_rate_limit_semantics_are_manifest_only",)),
    ("P143-CASE-41", "no_socket", (_CORE + "test_valid_processing_opens_no_socket",)),
    ("P143-CASE-42", "entrypoints_zero", (_CORE + "test_forbidden_network_environment_provider_entrypoints_stay_zero",)),
    ("P143-CASE-43", "no_commands", (_CORE + "test_no_subprocess_or_shell_path_exists",)),
    ("P143-CASE-44", "completed_replay", (_CORE + "test_completed_replay_opens_no_io_and_is_byte_identical",)),
    ("P143-CASE-45", "intent_crash", (_CORE + "test_intent_prepare_and_write_crashes_recover_byte_identically",)),
    ("P143-CASE-46", "projection_crash", (_CORE + "test_projection_prepare_and_write_crashes_recover_byte_identically",)),
    ("P143-CASE-47", "result_cursor_run_crash", (_CORE + "test_result_cursor_and_run_crashes_recover_byte_identically",)),
    ("P143-CASE-48", "conflict", (_CORE + "test_conflicting_replay_artifact_fails_closed",)),
    ("P143-CASE-49", "lease", (_CORE + "test_lease_conflict_fails_before_processing",)),
    ("P143-CASE-50", "cli_counters", (_CLI + "test_cli_emits_exact_int_only_counter_keysets",)),
    ("P143-CASE-51", "matrix_anti_forgery", (_RUNNER + "test_matrix_rejects_skip_reorder_hash_and_boolean_forgery",)),
    ("P143-CASE-52", "release_evidence", (_RELEASE + "test_final_evidence_binds_all_frozen_inputs_and_review",)),
)


def p143_release_case_catalog() -> list[dict[str, Any]]:
    return [{"case_id": case_id, "scenario": scenario, "selectors": list(selectors)} for case_id, scenario, selectors in _CASES]


def current_p143_runner_source_hash() -> str:
    return "sha256:" + hashlib.sha256(_RUNNER_SOURCE_PATH.read_bytes()).hexdigest()


def p143_case_execution_provenance(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runner": "run_p143_preliminary_matrix",
        "runner_source_sha256": current_p143_runner_source_hash(),
        "command_argv": [
            "python",
            "-m",
            "pytest",
            "-q",
            "-s",
            "-p",
            "app.services.p143_runner",
            "--p143-case-id",
            case["case_id"],
            *case["selectors"],
        ],
        "captured_streams": "stdout_and_stderr",
        "timeout_seconds": _CASE_TIMEOUT_SECONDS,
    }


def run_p143_preliminary_matrix(project_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p143_release_case_catalog():
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
                    "app.services.p143_runner",
                    "--p143-case-id",
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
            stderr = (exc.stderr or b"") + b"p143_case_timeout"
            exit_code = 124
        row = build_p143_case_result(
            case,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
        try:
            _validate_row(row, case)
        except ValueError as exc:
            raise ValueError(f"{case['case_id']}:{exc}") from exc
        rows.append(row)
    return validate_p143_case_matrix(build_p143_case_matrix(rows))


def build_p143_case_result(
    case: Mapping[str, Any],
    *,
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
    duration_ms: int,
    forbidden_counters: Mapping[str, Any] | None = None,
    allowed_counters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    transcript = stdout + stderr
    parsed_allowed = _parse_marker(transcript, _COUNTER_MARKER_PREFIX, ALLOWED_COUNTER_KEYS, exact_zero=False)
    parsed_forbidden = _parse_marker(transcript, _FORBIDDEN_MARKER_PREFIX, FORBIDDEN_COUNTER_KEYS, exact_zero=True)
    proof = _parse_json_marker(transcript, _PROOF_MARKER_PREFIX)
    provenance_marker = _parse_json_marker(transcript, _PROVENANCE_MARKER_PREFIX)
    counters = dict(allowed_counters or parsed_allowed or zero_allowed_counters())
    row: dict[str, Any] = {
        "schema_version": CASE_RESULT_SCHEMA_VERSION,
        **deepcopy(dict(case)),
        "runner": "run_p143_preliminary_matrix",
        "runner_source_sha256": current_p143_runner_source_hash(),
        "command_argv": p143_case_execution_provenance(case)["command_argv"],
        "captured_streams": "stdout_and_stderr",
        "timeout_seconds": _CASE_TIMEOUT_SECONDS,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout_b64": base64.b64encode(stdout).decode("ascii"),
        "stderr_b64": base64.b64encode(stderr).decode("ascii"),
        "transcript_sha256": "sha256:" + hashlib.sha256(transcript).hexdigest(),
        "selector_result": "passed" if exit_code == 0 else "failed",
        "selector_execution_proof": proof,
        "execution_provenance_marker": provenance_marker,
        "forbidden_counters": dict(forbidden_counters or parsed_forbidden or zero_forbidden_counters()),
        "allowed_counters": counters,
    }
    row["row_hash"] = stable_hash(row)
    return row


def build_p143_case_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "catalog_hash": stable_hash(p143_release_case_catalog()),
        "runner_source_sha256": current_p143_runner_source_hash(),
        "expected": 52,
        "passed": sum(1 for row in rows if row.get("selector_result") == "passed"),
        "failed": sum(1 for row in rows if row.get("selector_result") != "passed"),
        "forbidden_counters": zero_forbidden_counters(),
        "allowed_counters": _sum_allowed(rows),
        "rows": rows,
    }
    matrix["matrix_hash"] = stable_hash(matrix)
    return matrix


def validate_p143_case_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if value.get("schema_version") != CASE_MATRIX_SCHEMA_VERSION:
        raise ValueError("invalid_p143_matrix_schema")
    if value.get("catalog_hash") != stable_hash(p143_release_case_catalog()):
        raise ValueError("p143_catalog_hash_invalid")
    if value.get("runner_source_sha256") != current_p143_runner_source_hash():
        raise ValueError("p143_runner_source_drift")
    rows = value.get("rows")
    if not isinstance(rows, list) or len(rows) != 52:
        raise ValueError("invalid_p143_case_denominator")
    catalog = p143_release_case_catalog()
    if [row.get("case_id") for row in rows if isinstance(row, Mapping)] != [case["case_id"] for case in catalog]:
        raise ValueError("p143_case_catalog_drift")
    seen: set[str] = set()
    for row, expected in zip(rows, catalog, strict=True):
        _validate_row(row, expected)
        selector = row["selectors"][0]
        if selector in seen:
            raise ValueError("p143_selector_reuse")
        seen.add(selector)
    passed = sum(1 for row in rows if row["selector_result"] == "passed")
    if value.get("expected") != 52 or value.get("passed") != passed or value.get("failed") != 52 - passed:
        raise ValueError("p143_matrix_totals_invalid")
    if not _counter_map(value.get("forbidden_counters"), FORBIDDEN_COUNTER_KEYS, exact_zero=True) or value["forbidden_counters"] != zero_forbidden_counters():
        raise ValueError("p143_matrix_forbidden_invalid")
    if value.get("allowed_counters") != _sum_allowed(rows):
        raise ValueError("p143_matrix_allowed_invalid")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p143_matrix_hash_invalid")
    return value


def _validate_row(row: Any, expected: Mapping[str, Any]) -> None:
    if not isinstance(row, Mapping) or row.get("schema_version") != CASE_RESULT_SCHEMA_VERSION:
        raise ValueError("p143_case_schema_invalid")
    if any(row.get(key) != expected[key] for key in ("case_id", "scenario", "selectors")):
        raise ValueError("p143_case_definition_drift")
    if row.get("runner") != "run_p143_preliminary_matrix" or row.get("runner_source_sha256") != current_p143_runner_source_hash():
        raise ValueError("p143_runner_identity_invalid")
    if row.get("command_argv") != p143_case_execution_provenance(expected)["command_argv"]:
        raise ValueError("p143_command_argv_invalid")
    if row.get("captured_streams") != "stdout_and_stderr" or row.get("timeout_seconds") != _CASE_TIMEOUT_SECONDS:
        raise ValueError("p143_capture_contract_invalid")
    if type(row.get("exit_code")) is not int or row.get("selector_result") not in {"passed", "failed"} or (row["exit_code"] == 0) != (row["selector_result"] == "passed"):
        raise ValueError("p143_selector_result_invalid")
    if row["selector_result"] != "passed":
        raise ValueError("p143_selector_not_passed")
    if type(row.get("duration_ms")) is not int or row["duration_ms"] < 0:
        raise ValueError("p143_duration_invalid")
    stdout = _b64(row.get("stdout_b64"))
    stderr = _b64(row.get("stderr_b64"))
    if row.get("transcript_sha256") != "sha256:" + hashlib.sha256(stdout + stderr).hexdigest():
        raise ValueError("p143_transcript_hash_invalid")
    transcript = stdout + stderr
    proof = _parse_json_marker(transcript, _PROOF_MARKER_PREFIX, required=True)
    expected_proof = {"executed": expected["selectors"], "passed": expected["selectors"]}
    if proof != expected_proof or row.get("selector_execution_proof") != expected_proof:
        raise ValueError("p143_selector_execution_proof_invalid")
    provenance_marker = _parse_json_marker(transcript, _PROVENANCE_MARKER_PREFIX, required=True)
    expected_marker = {
        "case_id": expected["case_id"],
        "runner": "run_p143_preliminary_matrix",
        "runner_source_sha256": current_p143_runner_source_hash(),
        "selectors": expected["selectors"],
    }
    if provenance_marker != expected_marker or row.get("execution_provenance_marker") != expected_marker:
        raise ValueError("p143_execution_provenance_marker_invalid")
    if not _counter_map(row.get("forbidden_counters"), FORBIDDEN_COUNTER_KEYS, exact_zero=True):
        raise ValueError("p143_forbidden_counters_invalid")
    if not _counter_map(row.get("allowed_counters"), ALLOWED_COUNTER_KEYS, exact_zero=False):
        raise ValueError("p143_allowed_counters_invalid")
    forbidden_marker = _parse_marker(transcript, _FORBIDDEN_MARKER_PREFIX, FORBIDDEN_COUNTER_KEYS, exact_zero=True, required=True)
    if forbidden_marker != row["forbidden_counters"]:
        raise ValueError("p143_forbidden_counter_marker_mismatch")
    marker = _parse_marker(transcript, _COUNTER_MARKER_PREFIX, ALLOWED_COUNTER_KEYS, exact_zero=False, required=True)
    if marker != row["allowed_counters"]:
        raise ValueError("p143_counter_marker_mismatch")
    if row.get("row_hash") != stable_hash({key: item for key, item in row.items() if key != "row_hash"}):
        raise ValueError("p143_row_hash_invalid")


def _b64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("p143_transcript_invalid")
    return base64.b64decode(value, validate=True)


def _parse_json_marker(output: bytes, prefix: str, *, required: bool = False) -> Any | None:
    text = output.decode("utf-8")
    markers = [line.removeprefix(prefix) for line in text.splitlines() if line.startswith(prefix)]
    if not markers:
        if required:
            raise ValueError("p143_mandatory_marker_missing")
        return None
    if len(markers) != 1:
        raise ValueError("p143_marker_ambiguous")
    parsed = json.loads(markers[0])
    if markers[0] != json.dumps(parsed, sort_keys=True, separators=(",", ":")):
        raise ValueError("p143_marker_noncanonical")
    return parsed


def _parse_marker(
    output: bytes,
    prefix: str,
    keys: tuple[str, ...],
    *,
    exact_zero: bool,
    required: bool = False,
) -> dict[str, int] | None:
    parsed = _parse_json_marker(output, prefix, required=required)
    if parsed is None:
        return None
    if not _counter_map(parsed, keys, exact_zero=exact_zero):
        raise ValueError("p143_counter_marker_invalid")
    return dict(parsed)


def pytest_addoption(parser: Any) -> None:
    parser.addoption("--p143-case-id", action="store", default=None)


def pytest_sessionstart(session: Any) -> None:
    _ = session
    reset_measured_allowed_counters()


def pytest_runtest_logreport(report: Any) -> None:
    if report.when != "call":
        return
    selector = str(report.nodeid).split("[", 1)[0]
    if selector not in _PYTEST_EXECUTED:
        _PYTEST_EXECUTED.append(selector)
    if report.passed:
        _PYTEST_PASSED.add(selector)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    case_id = session.config.getoption("--p143-case-id")
    if case_id is None:
        return
    proof = {"executed": _PYTEST_EXECUTED, "passed": [item for item in _PYTEST_EXECUTED if item in _PYTEST_PASSED]}
    provenance = {
        "case_id": case_id,
        "runner": "run_p143_preliminary_matrix",
        "runner_source_sha256": current_p143_runner_source_hash(),
        "selectors": _PYTEST_EXECUTED,
    }
    markers = (
        (_PROOF_MARKER_PREFIX, proof),
        (_PROVENANCE_MARKER_PREFIX, provenance),
        (_FORBIDDEN_MARKER_PREFIX, zero_forbidden_counters()),
        (_COUNTER_MARKER_PREFIX, measured_allowed_counters()),
    )
    sys.stdout.write("\n")
    for prefix, value in markers:
        sys.stdout.write(prefix + json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _counter_map(value: Any, keys: tuple[str, ...], *, exact_zero: bool) -> bool:
    return isinstance(value, Mapping) and set(value) == set(keys) and all(type(value[key]) is int and (value[key] == 0 if exact_zero else 0 <= value[key] <= 10_000_000) for key in keys)


def _sum_allowed(rows: list[Any]) -> dict[str, int]:
    totals = zero_allowed_counters()
    for row in rows:
        counters = row.get("allowed_counters") if isinstance(row, Mapping) else None
        if isinstance(counters, Mapping):
            for key in ALLOWED_COUNTER_KEYS:
                value = counters.get(key)
                if type(value) is int:
                    totals[key] += value
    return totals


__all__ = [
    "ALLOWED_COUNTER_KEYS",
    "CASE_MATRIX_SCHEMA_VERSION",
    "FORBIDDEN_COUNTER_KEYS",
    "build_p143_case_matrix",
    "build_p143_case_result",
    "current_p143_runner_source_hash",
    "p143_case_execution_provenance",
    "p143_release_case_catalog",
    "run_p143_preliminary_matrix",
    "validate_p143_case_matrix",
    "zero_allowed_counters",
    "zero_forbidden_counters",
]
