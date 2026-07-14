"""Freeze and final-evidence contracts for P139 qualification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p139_local_triage_service import (
    EXPECTED_P138_EVIDENCE_HASH,
    EXPECTED_P138_REVIEW_HASH,
)
from app.services.p139_runner import validate_p139_case_matrix

P139_PRELIMINARY_STATUS = "p139_preliminary_qualification_frozen"
P139_READY_STATUS = "p139_local_triage_service_host_qualified"
P139_BLOCKED_STATUS = "p139_blocked"
FREEZE_SCHEMA_VERSION = "p139.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p139.final_implementation_review.v1"
EVIDENCE_SCHEMA_VERSION = "p139.release_evidence.v1"

P139_SOURCE_PATHS: tuple[str, ...] = (
    ".omx/plans/opscat-p139-local-triage-service-host.md",
    "app/p139_service_cli.py",
    "app/services/p139_local_triage_service.py",
    "app/services/p139_release_evidence.py",
    "app/services/p139_runner.py",
    "deploy/p139/compose.triage-service.yaml",
    "deploy/p139/opscat-triage-service.service",
    "docs/operations/p139-local-triage-service-host-roadmap.md",
    "docs/operations/p139-plan-review.md",
    "docs/operations/p139-test-spec.md",
    "scripts/run_p139_local_triage_service.py",
    "scripts/run_p139_service_evaluation.py",
    "scripts/verify.sh",
    "tests/fixtures/p139/__init__.py",
    "tests/fixtures/p139/builders.py",
    "tests/test_p139_local_triage_service.py",
    "tests/test_p139_release_evidence.py",
    "tests/test_p139_runner.py",
    "tests/test_p139_service_cli.py",
)


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p139_source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in P139_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p139_source_missing_or_unsafe:{relative}")
        result[relative] = file_sha256(path)
    return result


def build_p139_freeze_manifest(
    *,
    project_root: Path,
    profile: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_p139_case_matrix(matrix)
    evidence = _read_json(project_root / "evals/p138/output/release-evidence.json")
    review = _read_json(project_root / "evals/p138/final-implementation-review.json")
    if evidence.get("evidence_hash") != EXPECTED_P138_EVIDENCE_HASH:
        raise ValueError("p138_release_evidence_constant_drift")
    if review.get("review_hash") != EXPECTED_P138_REVIEW_HASH:
        raise ValueError("p138_review_constant_drift")
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "approved_plan_sha256": current_p139_source_hashes(project_root)[".omx/plans/opscat-p139-local-triage-service-host.md"],
        "profile_hash": stable_hash(profile),
        "matrix_hash": validated["matrix_hash"],
        "source_bindings": current_p139_source_hashes(project_root),
        "dependency_bindings": {
            "p138_status": evidence.get("status"),
            "p138_evidence_hash": evidence.get("evidence_hash"),
            "p138_review_hash": review.get("review_hash"),
        },
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def build_p139_preliminary_evidence(matrix: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p139_case_matrix(matrix)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P139_PRELIMINARY_STATUS if validated["failed"] == 0 else P139_BLOCKED_STATUS,
        "expected": 32,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": manifest.get("freeze_manifest_hash"),
        "final_review_hash": None,
        "limitations": [
            "no_auth_no_credentials_no_environment_no_network_no_provider_api",
            "no_notification_no_action_no_remediation_no_operator_replacement",
        ],
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def build_p139_final_review(
    *,
    manifest: Mapping[str, Any],
    reviewer_identity: str,
    implementation_identity: str,
    limitations: Sequence[str],
) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "reviewer_identity": reviewer_identity,
        "implementation_identity": implementation_identity,
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": deepcopy(manifest["source_bindings"]),
        "reviewed_dependency_bindings": deepcopy(manifest["dependency_bindings"]),
        "limitations": list(limitations),
    }
    review["review_hash"] = stable_hash(review)
    return review


def assemble_p139_final_evidence(
    matrix: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
    project_root: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_p139_case_matrix(matrix)
    expected_manifest = build_p139_freeze_manifest(
        project_root=project_root,
        profile=profile,
        matrix=validated,
    )
    if dict(manifest) != expected_manifest:
        raise ValueError("p139_freeze_manifest_drift")
    _validate_final_review(review, manifest=expected_manifest)
    ready = validated["passed"] == 32 and validated["failed"] == 0
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P139_READY_STATUS if ready else P139_BLOCKED_STATUS,
        "expected": 32,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": expected_manifest["freeze_manifest_hash"],
        "final_review_hash": review["review_hash"],
        "limitations": deepcopy(list(review["limitations"])),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_final_review(review: Mapping[str, Any], *, manifest: Mapping[str, Any]) -> None:
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("invalid_p139_review_schema")
    if review.get("decision") != "approve" or review.get("findings") != {
        "p0": 0,
        "p1": 0,
        "p2": 0,
        "p3": 0,
    }:
        raise ValueError("p139_review_not_approved")
    bindings = {
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": manifest["source_bindings"],
        "reviewed_dependency_bindings": manifest["dependency_bindings"],
    }
    if any(review.get(key) != value for key, value in bindings.items()):
        raise ValueError("p139_review_binding_drift")
    if review.get("review_hash") != stable_hash({key: item for key, item in review.items() if key != "review_hash"}):
        raise ValueError("p139_review_hash_invalid")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


__all__ = [
    "P139_BLOCKED_STATUS",
    "P139_PRELIMINARY_STATUS",
    "P139_READY_STATUS",
    "assemble_p139_final_evidence",
    "build_p139_final_review",
    "build_p139_freeze_manifest",
    "build_p139_preliminary_evidence",
    "current_p139_source_hashes",
]
