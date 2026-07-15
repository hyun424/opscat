from __future__ import annotations

import base64
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from tests.fixtures.p146.builders import P146_RELEASE_SELECTORS, build_known_conformance_corpus

ROOT = Path(__file__).resolve().parents[1]


def test_selector_row_binds_actual_subprocess_stdout_and_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.p146_runner as runner

    selector = P146_RELEASE_SELECTORS[0]
    proof = {"collected": [selector], "executed": [selector], "passed": [selector]}
    semantics = {"selector": selector, "semantic": selector.rsplit("::", 1)[-1], "passed": True}
    stdout = (
        b"real pytest prelude\n"
        + b"P146_SELECTOR_PROOF="
        + json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()
        + b"\nP146_OBSERVED_SEMANTICS="
        + json.dumps(semantics, sort_keys=True, separators=(",", ":")).encode()
        + b"\n1 passed\n"
    )
    stderr = b"real pytest warning\n"
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr=stderr),
    )

    row = runner._collect_selector_row(project_root=ROOT, selector=selector, ordinal=1)
    command_proof = row["command_proof"]

    assert base64.b64decode(command_proof["stdout_b64"], validate=True) == stdout
    assert base64.b64decode(command_proof["stderr_b64"], validate=True) == stderr
    assert command_proof["stdout_sha256"] == _bytes_sha256(stdout)
    assert command_proof["stderr_sha256"] == _bytes_sha256(stderr)
    assert command_proof["transcript_sha256"] == _bytes_sha256(stdout + stderr)
    assert row["resource_counters"]["artifact_bytes"] == len(stdout) + len(stderr)


def test_selector_collector_executes_actual_subprocesses_and_emits_required_markers(tmp_path: Path) -> None:
    from app.services.p146_release_evidence import validate_release_matrix
    from app.services.p146_runner import collect_selector_matrix

    matrix = collect_selector_matrix(
        project_root=ROOT,
        selectors=P146_RELEASE_SELECTORS,
        output_dir=tmp_path,
    )

    assert [row["selector"] for row in matrix["selectors"]] == list(P146_RELEASE_SELECTORS)
    assert matrix["aggregate_counters"]["forbidden"]["subprocess_action_count"] == 0
    for row in matrix["selectors"]:
        proof = row["command_proof"]
        transcript = base64.b64decode(proof["stdout_b64"], validate=True).decode("utf-8")
        assert proof["collected_nodeids"] == [row["selector"]]
        assert proof["selector_execution_proof"] == {
            "collected": [row["selector"]],
            "executed": [row["selector"]],
            "passed": [row["selector"]],
        }
        assert "P146_SELECTOR_PROOF=" in transcript
        assert "P146_OBSERVED_SEMANTICS=" in transcript
        assert proof["executable_provenance"]["python_sha256"].startswith("sha256:")
        assert proof["executable_provenance"]["pytest_module_sha256"].startswith("sha256:")
    validate_release_matrix(matrix)


def test_runner_generates_canonical_preliminary_artifact_set(tmp_path: Path) -> None:
    from app.services.p146_release_evidence import validate_freeze_manifest, validate_release_evidence, validate_release_matrix
    from app.services.p146_runner import generate_preliminary_release_artifacts, read_canonical_json

    artifacts = generate_preliminary_release_artifacts(project_root=ROOT, output_dir=tmp_path)

    assert artifacts == {
        "matrix": tmp_path / "canonical-matrix.json",
        "benchmark": tmp_path / "benchmark-report.json",
        "freeze": tmp_path / "freeze-manifest.json",
        "preliminary_evidence": tmp_path / "release-evidence.json",
    }
    for path in artifacts.values():
        assert path.is_file()
        assert path.read_bytes().endswith(b"\n")
        assert json.dumps(str(path)) not in path.read_text(encoding="utf-8")

    matrix = read_canonical_json(artifacts["matrix"])
    benchmark = read_canonical_json(artifacts["benchmark"])
    freeze = read_canonical_json(artifacts["freeze"])
    evidence = read_canonical_json(artifacts["preliminary_evidence"])
    validate_release_matrix(matrix)
    validate_freeze_manifest(freeze, matrix=matrix, corpus=build_known_conformance_corpus())
    validate_release_evidence(
        evidence,
        matrix=matrix,
        manifest=freeze,
        review=None,
        benchmark_report_path=artifacts["benchmark"],
    )
    assert evidence["benchmark_report_hash"] == _file_sha256(artifacts["benchmark"])
    assert benchmark["report_hash"] == stable_hash({key: value for key, value in benchmark.items() if key != "report_hash"})


