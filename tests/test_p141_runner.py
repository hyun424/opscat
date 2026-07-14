from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters as zero_p133_authority
from app.services.p141_notification_authority import zero_notification_authority_counters
from app.services.p141_runner import (
    CASE_MATRIX_SCHEMA_VERSION,
    current_p141_runner_source_hash,
    p141_case_execution_provenance,
    p141_release_case_catalog,
    validate_p141_case_matrix,
)


def qualified_p141_matrix() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in p141_release_case_catalog():
        row: dict[str, Any] = {
            "schema_version": "p141.release_case_result.v1",
            **case,
            "executed": True,
            "passed": True,
            "return_code": 0,
            "output_sha256": "sha256:" + hashlib.sha256(b"").hexdigest(),
            "captured_output_b64": "",
            "wall_time_ms": 1,
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
        "passed": 36,
        "failed": 0,
        "cases": rows,
    }
    matrix["transcript_manifest_hash"] = stable_hash(
        [{"case_id": row["case_id"], "output_sha256": row["output_sha256"], "return_code": row["return_code"]} for row in rows]
    )
    matrix["matrix_hash"] = stable_hash(matrix)
    return matrix


def test_p141_catalog_is_exact_ordered_immutable_denominator() -> None:
    catalog = p141_release_case_catalog()
    assert len(catalog) == 36
    assert [row["case_id"] for row in catalog] == [f"P141-CASE-{index:02d}" for index in range(1, 37)]
    assert validate_p141_case_matrix(qualified_p141_matrix())["passed"] == 36


@pytest.mark.parametrize(
    "mutation",
    ["skip", "definition", "result", "p133", "p141", "hash", "boolean", "provenance", "transcript", "transcript_bytes"],
)
def test_p141_matrix_rejects_skip_authority_and_hash_forgery(mutation: str) -> None:
    matrix = qualified_p141_matrix()
    row = matrix["cases"][0]
    if mutation == "skip":
        row["executed"] = False
    elif mutation == "definition":
        row["scenario"] = "forged"
    elif mutation == "result":
        row["passed"] = False
    elif mutation == "p133":
        row["asserted_p133_authority"]["network_mutation_count"] = 1
    elif mutation == "p141":
        row["asserted_p141_authority"]["network_call_count"] = 1
    elif mutation == "boolean":
        row["asserted_p141_authority"]["network_call_count"] = False
    elif mutation == "provenance":
        row["execution_provenance"]["runner"] = "forged"
    elif mutation == "transcript":
        matrix["transcript_manifest_hash"] = "sha256:" + "e" * 64
    elif mutation == "transcript_bytes":
        row["captured_output_b64"] = "Zm9yZ2Vk"
    else:
        row["case_evidence_hash"] = "sha256:" + "f" * 64
    if mutation not in {"hash", "transcript"}:
        row["case_evidence_hash"] = stable_hash({key: value for key, value in row.items() if key != "case_evidence_hash"})
        matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    with pytest.raises(ValueError):
        validate_p141_case_matrix(deepcopy(matrix))
