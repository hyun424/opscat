from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p144_runner import (
    FORBIDDEN_COUNTER_KEYS,
    build_p144_case_matrix,
    build_p144_case_result,
    current_p144_runner_source_hash,
    p144_case_execution_provenance,
    p144_release_case_catalog,
    validate_p144_case_matrix,
    zero_adapter_counters,
    zero_forbidden_counters,
    zero_transport_counters,
)


def _marker(name: str, value: object) -> bytes:
    return f"{name}={json.dumps(value, sort_keys=True, separators=(',', ':'))}\n".encode()


def _output(case: dict[str, Any], adapter: dict[str, int] | None = None) -> bytes:
    return b"".join(
        (
            _marker("P144_SELECTOR_PROOF", {"executed": case["selectors"], "passed": case["selectors"]}),
            _marker(
                "P144_CASE_PROVENANCE",
                {
                    "case_id": case["case_id"],
                    "runner": "run_p144_preliminary_matrix",
                    "runner_source_sha256": current_p144_runner_source_hash(),
                    "selectors": case["selectors"],
                },
            ),
            _marker("P144_FORBIDDEN_COUNTERS", zero_forbidden_counters()),
            _marker("P144_ADAPTER_COUNTERS", adapter or zero_adapter_counters()),
            _marker("P144_TRANSPORT_COUNTERS", zero_transport_counters()),
        )
    )


def qualified_p144_matrix() -> dict[str, Any]:
    rows = [
        build_p144_case_result(case, exit_code=0, stdout=_output(case), stderr=b"", duration_ms=1)
        for case in p144_release_case_catalog()
    ]
    return build_p144_case_matrix(rows)


def test_matrix_rejects_skip_reorder_hash_transcript_and_boolean_forgery() -> None:
    catalog = p144_release_case_catalog()
    assert [row["case_id"] for row in catalog] == [f"P144-CASE-{index:02d}" for index in range(1, 65)]
    assert catalog[0]["selectors"] == ["tests/test_p144_provider_adapter_lab.py::test_config_accepts_exact_closed_schema"]
    assert catalog[-1]["selectors"] == ["tests/test_p144_release_evidence.py::test_final_evidence_binds_freeze_review_dependencies_and_limitations"]
    assert tuple(zero_forbidden_counters()) == FORBIDDEN_COUNTER_KEYS
    matrix = qualified_p144_matrix()
    assert validate_p144_case_matrix(matrix)["passed"] == 64
    for mutation in ("skip", "reorder", "hash", "transcript", "boolean", "forbidden"):
        bad = deepcopy(matrix)
        if mutation == "skip":
            bad["rows"][0]["selector_result"] = "failed"
        elif mutation == "reorder":
            bad["rows"][0], bad["rows"][1] = bad["rows"][1], bad["rows"][0]
        elif mutation == "hash":
            bad["rows"][0]["row_hash"] = "sha256:" + "0" * 64
        elif mutation == "transcript":
            bad["rows"][1]["stdout_b64"] = bad["rows"][0]["stdout_b64"]
            bad["rows"][1]["transcript_sha256"] = bad["rows"][0]["transcript_sha256"]
            bad["rows"][1]["row_hash"] = stable_hash({key: value for key, value in bad["rows"][1].items() if key != "row_hash"})
        elif mutation == "boolean":
            bad["rows"][0]["forbidden_counters"]["credential_read_count"] = False
        else:
            bad["rows"][0]["forbidden_counters"]["credential_read_count"] = 1
        bad["matrix_hash"] = stable_hash({key: value for key, value in bad.items() if key != "matrix_hash"})
        with pytest.raises(ValueError):
            validate_p144_case_matrix(bad)


def test_case_result_records_exact_command_and_runner_identity() -> None:
    case = p144_release_case_catalog()[0]
    row = build_p144_case_result(case, exit_code=0, stdout=_output(case), stderr=b"", duration_ms=1)
    assert row["runner_source_sha256"] == current_p144_runner_source_hash()
    assert row["command_argv"] == p144_case_execution_provenance(case)["command_argv"]


def test_matrix_adapter_and_transport_counter_aggregate_is_recomputed() -> None:
    catalog = p144_release_case_catalog()
    adapter = zero_adapter_counters()
    adapter["adapter_request_write_count"] = 4
    rows = [
        build_p144_case_result(case, exit_code=0, stdout=_output(case, adapter if index == 0 else None), stderr=b"", duration_ms=1)
        for index, case in enumerate(catalog)
    ]
    matrix = build_p144_case_matrix(rows)
    assert matrix["adapter_counters"]["adapter_request_write_count"] == 4
    matrix["adapter_counters"]["adapter_request_write_count"] = 5
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    with pytest.raises(ValueError, match="adapter"):
        validate_p144_case_matrix(matrix)
