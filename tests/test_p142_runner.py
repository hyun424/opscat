from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p142_runner import (
    ALLOWED_TRANSPORT_COUNTER_KEYS,
    FORBIDDEN_NON_TRANSPORT_COUNTER_KEYS,
    TRANSPORT_ACTIVE_CASE_IDS,
    build_p142_case_matrix,
    build_p142_case_result,
    current_p142_runner_source_hash,
    p142_case_execution_provenance,
    p142_release_case_catalog,
    run_p142_preliminary_matrix,
    validate_p142_case_matrix,
    zero_allowed_transport_counters,
    zero_forbidden_non_transport_counters,
)


def transport_counters(**overrides: int) -> dict[str, int]:
    counters = zero_allowed_transport_counters()
    counters.update(
        {
            "loopback_socket_attempt_count": 2,
            "loopback_request_commit_count": 2,
            "loopback_request_byte_count": 128,
            "loopback_complete_response_count": 2,
            "loopback_response_byte_count": 16,
            "loopback_http_2xx_count": 2,
        }
    )
    counters.update(overrides)
    return counters


def counter_marker(counters: dict[str, int]) -> bytes:
    return f"P142_CASE_COUNTERS={json.dumps(counters, sort_keys=True, separators=(',', ':'))}\n".encode()


def qualified_p142_matrix() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p142_release_case_catalog():
        counters = transport_counters() if case["case_id"] in TRANSPORT_ACTIVE_CASE_IDS else zero_allowed_transport_counters()
        output = counter_marker(counters) if case["case_id"] in TRANSPORT_ACTIVE_CASE_IDS else b""
        row = {
            "schema_version": "p142.release_case_result.v1",
            **case,
            "executed": True,
            "passed": True,
            "return_code": 0,
            "output_sha256": "sha256:" + hashlib.sha256(output).hexdigest(),
            "captured_output_b64": base64.b64encode(output).decode("ascii"),
            "wall_time_ms": 1,
            "evaluator_activity": {"subprocess_launch_count": 1},
            "execution_provenance": p142_case_execution_provenance(case),
            "forbidden_non_transport_authority_counters": zero_forbidden_non_transport_counters(),
            "allowed_transport_activity_counters": counters,
        }
        row["case_evidence_hash"] = stable_hash(row)
        rows.append(row)
    return build_p142_case_matrix(rows)


def test_p142_catalog_is_exact_ordered_immutable_denominator() -> None:
    catalog = p142_release_case_catalog()
    assert len(catalog) == 44
    assert [row["case_id"] for row in catalog] == [f"P142-CASE-{index:02d}" for index in range(1, 45)]
    assert catalog[0] == {
        "case_id": "P142-CASE-01",
        "scenario": "canonical_config",
        "selectors": ["tests/test_p142_loopback_transport_lab.py::test_config_accepts_closed_numeric_loopback_routes"],
    }
    assert catalog[43] == {
        "case_id": "P142-CASE-44",
        "scenario": "final_does_not_rewrite_frozen_inputs",
        "selectors": ["tests/test_p142_release_evidence.py::test_p142_final_mode_does_not_rewrite_frozen_inputs"],
    }
    assert tuple(zero_forbidden_non_transport_counters()) == FORBIDDEN_NON_TRANSPORT_COUNTER_KEYS
    assert tuple(zero_allowed_transport_counters()) == ALLOWED_TRANSPORT_COUNTER_KEYS
    validated = validate_p142_case_matrix(qualified_p142_matrix())
    assert validated["runner_source_sha256"] == current_p142_runner_source_hash()
    assert validated["passed"] == 44


