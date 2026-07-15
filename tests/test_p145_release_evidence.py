from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p145_release_evidence import (
    P145_PRELIMINARY_STATUS,
    PREDECESSOR_BINDINGS,
    REQUIRED_LIMITATIONS,
    REVIEW_SCHEMA_VERSION,
    _validate_review,
    assemble_p145_final_evidence,
    build_p145_freeze_manifest,
    build_p145_preliminary_evidence,
)
from app.services.p145_runner import p145_release_case_catalog, validate_p145_case_matrix


def test_tracked_final_artifacts_are_current() -> None:
    matrix_path = Path("evals/p145/output/canonical-matrix.json")
    manifest_path = Path("evals/p145/output/freeze-manifest.json")
    evidence_path = Path("evals/p145/output/release-evidence.json")
    if not matrix_path.exists() or not manifest_path.exists() or not evidence_path.exists():
        pytest.skip("P145 preliminary artifacts not generated yet")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    validate_p145_case_matrix(matrix)
    expected = build_p145_preliminary_evidence(matrix, manifest)
    assert evidence == expected
    assert evidence["status"] == P145_PRELIMINARY_STATUS


def test_final_mode_requires_independent_review(tmp_path: Path) -> None:
    profile = {
        "schema_version": "p145.response_duty_profile.v1",
        "cases": p145_release_case_catalog(),
        "predecessor_bindings": PREDECESSOR_BINDINGS,
    }
    matrix_path = Path("evals/p145/output/canonical-matrix.json")
    if not matrix_path.exists():
        pytest.skip("P145 preliminary matrix not generated yet")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    manifest = build_p145_freeze_manifest(project_root=Path("."), profile=profile, matrix=matrix)
    with pytest.raises(ValueError, match="review"):
        assemble_p145_final_evidence(matrix, manifest=manifest, review={}, project_root=Path("."), profile=profile)


def test_final_mode_rejects_rehashed_dependency_binding_forgery() -> None:
    profile = {
        "schema_version": "p145.response_duty_profile.v1",
        "cases": p145_release_case_catalog(),
        "predecessor_bindings": PREDECESSOR_BINDINGS,
    }
    matrix = json.loads(Path("evals/p145/output/canonical-matrix.json").read_text(encoding="utf-8"))
    manifest = build_p145_freeze_manifest(project_root=Path("."), profile=profile, matrix=matrix)
    manifest["dependency_bindings"]["uv.lock"] = "sha256:" + "0" * 64
    manifest["freeze_manifest_hash"] = stable_hash(
        {key: value for key, value in manifest.items() if key != "freeze_manifest_hash"}
    )

    with pytest.raises(ValueError, match="freeze_manifest_drift"):
        assemble_p145_final_evidence(matrix, manifest=manifest, review={}, project_root=Path("."), profile=profile)


@pytest.mark.parametrize("severity", ["p0", "p1", "p2", "p3"])
def test_independent_review_requires_every_severity_count_to_be_integer_zero(severity: str) -> None:
    manifest = json.loads(Path("evals/p145/output/freeze-manifest.json").read_text(encoding="utf-8"))
    findings = {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
    findings[severity] = 1
    review = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "reviewer_identity": "independent-reviewer",
        "reviewer_agent_id": "0190d5f0-7b00-7000-8000-000000000001",
        "reviewer_type": "independent",
        "implementation_identity": "p145-implementation-agent",
        "reviewed_at": "2026-07-15T00:00:00Z",
        "decision": "approve",
        "findings": findings,
        "limitations": REQUIRED_LIMITATIONS,
        "reviewed_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_test_spec_sha256": manifest["approved_test_spec_sha256"],
        "reviewed_plan_review_sha256": manifest["plan_review_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_fixture_hash": manifest["fixture_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": manifest["source_bindings"],
        "reviewed_dependency_hashes": manifest["dependency_bindings"],
        "reviewed_predecessor_bindings": manifest["predecessor_bindings"],
        "review_hash": "",
    }
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    with pytest.raises(ValueError, match="findings"):
        _validate_review(review, manifest)


def test_release_validation_rejects_hollow_and_semantically_replayed_rows() -> None:
    matrix = json.loads(Path("evals/p145/output/canonical-matrix.json").read_text(encoding="utf-8"))
    hollow = json.loads(json.dumps(matrix))
    row = hollow["cases"][0]
    empty_sha = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    row["command_proof"]["stdout_b64"] = ""
    row["command_proof"]["stderr_b64"] = ""
    row["command_proof"]["stdout_sha256"] = empty_sha
    row["command_proof"]["stderr_sha256"] = empty_sha
    row["command_proof"]["transcript_sha256"] = empty_sha
    row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    hollow["matrix_hash"] = stable_hash({key: value for key, value in hollow.items() if key != "matrix_hash"})
    with pytest.raises(ValueError, match="selector|transcript|semantic|result"):
        validate_p145_case_matrix(hollow)

    replayed = json.loads(json.dumps(matrix))
    row = replayed["cases"][0]
    proof = row["command_proof"]
    stdout = base64.b64decode(proof["stdout_b64"])
    stdout = stdout.replace(b'"terminal_status":"recovery_verified"', b'"terminal_status":"human_escalation_required"', 1)
    stderr = base64.b64decode(proof["stderr_b64"])
    proof["stdout_b64"] = base64.b64encode(stdout).decode("ascii")
    proof["stdout_sha256"] = "sha256:" + hashlib.sha256(stdout).hexdigest()
    proof["transcript_sha256"] = "sha256:" + hashlib.sha256(stdout + stderr).hexdigest()
    row["row_hash"] = stable_hash({key: value for key, value in row.items() if key != "row_hash"})
    replayed["matrix_hash"] = stable_hash({key: value for key, value in replayed.items() if key != "matrix_hash"})
    with pytest.raises(ValueError, match="result|semantic"):
        validate_p145_case_matrix(replayed)
