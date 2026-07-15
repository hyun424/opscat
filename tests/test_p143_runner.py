from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

import app.services.p143_egress_contract_lab as p143
import app.services.p143_runner as p143_runner
from app.services.p110_evaluation import stable_hash
from app.services.p143_runner import (
    FORBIDDEN_COUNTER_KEYS,
    build_p143_case_matrix,
    build_p143_case_result,
    current_p143_runner_source_hash,
    p143_case_execution_provenance,
    p143_release_case_catalog,
    validate_p143_case_matrix,
    zero_allowed_counters,
    zero_forbidden_counters,
)


def _marker(name: str, value: object) -> bytes:
    return f"{name}={json.dumps(value, sort_keys=True, separators=(',', ':'))}\n".encode()


def _output(case: dict[str, Any], counters: dict[str, int] | None = None) -> bytes:
    return b"".join(
        (
            _marker("P143_SELECTOR_PROOF", {"executed": case["selectors"], "passed": case["selectors"]}),
            _marker(
                "P143_CASE_PROVENANCE",
                {
                    "case_id": case["case_id"],
                    "runner": "run_p143_preliminary_matrix",
                    "runner_source_sha256": current_p143_runner_source_hash(),
                    "selectors": case["selectors"],
                },
            ),
            _marker("P143_FORBIDDEN_COUNTERS", zero_forbidden_counters()),
            _marker("P143_CASE_COUNTERS", counters or zero_allowed_counters()),
        )
    )


def qualified_p143_matrix() -> dict[str, Any]:
    rows = [
        build_p143_case_result(case, exit_code=0, stdout=_output(case), stderr=b"", duration_ms=3)
        for case in p143_release_case_catalog()
    ]
    return build_p143_case_matrix(rows)


def test_matrix_rejects_skip_reorder_hash_and_boolean_forgery() -> None:
    catalog = p143_release_case_catalog()
    assert [row["case_id"] for row in catalog] == [f"P143-CASE-{index:02d}" for index in range(1, 53)]
    assert catalog[0]["selectors"] == ["tests/test_p143_egress_contract_lab.py::test_config_accepts_exact_closed_schema"]
    assert catalog[-1]["selectors"] == ["tests/test_p143_release_evidence.py::test_final_evidence_binds_all_frozen_inputs_and_review"]
    assert tuple(zero_forbidden_counters()) == FORBIDDEN_COUNTER_KEYS
    matrix = qualified_p143_matrix()
    assert validate_p143_case_matrix(matrix)["runner_source_sha256"] == current_p143_runner_source_hash()
    for mutation in ("skip", "reorder", "hash", "boolean", "forbidden", "selector"):
        bad = deepcopy(matrix)
        if mutation == "skip":
            bad["rows"][0]["selector_result"] = "skipped"
        elif mutation == "reorder":
            bad["rows"][0], bad["rows"][1] = bad["rows"][1], bad["rows"][0]
        elif mutation == "hash":
            bad["rows"][0]["row_hash"] = "sha256:" + "0" * 64
        elif mutation == "boolean":
            bad["rows"][0]["forbidden_counters"]["credential_read_count"] = False
        elif mutation == "forbidden":
            bad["rows"][0]["forbidden_counters"]["credential_read_count"] = 1
        else:
            bad["rows"][0]["selectors"] = ["tests/test_p143_runner.py::forged"]
        with pytest.raises(ValueError):
            validate_p143_case_matrix(bad)


def test_case_result_records_source_bound_runner_identity() -> None:
    case = p143_release_case_catalog()[0]
    row = build_p143_case_result(case, exit_code=0, stdout=_output(case), stderr=b"", duration_ms=1)
    assert row["runner"] == "run_p143_preliminary_matrix"
    assert row["runner_source_sha256"] == current_p143_runner_source_hash()
    assert row["command_argv"] == p143_case_execution_provenance(case)["command_argv"]
    assert validate_p143_case_matrix(build_p143_case_matrix([row, *qualified_p143_matrix()["rows"][1:]]))["passed"] == 52


def test_matrix_rejects_fake_ok_and_copied_selector_transcript() -> None:
    catalog = p143_release_case_catalog()
    fake = build_p143_case_result(catalog[0], exit_code=0, stdout=b"ok\n", stderr=b"", duration_ms=1)
    with pytest.raises(ValueError, match="marker|proof"):
        validate_p143_case_matrix(build_p143_case_matrix([fake, *qualified_p143_matrix()["rows"][1:]]))

    copied = qualified_p143_matrix()
    copied["rows"][1]["stdout_b64"] = copied["rows"][0]["stdout_b64"]
    copied["rows"][1]["transcript_sha256"] = copied["rows"][0]["transcript_sha256"]
    copied["rows"][1]["row_hash"] = stable_hash(
        {key: value for key, value in copied["rows"][1].items() if key != "row_hash"}
    )
    copied["matrix_hash"] = stable_hash({key: value for key, value in copied.items() if key != "matrix_hash"})
    with pytest.raises(ValueError, match="selector_execution_proof_invalid"):
        validate_p143_case_matrix(copied)


def test_pytest_case_marker_reports_measured_allowed_counters(capsys: pytest.CaptureFixture[str]) -> None:
    measured = zero_allowed_counters()
    measured["intent_projection_count"] = 3
    measured["replay_journal_entry_count"] = 19
    p143.reset_measured_allowed_counters()
    p143.record_measured_allowed_counters(measured)

    class Config:
        @staticmethod
        def getoption(_name: str) -> str:
            return "P143-CASE-30"

    class Session:
        config = Config()

    p143_runner.pytest_sessionfinish(Session(), 0)
    output = capsys.readouterr().out.encode()
    assert _marker("P143_CASE_COUNTERS", measured) in output


def test_matrix_allowed_counter_aggregate_is_exactly_recomputed() -> None:
    catalog = p143_release_case_catalog()
    first = zero_allowed_counters()
    first["intent_projection_count"] = 2
    second = zero_allowed_counters()
    second["replay_journal_entry_count"] = 7
    rows = [
        build_p143_case_result(
            case,
            exit_code=0,
            stdout=_output(case, first if index == 0 else second if index == 1 else None),
            stderr=b"",
            duration_ms=1,
        )
        for index, case in enumerate(catalog)
    ]
    matrix = build_p143_case_matrix(rows)
    assert matrix["allowed_counters"]["intent_projection_count"] == 2
    assert matrix["allowed_counters"]["replay_journal_entry_count"] == 7
    matrix["allowed_counters"]["replay_journal_entry_count"] += 1
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    with pytest.raises(ValueError, match="counter|matrix"):
        validate_p143_case_matrix(matrix)
