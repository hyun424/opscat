"""Frozen source and review contracts for P142 qualification."""

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
from app.services.p142_runner import (
    p142_release_case_catalog,
    validate_p142_case_matrix,
    zero_forbidden_non_transport_counters,
)

P142_PRELIMINARY_STATUS = "p142_preliminary_qualification_frozen"
P142_READY_STATUS = "p142_loopback_transport_lab_qualified"
P142_BLOCKED_STATUS = "p142_blocked"
FREEZE_SCHEMA_VERSION = "p142.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p142.final_implementation_review.v1"
EVIDENCE_SCHEMA_VERSION = "p142.release_evidence.v1"
PROFILE_SCHEMA_VERSION = "p142.loopback_transport_lab_profile.v1"
PLAN_REVIEW_ARTIFACT_PATH = "docs/operations/p142-plan-review.md"
IMPLEMENTATION_REVIEW_ARTIFACT_PATH = "evals/p142/final-implementation-review.json"
EXPECTED_PLAN_SHA256 = "sha256:3f1a92c3a10c4db42fd5530393c222fcf7bfe3d240d7da2990e1af865e4186d9"
EXPECTED_TEST_SPEC_SHA256 = "sha256:13b02f1fc442f31a8c4197719ec3c0bae36667c00160be148a011c270cc26fe7"
EXPECTED_PLAN_REVIEW_VERDICT = "APPROVE"
EXPECTED_P141_STATUS = "p141_notification_authority_simulator_qualified"
EXPECTED_P141_EVIDENCE_HASH = "sha256:f3298f1295515b89e5374a449e9deb29fbd70f7c2a1e09446b80d9279d73d3b2"
_REVIEWER_AGENT_ID_RE = re.compile(r"[a-f0-9-]{20,80}\Z")

REQUIRED_LIMITATIONS = frozenset(
    {
        "numeric_loopback_http_lab_only_no_external_notification_delivery",
        "no_credentials_tls_auth_dns_proxy_redirect_provider_sdk_or_environment_config",
        "no_p133_ack_action_remediation_staging_mutation_production_mutation_or_operator_replacement",
        "local_execution_provenance_not_cryptographic_attestation",
        "independent_reviewer_identity_not_externally_authenticated",
    }
)

P142_SOURCE_PATHS: tuple[str, ...] = (
    ".omx/plans/opscat-p142-loopback-notification-transport-lab.md",
    "app/p142_loopback_cli.py",
    "app/services/p142_loopback_transport_lab.py",
    "app/services/p142_release_evidence.py",
    "app/services/p142_runner.py",
    "docs/operations/p142-loopback-transport-roadmap.md",
    "docs/operations/p142-implementation-review.md",
    PLAN_REVIEW_ARTIFACT_PATH,
    "docs/operations/p142-test-spec.md",
    "evals/p142/input/loopback-transport-lab-profile.json",
    "scripts/run_p142_loopback_transport_lab.py",
    "tests/fixtures/p142/__init__.py",
    "tests/fixtures/p142/builders.py",
    "tests/test_p142_loopback_cli.py",
    "tests/test_p142_loopback_transport_lab.py",
    "tests/test_p142_release_evidence.py",
    "tests/test_p142_runner.py",
)


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p142_source_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in P142_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p142_source_missing_or_unsafe:{relative}")
        hashes[relative] = file_sha256(path)
    return hashes


