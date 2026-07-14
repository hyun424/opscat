from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p141_release_evidence import (
    P141_PRELIMINARY_STATUS,
    P141_READY_STATUS,
    REQUIRED_LIMITATIONS,
    REVIEW_ARTIFACT_PATH,
    assemble_p141_final_evidence,
    build_p141_freeze_manifest,
    build_p141_preliminary_evidence,
    file_sha256,
)
from app.services.p141_runner import p141_release_case_catalog
from tests.test_p141_runner import qualified_p141_matrix

ROOT = Path(__file__).resolve().parents[1]


def p141_profile() -> dict[str, Any]:
    return {"schema_version": "p141.notification_authority_profile.v1", "cases": p141_release_case_catalog()}


def p141_review(manifest: dict[str, Any]) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema_version": "p141.final_implementation_review.v1",
        "reviewer_identity": "p141-independent-code-reviewer",
        "reviewer_agent_id": "019f60e5-448c-75c2-a0af-6a328774ad61",
        "reviewer_type": "codex-native-code-reviewer",
        "implementation_identity": "p141-implementation-agent",
        "reviewed_at": "2026-07-14T12:00:00Z",
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "findings_resolved": [
            "runner provenance bound",
            "review auto-approval removed",
            "listing bound to P133",
            "fd-anchored filesystem access verified",
        ],
        "review_artifact_path": REVIEW_ARTIFACT_PATH,
        "review_artifact_sha256": file_sha256(ROOT / REVIEW_ARTIFACT_PATH),
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": deepcopy(manifest["source_bindings"]),
        "reviewed_dependency_bindings": deepcopy(manifest["dependency_bindings"]),
        "limitations": sorted(REQUIRED_LIMITATIONS),
    }
    review["review_hash"] = stable_hash(review)
    return review


def test_p141_preliminary_and_final_evidence_bind_sources_dependencies_and_review() -> None:
    matrix = qualified_p141_matrix()
    manifest = build_p141_freeze_manifest(project_root=ROOT, profile=p141_profile(), matrix=matrix)
    preliminary = build_p141_preliminary_evidence(matrix, manifest)
    assert preliminary["status"] == P141_PRELIMINARY_STATUS
    review = p141_review(manifest)
    final = assemble_p141_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=p141_profile())
    assert final["status"] == P141_READY_STATUS
    assert final["passed"] == 36


def test_p141_release_rejects_manifest_review_dependency_and_identity_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    matrix = qualified_p141_matrix()
    manifest = build_p141_freeze_manifest(project_root=ROOT, profile=p141_profile(), matrix=matrix)
    review = p141_review(manifest)
    bad_manifest = deepcopy(manifest)
    bad_manifest["matrix_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="freeze_manifest_drift"):
        assemble_p141_final_evidence(matrix, manifest=bad_manifest, review=review, project_root=ROOT, profile=p141_profile())
    bad_review = deepcopy(review)
    bad_review["findings"]["p1"] = 1
    with pytest.raises(ValueError, match="review_not_approved"):
        assemble_p141_final_evidence(matrix, manifest=manifest, review=bad_review, project_root=ROOT, profile=p141_profile())
    same_identity = deepcopy(review)
    same_identity["implementation_identity"] = same_identity["reviewer_identity"]
    same_identity["review_hash"] = stable_hash({key: value for key, value in same_identity.items() if key != "review_hash"})
    with pytest.raises(ValueError, match="identity_not_independent"):
        assemble_p141_final_evidence(matrix, manifest=manifest, review=same_identity, project_root=ROOT, profile=p141_profile())

    original = __import__("app.services.p141_release_evidence", fromlist=["_read_json"])._read_json

    def stale(path: Path) -> dict[str, object]:
        value = original(path)
        if path.as_posix().endswith("evals/p140/output/release-evidence.json"):
            value["evidence_hash"] = "sha256:" + "f" * 64
        return value

    monkeypatch.setattr("app.services.p141_release_evidence._read_json", stale)
    with pytest.raises(ValueError, match="dependency_hash_drift"):
        build_p141_freeze_manifest(project_root=ROOT, profile=p141_profile(), matrix=matrix)


def test_p141_final_mode_does_not_rewrite_frozen_inputs(tmp_path: Path) -> None:
    matrix = qualified_p141_matrix()
    manifest = build_p141_freeze_manifest(project_root=ROOT, profile=p141_profile(), matrix=matrix)
    review = p141_review(manifest)
    profile_path = tmp_path / "profile.json"
    matrix_path = tmp_path / "matrix.json"
    manifest_path = tmp_path / "manifest.json"
    review_path = tmp_path / "review.json"
    for path, value in (
        (profile_path, p141_profile()),
        (matrix_path, matrix),
        (manifest_path, manifest),
        (review_path, review),
    ):
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    before = (matrix_path.read_bytes(), manifest_path.read_bytes())
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_p141_notification_authority.py",
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


def test_p141_tracked_final_artifacts_are_current_and_qualified() -> None:
    profile = json.loads((ROOT / "evals/p141/input/notification-authority-profile.json").read_text(encoding="utf-8"))
    matrix = json.loads((ROOT / "evals/p141/output/canonical-matrix.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "evals/p141/output/freeze-manifest.json").read_text(encoding="utf-8"))
    review = json.loads((ROOT / "evals/p141/final-implementation-review.json").read_text(encoding="utf-8"))
    evidence = assemble_p141_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=profile)
    assert evidence["status"] == P141_READY_STATUS
    assert evidence["passed"] == 36
