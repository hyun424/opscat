"""Frozen source and review contracts for P141 qualification."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p141_runner import p141_release_case_catalog, validate_p141_case_matrix

P141_PRELIMINARY_STATUS = "p141_preliminary_qualification_frozen"
P141_READY_STATUS = "p141_notification_authority_simulator_qualified"
P141_BLOCKED_STATUS = "p141_blocked"
FREEZE_SCHEMA_VERSION = "p141.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p141.final_implementation_review.v1"
EVIDENCE_SCHEMA_VERSION = "p141.release_evidence.v1"
PROFILE_SCHEMA_VERSION = "p141.notification_authority_profile.v1"
EXPECTED_P133_STATUS = "p133_local_deadman_outbox_qualified"
EXPECTED_P133_HASH = "sha256:ba47502a7b82cea2521c581716801563f4ea31746cc243dfbbbd639707ffe73f"
EXPECTED_P140_STATUS = "p140_p139_deadman_adapter_qualified"
EXPECTED_P140_HASH = "sha256:a13f16288a601769e5e1e0e13d1d846dbf3e32a033da0a6fd4cce17b1d388cf9"
EXPECTED_P140_REVIEW_HASH = "sha256:8772a483ee83d8d5a9580d5c971cd567d51d5201a3133d3931ae2088741f51e1"
REQUIRED_LIMITATIONS = frozenset(
    {
        "local_simulated_notification_receipts_only_no_delivery",
        "no_auth_credentials_network_p133_ack_action_remediation_mutation_or_operator_replacement",
        "local_execution_provenance_not_cryptographic_attestation",
        "independent_reviewer_identity_not_externally_authenticated",
    }
)
REVIEW_ARTIFACT_PATH = "docs/operations/p141-implementation-review.md"
_REVIEWER_AGENT_ID_RE = re.compile(r"[a-f0-9-]{20,80}\Z")

P141_SOURCE_PATHS: tuple[str, ...] = (
    ".omx/plans/opscat-p141-notification-authority-simulator.md",
    "README.md",
    "ROADMAP.md",
    "app/p141_notification_cli.py",
    "app/services/p141_notification_authority.py",
    "app/services/p141_release_evidence.py",
    "app/services/p141_runner.py",
    "docs/operations/p141-notification-authority-roadmap.md",
    "docs/operations/p141-plan-review.md",
    REVIEW_ARTIFACT_PATH,
    "docs/operations/p141-test-spec.md",
    "deploy/p141/compose.notification-authority.yaml",
    "deploy/p141/opscat-notification-authority.service",
    "evals/p141/input/notification-authority-profile.json",
    "pyproject.toml",
    "scripts/run_p141_notification_authority.py",
    "scripts/verify.sh",
    "tests/fixtures/p141/__init__.py",
    "tests/fixtures/p141/builders.py",
    "tests/test_p141_notification_authority.py",
    "tests/test_p141_notification_cli.py",
    "tests/test_p141_release_evidence.py",
    "tests/test_p141_runner.py",
)


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p141_source_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in P141_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p141_source_missing_or_unsafe:{relative}")
        hashes[relative] = file_sha256(path)
    return hashes


def build_p141_freeze_manifest(
    *, project_root: Path, profile: Mapping[str, Any], matrix: Mapping[str, Any]
) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    validated_matrix = validate_p141_case_matrix(matrix)
    p133 = _read_json(project_root / "evals/p133/release-evidence.json")
    p140 = _read_json(project_root / "evals/p140/output/release-evidence.json")
    p140_review = _read_json(project_root / "evals/p140/final-implementation-review.json")
    _validate_dependency_hash(p133, "release_evidence_hash", EXPECTED_P133_HASH)
    _validate_dependency_hash(p140, "evidence_hash", EXPECTED_P140_HASH)
    _validate_dependency_hash(p140_review, "review_hash", EXPECTED_P140_REVIEW_HASH)
    if p133.get("release_status") != EXPECTED_P133_STATUS or p140.get("status") != EXPECTED_P140_STATUS:
        raise ValueError("p141_dependency_status_drift")
    source_hashes = current_p141_source_hashes(project_root)
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "approved_plan_sha256": source_hashes[".omx/plans/opscat-p141-notification-authority-simulator.md"],
        "profile_hash": stable_hash(validated_profile),
        "matrix_hash": validated_matrix["matrix_hash"],
        "source_bindings": source_hashes,
        "dependency_bindings": {
            "p133_status": p133["release_status"],
            "p133_evidence_hash": p133["release_evidence_hash"],
            "p140_status": p140["status"],
            "p140_evidence_hash": p140["evidence_hash"],
            "p140_review_hash": p140_review["review_hash"],
        },
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def build_p141_preliminary_evidence(matrix: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p141_case_matrix(matrix)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P141_PRELIMINARY_STATUS if validated["failed"] == 0 else P141_BLOCKED_STATUS,
        "expected": 36,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": manifest.get("freeze_manifest_hash"),
        "final_review_hash": None,
        "limitations": sorted(REQUIRED_LIMITATIONS),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def assemble_p141_final_evidence(
    matrix: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
    project_root: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_p141_case_matrix(matrix)
    expected_manifest = build_p141_freeze_manifest(project_root=project_root, profile=profile, matrix=validated)
    if dict(manifest) != expected_manifest:
        raise ValueError("p141_freeze_manifest_drift")
    _validate_review(review, expected_manifest, project_root=project_root)
    ready = validated["passed"] == 36 and validated["failed"] == 0
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P141_READY_STATUS if ready else P141_BLOCKED_STATUS,
        "expected": 36,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": expected_manifest["freeze_manifest_hash"],
        "final_review_hash": review["review_hash"],
        "limitations": deepcopy(list(review["limitations"])),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_review(review: Mapping[str, Any], manifest: Mapping[str, Any], *, project_root: Path) -> None:
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("invalid_p141_review_schema")
    if _identity(review.get("reviewer_identity"), "reviewer") == _identity(review.get("implementation_identity"), "implementer"):
        raise ValueError("p141_review_identity_not_independent")
    if review.get("decision") != "approve" or review.get("findings") != {"p0": 0, "p1": 0, "p2": 0, "p3": 0}:
        raise ValueError("p141_review_not_approved")
    if review.get("reviewer_type") != "codex-native-code-reviewer":
        raise ValueError("p141_reviewer_type_invalid")
    agent_id = review.get("reviewer_agent_id")
    if not isinstance(agent_id, str) or not _REVIEWER_AGENT_ID_RE.fullmatch(agent_id):
        raise ValueError("p141_reviewer_agent_id_invalid")
    _parse_reviewed_at(review.get("reviewed_at"))
    if review.get("review_artifact_path") != REVIEW_ARTIFACT_PATH:
        raise ValueError("p141_review_artifact_path_invalid")
    review_artifact = project_root / REVIEW_ARTIFACT_PATH
    if not review_artifact.is_file() or review_artifact.is_symlink():
        raise ValueError("p141_review_artifact_missing_or_unsafe")
    review_text = review_artifact.read_text(encoding="utf-8")
    if "Verdict: APPROVE" not in review_text or "P0: 0" not in review_text or len(review_text) < 500:
        raise ValueError("p141_review_artifact_incomplete")
    if review.get("review_artifact_sha256") != file_sha256(review_artifact):
        raise ValueError("p141_review_artifact_hash_invalid")
    resolutions = review.get("findings_resolved")
    if not isinstance(resolutions, list) or len(resolutions) < 4 or not all(isinstance(item, str) and item for item in resolutions):
        raise ValueError("p141_review_resolutions_incomplete")
    expected = {
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": manifest["source_bindings"],
        "reviewed_dependency_bindings": manifest["dependency_bindings"],
    }
    if any(review.get(key) != value for key, value in expected.items()):
        raise ValueError("p141_review_binding_drift")
    limitations = review.get("limitations")
    if not isinstance(limitations, list) or not REQUIRED_LIMITATIONS.issubset(limitations):
        raise ValueError("p141_review_limitations_incomplete")
    if review.get("review_hash") != stable_hash({key: value for key, value in review.items() if key != "review_hash"}):
        raise ValueError("p141_review_hash_invalid")


def _validate_dependency_hash(value: Mapping[str, Any], key: str, expected: str) -> None:
    if value.get(key) != stable_hash({name: item for name, item in value.items() if name != key}) or value.get(key) != expected:
        raise ValueError("p141_dependency_hash_drift")


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if set(value) != {"schema_version", "cases"} or value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_p141_profile_schema")
    if value.get("cases") != p141_release_case_catalog():
        raise ValueError("p141_profile_catalog_drift")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError(f"invalid_p141_{label}_identity")
    return value


def _parse_reviewed_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("p141_reviewed_at_invalid")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("p141_reviewed_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("p141_reviewed_at_invalid")
    return parsed.astimezone(UTC)


__all__ = [
    "P141_BLOCKED_STATUS",
    "P141_PRELIMINARY_STATUS",
    "P141_READY_STATUS",
    "assemble_p141_final_evidence",
    "build_p141_freeze_manifest",
    "build_p141_preliminary_evidence",
    "current_p141_source_hashes",
]
