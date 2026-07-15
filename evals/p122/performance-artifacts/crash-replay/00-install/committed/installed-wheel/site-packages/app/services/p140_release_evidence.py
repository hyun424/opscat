"""Frozen final-evidence contracts for P140 qualification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p140_runner import p140_release_case_catalog, validate_p140_case_matrix

P140_PRELIMINARY_STATUS = "p140_preliminary_qualification_frozen"
P140_READY_STATUS = "p140_p139_deadman_adapter_qualified"
P140_BLOCKED_STATUS = "p140_blocked"
FREEZE_SCHEMA_VERSION = "p140.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p140.final_implementation_review.v1"
EVIDENCE_SCHEMA_VERSION = "p140.release_evidence.v1"
PROFILE_SCHEMA_VERSION = "p140.p139_deadman_adapter_profile.v1"
REQUIRED_LIMITATIONS = frozenset(
    {
        "local_p133_deadman_evidence_only_no_delivery",
        "no_auth_credentials_network_notification_action_remediation_or_operator_replacement",
    }
)
EXPECTED_P133_STATUS = "p133_local_deadman_outbox_qualified"
EXPECTED_P133_EVIDENCE_HASH = "sha256:ba47502a7b82cea2521c581716801563f4ea31746cc243dfbbbd639707ffe73f"
EXPECTED_P139_STATUS = "p139_local_triage_service_host_qualified"
EXPECTED_P139_EVIDENCE_HASH = "sha256:154009dfae9c6485cd46cc280fa45fb1eda28be30daadbadd3058557be8bbf3e"
EXPECTED_P139_REVIEW_HASH = "sha256:afa63a0223379eb9707ee66360fc016f7552534c25e1659ac4ba2d51546f7226"

P140_SOURCE_PATHS: tuple[str, ...] = (
    ".omx/plans/opscat-p140-p139-deadman-adapter.md",
    "app/p140_deadman_cli.py",
    "app/services/p110_evaluation.py",
    "app/services/p121_signals.py",
    "app/services/p133_deadman_outbox.py",
    "app/services/p139_local_triage_service.py",
    "app/services/p140_p139_deadman_adapter.py",
    "app/services/p140_runner.py",
    "app/services/p140_release_evidence.py",
    "deploy/p140/opscat-triage-deadman.service",
    "deploy/p140/compose.triage-deadman.yaml",
    "docs/operations/p140-p139-deadman-adapter-roadmap.md",
    "docs/operations/p140-plan-review.md",
    "docs/operations/p140-test-spec.md",
    "evals/p140/input/p139-deadman-adapter-profile.json",
    "pyproject.toml",
    "scripts/run_p140_p139_deadman_adapter.py",
    "scripts/verify.sh",
    "tests/fixtures/p140/__init__.py",
    "tests/fixtures/p140/builders.py",
    "tests/test_p140_p139_deadman_adapter.py",
    "tests/test_p140_deadman_cli.py",
    "tests/test_p140_runner.py",
    "tests/test_p140_release_evidence.py",
)


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p140_source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in P140_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p140_source_missing_or_unsafe:{relative}")
        result[relative] = file_sha256(path)
    return result


def build_p140_freeze_manifest(
    *,
    project_root: Path,
    profile: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    validated = validate_p140_case_matrix(matrix)
    p133 = _read_json(project_root / "evals/p133/release-evidence.json")
    p139 = _read_json(project_root / "evals/p139/output/release-evidence.json")
    review = _read_json(project_root / "evals/p139/final-implementation-review.json")
    if p133.get("release_evidence_hash") != stable_hash(
        {key: item for key, item in p133.items() if key != "release_evidence_hash"}
    ):
        raise ValueError("p133_release_evidence_hash_invalid")
    if p133.get("release_status") != EXPECTED_P133_STATUS or p133.get("release_evidence_hash") != EXPECTED_P133_EVIDENCE_HASH:
        raise ValueError("p133_release_dependency_drift")
    if p139.get("evidence_hash") != stable_hash({key: item for key, item in p139.items() if key != "evidence_hash"}):
        raise ValueError("p139_release_evidence_hash_invalid")
    if p139.get("status") != EXPECTED_P139_STATUS or p139.get("evidence_hash") != EXPECTED_P139_EVIDENCE_HASH:
        raise ValueError("p139_release_dependency_drift")
    if review.get("review_hash") != stable_hash({key: item for key, item in review.items() if key != "review_hash"}):
        raise ValueError("p139_review_hash_invalid")
    if review.get("review_hash") != EXPECTED_P139_REVIEW_HASH:
        raise ValueError("p139_review_dependency_drift")
    source_hashes = current_p140_source_hashes(project_root)
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "approved_plan_sha256": source_hashes[".omx/plans/opscat-p140-p139-deadman-adapter.md"],
        "profile_hash": stable_hash(validated_profile),
        "matrix_hash": validated["matrix_hash"],
        "source_bindings": source_hashes,
        "dependency_bindings": {
            "p133_status": p133["release_status"],
            "p133_evidence_hash": p133["release_evidence_hash"],
            "p139_status": p139["status"],
            "p139_evidence_hash": p139["evidence_hash"],
            "p139_review_hash": review["review_hash"],
        },
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def build_p140_preliminary_evidence(matrix: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p140_case_matrix(matrix)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P140_PRELIMINARY_STATUS if validated["failed"] == 0 else P140_BLOCKED_STATUS,
        "expected": 32,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": manifest.get("freeze_manifest_hash"),
        "final_review_hash": None,
        "limitations": [
            "local_p133_deadman_evidence_only_no_delivery",
            "no_auth_credentials_network_notification_action_remediation_or_operator_replacement",
        ],
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def build_p140_final_review(
    *,
    manifest: Mapping[str, Any],
    reviewer_identity: str,
    implementation_identity: str,
    limitations: Sequence[str],
) -> dict[str, Any]:
    reviewer = _identity(reviewer_identity, "reviewer_identity")
    implementer = _identity(implementation_identity, "implementation_identity")
    if reviewer == implementer:
        raise ValueError("p140_review_identity_not_independent")
    limitation_values = list(limitations)
    if not REQUIRED_LIMITATIONS.issubset(limitation_values):
        raise ValueError("p140_review_limitations_incomplete")
    review: dict[str, Any] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "reviewer_identity": reviewer,
        "implementation_identity": implementer,
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": deepcopy(manifest["source_bindings"]),
        "reviewed_dependency_bindings": deepcopy(manifest["dependency_bindings"]),
        "limitations": limitation_values,
    }
    review["review_hash"] = stable_hash(review)
    return review


def assemble_p140_final_evidence(
    matrix: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
    project_root: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_p140_case_matrix(matrix)
    expected_manifest = build_p140_freeze_manifest(project_root=project_root, profile=profile, matrix=validated)
    if dict(manifest) != expected_manifest:
        raise ValueError("p140_freeze_manifest_drift")
    _validate_final_review(review, manifest=expected_manifest)
    ready = validated["passed"] == 32 and validated["failed"] == 0
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P140_READY_STATUS if ready else P140_BLOCKED_STATUS,
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
        raise ValueError("invalid_p140_review_schema")
    reviewer = _identity(review.get("reviewer_identity"), "reviewer_identity")
    implementer = _identity(review.get("implementation_identity"), "implementation_identity")
    if reviewer == implementer:
        raise ValueError("p140_review_identity_not_independent")
    if review.get("decision") != "approve" or review.get("findings") != {"p0": 0, "p1": 0, "p2": 0, "p3": 0}:
        raise ValueError("p140_review_not_approved")
    bindings = {
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": manifest["source_bindings"],
        "reviewed_dependency_bindings": manifest["dependency_bindings"],
    }
    if any(review.get(key) != value for key, value in bindings.items()):
        raise ValueError("p140_review_binding_drift")
    limitations = review.get("limitations")
    if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
        raise ValueError("p140_review_limitations_invalid")
    if not REQUIRED_LIMITATIONS.issubset(limitations):
        raise ValueError("p140_review_limitations_incomplete")
    if review.get("review_hash") != stable_hash({key: item for key, item in review.items() if key != "review_hash"}):
        raise ValueError("p140_review_hash_invalid")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if set(value) != {"schema_version", "cases"} or value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_p140_profile_schema")
    if value.get("cases") != p140_release_case_catalog():
        raise ValueError("p140_profile_catalog_drift")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError(f"invalid_p140_{label}")
    return value


__all__ = [
    "P140_BLOCKED_STATUS",
    "P140_PRELIMINARY_STATUS",
    "P140_READY_STATUS",
    "assemble_p140_final_evidence",
    "build_p140_final_review",
    "build_p140_freeze_manifest",
    "build_p140_preliminary_evidence",
    "current_p140_source_hashes",
]
