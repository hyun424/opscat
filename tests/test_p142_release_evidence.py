from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p142_release_evidence import (
    IMPLEMENTATION_REVIEW_ARTIFACT_PATH,
    P142_PRELIMINARY_STATUS,
    P142_READY_STATUS,
    REQUIRED_LIMITATIONS,
    assemble_p142_final_evidence,
    build_p142_freeze_manifest,
    build_p142_preliminary_evidence,
)
from app.services.p142_runner import p142_release_case_catalog
from tests.test_p142_runner import qualified_p142_matrix

ROOT = Path(__file__).resolve().parents[1]


def p142_profile() -> dict[str, Any]:
    return {"schema_version": "p142.loopback_transport_lab_profile.v1", "cases": p142_release_case_catalog()}


def p142_review(manifest: dict[str, Any]) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema_version": "p142.final_implementation_review.v1",
        "reviewer_identity": "p142-independent-code-reviewer",
        "reviewer_agent_id": "019f62b0-c874-73d6-a36e-5e8bc1b19998",
        "reviewer_type": "codex-native-code-reviewer",
        "implementation_identity": "p142-implementation-agent",
        "reviewed_at": "2026-07-15T12:00:00Z",
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_test_spec_sha256": manifest["approved_test_spec_sha256"],
        "reviewed_plan_review_sha256": manifest["plan_review_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": deepcopy(manifest["source_bindings"]),
        "reviewed_dependency_bindings": deepcopy(manifest["dependency_bindings"]),
        "limitations": sorted(REQUIRED_LIMITATIONS),
    }
    review["review_hash"] = stable_hash(review)
    return review


def test_p142_preliminary_and_final_evidence_bind_sources_p141_dependency_and_review() -> None:
    matrix = qualified_p142_matrix()
    manifest = build_p142_freeze_manifest(project_root=ROOT, profile=p142_profile(), matrix=matrix)
    assert manifest["dependency_bindings"]["p141_status"] == "p141_notification_authority_simulator_qualified"
    assert manifest["approved_plan_sha256"] == "sha256:3f1a92c3a10c4db42fd5530393c222fcf7bfe3d240d7da2990e1af865e4186d9"
    assert manifest["approved_test_spec_sha256"] == "sha256:13b02f1fc442f31a8c4197719ec3c0bae36667c00160be148a011c270cc26fe7"
    preliminary = build_p142_preliminary_evidence(matrix, manifest)
    assert preliminary["status"] == P142_PRELIMINARY_STATUS
    assert preliminary["final_review_hash"] is None
    assert preliminary["allowed_transport_activity_counters"] == matrix["allowed_transport_activity_counters"]
    review = p142_review(manifest)
    final = assemble_p142_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p142_profile())
    assert final["status"] == P142_READY_STATUS
    assert final["passed"] == 44
    assert final["final_review_hash"] == review["review_hash"]
    assert final["allowed_transport_activity_counters"] == matrix["allowed_transport_activity_counters"]


@pytest.mark.parametrize("mutation", ["manifest", "review_identity", "review_hash", "p141", "profile", "plan_review"])
def test_p142_release_rejects_source_dependency_profile_and_review_drift(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    matrix = qualified_p142_matrix()
    manifest = build_p142_freeze_manifest(project_root=ROOT, profile=p142_profile(), matrix=matrix)
    review = p142_review(manifest)
    if mutation == "manifest":
        bad_manifest = deepcopy(manifest)
        bad_manifest["matrix_hash"] = "sha256:" + "0" * 64
        with pytest.raises(ValueError, match="freeze_manifest_drift"):
            assemble_p142_final_evidence(matrix, manifest=bad_manifest, review=review, project_root=ROOT, profile=p142_profile())
    elif mutation == "review_identity":
        bad_review = deepcopy(review)
        bad_review["implementation_identity"] = bad_review["reviewer_identity"]
        bad_review["review_hash"] = stable_hash({key: value for key, value in bad_review.items() if key != "review_hash"})
        with pytest.raises(ValueError, match="identity_not_independent"):
            assemble_p142_final_evidence(matrix, manifest=manifest, review=bad_review, project_root=ROOT, profile=p142_profile())
    elif mutation == "review_hash":
        bad_review = deepcopy(review)
        bad_review["review_hash"] = "sha256:" + "f" * 64
        with pytest.raises(ValueError, match="review_hash_invalid"):
            assemble_p142_final_evidence(matrix, manifest=manifest, review=bad_review, project_root=ROOT, profile=p142_profile())
    elif mutation == "profile":
        bad_profile = p142_profile()
        bad_profile["cases"][0]["scenario"] = "forged"
        with pytest.raises(ValueError, match="profile_catalog_drift"):
            build_p142_freeze_manifest(project_root=ROOT, profile=bad_profile, matrix=matrix)
    else:
        original = __import__("app.services.p142_release_evidence", fromlist=["_read_json"])._read_json

        def stale(path: Path) -> dict[str, object]:
            value = original(path)
            if mutation == "p141" and path.as_posix().endswith("evals/p141/output/release-evidence.json"):
                value["evidence_hash"] = "sha256:" + "f" * 64
            return value

        monkeypatch.setattr("app.services.p142_release_evidence._read_json", stale)
        if mutation == "plan_review":
            monkeypatch.setattr(
                "app.services.p142_release_evidence._validate_plan_review",
                lambda path, source_hashes: (_ for _ in ()).throw(ValueError("p142_plan_review_not_approved")),
            )
            with pytest.raises(ValueError, match="plan_review_not_approved"):
                build_p142_freeze_manifest(project_root=ROOT, profile=p142_profile(), matrix=matrix)
        else:
            with pytest.raises(ValueError, match="p141_release_evidence_hash_invalid|p141_release_dependency_drift"):
                build_p142_freeze_manifest(project_root=ROOT, profile=p142_profile(), matrix=matrix)


def test_p142_final_mode_does_not_rewrite_frozen_inputs(tmp_path: Path) -> None:
    matrix = qualified_p142_matrix()
    manifest = build_p142_freeze_manifest(project_root=ROOT, profile=p142_profile(), matrix=matrix)
    review = p142_review(manifest)
    profile_path = tmp_path / "profile.json"
    matrix_path = tmp_path / "matrix.json"
    manifest_path = tmp_path / "manifest.json"
    review_path = tmp_path / "review.json"
    for path, value in (
        (profile_path, p142_profile()),
        (matrix_path, matrix),
        (manifest_path, manifest),
        (review_path, review),
    ):
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    before = (matrix_path.read_bytes(), manifest_path.read_bytes())
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_p142_loopback_transport_lab.py",
            "--mode",
            "final",
            "--profile",
            str(profile_path),
            "--canonical-matrix",
            str(matrix_path),
            "--freeze-manifest",
            str(manifest_path),
            "--final-review",
            str(review_path),
            "--output-dir",
            str(tmp_path / "output"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert (matrix_path.read_bytes(), manifest_path.read_bytes()) == before
    assert json.loads((tmp_path / "output/release-evidence.json").read_text(encoding="utf-8"))["status"] == P142_READY_STATUS


def test_p142_final_review_artifact_records_independent_approval() -> None:
    review = json.loads((ROOT / IMPLEMENTATION_REVIEW_ARTIFACT_PATH).read_text(encoding="utf-8"))
    assert review["decision"] == "approve"
    assert review["findings"] == {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
    assert review["reviewer_type"] == "codex-native-code-reviewer"
    assert review["reviewer_agent_id"] == "019f621e-febf-7491-af5c-ba0a05cee425"
