from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import pytest

from app.services.p110_evaluation import stable_hash
from tests.fixtures.p146.builders import P146_RELEASE_SELECTORS, build_known_conformance_corpus

ROOT = Path(__file__).resolve().parents[1]


def test_p145_final_dependency_is_assembled_not_preliminary() -> None:
    from app.services.p146_release_evidence import (
        P146_READY_STATUS,
        build_p146_freeze_manifest,
        build_p146_preliminary_evidence,
        validate_p145_final_dependency,
    )

    corpus = build_known_conformance_corpus()
    matrix = {"schema_version": "p146.release_case_matrix.v1", "expected": 12, "passed": 12, "failed": 0, "selectors": [], "matrix_hash": stable_hash({"p146": "matrix"})}
    manifest = build_p146_freeze_manifest(project_root=ROOT, corpus=corpus, matrix=matrix)
    binding = validate_p145_final_dependency(project_root=ROOT)
    assert binding["required_status_value"] == "p145_local_response_duty_officer_qualified"
    assert binding["evidence_hash"]
    assert binding["review_hash"]
    assert binding["matrix_hash"]
    assert binding["freeze_hash"]
    assert manifest["dependency_bindings"]["p145_response_duty"] == binding
    evidence = build_p146_preliminary_evidence(matrix, manifest, corpus=corpus)
    assert evidence["status"] != P146_READY_STATUS
    stale = copy.deepcopy(binding)
    stale["required_status_value"] = "p145_preliminary_qualification_frozen"
    with pytest.raises(ValueError, match="p145|final|preliminary|stale"):
        validate_p145_final_dependency(project_root=ROOT, dependency_binding=stale)


def test_release_matrix_rejects_forgery() -> None:
    from app.services.p146_release_evidence import validate_release_matrix

    matrix = _valid_selector_matrix()
    assert [row["selector"] for row in matrix["selectors"]] == list(P146_RELEASE_SELECTORS)
    validate_release_matrix(matrix)
    for mutation in (
        "skip",
        "xfail",
        "zero_collection",
        "reorder",
        "duplicate",
        "copied_transcript",
        "helper_only",
        "non_project_python",
    ):
        forged = _forge_matrix(matrix, mutation)
        with pytest.raises(ValueError, match="selector|transcript|semantic|pytest|forgery|proof"):
            validate_release_matrix(forged)


def _valid_selector_matrix() -> dict[str, object]:
    rows = []
    for ordinal, selector in enumerate(P146_RELEASE_SELECTORS, start=1):
        observed = {"selector": selector, "semantic": selector.rsplit("::", 1)[1], "passed": True}
        proof = {"collected": [selector], "executed": [selector], "passed": [selector]}
        marker = (
            "P146_SELECTOR_PROOF="
            + json.dumps(proof, sort_keys=True, separators=(",", ":"))
            + "\nP146_OBSERVED_SEMANTICS="
            + json.dumps(observed, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        command_proof = {
            "argv": [".venv/bin/python", "-m", "pytest", selector, "-q"],
            "executable_provenance": {
                "resolved_python": ".venv/bin/python",
                "project_python": True,
                "python_sha256": "sha256:" + f"{ordinal:064x}"[-64:],
                "pytest_module_path": ".venv/lib/python/site-packages/pytest/__init__.py",
                "pytest_module_sha256": "sha256:" + f"{ordinal + 100:064x}"[-64:],
            },
            "exit_code": 0,
            "collected_nodeids": [selector],
            "selector_execution_proof": proof,
            "stdout_sha256": stable_hash(marker),
            "stderr_sha256": stable_hash(b""),
            "transcript_sha256": stable_hash(marker),
            "stdout_b64": base64.b64encode(marker).decode("ascii"),
            "stderr_b64": "",
            "transcript_form": "stdout_then_stderr",
            "selector_proof_hash": stable_hash({"selector_execution_proof": proof, "observed_semantics": observed}),
        }
        row = {
            "schema_version": "p146.matrix_row.v1",
            "ordinal": ordinal,
            "selector": selector,
            "semantic_name": observed["semantic"],
            "expected_semantics": observed,
            "observed_semantics": observed,
            "command_proof": command_proof,
            "runtime_counters": {},
            "evaluator_counters": {},
            "resource_counters": {},
            "forbidden_counters": {},
            "passed": True,
            "failure_reason": None,
            "row_hash": "",
        }
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
        rows.append(row)
    matrix = {"schema_version": "p146.release_case_matrix.v1", "expected": 12, "passed": 12, "failed": 0, "selectors": rows, "aggregate_counters": {}, "matrix_hash": ""}
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    return matrix


def _forge_matrix(matrix: dict[str, object], mutation: str) -> dict[str, object]:
    forged = copy.deepcopy(matrix)
    rows = forged["selectors"]
    assert isinstance(rows, list)
    if mutation == "skip":
        rows[0]["failure_reason"] = "skipped"
        rows[0]["passed"] = False
    elif mutation == "xfail":
        rows[0]["observed_semantics"] = {"xfail": True}
    elif mutation == "zero_collection":
        rows[0]["command_proof"]["collected_nodeids"] = []
        rows[0]["command_proof"]["selector_execution_proof"]["collected"] = []
    elif mutation == "reorder":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "duplicate":
        rows[1]["selector"] = rows[0]["selector"]
    elif mutation == "copied_transcript":
        rows[1]["command_proof"] = copy.deepcopy(rows[0]["command_proof"])
    elif mutation == "helper_only":
        rows[0]["selector"] = "tests/fixtures/p146/builders.py::helper"
    elif mutation == "non_project_python":
        rows[0]["command_proof"]["executable_provenance"]["resolved_python"] = "/usr/bin/python3"
        rows[0]["command_proof"]["executable_provenance"]["project_python"] = False
    for row in rows:
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    forged["matrix_hash"] = stable_hash({key: value for key, value in forged.items() if key != "matrix_hash"})
    return forged

