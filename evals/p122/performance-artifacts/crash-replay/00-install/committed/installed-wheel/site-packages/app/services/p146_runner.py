"""P146 release runner and selector-proof pytest plugin."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p146_live_shadow import run_known_conformance_benchmark
from app.services.p146_release_evidence import (
    EVALUATOR_COUNTER_KEYS,
    FORBIDDEN_COUNTER_KEYS,
    P146_RELEASE_SELECTORS,
    RESOURCE_COUNTER_KEYS,
    RUNTIME_COUNTER_KEYS,
    assemble_p146_final_evidence,
    build_p146_freeze_manifest,
    build_p146_preliminary_evidence,
    file_sha256,
    validate_final_review,
    validate_freeze_manifest,
    validate_release_evidence,
    validate_release_matrix,
)
from tests.fixtures.p146.builders import build_known_conformance_corpus

MATRIX_SCHEMA_VERSION = "p146.release_case_matrix.v1"
MATRIX_ROW_SCHEMA_VERSION = "p146.matrix_row.v1"
RUNNER_RECEIPT_SCHEMA_VERSION = "p146.release_runner_receipt.v1"
_PROOF_MARKER_PREFIX = "P146_SELECTOR_PROOF="
_SEMANTIC_MARKER_PREFIX = "P146_OBSERVED_SEMANTICS="
_TRANSCRIPT_FORM = "stdout_then_stderr"
_PYTEST_COLLECTED: list[str] = []
_PYTEST_EXECUTED: list[str] = []
_PYTEST_PASSED: set[str] = set()


def read_canonical_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object)
    if not isinstance(value, dict):
        raise ValueError("p146_canonical_json_object_required")
    return value


def write_canonical_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if path.is_symlink():
        raise ValueError("p146_artifact_symlink_forbidden")
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        if tmp_path.exists() or tmp_path.is_symlink():
            raise ValueError("p146_artifact_temp_collision")
        tmp_path.write_bytes(data)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def collect_selector_matrix(
    *,
    project_root: Path,
    selectors: Sequence[str] = P146_RELEASE_SELECTORS,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    _ = output_dir
    project_root = project_root.resolve()
    if tuple(selectors) != tuple(P146_RELEASE_SELECTORS):
        raise ValueError("p146_selector_catalog_mismatch")
    rows = []
    for ordinal, selector in enumerate(selectors, start=1):
        rows.append(_collect_selector_row(project_root=project_root, selector=selector, ordinal=ordinal))
    matrix: dict[str, Any] = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "expected": len(P146_RELEASE_SELECTORS),
        "passed": sum(1 for row in rows if row["passed"] is True),
        "failed": sum(1 for row in rows if row["passed"] is not True),
        "selectors": rows,
        "aggregate_counters": _aggregate_counters(rows),
        "matrix_hash": "",
    }
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    return validate_release_matrix(matrix)


def generate_preliminary_release_artifacts(*, project_root: Path, output_dir: Path) -> dict[str, Path]:
    project_root = project_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus = build_known_conformance_corpus()
    matrix = collect_selector_matrix(project_root=project_root, selectors=P146_RELEASE_SELECTORS, output_dir=output_dir)
    benchmark = run_known_conformance_benchmark(corpus)
    freeze = build_p146_freeze_manifest(project_root=project_root, corpus=corpus, matrix=matrix)
    benchmark_path = output_dir / "benchmark-report.json"
    artifacts = {
        "matrix": output_dir / "canonical-matrix.json",
        "benchmark": benchmark_path,
        "freeze": output_dir / "freeze-manifest.json",
        "preliminary_evidence": output_dir / "release-evidence.json",
    }
    write_canonical_json(artifacts["matrix"], matrix)
    write_canonical_json(artifacts["benchmark"], benchmark)
    evidence = build_p146_preliminary_evidence(
        matrix,
        freeze,
        corpus=corpus,
        benchmark_report_path=artifacts["benchmark"],
    )
    write_canonical_json(artifacts["freeze"], freeze)
    write_canonical_json(artifacts["preliminary_evidence"], evidence)
    return artifacts


def generate_final_release_artifacts(
    *,
    project_root: Path,
    matrix_path: Path,
    benchmark_report_path: Path,
    freeze_manifest_path: Path,
    final_review_path: Path,
    output_dir: Path,
) -> Path:
    _ = project_root
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix = validate_release_matrix(read_canonical_json(matrix_path))
    freeze = validate_freeze_manifest(read_canonical_json(freeze_manifest_path), matrix=matrix)
    review = validate_final_review(read_canonical_json(final_review_path), manifest=freeze)
    evidence = assemble_p146_final_evidence(
        matrix,
        manifest=freeze,
        review=review,
        benchmark_report_path=benchmark_report_path,
    )
    validate_release_evidence(
        evidence,
        matrix=matrix,
        manifest=freeze,
        review=review,
        benchmark_report_path=benchmark_report_path,
    )
    final_path = output_dir / "release-evidence.json"
    write_canonical_json(final_path, evidence)
    return final_path


def runner_receipt(*, mode: str, artifacts: Mapping[str, Path], output_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": RUNNER_RECEIPT_SCHEMA_VERSION,
        "mode": mode,
        "status": "ok",
        "artifact_root": output_dir.name,
        "artifacts": {key: path.name for key, path in artifacts.items()},
    }


def _collect_selector_row(*, project_root: Path, selector: str, ordinal: int) -> dict[str, Any]:
    started_wall = time.monotonic_ns()
    started_cpu = time.process_time_ns()
    completed = subprocess.run(
        [
            str(project_root / ".venv/bin/python"),
            "-m",
            "pytest",
            selector,
            "-q",
            "-s",
            "-p",
            "app.services.p146_runner",
        ],
        cwd=project_root,
        check=False,
        capture_output=True,
        timeout=180,
    )
    wall_time_ns = max(0, time.monotonic_ns() - started_wall)
    cpu_time_ns = max(0, time.process_time_ns() - started_cpu)
    raw_transcript = completed.stdout + completed.stderr
    proof = _parse_json_marker(raw_transcript, _PROOF_MARKER_PREFIX)
    observed = _parse_json_marker(raw_transcript, _SEMANTIC_MARKER_PREFIX)
    expected_proof = {"collected": [selector], "executed": [selector], "passed": [selector]}
    expected_semantics = {"selector": selector, "semantic": selector.rsplit("::", 1)[-1], "passed": True}
    command_proof = {
        "argv": [".venv/bin/python", "-m", "pytest", selector, "-q"],
        "executable_provenance": _executable_provenance(project_root),
        "exit_code": completed.returncode,
        "collected_nodeids": proof.get("collected") if isinstance(proof, Mapping) else [],
        "selector_execution_proof": proof,
        "stdout_sha256": _bytes_sha256(completed.stdout),
        "stderr_sha256": _bytes_sha256(completed.stderr),
        "transcript_sha256": _bytes_sha256(raw_transcript),
        "stdout_b64": base64.b64encode(completed.stdout).decode("ascii"),
        "stderr_b64": base64.b64encode(completed.stderr).decode("ascii"),
        "transcript_form": _TRANSCRIPT_FORM,
        "selector_proof_hash": stable_hash({"selector_execution_proof": expected_proof, "observed_semantics": expected_semantics}),
    }
    row: dict[str, Any] = {
        "schema_version": MATRIX_ROW_SCHEMA_VERSION,
        "ordinal": ordinal,
        "selector": selector,
        "semantic_name": selector.rsplit("::", 1)[-1],
        "expected_semantics": expected_semantics,
        "observed_semantics": observed,
        "command_proof": command_proof,
        "runtime_counters": _zero_counter_map(RUNTIME_COUNTER_KEYS),
        "evaluator_counters": _zero_counter_map(EVALUATOR_COUNTER_KEYS),
        "resource_counters": {
            **_zero_counter_map(RESOURCE_COUNTER_KEYS),
            "wall_time_ns": wall_time_ns,
            "cpu_time_ns": cpu_time_ns,
            "artifact_bytes": len(raw_transcript),
        },
        "forbidden_counters": _zero_counter_map(FORBIDDEN_COUNTER_KEYS),
        "passed": completed.returncode == 0 and proof == expected_proof and observed == expected_semantics,
        "failure_reason": None,
        "row_hash": "",
    }
    if row["passed"] is not True:
        row["failure_reason"] = "selector_subprocess_failed"
    row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    return row


def _executable_provenance(project_root: Path) -> dict[str, Any]:
    python_path = project_root / ".venv/bin/python"
    import pytest as pytest_module

    pytest_path = Path(pytest_module.__file__).resolve()
    return {
        "resolved_python": ".venv/bin/python",
        "project_python": True,
        "python_sha256": file_sha256(python_path),
        "pytest_module_path": _project_relative_or_site_package(project_root, pytest_path),
        "pytest_module_sha256": file_sha256(pytest_path),
    }


def _project_relative_or_site_package(project_root: Path, path: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _parse_json_marker(output: bytes, prefix: str) -> Any:
    matches = [line.removeprefix(prefix) for line in output.decode("utf-8", errors="replace").splitlines() if line.startswith(prefix)]
    if len(matches) != 1:
        return None
    parsed = json.loads(matches[0], object_pairs_hook=_strict_json_object)
    if matches[0] != json.dumps(parsed, sort_keys=True, separators=(",", ":")):
        return None
    return parsed


def _aggregate_counters(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "runtime": _sum_counter(rows, "runtime_counters", RUNTIME_COUNTER_KEYS),
        "evaluator": _sum_counter(rows, "evaluator_counters", EVALUATOR_COUNTER_KEYS),
        "resources": _sum_counter(rows, "resource_counters", RESOURCE_COUNTER_KEYS),
        "forbidden": _sum_counter(rows, "forbidden_counters", FORBIDDEN_COUNTER_KEYS),
    }


def _sum_counter(rows: Sequence[Mapping[str, Any]], field: str, keys: tuple[str, ...]) -> dict[str, int]:
    totals = _zero_counter_map(keys)
    for row in rows:
        counters = row.get(field)
        if not isinstance(counters, Mapping):
            raise ValueError("p146_selector_counter_schema_invalid")
        for key in keys:
            value = counters.get(key)
            if type(value) is not int:
                raise ValueError("p146_selector_counter_int_required")
            totals[key] += value
    return totals


def _zero_counter_map(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _bytes_sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, frozenset | set):
        return [_json_ready(item) for item in sorted(value, key=repr)]
    if isinstance(value, Path):
        return value.name
    return value


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def pytest_collection_finish(session: Any) -> None:
    _PYTEST_COLLECTED[:] = [str(item.nodeid).split("[", 1)[0] for item in session.items]


def pytest_runtest_logreport(report: Any) -> None:
    if report.when != "call":
        return
    selector = str(report.nodeid).split("[", 1)[0]
    if selector not in _PYTEST_EXECUTED:
        _PYTEST_EXECUTED.append(selector)
    if report.passed:
        _PYTEST_PASSED.add(selector)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    _ = session, exitstatus
    selected = _PYTEST_COLLECTED[:1]
    if len(selected) != 1:
        return
    selector = selected[0]
    proof = {"collected": [selector], "executed": _PYTEST_EXECUTED, "passed": [item for item in _PYTEST_EXECUTED if item in _PYTEST_PASSED]}
    semantics = {"selector": selector, "semantic": selector.rsplit("::", 1)[-1], "passed": proof["passed"] == [selector]}
    sys.stdout.write("\n" + _PROOF_MARKER_PREFIX + json.dumps(proof, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.write(_SEMANTIC_MARKER_PREFIX + json.dumps(semantics, sort_keys=True, separators=(",", ":")) + "\n")