def build_p142_freeze_manifest(
    *, project_root: Path, profile: Mapping[str, Any], matrix: Mapping[str, Any]
) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    validated_matrix = validate_p142_case_matrix(matrix)
    p141 = _read_json(project_root / "evals/p141/output/release-evidence.json")
    _validate_p141_dependency(p141)
    source_hashes = current_p142_source_hashes(project_root)
    if source_hashes[".omx/plans/opscat-p142-loopback-notification-transport-lab.md"] != EXPECTED_PLAN_SHA256:
        raise ValueError("p142_approved_plan_hash_drift")
    if source_hashes["docs/operations/p142-test-spec.md"] != EXPECTED_TEST_SPEC_SHA256:
        raise ValueError("p142_test_spec_hash_drift")
    _validate_plan_review(project_root / PLAN_REVIEW_ARTIFACT_PATH, source_hashes)
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "approved_plan_sha256": EXPECTED_PLAN_SHA256,
        "approved_test_spec_sha256": EXPECTED_TEST_SPEC_SHA256,
        "plan_review_sha256": source_hashes[PLAN_REVIEW_ARTIFACT_PATH],
        "profile_hash": stable_hash(validated_profile),
        "matrix_hash": validated_matrix["matrix_hash"],
        "source_bindings": source_hashes,
        "dependency_bindings": {
            "p141_status": p141["status"],
            "p141_evidence_hash": p141["evidence_hash"],
            "p141_matrix_hash": p141["matrix_hash"],
            "p141_freeze_manifest_hash": p141["freeze_manifest_hash"],
            "p141_final_review_hash": p141["final_review_hash"],
        },
        "implementation_review_artifact_path": IMPLEMENTATION_REVIEW_ARTIFACT_PATH,
        "implementation_review_required_for_final": True,
    }
    manifest["forbidden_non_transport_authority_counters"] = zero_forbidden_non_transport_counters()
    manifest["allowed_transport_activity_counters"] = deepcopy(validated_matrix["allowed_transport_activity_counters"])
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def build_p142_preliminary_evidence(matrix: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p142_case_matrix(matrix)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P142_PRELIMINARY_STATUS if validated["failed"] == 0 else P142_BLOCKED_STATUS,
        "expected": 44,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": manifest.get("freeze_manifest_hash"),
        "final_review_hash": None,
        "p141_dependency": deepcopy(dict(manifest.get("dependency_bindings", {}))),
        "forbidden_non_transport_authority_counters": zero_forbidden_non_transport_counters(),
        "allowed_transport_activity_counters": deepcopy(validated["allowed_transport_activity_counters"]),
        "limitations": sorted(REQUIRED_LIMITATIONS),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def assemble_p142_final_evidence(
    matrix: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
    project_root: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_p142_case_matrix(matrix)
    expected_manifest = build_p142_freeze_manifest(project_root=project_root, profile=profile, matrix=validated)
    if dict(manifest) != expected_manifest:
        raise ValueError("p142_freeze_manifest_drift")
    _validate_review(review, expected_manifest)
    ready = validated["passed"] == 44 and validated["failed"] == 0
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P142_READY_STATUS if ready else P142_BLOCKED_STATUS,
        "expected": 44,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": expected_manifest["freeze_manifest_hash"],
        "final_review_hash": review["review_hash"],
        "p141_dependency": deepcopy(expected_manifest["dependency_bindings"]),
        "forbidden_non_transport_authority_counters": zero_forbidden_non_transport_counters(),
        "allowed_transport_activity_counters": deepcopy(validated["allowed_transport_activity_counters"]),
        "limitations": deepcopy(list(review["limitations"])),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if set(value) != {"schema_version", "cases"} or value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_p142_profile_schema")
    if value.get("cases") != p142_release_case_catalog():
        raise ValueError("p142_profile_catalog_drift")
    return value


def _validate_p141_dependency(p141: Mapping[str, Any]) -> None:
    if p141.get("evidence_hash") != stable_hash({key: value for key, value in p141.items() if key != "evidence_hash"}):
        raise ValueError("p141_release_evidence_hash_invalid")
    if p141.get("status") != EXPECTED_P141_STATUS or p141.get("evidence_hash") != EXPECTED_P141_EVIDENCE_HASH:
        raise ValueError("p141_release_dependency_drift")


def _validate_plan_review(path: Path, source_hashes: Mapping[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        f"Plan SHA-256:\n  `{EXPECTED_PLAN_SHA256.removeprefix('sha256:')}`",
        f"Test spec SHA-256:\n  `{EXPECTED_TEST_SPEC_SHA256.removeprefix('sha256:')}`",
        "Verdict: APPROVE",
        "Final critic pass: **APPROVED**",
    )
    if any(item not in text for item in required):
        raise ValueError("p142_plan_review_not_approved")
    if source_hashes.get(PLAN_REVIEW_ARTIFACT_PATH) != file_sha256(path):
        raise ValueError("p142_plan_review_hash_drift")


def _validate_review(review: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("invalid_p142_review_schema")
    if _identity(review.get("reviewer_identity"), "reviewer") == _identity(review.get("implementation_identity"), "implementer"):
        raise ValueError("p142_review_identity_not_independent")
    if review.get("decision") != "approve" or review.get("findings") != {"p0": 0, "p1": 0, "p2": 0, "p3": 0}:
        raise ValueError("p142_review_not_approved")
    if review.get("reviewer_type") != "codex-native-code-reviewer":
        raise ValueError("p142_reviewer_type_invalid")
    agent_id = review.get("reviewer_agent_id")
    if not isinstance(agent_id, str) or not _REVIEWER_AGENT_ID_RE.fullmatch(agent_id):
        raise ValueError("p142_reviewer_agent_id_invalid")
    _parse_reviewed_at(review.get("reviewed_at"))
    expected = {
        "approved_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_test_spec_sha256": manifest["approved_test_spec_sha256"],
        "reviewed_plan_review_sha256": manifest["plan_review_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": manifest["source_bindings"],
        "reviewed_dependency_bindings": manifest["dependency_bindings"],
    }
    if any(review.get(key) != value for key, value in expected.items()):
        raise ValueError("p142_review_binding_drift")
    limitations = review.get("limitations")
    if not isinstance(limitations, list) or not REQUIRED_LIMITATIONS.issubset(limitations):
        raise ValueError("p142_review_limitations_incomplete")
    if review.get("review_hash") != stable_hash({key: value for key, value in review.items() if key != "review_hash"}):
        raise ValueError("p142_review_hash_invalid")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError(f"invalid_p142_{label}_identity")
    return value


def _parse_reviewed_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("p142_reviewed_at_invalid")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("p142_reviewed_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("p142_reviewed_at_invalid")
    return parsed.astimezone(UTC)


__all__ = [
    "IMPLEMENTATION_REVIEW_ARTIFACT_PATH",
    "P142_BLOCKED_STATUS",
    "P142_PRELIMINARY_STATUS",
    "P142_READY_STATUS",
    "REQUIRED_LIMITATIONS",
    "assemble_p142_final_evidence",
    "build_p142_freeze_manifest",
    "build_p142_preliminary_evidence",
    "current_p142_source_hashes",
    "file_sha256",
]
