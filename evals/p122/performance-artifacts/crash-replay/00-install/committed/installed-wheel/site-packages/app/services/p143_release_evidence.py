"""Frozen source and review contracts for P143 qualification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import RFC_4122, UUID

from app.services.p110_evaluation import stable_hash
from app.services.p143_egress_contract_lab import EXPECTED_P142_EVIDENCE_HASH, EXPECTED_P142_STATUS, zero_forbidden_counters
from app.services.p143_runner import p143_release_case_catalog, validate_p143_case_matrix

P143_PRELIMINARY_STATUS = "p143_preliminary_qualification_frozen"
P143_READY_STATUS = "p143_provider_neutral_egress_contract_lab_qualified"
P143_BLOCKED_STATUS = "p143_blocked"
FREEZE_SCHEMA_VERSION = "p143.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p143.final_implementation_review.v1"
EVIDENCE_SCHEMA_VERSION = "p143.release_evidence.v1"
PROFILE_SCHEMA_VERSION = "p143.egress_contract_lab_profile.v1"
PLAN_REVIEW_ARTIFACT_PATH = "docs/operations/p143-plan-review.md"
IMPLEMENTATION_REVIEW_ARTIFACT_PATH = "evals/p143/final-implementation-review.json"
EXPECTED_PLAN_SHA256 = "sha256:220b75a4ee32871eed1c2b41b43bbd299c425ea330fc023b73ca5f891668099e"
EXPECTED_TEST_SPEC_SHA256 = "sha256:5c7f32cfb563df023544792c0494c842fdc3f566e0725cf9322ccbf0117f19ab"
_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "reviewer_identity",
        "reviewer_agent_id",
        "reviewer_type",
        "implementation_identity",
        "reviewed_at",
        "decision",
        "findings",
        "approved_plan_sha256",
        "reviewed_test_spec_sha256",
        "reviewed_plan_review_sha256",
        "reviewed_profile_hash",
        "reviewed_matrix_hash",
        "reviewed_freeze_manifest_hash",
        "reviewed_source_hashes",
        "reviewed_dependency_bindings",
        "limitations",
        "review_hash",
    }
)
_FINDING_FIELDS = frozenset({"p0", "p1", "p2", "p3"})

REQUIRED_LIMITATIONS = frozenset(
    {
        "provider_neutral_local_projection_lab_only_no_external_delivery",
        "no_credentials_auth_endpoints_urls_dns_proxy_tls_http_provider_sdk_or_environment_config",
        "no_p133_ack_approval_action_remediation_ticket_staging_production_mutation_or_operator_replacement",
        "p142_dependency_validation_does_not_grant_loopback_socket_authority_to_p143",
        "local_execution_provenance_not_cryptographic_attestation",
        "independent_reviewer_identity_not_externally_authenticated",
        "shadow_capability_compatibility_is_not_provider_certification",
    }
)

P143_SOURCE_PATHS: tuple[str, ...] = (
    ".omx/plans/opscat-p143-provider-neutral-egress-contract-lab.md",
    "app/p143_egress_contract_cli.py",
    "app/services/p143_egress_contract_lab.py",
    "app/services/p143_release_evidence.py",
    "app/services/p143_runner.py",
    "docs/operations/p143-implementation-review.md",
    PLAN_REVIEW_ARTIFACT_PATH,
    "docs/operations/p143-test-spec.md",
    "evals/p143/input/egress-contract-lab-profile.json",
    "scripts/run_p143_egress_contract_lab.py",
    "tests/fixtures/p143/__init__.py",
    "tests/fixtures/p143/builders.py",
    "tests/test_p143_egress_contract_cli.py",
    "tests/test_p143_egress_contract_lab.py",
    "tests/test_p143_release_evidence.py",
    "tests/test_p143_runner.py",
)


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p143_source_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in P143_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p143_source_missing_or_unsafe:{relative}")
        hashes[relative] = file_sha256(path)
    return hashes


def build_p143_freeze_manifest(*, project_root: Path, profile: Mapping[str, Any], matrix: Mapping[str, Any]) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    validated_matrix = validate_p143_case_matrix(matrix)
    p142 = _read_json(project_root / "evals/p142/output/release-evidence.json")
    _validate_p142_dependency(p142)
    source_hashes = current_p143_source_hashes(project_root)
    if source_hashes[".omx/plans/opscat-p143-provider-neutral-egress-contract-lab.md"] != EXPECTED_PLAN_SHA256:
        raise ValueError("p143_approved_plan_hash_drift")
    if source_hashes["docs/operations/p143-test-spec.md"] != EXPECTED_TEST_SPEC_SHA256:
        raise ValueError("p143_test_spec_hash_drift")
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
            "p142_status": p142["status"],
            "p142_evidence_hash": p142["evidence_hash"],
            "p142_matrix_hash": p142["matrix_hash"],
            "p142_freeze_manifest_hash": p142["freeze_manifest_hash"],
            "p142_final_review_hash": p142["final_review_hash"],
            "p141_dependency": deepcopy(p142["p141_dependency"]),
        },
        "implementation_review_artifact_path": IMPLEMENTATION_REVIEW_ARTIFACT_PATH,
        "implementation_review_required_for_final": True,
        "forbidden_counters": zero_forbidden_counters(),
        "allowed_counters": deepcopy(validated_matrix["allowed_counters"]),
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def build_p143_preliminary_evidence(matrix: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p143_case_matrix(matrix)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P143_PRELIMINARY_STATUS if validated["failed"] == 0 else P143_BLOCKED_STATUS,
        "expected": 52,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": manifest.get("freeze_manifest_hash"),
        "final_review_hash": None,
        "dependency_bindings": deepcopy(dict(manifest.get("dependency_bindings", {}))),
        "forbidden_counters": zero_forbidden_counters(),
        "allowed_counters": deepcopy(validated["allowed_counters"]),
        "limitations": sorted(REQUIRED_LIMITATIONS),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def assemble_p143_final_evidence(
    matrix: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
    project_root: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_p143_case_matrix(matrix)
    expected_manifest = build_p143_freeze_manifest(project_root=project_root, profile=profile, matrix=validated)
    if dict(manifest) != expected_manifest:
        raise ValueError("p143_freeze_manifest_drift")
    _validate_review(review, expected_manifest)
    ready = validated["passed"] == 52 and validated["failed"] == 0
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P143_READY_STATUS if ready else P143_BLOCKED_STATUS,
        "expected": 52,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": expected_manifest["freeze_manifest_hash"],
        "final_review_hash": review["review_hash"],
        "dependency_bindings": deepcopy(expected_manifest["dependency_bindings"]),
        "forbidden_counters": zero_forbidden_counters(),
        "allowed_counters": deepcopy(validated["allowed_counters"]),
        "limitations": deepcopy(list(review["limitations"])),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if set(value) != {"schema_version", "cases"} or value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_p143_profile_schema")
    if value.get("cases") != p143_release_case_catalog():
        raise ValueError("p143_profile_catalog_drift")
    return value


def _validate_p142_dependency(p142: Mapping[str, Any]) -> None:
    if p142.get("evidence_hash") != stable_hash({key: value for key, value in p142.items() if key != "evidence_hash"}):
        raise ValueError("p142_release_evidence_hash_invalid")
    if p142.get("status") != EXPECTED_P142_STATUS or p142.get("evidence_hash") != EXPECTED_P142_EVIDENCE_HASH:
        raise ValueError("p142_release_dependency_drift")


def _validate_plan_review(path: Path, source_hashes: Mapping[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        EXPECTED_PLAN_SHA256.removeprefix("sha256:"),
        EXPECTED_TEST_SPEC_SHA256.removeprefix("sha256:"),
        "APPROVE",
    )
    if any(item not in text for item in required):
        raise ValueError("p143_plan_review_not_approved")
    if source_hashes.get(PLAN_REVIEW_ARTIFACT_PATH) != file_sha256(path):
        raise ValueError("p143_plan_review_hash_drift")


def _validate_review(review: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    if set(review) != _REVIEW_FIELDS:
        raise ValueError("p143_review_fields_invalid")
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("invalid_p143_review_schema")
    if _identity(review.get("reviewer_identity"), "reviewer") == _identity(review.get("implementation_identity"), "implementer"):
        raise ValueError("p143_review_identity_not_independent")
    if review.get("decision") != "approve":
        raise ValueError("p143_review_not_approved")
    findings = review.get("findings")
    if (
        not isinstance(findings, Mapping)
        or set(findings) != _FINDING_FIELDS
        or any(type(findings[key]) is not int or findings[key] != 0 for key in _FINDING_FIELDS)
    ):
        raise ValueError("p143_review_findings_invalid")
    if review.get("reviewer_type") != "codex-native-code-reviewer":
        raise ValueError("p143_reviewer_type_invalid")
    agent_id = review.get("reviewer_agent_id")
    if not isinstance(agent_id, str):
        raise ValueError("p143_reviewer_agent_id_invalid")
    try:
        parsed_agent_id = UUID(agent_id)
    except ValueError as exc:
        raise ValueError("p143_reviewer_agent_id_invalid") from exc
    if parsed_agent_id.variant != RFC_4122 or parsed_agent_id.version != 7 or str(parsed_agent_id) != agent_id:
        raise ValueError("p143_reviewer_agent_id_invalid")
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
        raise ValueError("p143_review_binding_drift")
    limitations = review.get("limitations")
    if (
        not isinstance(limitations, list)
        or len(limitations) != len(REQUIRED_LIMITATIONS)
        or set(limitations) != REQUIRED_LIMITATIONS
    ):
        raise ValueError("p143_review_limitations_incomplete")
    if review.get("review_hash") != stable_hash({key: value for key, value in review.items() if key != "review_hash"}):
        raise ValueError("p143_review_hash_invalid")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError(f"invalid_p143_{label}_identity")
    return value


def _parse_reviewed_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("p143_reviewed_at_invalid")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("p143_reviewed_at_invalid")
    return parsed.astimezone(UTC)


__all__ = [
    "IMPLEMENTATION_REVIEW_ARTIFACT_PATH",
    "P143_BLOCKED_STATUS",
    "P143_PRELIMINARY_STATUS",
    "P143_READY_STATUS",
    "REQUIRED_LIMITATIONS",
    "assemble_p143_final_evidence",
    "build_p143_freeze_manifest",
    "build_p143_preliminary_evidence",
    "current_p143_source_hashes",
    "file_sha256",
]
