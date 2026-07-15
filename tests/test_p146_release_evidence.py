from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import pytest as pytest_module

from app.services.p110_evaluation import stable_hash
from tests.fixtures.p146.builders import (
    EVALUATOR_COUNTER_KEYS,
    FORBIDDEN_COUNTER_KEYS,
    P146_RELEASE_SELECTORS,
    RESOURCE_COUNTER_KEYS,
    RUNTIME_COUNTER_KEYS,
    build_known_conformance_corpus,
)

ROOT = Path(__file__).resolve().parents[1]


def test_p145_final_dependency_is_assembled_not_preliminary() -> None:
    from app.services.p146_release_evidence import (
        P146_READY_STATUS,
        build_p146_freeze_manifest,
        build_p146_preliminary_evidence,
        validate_p145_final_dependency,
    )

    corpus = build_known_conformance_corpus()
    matrix = _valid_selector_matrix()
    manifest = build_p146_freeze_manifest(project_root=ROOT, corpus=corpus, matrix=matrix)
    binding = validate_p145_final_dependency(project_root=ROOT)
    assert binding["required_status_value"] == "p145_local_response_duty_officer_qualified"
    assert binding["evidence_hash"]
    assert binding["review_hash"]
    assert binding["matrix_hash"]
    assert binding["freeze_hash"]
    assert manifest["dependency_bindings"]["p145_duty_officer"] == binding
    assert "p145_response_duty" not in manifest["dependency_bindings"]
    evidence = build_p146_preliminary_evidence(matrix, manifest, corpus=corpus)
    assert evidence["status"] != P146_READY_STATUS
    stale = copy.deepcopy(binding)
    stale["required_status_value"] = "p145_preliminary_qualification_frozen"
    with pytest.raises(ValueError, match="p145|final|preliminary|stale"):
        validate_p145_final_dependency(project_root=ROOT, dependency_binding=stale)


def test_release_matrix_rejects_forgery() -> None:
    from app.services.p146_release_evidence import build_p146_freeze_manifest, validate_release_matrix

    matrix = _valid_selector_matrix()
    selectors = cast(list[dict[str, Any]], matrix["selectors"])
    assert [row["selector"] for row in selectors] == list(P146_RELEASE_SELECTORS)
    validate_release_matrix(matrix)
    selectorless = {
        "schema_version": "p146.release_case_matrix.v1",
        "expected": len(P146_RELEASE_SELECTORS),
        "passed": len(P146_RELEASE_SELECTORS),
        "failed": 0,
        "selectors": [],
        "matrix_hash": stable_hash({"p146": "matrix"}),
    }
    with pytest.raises(ValueError, match="selector|matrix|denominator"):
        build_p146_freeze_manifest(project_root=ROOT, corpus=build_known_conformance_corpus(), matrix=selectorless)
    for mutation in (
        "skip",
        "xfail",
        "zero_collection",
        "reorder",
        "duplicate",
        "copied_transcript",
        "helper_only",
        "non_project_python",
        "missing_counter",
        "boolean_counter",
        "raw_transcript_hash",
    ):
        forged = _forge_matrix(matrix, mutation)
        with pytest.raises(ValueError, match="selector|transcript|semantic|pytest|forgery|proof|counter"):
            validate_release_matrix(forged)


def test_release_matrix_requires_exact_nonempty_aggregate_counters() -> None:
    from app.services.p146_release_evidence import validate_release_matrix

    matrix = _valid_selector_matrix()
    with pytest.raises(ValueError, match="aggregate|counter"):
        validate_release_matrix(matrix)

    _bind_aggregate_counters(matrix)
    validate_release_matrix(matrix)

    forged = copy.deepcopy(matrix)
    forged["aggregate_counters"]["runtime"]["request_commit_count"] += 1
    forged["matrix_hash"] = stable_hash({key: value for key, value in forged.items() if key != "matrix_hash"})
    with pytest.raises(ValueError, match="aggregate|counter"):
        validate_release_matrix(forged)


