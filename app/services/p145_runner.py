"""Selector-bound P145 preliminary matrix runner."""

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
from app.services.p145_response_duty_officer import (
    CASE_SELECTOR_NAMES,
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    LAB_ACTIVITY_KEYS,
    RESOURCE_USAGE_KEYS,
    RUNTIME_ACTIVITY_KEYS,
    exact_counter_map,
    process_episode_fixture,
    validate_case_fixture,
    zero_evaluator_activity,
    zero_forbidden_authority,
    zero_lab_activity,
    zero_resource_usage,
    zero_runtime_activity,
)

CASE_MATRIX_SCHEMA_VERSION = "p145.release_case_matrix.v1"
CASE_RESULT_SCHEMA_VERSION = "p145.release_case_result.v1"
EXECUTABLE_PROVENANCE_SCHEMA_VERSION = "p145.python_executable_provenance.v1"
_CASE_TIMEOUT_SECONDS = 120
_RUNNER_SOURCE_PATH = Path(__file__)
_PROJECT_ROOT = _RUNNER_SOURCE_PATH.resolve().parents[2]
_APPROVED_VENV_BIN = (_PROJECT_ROOT / ".venv" / "bin").resolve()
_APPROVED_PYTHON_ALIASES = ("python", "python3")
_PORTABLE_PROJECT_ROOT = "$PROJECT_ROOT"
_PORTABLE_VENV_BIN = f"{_PORTABLE_PROJECT_ROOT}/.venv/bin"
_TRANSCRIPT_FORM = "canonical_selector_markers_v1"
_PROOF_MARKER_PREFIX = "P145_SELECTOR_PROOF="
_RESULT_MARKER_PREFIX = "P145_CASE_RESULT="
_PYTEST_EXECUTED: list[str] = []
_PYTEST_PASSED: set[str] = set()
_CASE_RESULTS: list[dict[str, Any]] = []


def p145_release_case_catalog() -> list[dict[str, Any]]:
    return [
        {
            "case_id": case_id,
            "scenario": _SCENARIOS[case_id],
            "selector": f"tests/test_p145_response_duty_officer.py::{selector_name}",
            "fixture_path": f"tests/fixtures/p145/cases/{case_id}.json",
            "expected_terminal_status": _TERMINALS[case_id],
        }
        for case_id, selector_name in CASE_SELECTOR_NAMES.items()
    ]


def current_p145_runner_source_hash() -> str:
    return "sha256:" + hashlib.sha256(_RUNNER_SOURCE_PATH.read_bytes()).hexdigest()


def _approved_executable_provenance() -> dict[str, Any]:
    identity: dict[str, Any] = {
        "schema_version": EXECUTABLE_PROVENANCE_SCHEMA_VERSION,
        "canonical_project_root": _PORTABLE_PROJECT_ROOT,
        "canonical_venv_bin": _PORTABLE_VENV_BIN,
        "allowed_aliases": list(_APPROVED_PYTHON_ALIASES),
    }
    identity["identity_hash"] = stable_hash(identity)
    return identity


def _is_approved_python_executable(executable: str) -> bool:
    path = Path(executable)
    return (
        path.is_absolute()
        and path.is_file()
        and path.name in _APPROVED_PYTHON_ALIASES
        and path.parent.resolve() == _APPROVED_VENV_BIN
    )


def _selector_argv(case: Mapping[str, Any]) -> list[str]:
    if not _is_approved_python_executable(sys.executable):
        raise ValueError("p145_generation_executable_provenance_invalid")
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-s",
        "-p",
        "app.services.p145_runner",
        "--p145-case-id",
        str(case["case_id"]),
        str(case["selector"]),
    ]


def _persisted_selector_argv(case: Mapping[str, Any], executable: str) -> list[str]:
    alias = Path(executable).name
    if alias not in _APPROVED_PYTHON_ALIASES:
        raise ValueError("p145_generation_executable_provenance_invalid")
    return [f"{_PORTABLE_VENV_BIN}/{alias}", *_selector_argv(case)[1:]]


