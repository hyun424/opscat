from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p139_release_evidence import (
    P139_PRELIMINARY_STATUS,
    P139_READY_STATUS,
    assemble_p139_final_evidence,
    build_p139_final_review,
    build_p139_freeze_manifest,
    build_p139_preliminary_evidence,
)
from app.services.p139_runner import p139_release_case_catalog
from tests.test_p139_runner import qualified_matrix

ROOT = Path(__file__).resolve().parents[1]


def profile() -> dict[str, object]:
    return {
        "schema_version": "p139.local_triage_service_profile.v1",
        "cases": p139_release_case_catalog(),
    }


def test_preliminary_and_final_evidence_bind_all_frozen_inputs() -> None:
    matrix = qualified_matrix()
    manifest = build_p139_freeze_manifest(project_root=ROOT, profile=profile(), matrix=matrix)
    preliminary = build_p139_preliminary_evidence(matrix, manifest)
    assert preliminary["status"] == P139_PRELIMINARY_STATUS
    review = build_p139_final_review(
        manifest=manifest,
        reviewer_identity="local-adversarial-p139-implementation-reviewer",
        implementation_identity="p139-parent-implementation-agent",
        limitations=("external_review_security_block_recorded",),
    )
    final = assemble_p139_final_evidence(
        matrix,
        manifest=manifest,
        review=review,
        project_root=ROOT,
        profile=profile(),
    )
    assert final["status"] == P139_READY_STATUS
    assert final["passed"] == 32


def test_final_evidence_rejects_manifest_or_review_drift() -> None:
    matrix = qualified_matrix()
    manifest = build_p139_freeze_manifest(project_root=ROOT, profile=profile(), matrix=matrix)
    review = build_p139_final_review(
        manifest=manifest,
        reviewer_identity="reviewer",
        implementation_identity="implementer",
        limitations=(),
    )
    bad_manifest = deepcopy(manifest)
    bad_manifest["matrix_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="freeze_manifest_drift"):
        assemble_p139_final_evidence(
            matrix,
            manifest=bad_manifest,
            review=review,
            project_root=ROOT,
            profile=profile(),
        )
    bad_review = deepcopy(review)
    bad_review["findings"]["p2"] = 1
    with pytest.raises(ValueError, match="review_not_approved"):
        assemble_p139_final_evidence(
            matrix,
            manifest=manifest,
            review=bad_review,
            project_root=ROOT,
            profile=profile(),
        )