def test_release_matrix_requires_current_python_and_pytest_raw_hashes() -> None:
    from app.services.p146_release_evidence import validate_release_matrix

    matrix = _valid_selector_matrix()
    _bind_aggregate_counters(matrix)
    rows = cast(list[dict[str, Any]], matrix["selectors"])
    for row in rows:
        provenance = row["command_proof"]["executable_provenance"]
        provenance["resolved_python"] = ".venv/bin/python"
        provenance["project_python"] = True
        provenance["python_sha256"] = _file_sha256(Path(sys.executable))
        provenance["pytest_module_path"] = _project_relative_path(Path(pytest_module.__file__).resolve())
        provenance["pytest_module_sha256"] = _file_sha256(Path(pytest_module.__file__).resolve())
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    validate_release_matrix(matrix)

    forged = copy.deepcopy(matrix)
    cast(list[dict[str, Any]], forged["selectors"])[0]["command_proof"]["executable_provenance"]["python_sha256"] = "sha256:" + "0" * 64
    for row in cast(list[dict[str, Any]], forged["selectors"]):
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    forged["matrix_hash"] = stable_hash({key: value for key, value in forged.items() if key != "matrix_hash"})
    with pytest.raises(ValueError, match="python|pytest|hash|provenance|forgery"):
        validate_release_matrix(forged)


def test_freeze_dependency_graph_is_exact_appendix_f_without_duplicate_p145_key() -> None:
    from app.services.p146_release_evidence import build_p146_freeze_manifest

    matrix = _valid_selector_matrix()
    _bind_aggregate_counters(matrix)
    manifest = build_p146_freeze_manifest(project_root=ROOT, corpus=build_known_conformance_corpus(), matrix=matrix)
    assert list(manifest["dependency_bindings"]) == [
        "p96_prometheus_contract",
        "p124_quality",
        "p134_authority",
        "p135_normalization",
        "p137_triage",
        "p142_transport",
        "p144_capability",
        "p145_duty_officer",
    ]
    assert "p145_response_duty" not in manifest["dependency_bindings"]
    for key, binding in manifest["dependency_bindings"].items():
        assert binding["key"] == key


def test_source_scope_binds_runner_verifier_and_installed_entrypoint() -> None:
    from app.services.p146_release_evidence import current_p146_source_hashes

    hashes = current_p146_source_hashes(ROOT)
    assert {
        "app/services/p146_runner.py",
        "scripts/run_p146_release.py",
        "scripts/verify_p146.sh",
        "pyproject.toml",
    }.issubset(hashes)


def test_release_evidence_validates_and_binds_actual_benchmark_artifact(tmp_path: Path) -> None:
    from app.services.p146_release_evidence import (
        assemble_p146_final_evidence,
        build_p146_final_review,
        build_p146_freeze_manifest,
        validate_release_evidence,
    )
    from app.services.p146_runner import write_canonical_json

    matrix = _valid_selector_matrix()
    _bind_aggregate_counters(matrix)
    corpus = build_known_conformance_corpus()
    manifest = build_p146_freeze_manifest(project_root=ROOT, corpus=corpus, matrix=matrix)
    review = build_p146_final_review(
        manifest=manifest,
        reviewer_identity="p146-independent-final-reviewer",
        reviewer_agent_id="0190d5f0-7b00-7000-8000-000000000146",
        implementation_identity="p146-implementation",
        reviewed_at="2026-07-15T15:00:00Z",
        findings={"p0": 0, "p1": 0, "p2": 0, "p3": 0},
    )
    benchmark = _valid_benchmark_report(matrix)
    benchmark_path = tmp_path / "benchmark-report.json"
    write_canonical_json(benchmark_path, benchmark)

    evidence = assemble_p146_final_evidence(
        matrix,
        manifest=manifest,
        review=review,
        benchmark_report_path=benchmark_path,
    )
    assert evidence["benchmark_report_hash"] == _file_sha256(benchmark_path)

    forged = copy.deepcopy(evidence)
    forged["benchmark_report_hash"] = "sha256:" + "0" * 64
    forged["evidence_hash"] = stable_hash({key: value for key, value in forged.items() if key != "evidence_hash"})
    with pytest.raises(ValueError, match="benchmark|artifact|binding|hash"):
        validate_release_evidence(forged, matrix=matrix, manifest=manifest, review=review, benchmark_report_path=benchmark_path)


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
            "stdout_sha256": "sha256:" + hashlib.sha256(marker).hexdigest(),
            "stderr_sha256": "sha256:" + hashlib.sha256(b"").hexdigest(),
            "transcript_sha256": "sha256:" + hashlib.sha256(marker).hexdigest(),
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
            "runtime_counters": {key: 0 for key in RUNTIME_COUNTER_KEYS},
            "evaluator_counters": {key: 0 for key in EVALUATOR_COUNTER_KEYS},
            "resource_counters": {key: 0 for key in RESOURCE_COUNTER_KEYS},
            "forbidden_counters": {key: 0 for key in FORBIDDEN_COUNTER_KEYS},
            "passed": True,
            "failure_reason": None,
            "row_hash": "",
        }
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
        rows.append(row)
    matrix = {"schema_version": "p146.release_case_matrix.v1", "expected": 12, "passed": 12, "failed": 0, "selectors": rows, "aggregate_counters": {}, "matrix_hash": ""}
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    return matrix