def test_runner_final_mode_requires_frozen_artifacts_and_zero_finding_review(tmp_path: Path) -> None:
    from app.services.p146_runner import generate_final_release_artifacts, generate_preliminary_release_artifacts, read_canonical_json, write_canonical_json

    artifacts = generate_preliminary_release_artifacts(project_root=ROOT, output_dir=tmp_path)
    freeze = read_canonical_json(artifacts["freeze"])
    review = _zero_finding_review(freeze)
    review_path = tmp_path / "final-implementation-review.json"
    write_canonical_json(review_path, review)

    final = generate_final_release_artifacts(
        project_root=ROOT,
        matrix_path=artifacts["matrix"],
        benchmark_report_path=artifacts["benchmark"],
        freeze_manifest_path=artifacts["freeze"],
        final_review_path=review_path,
        output_dir=tmp_path / "final",
    )
    assert final == tmp_path / "final" / "release-evidence.json"
    assert read_canonical_json(final)["status"] == "p146_live_shadow_qualification_ready"

    forged_review = copy.deepcopy(review)
    forged_review["findings"]["p1"] = 1
    forged_review["review_hash"] = stable_hash({key: value for key, value in forged_review.items() if key != "review_hash"})
    forged_review_path = tmp_path / "forged-final-implementation-review.json"
    write_canonical_json(forged_review_path, forged_review)
    with pytest.raises(ValueError, match="finding|review|final"):
        generate_final_release_artifacts(
            project_root=ROOT,
            matrix_path=artifacts["matrix"],
            benchmark_report_path=artifacts["benchmark"],
            freeze_manifest_path=artifacts["freeze"],
            final_review_path=forged_review_path,
            output_dir=tmp_path / "forged-final",
        )


def test_release_cli_runs_preliminary_and_final_modes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from app.services.p146_runner import generate_preliminary_release_artifacts, read_canonical_json, write_canonical_json
    from scripts.run_p146_release import main

    preliminary_dir = tmp_path / "preliminary"
    assert main(["preliminary", "--project-root", str(ROOT), "--output-dir", str(preliminary_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "p146.release_runner_receipt.v1"
    assert payload["mode"] == "preliminary"
    assert payload["artifacts"]["release_evidence"] == "release-evidence.json"

    artifacts = generate_preliminary_release_artifacts(project_root=ROOT, output_dir=tmp_path / "prepared")
    freeze = read_canonical_json(artifacts["freeze"])
    review_path = tmp_path / "final-implementation-review.json"
    write_canonical_json(review_path, _zero_finding_review(freeze))
    final_dir = tmp_path / "final"
    assert main(
        [
            "final",
            "--project-root",
            str(ROOT),
            "--matrix",
            str(artifacts["matrix"]),
            "--benchmark-report",
            str(artifacts["benchmark"]),
            "--freeze-manifest",
            str(artifacts["freeze"]),
            "--final-review",
            str(review_path),
            "--output-dir",
            str(final_dir),
        ]
    ) == 0
    final_payload = json.loads(capsys.readouterr().out)
    assert final_payload["mode"] == "final"
    assert final_payload["artifacts"]["release_evidence"] == "release-evidence.json"


def _zero_finding_review(freeze: dict[str, Any]) -> dict[str, Any]:
    review = {
        "schema_version": "p146.final_implementation_review.v1",
        "reviewer_identity": "p146-independent-final-reviewer",
        "reviewer_agent_id": "0190d5f0-7b00-7000-8000-000000000146",
        "implementation_identity": "p146-implementation",
        "reviewed_at": "2026-07-15T15:00:00Z",
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": [
            "known_synthetic_conformance_corpus_not_hidden_or_generalized",
            "process_owned_numeric_loopback_only_no_external_provider_credentials_or_network",
            "advisory_shadow_routes_only_no_actions_approvals_remediation_or_operator_replacement",
            "p145_dependency_is_predecessor_readiness_only_not_runtime_state_machine_execution",
        ],
        "reviewed_plan_hash": freeze["plan_hash"],
        "reviewed_test_spec_hash": freeze["test_spec_hash"],
        "reviewed_plan_review_hash": freeze["plan_review_hash"],
        "reviewed_profile_hash": freeze["profile_hash"],
        "reviewed_visible_hash": freeze["visible_corpus_hash"],
        "reviewed_truth_hash": freeze["truth_manifest_hash"],
        "reviewed_source_hashes": freeze["source_hashes"],
        "reviewed_dependency_bindings": freeze["dependency_bindings"],
        "reviewed_matrix_hash": freeze["matrix_hash"],
        "reviewed_freeze_hash": freeze["manifest_hash"],
        "review_hash": "",
    }
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    return review


def _bytes_sha256(value: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
