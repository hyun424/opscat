from __future__ import annotations

import base64
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p145_runner import (
    _approved_executable_provenance,
    current_p145_runner_source_hash,
    validate_p145_case_matrix,
)


def _matrix() -> dict[str, Any]:
    return json.loads(Path("evals/p145/output/canonical-matrix.json").read_text(encoding="utf-8"))


def _rehash(matrix: dict[str, Any], row_index: int = 0) -> None:
    cases = matrix["cases"]
    assert isinstance(cases, list)
    row = cases[row_index]
    assert isinstance(row, dict)
    row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})


def _bind_current_executable_provenance(matrix: dict[str, Any]) -> None:
    for row in matrix["cases"]:
        row["command_proof"]["executable_provenance"] = _approved_executable_provenance()
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    matrix["runner_source_sha256"] = current_p145_runner_source_hash()
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})


def test_matrix_rejects_skip_reorder_hash_transcript_and_boolean_forgery() -> None:
    matrix = _matrix()
    validate_p145_case_matrix(matrix)

    bad = deepcopy(matrix)
    cases = bad["cases"]
    assert isinstance(cases, list)
    bad["cases"] = cases[1:]
    with pytest.raises(ValueError, match="denominator"):
        validate_p145_case_matrix(bad)

    bad = deepcopy(matrix)
    cases = bad["cases"]
    assert isinstance(cases, list)
    cases[0], cases[1] = cases[1], cases[0]
    with pytest.raises(ValueError, match="order"):
        validate_p145_case_matrix(bad)

    bad = deepcopy(matrix)
    row = bad["cases"][0]
    row["forbidden_authority"][next(iter(row["forbidden_authority"]))] = True
    _rehash(bad)
    with pytest.raises(ValueError, match="forbidden"):
        validate_p145_case_matrix(bad)

    bad = deepcopy(matrix)
    bad["cases"][0]["command_proof"]["stdout_b64"] = ""
    _rehash(bad)
    with pytest.raises(ValueError, match="transcript"):
        validate_p145_case_matrix(bad)


def test_matrix_rejects_empty_or_mismatched_phase_paths_even_when_rehashed() -> None:
    matrix = _matrix()
    for observed in ([], ["registered", "recovery_verified"]):
        bad = deepcopy(matrix)
        bad["cases"][0]["observed_phase_path"] = observed
        _rehash(bad)
        with pytest.raises(ValueError, match="phase"):
            validate_p145_case_matrix(bad)


def test_evaluator_process_count_is_not_forbidden_subprocess_authority() -> None:
    matrix = _matrix()
    assert matrix["aggregate_counters"]["evaluator_activity"]["child_process_count"] == 48
    assert matrix["aggregate_counters"]["evaluator_activity"]["crash_injection_count"] == 11
    assert matrix["aggregate_counters"]["forbidden_authority"]["subprocess_shell_count"] == 0


