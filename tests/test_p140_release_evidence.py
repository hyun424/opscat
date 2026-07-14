from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p140_release_evidence import (
    P140_PRELIMINARY_STATUS,
    P140_READY_STATUS,
    REQUIRED_LIMITATIONS,
    assemble_p140_final_evidence,
    build_p140_final_review,
    build_p140_freeze_manifest,
    build_p140_preliminary_evidence,
)
from app.services.p140_runner import p140_release_case_catalog
from tests.test_p140_runner import qualified_matrix

ROOT = Path(__file__).resolve().parents[1]


def profile() -> dict[str, object]:
    return {"schema_version": "p140.p139_deadman_adapter_profile.v1", "cases": p140_release_case_catalog()}


def test_preliminary_and_final_evidence_bind_sources_dependencies_and_review() -> None:
    matrix = qualified_matrix()
    manifest = build_p140_freeze_manifest(project_root=ROOT, profile=profile(), matrix=matrix)
    preliminary = build_p140_preliminary_evidence(matrix, manifest)
    assert preliminary["status"] == P140_PRELIMINARY_STATUS
    review = build_p140_final_review(
        manifest=manifest,
        reviewer_identity="local-adversarial-p140-reviewer",
        implementation_identity="p140-implementation-agent",
        limitations=tuple(sorted(REQUIRED_LIMITATIONS | {"notification_authority_not_present"})),
    )
    final = assemble_p140_final_evidence(matrix, manifest=manifest, review=review, project_root=ROOT, profile=profile())
    assert final["status"] == P140_READY_STATUS
    assert final["passed"] == 32


def test_final_evidence_rejects_manifest_review_and_dependency_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    matrix = qualified_matrix()
    manifest = build_p140_freeze_manifest(project_root=ROOT, profile=profile(), matrix=matrix)
    review = build_p140_final_review(
        manifest=manifest,
        reviewer_identity="reviewer",
        implementation_identity="implementer",
        limitations=tuple(sorted(REQUIRED_LIMITATIONS)),
    )
    bad_manifest = deepcopy(manifest)
    bad_manifest["matrix_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="freeze_manifest_drift"):
        assemble_p140_final_evidence(matrix, manifest=bad_manifest, review=review, project_root=ROOT, profile=profile())
    bad_review = deepcopy(review)
    bad_review["findings"]["p1"] = 1
    with pytest.raises(ValueError, match="review_not_approved"):
        assemble_p140_final_evidence(matrix, manifest=manifest, review=bad_review, project_root=ROOT, profile=profile())

    original = __import__("app.services.p140_release_evidence", fromlist=["_read_json"])._read_json

    def stale(path: Path) -> dict[str, object]:
        value = original(path)
        if path.as_posix().endswith("evals/p133/release-evidence.json"):
            value["release_evidence_hash"] = "sha256:" + "f" * 64
        return value

    monkeypatch.setattr("app.services.p140_release_evidence._read_json", stale)
    with pytest.raises(ValueError, match="p133_release_evidence_hash_invalid"):
        build_p140_freeze_manifest(project_root=ROOT, profile=profile(), matrix=matrix)


def test_release_rejects_profile_drift_and_non_independent_or_incomplete_review() -> None:
    matrix = qualified_matrix()
    bad_profile = profile()
    bad_profile["schema_version"] = "p140.wrong.v1"
    with pytest.raises(ValueError, match="invalid_p140_profile_schema"):
        build_p140_freeze_manifest(project_root=ROOT, profile=bad_profile, matrix=matrix)

    manifest = build_p140_freeze_manifest(project_root=ROOT, profile=profile(), matrix=matrix)
    with pytest.raises(ValueError, match="identity_not_independent"):
        build_p140_final_review(
            manifest=manifest,
            reviewer_identity="same-agent",
            implementation_identity="same-agent",
            limitations=tuple(sorted(REQUIRED_LIMITATIONS)),
        )
    with pytest.raises(ValueError, match="limitations_incomplete"):
        build_p140_final_review(
            manifest=manifest,
            reviewer_identity="reviewer",
            implementation_identity="implementer",
            limitations=(),
        )


def test_tracked_final_artifacts_are_current_and_qualified() -> None:
    tracked_profile = json.loads(
        (ROOT / "evals/p140/input/p139-deadman-adapter-profile.json").read_text(encoding="utf-8")
    )
    tracked_matrix = json.loads((ROOT / "evals/p140/output/canonical-matrix.json").read_text(encoding="utf-8"))
    tracked_manifest = json.loads((ROOT / "evals/p140/output/freeze-manifest.json").read_text(encoding="utf-8"))
    tracked_review = json.loads(
        (ROOT / "evals/p140/final-implementation-review.json").read_text(encoding="utf-8")
    )
    evidence = assemble_p140_final_evidence(
        tracked_matrix,
        manifest=tracked_manifest,
        review=tracked_review,
        project_root=ROOT,
        profile=tracked_profile,
    )
    assert evidence["status"] == P140_READY_STATUS
    assert evidence["passed"] == 32
