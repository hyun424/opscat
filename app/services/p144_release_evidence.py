"""Frozen source and review contracts for P144 qualification."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import RFC_4122, UUID

from app.services.p110_evaluation import stable_hash
from app.services.p144_provider_adapter_lab import (
    ADAPTER_COUNTER_KEYS,
    EXPECTED_P142_EVIDENCE_HASH,
    EXPECTED_P142_STATUS,
    EXPECTED_P143_EVIDENCE_HASH,
    EXPECTED_P143_STATUS,
    FORBIDDEN_COUNTER_KEYS,
    TRANSPORT_COUNTER_KEYS,
    zero_adapter_counters,
    zero_forbidden_counters,
    zero_transport_counters,
)
from app.services.p144_runner import p144_release_case_catalog, validate_p144_case_matrix

P144_PRELIMINARY_STATUS = "p144_preliminary_qualification_frozen"
P144_READY_STATUS = "p144_numeric_loopback_provider_adapter_qualified"
P144_BLOCKED_STATUS = "p144_blocked"
FREEZE_SCHEMA_VERSION = "p144.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p144.final_implementation_review.v1"
EVIDENCE_SCHEMA_VERSION = "p144.release_evidence.v1"
PROFILE_SCHEMA_VERSION = "p144.provider_adapter_lab_profile.v1"
PLAN_REVIEW_ARTIFACT_PATH = "docs/operations/p144-plan-review.md"
IMPLEMENTATION_REVIEW_ARTIFACT_PATH = "evals/p144/final-implementation-review.json"
EXPECTED_PLAN_SHA256 = "sha256:592153aec6310429b4ddd728b25633d2553b07682513463d23641ed1fdd9e886"
EXPECTED_TEST_SPEC_SHA256 = "sha256:7266e0546023b69b34fab6b9c548316e546f71a9001cd2be71e7caa9aa60969f"

REQUIRED_LIMITATIONS = frozenset(
    {
        "numeric_loopback_provider_adapter_conformance_only_no_external_delivery",
        "no_credentials_auth_dns_tls_proxy_provider_sdk_or_environment_config",
        "receiver_address_process_owned_not_configurable_or_persisted_as_authority",
        "provider_shaped_response_is_local_fixture_evidence_not_certification",
        "indeterminate_post_send_state_requires_review_and_never_auto_retries",
        "no_p133_ack_approval_action_remediation_ticket_staging_production_mutation_or_operator_replacement",
        "local_execution_provenance_not_cryptographic_attestation",
        "independent_reviewer_identity_not_externally_authenticated",
    }
)

P144_SOURCE_PATHS: tuple[str, ...] = (
    ".omx/plans/opscat-p144-loopback-provider-adapter-conformance.md",
    "app/p144_provider_adapter_cli.py",
    "app/services/p144_provider_adapter_lab.py",
    "app/services/p144_release_evidence.py",
    "app/services/p144_runner.py",
    "docs/operations/p144-implementation-review.md",
    PLAN_REVIEW_ARTIFACT_PATH,
    "docs/operations/p144-test-spec.md",
    "evals/p144/input/provider-adapter-profile.json",
    "scripts/run_p144_provider_adapter_lab.py",
    "tests/fixtures/p144/__init__.py",
    "tests/fixtures/p144/builders.py",
    "tests/test_p144_provider_adapter_cli.py",
    "tests/test_p144_provider_adapter_lab.py",
    "tests/test_p144_release_evidence.py",
    "tests/test_p144_runner.py",
)

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


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p144_source_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in P144_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p144_source_missing_or_unsafe:{relative}")
        hashes[relative] = file_sha256(path)
    return hashes


def build_p144_freeze_manifest(*, project_root: Path, profile: Mapping[str, Any], matrix: Mapping[str, Any]) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    validated_matrix = validate_p144_case_matrix(matrix)
    source_hashes = current_p144_source_hashes(project_root)
    if source_hashes[".omx/plans/opscat-p144-loopback-provider-adapter-conformance.md"] != EXPECTED_PLAN_SHA256:
        raise ValueError("p144_approved_plan_hash_drift")
    if source_hashes["docs/operations/p144-test-spec.md"] != EXPECTED_TEST_SPEC_SHA256:
        raise ValueError("p144_test_spec_hash_drift")
    _validate_plan_review(project_root / PLAN_REVIEW_ARTIFACT_PATH, source_hashes)
    dependency_bindings = _dependency_bindings(project_root)
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "approved_plan_sha256": EXPECTED_PLAN_SHA256,
        "approved_test_spec_sha256": EXPECTED_TEST_SPEC_SHA256,
        "plan_review_sha256": source_hashes[PLAN_REVIEW_ARTIFACT_PATH],
        "profile_hash": stable_hash(validated_profile),
        "matrix_hash": validated_matrix["matrix_hash"],
        "source_bindings": source_hashes,
        "dependency_bindings": dependency_bindings,
        "implementation_review_artifact_path": IMPLEMENTATION_REVIEW_ARTIFACT_PATH,
        "implementation_review_required_for_final": True,
        "forbidden_counters": zero_forbidden_counters(),
        "adapter_counters": deepcopy(validated_matrix["adapter_counters"]),
        "transport_counters": deepcopy(validated_matrix["transport_counters"]),
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def build_p144_preliminary_evidence(matrix: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p144_case_matrix(matrix)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P144_PRELIMINARY_STATUS if validated["failed"] == 0 else P144_BLOCKED_STATUS,
        "expected": 64,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": manifest.get("freeze_manifest_hash"),
        "final_review_hash": None,
        "dependency_bindings": deepcopy(dict(manifest.get("dependency_bindings", {}))),
        "forbidden_counters": zero_forbidden_counters(),
        "adapter_counters": deepcopy(validated["adapter_counters"]),
        "transport_counters": deepcopy(validated["transport_counters"]),
        "limitations": sorted(REQUIRED_LIMITATIONS),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def assemble_p144_final_evidence(
    matrix: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
    project_root: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_p144_case_matrix(matrix)
    expected_manifest = build_p144_freeze_manifest(project_root=project_root, profile=profile, matrix=validated)
    if dict(manifest) != expected_manifest:
        raise ValueError("p144_freeze_manifest_drift")
    _validate_review(review, expected_manifest)
    ready = validated["passed"] == 64 and validated["failed"] == 0
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P144_READY_STATUS if ready else P144_BLOCKED_STATUS,
        "expected": 64,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": expected_manifest["freeze_manifest_hash"],
        "final_review_hash": review["review_hash"],
        "dependency_bindings": deepcopy(expected_manifest["dependency_bindings"]),
        "forbidden_counters": zero_forbidden_counters(),
        "adapter_counters": deepcopy(validated["adapter_counters"]),
        "transport_counters": deepcopy(validated["transport_counters"]),
        "limitations": deepcopy(list(review["limitations"])),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if set(value) != {"schema_version", "cases"} or value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_p144_profile_schema")
    if value.get("cases") != p144_release_case_catalog():
        raise ValueError("p144_profile_catalog_drift")
    return value


def _dependency_bindings(project_root: Path) -> dict[str, Any]:
    p143 = _read_json(project_root / "evals/p143/output/release-evidence.json")
    p142 = _read_json(project_root / "evals/p142/output/release-evidence.json")
    _require_self_hash(p143, "evidence_hash")
    _require_self_hash(p142, "evidence_hash")
    if p143.get("status") != EXPECTED_P143_STATUS or p143.get("evidence_hash") != EXPECTED_P143_EVIDENCE_HASH:
        raise ValueError("p144_p143_dependency_drift")
    if p142.get("status") != EXPECTED_P142_STATUS or p142.get("evidence_hash") != EXPECTED_P142_EVIDENCE_HASH:
        raise ValueError("p144_p142_dependency_drift")
    p143_dependency = p143.get("dependency_bindings")
    p142_p141 = p142.get("p141_dependency")
    if not isinstance(p143_dependency, Mapping) or not isinstance(p142_p141, Mapping):
        raise ValueError("p144_transitive_dependency_graph_invalid")
    expected_p143_dependency = {
        "p142_status": p142.get("status"),
        "p142_evidence_hash": p142.get("evidence_hash"),
        "p142_matrix_hash": p142.get("matrix_hash"),
        "p142_freeze_manifest_hash": p142.get("freeze_manifest_hash"),
        "p142_final_review_hash": p142.get("final_review_hash"),
        "p141_dependency": deepcopy(dict(p142_p141)),
    }
    if dict(p143_dependency) != expected_p143_dependency:
        raise ValueError("p144_transitive_dependency_graph_invalid")
    p141_release = _read_json(project_root / "evals/p141/output/release-evidence.json")
    p141_freeze = _read_json(project_root / "evals/p141/output/freeze-manifest.json")
    p141_review = _read_json(project_root / "evals/p141/final-implementation-review.json")
    p133 = _read_json(project_root / "evals/p133/release-evidence.json")
    _require_self_hash(p141_release, "evidence_hash")
    _require_self_hash(p141_freeze, "freeze_manifest_hash")
    _require_self_hash(p141_review, "review_hash")
    _require_self_hash(p133, "release_evidence_hash")
    expected_p141 = {
        "p141_status": p141_release.get("status"),
        "p141_evidence_hash": p141_release.get("evidence_hash"),
        "p141_matrix_hash": p141_release.get("matrix_hash"),
        "p141_freeze_manifest_hash": p141_release.get("freeze_manifest_hash"),
        "p141_final_review_hash": p141_release.get("final_review_hash"),
    }
    p141_dependencies = p141_freeze.get("dependency_bindings")
    p133_dependency = {"p133_status": p133.get("release_status"), "p133_evidence_hash": p133.get("release_evidence_hash")}
    if (
        dict(p142_p141) != expected_p141
        or p141_review.get("reviewed_dependency_bindings") != p141_dependencies
        or p141_review.get("reviewed_freeze_manifest_hash") != p141_freeze.get("freeze_manifest_hash")
        or not isinstance(p141_dependencies, Mapping)
        or p141_dependencies.get("p133_status") != p133_dependency["p133_status"]
        or p141_dependencies.get("p133_evidence_hash") != p133_dependency["p133_evidence_hash"]
    ):
        raise ValueError("p144_transitive_p133_dependency_graph_invalid")
    return {
        "p143_status": p143["status"],
        "p143_evidence_hash": p143["evidence_hash"],
        "p143_matrix_hash": p143["matrix_hash"],
        "p143_freeze_manifest_hash": p143["freeze_manifest_hash"],
        "p143_final_review_hash": p143["final_review_hash"],
        "p142_status": p142["status"],
        "p142_evidence_hash": p142["evidence_hash"],
        "p142_matrix_hash": p142["matrix_hash"],
        "p142_freeze_manifest_hash": p142["freeze_manifest_hash"],
        "p142_final_review_hash": p142["final_review_hash"],
        "p143_p141_dependency": deepcopy(dict(p142_p141)),
        "p142_p141_dependency": deepcopy(dict(p142_p141)),
        "p141_dependency": deepcopy(dict(p142_p141)),
        "p133_dependency": p133_dependency,
    }


def _validate_plan_review(path: Path, source_hashes: Mapping[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    required = (EXPECTED_PLAN_SHA256.removeprefix("sha256:"), EXPECTED_TEST_SPEC_SHA256.removeprefix("sha256:"), "APPROVE")
    if any(item not in text for item in required):
        raise ValueError("p144_plan_review_not_approved")
    if source_hashes.get(PLAN_REVIEW_ARTIFACT_PATH) != file_sha256(path):
        raise ValueError("p144_plan_review_hash_drift")


def _validate_review(review: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    if set(review) != _REVIEW_FIELDS or review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("p144_review_fields_invalid")
    reviewer_identity = _identity(review.get("reviewer_identity"), "reviewer")
    implementation_identity = _identity(review.get("implementation_identity"), "implementer")
    if reviewer_identity == implementation_identity:
        raise ValueError("p144_review_identity_not_independent")
    if review.get("decision") != "approve":
        raise ValueError("p144_review_not_approved")
    findings = review.get("findings")
    if not isinstance(findings, Mapping) or set(findings) != _FINDING_FIELDS or any(type(findings[key]) is not int or findings[key] != 0 for key in _FINDING_FIELDS):
        raise ValueError("p144_review_findings_invalid")
    if review.get("reviewer_type") != "codex-native-code-reviewer":
        raise ValueError("p144_reviewer_type_invalid")
    agent_id = review.get("reviewer_agent_id")
    if not isinstance(agent_id, str):
        raise ValueError("p144_reviewer_agent_id_invalid")
    try:
        parsed = UUID(agent_id)
    except ValueError as exc:
        raise ValueError("p144_reviewer_agent_id_invalid") from exc
    if parsed.variant != RFC_4122 or parsed.version != 7 or str(parsed) != agent_id:
        raise ValueError("p144_reviewer_agent_id_invalid")
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
        raise ValueError("p144_review_binding_invalid")
    limitations = review.get("limitations")
    if not isinstance(limitations, list) or limitations != sorted(REQUIRED_LIMITATIONS):
        raise ValueError("p144_review_limitations_invalid")
    if review.get("review_hash") != stable_hash({key: value for key, value in review.items() if key != "review_hash"}):
        raise ValueError("p144_review_hash_invalid")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_strict_json_object)
    if not isinstance(value, dict):
        raise ValueError("json_object_required")
    return value


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _identity(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError(f"p144_{label}_identity_invalid")
    return value


def _parse_reviewed_at(value: Any) -> datetime:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is None:
        raise ValueError("p144_review_timestamp_invalid")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("p144_review_timestamp_invalid") from exc


def _require_self_hash(value: Mapping[str, Any], field: str) -> None:
    if value.get(field) != stable_hash({key: item for key, item in value.items() if key != field}):
        raise ValueError("dependency_self_hash_invalid")


__all__ = [
    "ADAPTER_COUNTER_KEYS",
    "FORBIDDEN_COUNTER_KEYS",
    "P144_BLOCKED_STATUS",
    "P144_PRELIMINARY_STATUS",
    "P144_READY_STATUS",
    "P144_SOURCE_PATHS",
    "REQUIRED_LIMITATIONS",
    "TRANSPORT_COUNTER_KEYS",
    "assemble_p144_final_evidence",
    "build_p144_freeze_manifest",
    "build_p144_preliminary_evidence",
    "current_p144_source_hashes",
    "file_sha256",
    "zero_adapter_counters",
    "zero_forbidden_counters",
    "zero_transport_counters",
]