@pytest.mark.parametrize(
    "mutation",
    [
        "skip",
        "definition",
        "selector",
        "result",
        "forbidden_nonzero",
        "forbidden_unknown",
        "forbidden_missing",
        "forbidden_boolean",
        "transport_boolean",
        "transport_unknown",
        "transport_negative",
        "transport_active_missing_marker",
        "transport_active_zero_attempt",
        "transport_active_status_impossible",
        "transport_inactive_marker_forgery",
        "matrix_transport_forged",
        "hash",
        "provenance",
        "transcript",
        "transcript_bytes",
        "evaluator_activity",
    ],
)
def test_p142_matrix_rejects_skip_authority_activity_hash_and_boolean_forgery(mutation: str) -> None:
    matrix = qualified_p142_matrix()
    row = matrix["cases"][0]
    if mutation == "skip":
        row["executed"] = False
    elif mutation == "definition":
        row["scenario"] = "forged"
    elif mutation == "selector":
        row["selectors"] = ["tests/test_p142_runner.py::forged"]
    elif mutation == "result":
        row["passed"] = False
    elif mutation == "forbidden_nonzero":
        row["forbidden_non_transport_authority_counters"]["credential_read_count"] = 1
    elif mutation == "forbidden_unknown":
        row["forbidden_non_transport_authority_counters"]["hidden_nonzero_authority_count"] = 1
    elif mutation == "forbidden_missing":
        del row["forbidden_non_transport_authority_counters"]["credential_read_count"]
    elif mutation == "forbidden_boolean":
        row["forbidden_non_transport_authority_counters"]["credential_read_count"] = False
    elif mutation == "transport_boolean":
        row["allowed_transport_activity_counters"]["loopback_socket_attempt_count"] = True
    elif mutation == "transport_unknown":
        row["allowed_transport_activity_counters"]["hidden_transport_count"] = 1
    elif mutation == "transport_negative":
        row["allowed_transport_activity_counters"]["loopback_socket_attempt_count"] = -1
    elif mutation == "transport_active_missing_marker":
        row = next(item for item in matrix["cases"] if item["case_id"] in TRANSPORT_ACTIVE_CASE_IDS)
        row["captured_output_b64"] = ""
        row["output_sha256"] = "sha256:" + hashlib.sha256(b"").hexdigest()
    elif mutation == "transport_active_zero_attempt":
        row = next(item for item in matrix["cases"] if item["case_id"] in TRANSPORT_ACTIVE_CASE_IDS)
        counters = transport_counters(loopback_socket_attempt_count=0)
        row["allowed_transport_activity_counters"] = counters
        output = counter_marker(counters)
        row["captured_output_b64"] = base64.b64encode(output).decode("ascii")
        row["output_sha256"] = "sha256:" + hashlib.sha256(output).hexdigest()
    elif mutation == "transport_active_status_impossible":
        row = next(item for item in matrix["cases"] if item["case_id"] in TRANSPORT_ACTIVE_CASE_IDS)
        counters = transport_counters(loopback_complete_response_count=2, loopback_http_2xx_count=1)
        row["allowed_transport_activity_counters"] = counters
        output = counter_marker(counters)
        row["captured_output_b64"] = base64.b64encode(output).decode("ascii")
        row["output_sha256"] = "sha256:" + hashlib.sha256(output).hexdigest()
    elif mutation == "transport_inactive_marker_forgery":
        counters = transport_counters()
        output = counter_marker(counters)
        row["captured_output_b64"] = base64.b64encode(output).decode("ascii")
        row["output_sha256"] = "sha256:" + hashlib.sha256(output).hexdigest()
        row["allowed_transport_activity_counters"] = counters
    elif mutation == "matrix_transport_forged":
        matrix["allowed_transport_activity_counters"]["loopback_socket_attempt_count"] = 999
    elif mutation == "provenance":
        row["execution_provenance"]["command_argv"] = ["pytest"]
    elif mutation == "transcript":
        matrix["transcript_manifest_hash"] = "sha256:" + "e" * 64
    elif mutation == "transcript_bytes":
        row["captured_output_b64"] = "Zm9yZ2Vk"
    elif mutation == "evaluator_activity":
        row["evaluator_activity"] = {"subprocess_launch_count": 2}
    else:
        row["case_evidence_hash"] = "sha256:" + "f" * 64
    if mutation not in {"hash", "transcript", "matrix_transport_forged"}:
        row["case_evidence_hash"] = stable_hash({key: value for key, value in row.items() if key != "case_evidence_hash"})
        matrix["allowed_transport_activity_counters"] = {
            key: sum(case["allowed_transport_activity_counters"][key] for case in matrix["cases"])
            for key in zero_allowed_transport_counters()
        }
        matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    with pytest.raises(ValueError):
        validate_p142_case_matrix(deepcopy(matrix))


def test_p142_case_result_records_subprocess_evaluator_provenance() -> None:
    case = p142_release_case_catalog()[0]
    row = build_p142_case_result(case, return_code=0, output=b"ok", wall_time_ms=7)
    assert row["evaluator_activity"] == {"subprocess_launch_count": 1}
    assert row["execution_provenance"] == p142_case_execution_provenance(case)
    assert row["passed"] is True
    assert validate_p142_case_matrix(build_p142_case_matrix([row, *qualified_p142_matrix()["cases"][1:]]))["passed"] == 44


def test_p142_preliminary_runner_parses_transport_counter_markers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str],
        *,
        cwd: Path,
        check: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, check, capture_output, timeout
        calls.append(argv)
        selector = argv[-1]
        case = next(item for item in p142_release_case_catalog() if selector in item["selectors"])
        output = counter_marker(transport_counters()) if case["case_id"] in TRANSPORT_ACTIVE_CASE_IDS else b""
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    matrix = run_p142_preliminary_matrix(tmp_path)
    assert matrix["passed"] == 44
    assert all("-s" in argv for argv in calls)
    assert matrix["allowed_transport_activity_counters"]["loopback_socket_attempt_count"] == 2 * len(TRANSPORT_ACTIVE_CASE_IDS)


def test_p142_preliminary_runner_rejects_missing_active_transport_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(
        argv: list[str],
        *,
        cwd: Path,
        check: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[bytes]:
        del cwd, check, capture_output, timeout
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="transport_counter_marker_missing"):
        run_p142_preliminary_matrix(tmp_path)
