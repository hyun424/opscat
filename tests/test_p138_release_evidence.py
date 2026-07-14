from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p138_observation_triage_supervisor import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RUNTIME_ACTIVITY_KEYS,
)
from app.services.p138_release_evidence import (
    APPROVED_PLAN_SHA256,
    FINAL_REVIEW_SCHEMA_VERSION,
    P138_READY_STATUS,
    P138ReleaseEvidenceError,
    assemble_p138_release_evidence_from_frozen_matrix,
    build_p138_freeze_manifest,
    current_p138_source_hashes,
    p138_fixture_hash,
    p138_profile_hash,
    validate_p138_canonical_matrix,
    validate_p138_final_implementation_review,
    validate_p138_freeze_manifest,
    validate_p138_release_evidence,
)
from app.services.p138_runner import p138_release_case_matrix, run_p138_preliminary_matrix


def _zero(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _resources() -> dict[str, int]:
    return {
        "wall_time_ms": 0,
        "cpu_time_ms": 0,
        "child_cpu_time_ms": 0,
        "peak_memory_bytes": 0,
        "wall_limit_ms": 30_000,
        "cpu_limit_ms": 15_000,
        "peak_memory_limit_bytes": 134_217_728,
    }


def _dependencies() -> dict[str, str]:
    return {
        "p136_status": "p136_incremental_local_observation_qualified",
        "p136_evidence_hash": stable_hash({"dependency": "p136-evidence"}),
        "p136_review_hash": stable_hash({"dependency": "p136-review"}),
        "p137_status": "p137_local_evidence_triage_qualified",
        "p137_evidence_hash": stable_hash({"dependency": "p137-evidence"}),
        "p137_review_hash": stable_hash({"dependency": "p137-review"}),
    }


def _factory(case_id: str) -> dict[str, Any]:
    row = next(item for item in p138_release_case_matrix() if item["case_id"] == case_id)

    def execute() -> dict[str, Any]:
        expected = deepcopy(row["expected"])
        return {
            "status": expected["status"],
            "error": expected["error"],
            "stop_reason": expected["stop_reason"],
            "phase_path": expected["phase_path"],
            "component_boundaries": expected["component_boundaries"],
            "durable_post_state": expected["durable_post_state"],
            "runtime_activity": _zero(RUNTIME_ACTIVITY_KEYS),
            "forbidden_authority": _zero(FORBIDDEN_AUTHORITY_KEYS),
            "evaluator_activity": _zero(EVALUATOR_ACTIVITY_KEYS),
            "resource_usage": _resources(),
            "execution_source": "tests.test_p138_release_evidence._factory",
        }

    return {
        "schema_version": "p138.case_runtime.v1",
        "case_id": case_id,
        "input_profile": {"scenario": row["scenario"]},
        "expected_runtime_activity": _zero(RUNTIME_ACTIVITY_KEYS),
        "expected_forbidden_authority": _zero(FORBIDDEN_AUTHORITY_KEYS),
        "expected_evaluator_activity": _zero(EVALUATOR_ACTIVITY_KEYS),
        "expected_resource_usage": _resources(),
        "execute": execute,
    }


def _profile(project_root: Path) -> dict[str, Any]:
    return json.loads((project_root / "evals/p138/input/observation-triage-supervisor-profile.json").read_text(encoding="utf-8"))


def _review(
    *,
    sources: dict[str, str],
    profile_hash: str,
    fixture_hash: str,
    matrix_hash: str,
    freeze_manifest_hash: str,
) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema_version": FINAL_REVIEW_SCHEMA_VERSION,
        "reviewer_identity": "independent-p138-release-reviewer",
        "implementation_identity": "p138-implementation-executor",
        "approved_plan_sha256": APPROVED_PLAN_SHA256,
        "reviewed_source_hashes": deepcopy(sources),
        "reviewed_profile_hash": profile_hash,
        "reviewed_fixture_hash": fixture_hash,
        "reviewed_matrix_hash": matrix_hash,
        "reviewed_freeze_manifest_hash": freeze_manifest_hash,
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "decision": "approve",
        "limitations": ["no_auth_no_credentials_no_environment_no_network_no_provider_api_no_notification_no_action_no_remediation"],
    }
    review["review_hash"] = stable_hash(review)
    return review