def run_p145_preliminary_matrix(project_root: Path, *, output_dir: Path | None = None) -> dict[str, Any]:
    _ = output_dir
    rows: list[dict[str, Any]] = []
    for case in p145_release_case_catalog():
        started = time.monotonic()
        argv = _selector_argv(case)
        try:
            completed = subprocess.run(
                [argv[0], *argv[1:]],
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
            stderr = (exc.stderr or b"") + b"p145_case_timeout"
            exit_code = 124
        rows.append(
            build_p145_case_result(
                case,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        )
    return validate_p145_case_matrix(build_p145_case_matrix(rows))


def _canonical_selector_transcript(selector_proof: Any, result: Any) -> bytes:
    lines: list[str] = []
    if isinstance(selector_proof, Mapping):
        lines.append(_PROOF_MARKER_PREFIX + json.dumps(selector_proof, sort_keys=True, separators=(",", ":")))
    if isinstance(result, Mapping):
        portable_result = deepcopy(dict(result))
        portable_result["journal_path"] = "$CASE_DIR/journal.jsonl"
        portable_result["cursor_path"] = "$CASE_DIR/cursor.json"
        portable_result["result_hash"] = stable_hash({key: value for key, value in portable_result.items() if key != "result_hash"})
        lines.append(_RESULT_MARKER_PREFIX + json.dumps(portable_result, sort_keys=True, separators=(",", ":")))
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def build_p145_case_result(case: Mapping[str, Any], *, exit_code: int, stdout: bytes, stderr: bytes, duration_ms: int) -> dict[str, Any]:
    raw_transcript = stdout + stderr
    result = _parse_json_marker(raw_transcript, _RESULT_MARKER_PREFIX)
    selector_proof = _parse_json_marker(raw_transcript, _PROOF_MARKER_PREFIX)
    canonical_stdout = _canonical_selector_transcript(selector_proof, result)
    canonical_stderr = b""
    transcript = canonical_stdout + canonical_stderr
    fixture = _read_fixture(Path(case["fixture_path"]))
    expected_counts = deepcopy(fixture["expected_counts"])
    observed = result or {}
    row: dict[str, Any] = {
        "schema_version": CASE_RESULT_SCHEMA_VERSION,
        "case_id": case["case_id"],
        "scenario": case["scenario"],
        "selector": case["selector"],
        "fixture_path": case["fixture_path"],
        "input_hash": stable_hash(fixture["p133_event"]),
        "config_hash": stable_hash({"predecessor_bindings": fixture["predecessor_bindings"], "source_profile_bindings": fixture["source_profile_bindings"]}),
        "evidence_hash": fixture["evidence_hash"],
        "expected_terminal_status": case["expected_terminal_status"],
        "observed_terminal_status": observed.get("terminal_status"),
        "expected_phase_path": fixture["expected_phase_path"],
        "observed_phase_path": observed.get("phase_path", []),
        "expected_crash_point": fixture["expected_crash_point"],
        "observed_crash_point": observed.get("crash_point"),
        "expected_counts": expected_counts,
        "observed_counts": observed.get("counts", _zero_all_counts()),
        "forbidden_authority": observed.get("counts", {}).get("forbidden_authority", zero_forbidden_authority()),
        "runtime_activity": observed.get("counts", {}).get("runtime_activity", zero_runtime_activity()),
        "lab_activity": observed.get("counts", {}).get("lab_activity", zero_lab_activity()),
        "evaluator_activity": _evaluator_counters(exit_code, crash_injected=observed.get("crash_point") is not None),
        "resource_usage": observed.get("counts", {}).get("resource_usage", zero_resource_usage()),
        "command_proof": {
            "argv": _persisted_selector_argv(case, sys.executable),
            "executable_provenance": _approved_executable_provenance(),
            "exit_code": exit_code,
            "stdout_sha256": "sha256:" + hashlib.sha256(canonical_stdout).hexdigest(),
            "stderr_sha256": "sha256:" + hashlib.sha256(canonical_stderr).hexdigest(),
            "transcript_sha256": "sha256:" + hashlib.sha256(transcript).hexdigest(),
            "stdout_b64": base64.b64encode(canonical_stdout).decode("ascii"),
            "stderr_b64": base64.b64encode(canonical_stderr).decode("ascii"),
            "transcript_form": _TRANSCRIPT_FORM,
            "duration_ms": duration_ms,
            "selector_execution_proof": selector_proof,
        },
        "passed": False,
        "failure_reason": None,
    }
    row["passed"], row["failure_reason"] = _row_passed(row, case)
    row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    return row


def build_p145_case_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "expected": 48,
        "passed": sum(1 for row in rows if row.get("passed") is True),
        "failed": sum(1 for row in rows if row.get("passed") is not True),
        "cases": rows,
        "case_input_hash": stable_hash([row["input_hash"] for row in rows]),
        "case_config_hash": stable_hash([row["config_hash"] for row in rows]),
        "case_evidence_hash": stable_hash([row["evidence_hash"] for row in rows]),
        "aggregate_counters": _aggregate(rows),
        "runner_source_sha256": current_p145_runner_source_hash(),
        "catalog_hash": stable_hash(p145_release_case_catalog()),
    }
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    return matrix


def validate_p145_case_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if value.get("schema_version") != CASE_MATRIX_SCHEMA_VERSION:
        raise ValueError("invalid_p145_matrix_schema")
    rows = value.get("cases")
    if not isinstance(rows, list) or len(rows) != 48:
        raise ValueError("invalid_p145_case_denominator")
    catalog = p145_release_case_catalog()
    if [row.get("case_id") for row in rows if isinstance(row, Mapping)] != [case["case_id"] for case in catalog]:
        raise ValueError("p145_case_order_invalid")
    for row, case in zip(rows, catalog, strict=True):
        _validate_row(row, case)
    passed = sum(1 for row in rows if row["passed"] is True)
    if value.get("expected") != 48 or value.get("passed") != passed or value.get("failed") != 48 - passed:
        raise ValueError("p145_matrix_totals_invalid")
    if value.get("aggregate_counters") != _aggregate(rows):
        raise ValueError("p145_aggregate_counters_invalid")
    if value.get("case_input_hash") != stable_hash([row["input_hash"] for row in rows]):
        raise ValueError("p145_input_hash_invalid")
    if value.get("case_config_hash") != stable_hash([row["config_hash"] for row in rows]):
        raise ValueError("p145_config_hash_invalid")
    if value.get("case_evidence_hash") != stable_hash([row["evidence_hash"] for row in rows]):
        raise ValueError("p145_evidence_hash_invalid")
    if value.get("runner_source_sha256") != current_p145_runner_source_hash() or value.get("catalog_hash") != stable_hash(catalog):
        raise ValueError("p145_runner_or_catalog_drift")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p145_matrix_hash_invalid")
    return value


def load_case_fixture(case_id: str, *, project_root: Path = Path(".")) -> dict[str, Any]:
    case = next(item for item in p145_release_case_catalog() if item["case_id"] == case_id)
    return validate_case_fixture(_read_fixture(project_root / case["fixture_path"]))


def execute_case(case_id: str, *, project_root: Path, output_dir: Path) -> dict[str, Any]:
    fixture = load_case_fixture(case_id, project_root=project_root)
    return process_episode_fixture(fixture, output_dir=output_dir).as_dict()


def _validate_row(row: Any, case: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "case_id", "scenario", "selector", "fixture_path", "input_hash", "config_hash",
        "evidence_hash", "expected_terminal_status", "observed_terminal_status", "expected_phase_path",
        "observed_phase_path", "expected_crash_point", "observed_crash_point", "expected_counts",
        "observed_counts", "forbidden_authority", "runtime_activity", "lab_activity", "evaluator_activity",
        "resource_usage", "command_proof", "passed", "failure_reason", "row_hash",
    }
    if not isinstance(row, Mapping) or set(row) != required or row.get("schema_version") != CASE_RESULT_SCHEMA_VERSION:
        raise ValueError("invalid_p145_row_schema")
    for key in ("case_id", "scenario", "selector", "fixture_path", "expected_terminal_status"):
        if row.get(key) != case[key]:
            raise ValueError(f"p145_row_{key}_invalid")
    fixture = validate_case_fixture(_read_fixture(Path(case["fixture_path"])))
    expected_bindings = {
        "input_hash": stable_hash(fixture["p133_event"]),
        "config_hash": stable_hash({"predecessor_bindings": fixture["predecessor_bindings"], "source_profile_bindings": fixture["source_profile_bindings"]}),
        "evidence_hash": fixture["evidence_hash"],
        "expected_terminal_status": fixture["expected_terminal_status"],
        "expected_phase_path": fixture["expected_phase_path"],
        "expected_crash_point": fixture["expected_crash_point"],
        "expected_counts": fixture["expected_counts"],
    }
    if any(row.get(key) != value for key, value in expected_bindings.items()):
        raise ValueError("p145_row_fixture_binding_invalid")
    if not isinstance(row.get("expected_phase_path"), list) or not row["expected_phase_path"]:
        raise ValueError("p145_expected_phase_path_empty")
    if row.get("observed_phase_path") != row["expected_phase_path"]:
        raise ValueError("p145_phase_path_mismatch")
    if row.get("observed_terminal_status") != row["expected_terminal_status"]:
        raise ValueError("p145_terminal_mismatch")
    if row.get("observed_crash_point") != row["expected_crash_point"]:
        raise ValueError("p145_crash_point_mismatch")
    if row.get("observed_counts") != row["expected_counts"]:
        raise ValueError("p145_observed_count_mismatch")
    if row.get("row_hash") != stable_hash({key: value for key, value in row.items() if key != "row_hash"}):
        raise ValueError("p145_row_hash_invalid")
    if row.get("passed") is not True or row.get("failure_reason") is not None:
        raise ValueError("p145_case_not_passed")
    counts = row.get("observed_counts")
    if not isinstance(counts, Mapping) or set(counts) != {"forbidden_authority", "runtime_activity", "lab_activity", "evaluator_activity", "resource_usage"}:
        raise ValueError("p145_counts_invalid")
    for field, keys in (
        ("forbidden_authority", FORBIDDEN_AUTHORITY_KEYS),
        ("runtime_activity", RUNTIME_ACTIVITY_KEYS),
        ("lab_activity", LAB_ACTIVITY_KEYS),
        ("evaluator_activity", EVALUATOR_ACTIVITY_KEYS),
        ("resource_usage", RESOURCE_USAGE_KEYS),
    ):
        if not exact_counter_map(counts.get(field), keys, exact_zero=field == "forbidden_authority"):
            raise ValueError(f"p145_observed_{field}_invalid")
    if not exact_counter_map(row.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, exact_zero=True):
        raise ValueError("p145_forbidden_counters_invalid")
    for field, keys in (
        ("runtime_activity", RUNTIME_ACTIVITY_KEYS),
        ("lab_activity", LAB_ACTIVITY_KEYS),
        ("evaluator_activity", EVALUATOR_ACTIVITY_KEYS),
        ("resource_usage", RESOURCE_USAGE_KEYS),
    ):
        if not exact_counter_map(row.get(field), keys):
            raise ValueError(f"p145_{field}_invalid")
    projected_counts = {
        "forbidden_authority": row["forbidden_authority"],
        "runtime_activity": row["runtime_activity"],
        "lab_activity": row["lab_activity"],
        "resource_usage": row["resource_usage"],
    }
    if any(projected_counts[field] != counts[field] for field in projected_counts):
        raise ValueError("p145_row_counter_projection_invalid")
    proof = row.get("command_proof")
    proof_fields = {
        "argv", "executable_provenance", "exit_code", "stdout_sha256", "stderr_sha256", "transcript_sha256",
        "stdout_b64", "stderr_b64", "transcript_form", "duration_ms", "selector_execution_proof",
    }
    if not isinstance(proof, Mapping) or set(proof) != proof_fields or proof.get("exit_code") != 0:
        raise ValueError("p145_command_proof_invalid")
    expected_argv_tail = ["-m", "pytest", "-q", "-s", "-p", "app.services.p145_runner", "--p145-case-id", case["case_id"], case["selector"]]
    argv = proof.get("argv")
    if (
        not isinstance(argv, list)
        or len(argv) != len(expected_argv_tail) + 1
        or not isinstance(argv[0], str)
        or not argv[0]
        or argv[1:] != expected_argv_tail
        or proof.get("transcript_form") != _TRANSCRIPT_FORM
        or type(proof.get("duration_ms")) is not int
        or proof["duration_ms"] < 0
    ):
        raise ValueError("p145_command_argv_invalid")
    if (
        argv[0] not in {f"{_PORTABLE_VENV_BIN}/{alias}" for alias in _APPROVED_PYTHON_ALIASES}
        or proof.get("executable_provenance") != _approved_executable_provenance()
    ):
        raise ValueError("p145_command_executable_provenance_invalid")
    try:
        stdout = base64.b64decode(proof["stdout_b64"], validate=True)
        stderr = base64.b64decode(proof["stderr_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("p145_transcript_base64_invalid") from exc
    transcript = stdout + stderr
    expected_transcript_hashes = {
        "stdout_sha256": "sha256:" + hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": "sha256:" + hashlib.sha256(stderr).hexdigest(),
        "transcript_sha256": "sha256:" + hashlib.sha256(transcript).hexdigest(),
    }
    if any(proof.get(key) != value for key, value in expected_transcript_hashes.items()):
        raise ValueError("p145_transcript_hash_invalid")
    expected_proof = {"executed": [case["selector"]], "passed": [case["selector"]]}
    if proof.get("selector_execution_proof") != expected_proof or _parse_json_marker(transcript, _PROOF_MARKER_PREFIX) != expected_proof:
        raise ValueError("p145_selector_proof_invalid")
    observed = _parse_json_marker(transcript, _RESULT_MARKER_PREFIX)
    if not isinstance(observed, Mapping):
        raise ValueError("p145_result_marker_missing")
    if observed.get("result_hash") != stable_hash({key: value for key, value in observed.items() if key != "result_hash"}):
        raise ValueError("p145_result_marker_hash_invalid")
    if observed.get("journal_path") != "$CASE_DIR/journal.jsonl" or observed.get("cursor_path") != "$CASE_DIR/cursor.json":
        raise ValueError("p145_result_portable_path_invalid")
    semantic = {
        "terminal_status": row["observed_terminal_status"], "phase_path": row["observed_phase_path"],
        "counts": row["observed_counts"], "crash_point": row["observed_crash_point"],
    }
    if any(observed.get(key) != value for key, value in semantic.items()):
        raise ValueError("p145_result_semantic_mismatch")
    if case["case_id"] == "P145-CASE-45":
        correlation = observed.get("correlation_action_receipt")
        correlated_event = fixture["correlated_p133_event"]
        action_receipt_hashes = observed.get("action_receipt_hashes")
        if (
            not isinstance(correlation, Mapping)
            or not isinstance(correlated_event, Mapping)
            or correlation.get("schema_version") != "p145.correlation_action_receipt.v1"
            or correlation.get("correlation_id") != fixture["p133_event"].get("correlation_id")
            or correlation.get("first_event_id") != fixture["p133_event"]["event_id"]
            or correlation.get("second_event_id") != correlated_event["event_id"]
            or correlation.get("action_reused") is not True
            or correlation.get("second_action_mutation") is not False
            or not isinstance(action_receipt_hashes, list)
            or action_receipt_hashes != [correlation.get("action_receipt_hash")]
            or not isinstance(observed.get("ack_receipt_hashes"), list)
            or len(observed["ack_receipt_hashes"]) != 2
            or "correlated_duplicate_action_reused" not in observed.get("command_notes", [])
        ):
            raise ValueError("p145_correlated_duplicate_proof_invalid")


def _row_passed(row: Mapping[str, Any], case: Mapping[str, Any]) -> tuple[bool, str | None]:
    if row["command_proof"]["exit_code"] != 0:
        return False, "selector_failed"
    if row["command_proof"].get("selector_execution_proof") != {"executed": [case["selector"]], "passed": [case["selector"]]}:
        return False, "selector_proof_mismatch"
    if row["observed_terminal_status"] != row["expected_terminal_status"]:
        return False, "terminal_mismatch"
    if not row["expected_phase_path"] or row["observed_phase_path"] != row["expected_phase_path"]:
        return False, "phase_path_mismatch"
    if row["observed_crash_point"] != row["expected_crash_point"]:
        return False, "crash_point_mismatch"
    for group, expected in row["expected_counts"].items():
        observed = row["observed_counts"].get(group, {})
        for key, value in expected.items():
            if observed.get(key) != value:
                return False, f"counter_mismatch:{group}.{key}"
    if not exact_counter_map(row["forbidden_authority"], FORBIDDEN_AUTHORITY_KEYS, exact_zero=True):
        return False, "forbidden_authority_nonzero"
    return True, None


def _aggregate(rows: list[Any]) -> dict[str, dict[str, int]]:
    return {
        "forbidden_authority": zero_forbidden_authority(),
        "runtime_activity": _sum(rows, "runtime_activity", RUNTIME_ACTIVITY_KEYS),
        "lab_activity": _sum(rows, "lab_activity", LAB_ACTIVITY_KEYS),
        "evaluator_activity": _sum(rows, "evaluator_activity", EVALUATOR_ACTIVITY_KEYS),
        "resource_usage": _sum(rows, "resource_usage", RESOURCE_USAGE_KEYS),
    }


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


def _evaluator_counters(exit_code: int, *, crash_injected: bool) -> dict[str, int]:
    counters = zero_evaluator_activity()
    counters["runner_invocation_count"] = 1
    counters["selector_command_count"] = 1
    counters["child_process_count"] = 1
    counters["crash_injection_count"] = int(crash_injected)
    counters["artifact_write_count"] = 1 if exit_code == 0 else 0
    return counters


def _zero_all_counts() -> dict[str, dict[str, int]]:
    return {
        "forbidden_authority": zero_forbidden_authority(),
        "runtime_activity": zero_runtime_activity(),
        "lab_activity": zero_lab_activity(),
        "evaluator_activity": zero_evaluator_activity(),
        "resource_usage": zero_resource_usage(),
    }


def _read_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object)
    if not isinstance(value, dict):
        raise ValueError("fixture_object_required")
    return value


def _parse_json_marker(output: bytes, prefix: str) -> Any | None:
    markers = [line.removeprefix(prefix) for line in output.decode("utf-8").splitlines() if line.startswith(prefix)]
    if not markers:
        return None
    if len(markers) != 1:
        raise ValueError("p145_marker_ambiguous")
    parsed = json.loads(markers[0], object_pairs_hook=_strict_json_object)
    if markers[0] != json.dumps(parsed, sort_keys=True, separators=(",", ":")):
        raise ValueError("p145_marker_noncanonical")
    return parsed


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def pytest_addoption(parser: Any) -> None:
    parser.addoption("--p145-case-id", action="store", default=None)


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
    case_id = session.config.getoption("--p145-case-id")
    if case_id is None:
        return
    proof = {"executed": _PYTEST_EXECUTED, "passed": [item for item in _PYTEST_EXECUTED if item in _PYTEST_PASSED]}
    sys.stdout.write("\n" + _PROOF_MARKER_PREFIX + json.dumps(proof, sort_keys=True, separators=(",", ":")) + "\n")
    if _CASE_RESULTS:
        sys.stdout.write(_RESULT_MARKER_PREFIX + json.dumps(_CASE_RESULTS[-1], sort_keys=True, separators=(",", ":")) + "\n")


def record_pytest_case_result(result: Mapping[str, Any]) -> None:
    _CASE_RESULTS.append(deepcopy(dict(result)))


_SCENARIOS = {case_id: name.removeprefix("test_").replace("_", " ") for case_id, name in CASE_SELECTOR_NAMES.items()}
_RECOVERY_CASES = {
    "P145-CASE-01",
    "P145-CASE-02",
    "P145-CASE-03",
    "P145-CASE-04",
    "P145-CASE-05",
    "P145-CASE-13",
    "P145-CASE-14",
    "P145-CASE-18",
    "P145-CASE-19",
    "P145-CASE-36",
    "P145-CASE-39",
    "P145-CASE-44",
    "P145-CASE-45",
}
_ROLLBACK_CASES = {"P145-CASE-10", "P145-CASE-37", "P145-CASE-38", "P145-CASE-41", "P145-CASE-43"}
_TERMINALS = {case_id: ("recovery_verified" if case_id in _RECOVERY_CASES else "rollback_verified" if case_id in _ROLLBACK_CASES else "human_escalation_required") for case_id in CASE_SELECTOR_NAMES}