@pytest.mark.parametrize("interpreter", ["/workspace/.venv/bin/python", "python3"])
def test_persisted_matrix_validation_is_independent_of_current_interpreter(
    interpreter: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = _matrix()
    monkeypatch.setattr(sys, "executable", interpreter)
    assert validate_p145_case_matrix(matrix)["matrix_hash"] == matrix["matrix_hash"]


def test_matrix_still_rejects_unstable_command_argv_structure() -> None:
    bad = _matrix()
    bad["cases"][0]["command_proof"]["argv"][1] = "-c"
    _rehash(bad)
    with pytest.raises(ValueError, match="command_argv"):
        validate_p145_case_matrix(bad)


@pytest.mark.parametrize("alias", ["python", "python3"])
def test_matrix_accepts_approved_project_venv_executable_aliases(alias: str) -> None:
    matrix = _matrix()
    _bind_current_executable_provenance(matrix)
    matrix["cases"][0]["command_proof"]["argv"][0] = f"$PROJECT_ROOT/.venv/bin/{alias}"
    _rehash(matrix)
    validate_p145_case_matrix(matrix)


def test_matrix_rejects_rehashed_untrusted_python_executable_path() -> None:
    bad = _matrix()
    _bind_current_executable_provenance(bad)
    bad["cases"][0]["command_proof"]["argv"][0] = "/tmp/untrusted/python"
    _rehash(bad)
    with pytest.raises(ValueError, match="executable_provenance"):
        validate_p145_case_matrix(bad)


def test_persisted_matrix_contains_no_machine_specific_home_or_case_paths() -> None:
    serialized = json.dumps(_matrix(), sort_keys=True)

    assert "/Users/" not in serialized
    assert "/private/var/" not in serialized
    assert "$PROJECT_ROOT/.venv/bin/python" in serialized
    transcripts = [base64.b64decode(row["command_proof"]["stdout_b64"]).decode("utf-8") for row in _matrix()["cases"]]
    assert all("$CASE_DIR/journal.jsonl" in transcript for transcript in transcripts)
    assert all("/private/var/" not in transcript for transcript in transcripts)


def test_matrix_rejects_rehashed_nonportable_result_paths() -> None:
    bad = _matrix()
    row = bad["cases"][0]
    proof = row["command_proof"]
    stdout_lines = base64.b64decode(proof["stdout_b64"]).decode("utf-8").splitlines()
    marker_index = next(index for index, line in enumerate(stdout_lines) if line.startswith("P145_CASE_RESULT="))
    observed = json.loads(stdout_lines[marker_index].split("=", 1)[1])
    observed["journal_path"] = "/Users/attacker/journal.jsonl"
    observed["result_hash"] = stable_hash({key: value for key, value in observed.items() if key != "result_hash"})
    stdout_lines[marker_index] = "P145_CASE_RESULT=" + json.dumps(observed, sort_keys=True, separators=(",", ":"))
    stdout = ("\n".join(stdout_lines) + "\n").encode("utf-8")
    stderr = base64.b64decode(proof["stderr_b64"])
    proof["stdout_b64"] = base64.b64encode(stdout).decode("ascii")
    proof["stdout_sha256"] = "sha256:" + hashlib.sha256(stdout).hexdigest()
    proof["transcript_sha256"] = "sha256:" + hashlib.sha256(stdout + stderr).hexdigest()
    _rehash(bad)

    with pytest.raises(ValueError, match="portable_path"):
        validate_p145_case_matrix(bad)


def test_matrix_rejects_rehashed_correlated_duplicate_semantic_forgery() -> None:
    bad = _matrix()
    row_index = 44
    proof = bad["cases"][row_index]["command_proof"]
    stdout_lines = base64.b64decode(proof["stdout_b64"]).decode("utf-8").splitlines()
    marker_index = next(index for index, line in enumerate(stdout_lines) if line.startswith("P145_CASE_RESULT="))
    observed = json.loads(stdout_lines[marker_index].split("=", 1)[1])
    observed["correlation_action_receipt"]["action_reused"] = False
    observed["correlation_action_receipt"]["second_action_mutation"] = True
    observed["result_hash"] = stable_hash({key: value for key, value in observed.items() if key != "result_hash"})
    stdout_lines[marker_index] = "P145_CASE_RESULT=" + json.dumps(observed, sort_keys=True, separators=(",", ":"))
    stdout = ("\n".join(stdout_lines) + "\n").encode("utf-8")
    stderr = base64.b64decode(proof["stderr_b64"])
    proof["stdout_b64"] = base64.b64encode(stdout).decode("ascii")
    proof["stdout_sha256"] = "sha256:" + hashlib.sha256(stdout).hexdigest()
    proof["transcript_sha256"] = "sha256:" + hashlib.sha256(stdout + stderr).hexdigest()
    _rehash(bad, row_index)
    with pytest.raises(ValueError, match="correlated_duplicate_proof"):
        validate_p145_case_matrix(bad)