def _frozen(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[1]
    profile = _profile(project_root)
    matrix = run_p138_preliminary_matrix(tmp_path, runtime_factory=_factory)
    sources = current_p138_source_hashes(project_root)
    manifest = build_p138_freeze_manifest(
        source_bindings=sources,
        profile=profile,
        canonical_matrix=matrix,
        dependency_bindings=_dependencies(),
        project_root=project_root,
    )
    review = _review(
        sources=sources,
        profile_hash=p138_profile_hash(profile),
        fixture_hash=p138_fixture_hash(profile, project_root=project_root),
        matrix_hash=matrix["matrix_hash"],
        freeze_manifest_hash=manifest["freeze_manifest_hash"],
    )
    return project_root, profile, matrix, manifest, review


@pytest.mark.parametrize("artifact", ["matrix", "manifest", "review", "evidence"])
def test_all_release_artifacts_are_exact_key_and_canonical_hash_validated(tmp_path: Path, artifact: str) -> None:
    project_root, profile, matrix, manifest, review = _frozen(tmp_path)
    evidence = assemble_p138_release_evidence_from_frozen_matrix(
        matrix,
        freeze_manifest=manifest,
        final_implementation_review=review,
        expected_source_hashes=current_p138_source_hashes(project_root),
        expected_profile_hash=p138_profile_hash(profile),
        expected_fixture_hash=p138_fixture_hash(profile, project_root=project_root),
    )
    validators: dict[
        str,
        tuple[Callable[[Mapping[str, Any]], Any], dict[str, Any]],
    ] = {
        "matrix": (validate_p138_canonical_matrix, matrix),
        "manifest": (validate_p138_freeze_manifest, manifest),
        "review": (validate_p138_final_implementation_review, review),
        "evidence": (
            lambda value: validate_p138_release_evidence(
                value,
                final_implementation_review=review,
            ),
            evidence,
        ),
    }
    validator, value = validators[artifact]
    tampered = deepcopy(value)
    tampered["unexpected"] = True
    with pytest.raises(P138ReleaseEvidenceError, match="fields"):
        validator(tampered)


def test_final_release_consumes_frozen_30_case_matrix_without_regeneration(tmp_path: Path) -> None:
    project_root, profile, matrix, manifest, review = _frozen(tmp_path)
    frozen_matrix = deepcopy(matrix)
    frozen_manifest = deepcopy(manifest)
    evidence = assemble_p138_release_evidence_from_frozen_matrix(
        matrix,
        freeze_manifest=manifest,
        final_implementation_review=review,
        expected_source_hashes=current_p138_source_hashes(project_root),
        expected_profile_hash=p138_profile_hash(profile),
        expected_fixture_hash=p138_fixture_hash(profile, project_root=project_root),
    )
    assert matrix == frozen_matrix
    assert manifest == frozen_manifest
    assert evidence["status"] == P138_READY_STATUS
    assert evidence["totals"] == {"expected": 30, "passed": 30, "failed": 0}
    assert evidence["forbidden_authority"] == _zero(FORBIDDEN_AUTHORITY_KEYS)
    assert evidence["expected_forbidden_authority"] == _zero(FORBIDDEN_AUTHORITY_KEYS)


def test_final_review_rejects_self_approval_and_any_unresolved_p0_p1_p2(
    tmp_path: Path,
) -> None:
    _, _, _, _, review = _frozen(tmp_path)
    self_review = deepcopy(review)
    self_review["reviewer_identity"] = self_review["implementation_identity"]
    self_review["review_hash"] = stable_hash({key: value for key, value in self_review.items() if key != "review_hash"})
    with pytest.raises(P138ReleaseEvidenceError, match="independent"):
        validate_p138_final_implementation_review(self_review)

    for severity in ("p0", "p1", "p2"):
        blocked = deepcopy(review)
        blocked["findings"][severity] = 1
        blocked["review_hash"] = stable_hash({key: value for key, value in blocked.items() if key != "review_hash"})
        with pytest.raises(P138ReleaseEvidenceError, match="blocking_findings"):
            validate_p138_final_implementation_review(blocked)


def test_transitive_drift_is_rejected_by_manifest_review_and_final_evidence(
    tmp_path: Path,
) -> None:
    project_root, profile, matrix, manifest, review = _frozen(tmp_path)
    sources = current_p138_source_hashes(project_root)
    drifted = deepcopy(sources)
    drifted["app/services/p136_incremental_observer.py"] = stable_hash({"drift": True})
    with pytest.raises(P138ReleaseEvidenceError, match="source_stale"):
        assemble_p138_release_evidence_from_frozen_matrix(
            matrix,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=drifted,
            expected_profile_hash=p138_profile_hash(profile),
            expected_fixture_hash=p138_fixture_hash(profile, project_root=project_root),
        )


def test_dependency_release_hash_drift_is_rejected_even_when_outer_hashes_are_rebuilt(
    tmp_path: Path,
) -> None:
    project_root, profile, matrix, manifest, review = _frozen(tmp_path)
    expected_dependencies = _dependencies()
    drifted_manifest = deepcopy(manifest)
    drifted_manifest["dependency_bindings"]["p137_evidence_hash"] = stable_hash(
        {"dependency": "stale-p137-evidence"}
    )
    drifted_manifest["freeze_manifest_hash"] = stable_hash(
        {
            key: value
            for key, value in drifted_manifest.items()
            if key != "freeze_manifest_hash"
        }
    )
    with pytest.raises(P138ReleaseEvidenceError, match="dependency_stale"):
        validate_p138_freeze_manifest(
            drifted_manifest,
            expected_dependency_bindings=expected_dependencies,
        )

    evidence = assemble_p138_release_evidence_from_frozen_matrix(
        matrix,
        freeze_manifest=manifest,
        final_implementation_review=review,
        expected_source_hashes=current_p138_source_hashes(project_root),
        expected_profile_hash=p138_profile_hash(profile),
        expected_fixture_hash=p138_fixture_hash(profile, project_root=project_root),
        expected_dependency_bindings=expected_dependencies,
    )
    drifted_evidence = deepcopy(evidence)
    drifted_evidence["dependency_bindings"]["p136_review_hash"] = stable_hash(
        {"dependency": "stale-p136-review"}
    )
    drifted_evidence["evidence_hash"] = stable_hash(
        {
            key: value
            for key, value in drifted_evidence.items()
            if key != "evidence_hash"
        }
    )
    with pytest.raises(P138ReleaseEvidenceError, match="dependency_binding_mismatch"):
        validate_p138_release_evidence(
            drifted_evidence,
            final_implementation_review=review,
            expected_dependency_bindings=expected_dependencies,
        )


def test_matrix_rebuild_rejects_counter_hash_and_case_denominator_tamper(
    tmp_path: Path,
) -> None:
    _, _, matrix, _, _ = _frozen(tmp_path)
    nonzero = deepcopy(matrix)
    nonzero["cases"][0]["evidence"]["forbidden_authority"]["network_call_count"] = 1
    with pytest.raises(P138ReleaseEvidenceError, match="forbidden_authority"):
        validate_p138_canonical_matrix(nonzero)

    missing = deepcopy(matrix)
    missing["cases"].pop()
    missing["matrix_hash"] = stable_hash(missing["cases"])
    with pytest.raises(P138ReleaseEvidenceError, match="case_count"):
        validate_p138_canonical_matrix(missing)

    bad_hash = deepcopy(matrix)
    bad_hash["matrix_hash"] = stable_hash({"not": "the matrix"})
    with pytest.raises(P138ReleaseEvidenceError, match="matrix_hash"):
        validate_p138_canonical_matrix(bad_hash)


def test_final_evidence_rebuilds_case_counters_and_resources(
    tmp_path: Path,
) -> None:
    project_root, profile, matrix, manifest, review = _frozen(tmp_path)
    evidence = assemble_p138_release_evidence_from_frozen_matrix(
        matrix,
        freeze_manifest=manifest,
        final_implementation_review=review,
        expected_source_hashes=current_p138_source_hashes(project_root),
        expected_profile_hash=p138_profile_hash(profile),
        expected_fixture_hash=p138_fixture_hash(profile, project_root=project_root),
    )

    counter_tamper = deepcopy(evidence)
    counter_tamper["runtime_activity"]["fsync_count"] += 1
    counter_tamper["expected_runtime_activity"]["fsync_count"] += 1
    counter_tamper["evidence_hash"] = stable_hash({key: value for key, value in counter_tamper.items() if key != "evidence_hash"})
    with pytest.raises(P138ReleaseEvidenceError, match="runtime_activity"):
        validate_p138_release_evidence(
            counter_tamper,
            final_implementation_review=review,
        )

    resource_tamper = deepcopy(evidence)
    resource_tamper["resource_usage"]["wall_time_ms"] += 1
    resource_tamper["evidence_hash"] = stable_hash({key: value for key, value in resource_tamper.items() if key != "evidence_hash"})
    with pytest.raises(P138ReleaseEvidenceError, match="resource_usage"):
        validate_p138_release_evidence(
            resource_tamper,
            final_implementation_review=review,
        )
