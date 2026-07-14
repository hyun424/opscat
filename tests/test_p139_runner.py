from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p139_local_triage_service import zero_forbidden_authority
from app.services.p139_runner import (
    CASE_MATRIX_SCHEMA_VERSION,
    p139_release_case_catalog,
    validate_p139_case_matrix,
)


def qualified_matrix() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p139_release_case_catalog():
        row: dict[str, Any] = {
            "schema_version": "p139.release_case_result.v1",
            **case,
            "executed": True,
            "passed": True,
            "return_code": 0,
            "output_sha256": "sha256:" + "0" * 64,
            "wall_time_ms": 1,
            "evaluator_activity": {"subprocess_launch_count": 1},
            "asserted_runtime_forbidden_authority": zero_forbidden_authority(),
        }
        row["case_evidence_hash"] = stable_hash(row)
        rows.append(row)
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "expected": 32,
        "passed": 32,
        "failed": 0,
        "cases": rows,
    }
    matrix["matrix_hash"] = stable_hash(matrix)
    return matrix


def test_catalog_is_exact_ordered_immutable_denominator() -> None:
    catalog = p139_release_case_catalog()
    assert len(catalog) == 32
    assert [row["case_id"] for row in catalog] == [f"P139-CASE-{index:02d}" for index in range(1, 33)]
    assert validate_p139_case_matrix(qualified_matrix())["passed"] == 32


def test_matrix_rejects_skip_failure_authority_and_hash_forgery() -> None:
    for mutation in ("skip", "authority", "hash"):
        matrix = qualified_matrix()
        row = matrix["cases"][0]
        if mutation == "skip":
            row["executed"] = False
        elif mutation == "authority":
            row["asserted_runtime_forbidden_authority"]["network_call_count"] = 1
        else:
            row["case_evidence_hash"] = "sha256:" + "f" * 64
        if mutation != "hash":
            row["case_evidence_hash"] = stable_hash({key: value for key, value in row.items() if key != "case_evidence_hash"})
            matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
        with pytest.raises(ValueError):
            validate_p139_case_matrix(deepcopy(matrix))