def _aggregate_counters(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "runtime": {key: sum(row["runtime_counters"][key] for row in rows) for key in RUNTIME_COUNTER_KEYS},
        "evaluator": {key: sum(row["evaluator_counters"][key] for row in rows) for key in EVALUATOR_COUNTER_KEYS},
        "resources": {key: sum(row["resource_counters"][key] for row in rows) for key in RESOURCE_COUNTER_KEYS},
        "forbidden": {key: sum(row["forbidden_counters"][key] for row in rows) for key in FORBIDDEN_COUNTER_KEYS},
    }


def _bind_aggregate_counters(matrix: dict[str, object]) -> None:
    matrix["aggregate_counters"] = _aggregate_counters(cast(list[dict[str, Any]], matrix["selectors"]))
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _project_relative_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _valid_benchmark_report(matrix: dict[str, object]) -> dict[str, object]:
    rows = []
    for ordinal in range(48):
        row = {
            "schema_version": "p146.benchmark_row.v1",
            "case_ref_hash": "sha256:" + hashlib.sha256(f"case-{ordinal}".encode()).hexdigest(),
            "prediction_hash": "sha256:" + hashlib.sha256(f"prediction-{ordinal}".encode()).hexdigest(),
            "truth_row_hash": "sha256:" + hashlib.sha256(f"truth-{ordinal}".encode()).hexdigest(),
            "diagnostic_match": True,
            "top3_match": True,
            "abstention_match": ordinal >= 40,
            "citation_valid": True,
            "injection_contained": ordinal < 8,
            "latency_ns": 1000 + ordinal,
            "row_hash": "",
        }
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
        rows.append(row)
    report = {
        "schema_version": "p146.benchmark_report.v1",
        "corpus_version": "p146_known_conformance_corpus_v1",
        "denominators": {"all": 48, "complete_fault": 32, "healthy": 8, "gap": 8, "injection": 8},
        "confusion": {"tp": 32, "fp": 0, "fn": 0, "tn": 8},
        "descriptive_metrics": {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "false_positive_rate": 0.0,
            "top1_accuracy": 1.0,
            "top3_accuracy": 1.0,
            "brier_score": 0.0,
            "p95_latency_ns": 1045,
        },
        "wilson_intervals": {},
        "slices": {},
        "failure_analysis": [],
        "aggregate_counters": matrix["aggregate_counters"],
        "semantic_prediction_hash": stable_hash([row["prediction_hash"] for row in rows]),
        "rows": rows,
        "report_hash": "",
    }
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    return report


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
    elif mutation == "missing_counter":
        del rows[0]["runtime_counters"][RUNTIME_COUNTER_KEYS[0]]
    elif mutation == "boolean_counter":
        rows[0]["forbidden_counters"][FORBIDDEN_COUNTER_KEYS[0]] = False
    elif mutation == "raw_transcript_hash":
        rows[0]["command_proof"]["stdout_sha256"] = stable_hash(base64.b64decode(rows[0]["command_proof"]["stdout_b64"]))
    for row in rows:
        row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    forged["matrix_hash"] = stable_hash({key: value for key, value in forged.items() if key != "matrix_hash"})
    return forged
