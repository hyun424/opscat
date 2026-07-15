"""P145 preliminary and final release-evidence contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services.p110_evaluation import stable_hash
from app.services.p145_response_duty_officer import APPROVED_PROFILE_SHA256, PREDECESSOR_BINDINGS, zero_forbidden_authority
from app.services.p145_runner import p145_release_case_catalog, validate_p145_case_matrix

P145_PRELIMINARY_STATUS = "p145_preliminary_qualification_frozen"
P145_READY_STATUS = "p145_local_response_duty_officer_qualified"
P145_BLOCKED_STATUS = "p145_blocked"
FREEZE_SCHEMA_VERSION = "p145.freeze_manifest.v1"
REVIEW_SCHEMA_VERSION = "p145.final_implementation_review.v1"
EVIDENCE_SCHEMA_VERSION = "p145.release_evidence.v1"
PROFILE_SCHEMA_VERSION = "p145.response_duty_profile.v1"
PLAN_PATH = ".omx/plans/opscat-p145-unattended-response-episode.md"
TEST_SPEC_PATH = "docs/operations/p145-test-spec.md"
PLAN_REVIEW_PATH = "docs/operations/p145-plan-review.md"
IMPLEMENTATION_REVIEW_PATH = "evals/p145/final-implementation-review.json"
EXPECTED_PLAN_SHA256 = "sha256:72e3ce302020acd05061fecb178b5f5fbddadae751cf42be0dfc28e92edb8a3b"
EXPECTED_TEST_SPEC_SHA256 = "sha256:72274365b622629154b4347ea3caff48bb4672076287c72165c19b01aeab8050"

P145_SOURCE_PATHS: tuple[str, ...] = (
    PLAN_PATH,
    "app/p145_response_duty_cli.py",
    "app/services/p145_response_duty_officer.py",
    "app/services/p145_release_evidence.py",
    "app/services/p145_runner.py",
    "docs/operations/p145-implementation-review.md",
    PLAN_REVIEW_PATH,
    TEST_SPEC_PATH,
    "evals/p145/input/response-duty-profile.json",
    "pyproject.toml",
    "scripts/run_p145_response_duty_officer.py",
    "scripts/verify.sh",
    "tests/fixtures/p145/__init__.py",
    "tests/fixtures/p145/builders.py",
    "tests/test_p145_response_duty_officer.py",
    "tests/test_p145_runner.py",
    "tests/test_p145_release_evidence.py",
)
P145_DEPENDENCY_PATHS: tuple[str, ...] = (
    "uv.lock",
    "evals/p122/security-report.json",
    "evals/p122/package-checksums.json",
    "evals/p122/release-evidence.json",
)

REQUIRED_LIMITATIONS = sorted(
    {
        "local_response_duty_officer_qualification_only_no_operator_replacement",
        "p133_acknowledgement_is_local_ownership_only_not_external_closure",
        "local_policy_authorization_is_not_human_external_or_provider_approval",
        "process_owned_fault_lab_only_no_staging_production_or_real_remediation",
        "no_credentials_auth_environment_network_provider_sdk_shell_ticket_or_external_message",
        "preliminary_evidence_requires_independent_review_before_final_qualification",
    }
)


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p145_source_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in P145_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p145_source_missing_or_unsafe:{relative}")
        hashes[relative] = file_sha256(path)
    return hashes


def _current_dependency_hashes(project_root: Path) -> dict[str, str]:
    paths = {relative: project_root / relative for relative in P145_DEPENDENCY_PATHS}
    if any(not path.is_file() or path.is_symlink() for path in paths.values()):
        raise ValueError("p145_dependency_missing_or_unsafe")
    security = _read_json(paths["evals/p122/security-report.json"])
    checksums = _read_json(paths["evals/p122/package-checksums.json"])
    release = _read_json(paths["evals/p122/release-evidence.json"])
    if security.get("status") != "pass" or security.get("findings") != []:
        raise ValueError("p145_p122_security_not_qualified")
    expected_packages = {"opscat-0.2.0-py3-none-any.whl", "opscat-0.2.0.tar.gz"}
    if set(checksums) != expected_packages or any(
        not isinstance(value, str) or not value.startswith("sha256:") for value in checksums.values()
    ):
        raise ValueError("p145_p122_package_checksums_invalid")
    if release.get("release_status") != "p122_open_source_local_rc" or release.get("package_checksums") != checksums:
        raise ValueError("p145_p122_release_not_qualified")
    return {relative: file_sha256(path) for relative, path in paths.items()}


def build_p145_freeze_manifest(*, project_root: Path, profile: Mapping[str, Any], matrix: Mapping[str, Any]) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    validated_matrix = validate_p145_case_matrix(matrix)
    source_hashes = current_p145_source_hashes(project_root)
    dependency_hashes = _current_dependency_hashes(project_root)
    if source_hashes[PLAN_PATH] != EXPECTED_PLAN_SHA256:
        raise ValueError("p145_approved_plan_hash_drift")
    if source_hashes[TEST_SPEC_PATH] != EXPECTED_TEST_SPEC_SHA256:
        raise ValueError("p145_test_spec_hash_drift")
    if source_hashes["evals/p145/input/response-duty-profile.json"] != APPROVED_PROFILE_SHA256:
        raise ValueError("p145_profile_source_hash_drift")
    _validate_plan_review(project_root / PLAN_REVIEW_PATH, source_hashes)
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "approved_plan_sha256": EXPECTED_PLAN_SHA256,
        "approved_test_spec_sha256": EXPECTED_TEST_SPEC_SHA256,
        "plan_review_sha256": source_hashes[PLAN_REVIEW_PATH],
        "profile_hash": stable_hash(validated_profile),
        "fixture_hash": stable_hash(_fixture_hashes(project_root)),
        "matrix_hash": validated_matrix["matrix_hash"],
        "row_hashes": [row["row_hash"] for row in validated_matrix["cases"]],
        "source_bindings": source_hashes,
        "dependency_bindings": dependency_hashes,
        "predecessor_bindings": deepcopy(PREDECESSOR_BINDINGS),
        "implementation_review_artifact_path": IMPLEMENTATION_REVIEW_PATH,
        "implementation_review_required_for_final": True,
        "counter_totals": deepcopy(validated_matrix["aggregate_counters"]),
        "forbidden_authority": zero_forbidden_authority(),
        "resource_limits": {"expected_cases": 48, "max_child_processes": 48, "network_allowed": False, "shell_allowed": False},
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def build_p145_preliminary_evidence(matrix: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p145_case_matrix(matrix)
    validated_manifest = _validate_frozen_manifest(manifest, validated)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P145_PRELIMINARY_STATUS if validated["failed"] == 0 else P145_BLOCKED_STATUS,
        "expected": 48,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": validated_manifest["freeze_manifest_hash"],
        "final_review_hash": None,
        "predecessor_bindings": deepcopy(PREDECESSOR_BINDINGS),
        "counter_totals": deepcopy(validated["aggregate_counters"]),
        "forbidden_authority": zero_forbidden_authority(),
        "limitations": deepcopy(REQUIRED_LIMITATIONS),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_frozen_manifest(manifest: Mapping[str, Any], matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    required = {
        "schema_version", "approved_plan_sha256", "approved_test_spec_sha256", "plan_review_sha256",
        "profile_hash", "fixture_hash", "matrix_hash", "row_hashes", "source_bindings",
        "dependency_bindings",
        "predecessor_bindings", "implementation_review_artifact_path",
        "implementation_review_required_for_final", "counter_totals", "forbidden_authority",
        "resource_limits", "freeze_manifest_hash",
    }
    if set(value) != required or value.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise ValueError("p145_freeze_manifest_schema_invalid")
    if value.get("approved_plan_sha256") != EXPECTED_PLAN_SHA256 or value.get("approved_test_spec_sha256") != EXPECTED_TEST_SPEC_SHA256:
        raise ValueError("p145_freeze_approved_source_drift")
    if value.get("predecessor_bindings") != PREDECESSOR_BINDINGS or value.get("matrix_hash") != matrix["matrix_hash"]:
        raise ValueError("p145_freeze_binding_drift")
    if value.get("row_hashes") != [row["row_hash"] for row in matrix["cases"]] or value.get("counter_totals") != matrix["aggregate_counters"]:
        raise ValueError("p145_freeze_row_or_counter_drift")
    if value.get("forbidden_authority") != zero_forbidden_authority():
        raise ValueError("p145_freeze_forbidden_authority_invalid")
    if value.get("implementation_review_artifact_path") != IMPLEMENTATION_REVIEW_PATH or value.get("implementation_review_required_for_final") is not True:
        raise ValueError("p145_freeze_review_gate_invalid")
    if value.get("resource_limits") != {"expected_cases": 48, "max_child_processes": 48, "network_allowed": False, "shell_allowed": False}:
        raise ValueError("p145_freeze_resource_limits_invalid")
    sources = value.get("source_bindings")
    if not isinstance(sources, Mapping) or set(sources) != set(P145_SOURCE_PATHS) or any(not isinstance(item, str) or not item.startswith("sha256:") for item in sources.values()):
        raise ValueError("p145_freeze_source_bindings_invalid")
    dependencies = value.get("dependency_bindings")
    if (
        not isinstance(dependencies, Mapping)
        or set(dependencies) != set(P145_DEPENDENCY_PATHS)
        or any(not isinstance(item, str) or not item.startswith("sha256:") for item in dependencies.values())
    ):
        raise ValueError("p145_freeze_dependency_bindings_invalid")
    if value.get("freeze_manifest_hash") != stable_hash({key: item for key, item in value.items() if key != "freeze_manifest_hash"}):
        raise ValueError("p145_freeze_manifest_hash_invalid")
    return value


def assemble_p145_final_evidence(matrix: Mapping[str, Any], *, manifest: Mapping[str, Any], review: Mapping[str, Any], project_root: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_p145_case_matrix(matrix)
    expected_manifest = build_p145_freeze_manifest(project_root=project_root, profile=profile, matrix=validated)
    if dict(manifest) != expected_manifest:
        raise ValueError("p145_freeze_manifest_drift")
    _validate_review(review, expected_manifest)
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P145_READY_STATUS if validated["passed"] == 48 and validated["failed"] == 0 else P145_BLOCKED_STATUS,
        "expected": 48,
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_manifest_hash": expected_manifest["freeze_manifest_hash"],
        "final_review_hash": review["review_hash"],
        "predecessor_bindings": deepcopy(PREDECESSOR_BINDINGS),
        "counter_totals": deepcopy(validated["aggregate_counters"]),
        "forbidden_authority": zero_forbidden_authority(),
        "limitations": deepcopy(list(review["limitations"])),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if set(value) != {"schema_version", "cases", "predecessor_bindings"} or value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_p145_profile_schema")
    if value.get("cases") != p145_release_case_catalog() or value.get("predecessor_bindings") != PREDECESSOR_BINDINGS:
        raise ValueError("p145_profile_binding_drift")
    return value


def _validate_plan_review(path: Path, source_hashes: Mapping[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    if "APPROVE" not in text or EXPECTED_PLAN_SHA256.removeprefix("sha256:") not in text or EXPECTED_TEST_SPEC_SHA256.removeprefix("sha256:") not in text:
        raise ValueError("p145_plan_review_not_approved")
    if source_hashes[PLAN_REVIEW_PATH] != file_sha256(path):
        raise ValueError("p145_plan_review_hash_drift")


def _validate_review(review: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "reviewer_identity",
        "reviewer_agent_id",
        "reviewer_type",
        "implementation_identity",
        "reviewed_at",
        "decision",
        "findings",
        "limitations",
        "reviewed_plan_sha256",
        "reviewed_test_spec_sha256",
        "reviewed_plan_review_sha256",
        "reviewed_profile_hash",
        "reviewed_fixture_hash",
        "reviewed_matrix_hash",
        "reviewed_freeze_manifest_hash",
        "reviewed_source_hashes",
        "reviewed_dependency_hashes",
        "reviewed_predecessor_bindings",
        "review_hash",
    }
    if set(review) != required or review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("p145_review_schema_invalid")
    if review.get("reviewer_identity") == review.get("implementation_identity"):
        raise ValueError("p145_review_identity_not_independent")
    try:
        reviewer_id = UUID(str(review.get("reviewer_agent_id")))
    except ValueError as exc:
        raise ValueError("p145_review_uuid_invalid") from exc
    if reviewer_id.version != 7 or str(reviewer_id) != review.get("reviewer_agent_id"):
        raise ValueError("p145_review_uuid_invalid")
    if not isinstance(review.get("reviewed_at"), str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", review["reviewed_at"]) is None:
        raise ValueError("p145_review_timestamp_invalid")
    datetime.strptime(review["reviewed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    findings = review.get("findings")
    if not isinstance(findings, Mapping) or set(findings) != {"p0", "p1", "p2", "p3"} or any(
        type(findings[key]) is not int or findings[key] != 0 for key in ("p0", "p1", "p2", "p3")
    ):
        raise ValueError("p145_review_findings_invalid")
    if review.get("decision") != "approve":
        raise ValueError("p145_review_not_approved")
    expected = {
        "reviewed_plan_sha256": manifest["approved_plan_sha256"],
        "reviewed_test_spec_sha256": manifest["approved_test_spec_sha256"],
        "reviewed_plan_review_sha256": manifest["plan_review_sha256"],
        "reviewed_profile_hash": manifest["profile_hash"],
        "reviewed_fixture_hash": manifest["fixture_hash"],
        "reviewed_matrix_hash": manifest["matrix_hash"],
        "reviewed_freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "reviewed_source_hashes": manifest["source_bindings"],
        "reviewed_dependency_hashes": manifest["dependency_bindings"],
        "reviewed_predecessor_bindings": manifest["predecessor_bindings"],
        "limitations": REQUIRED_LIMITATIONS,
    }
    if any(review.get(key) != value for key, value in expected.items()):
        raise ValueError("p145_review_binding_invalid")
    if review.get("review_hash") != stable_hash({key: value for key, value in review.items() if key != "review_hash"}):
        raise ValueError("p145_review_hash_invalid")


def _fixture_hashes(project_root: Path) -> dict[str, str]:
    return {case["fixture_path"]: file_sha256(project_root / case["fixture_path"]) for case in p145_release_case_catalog()}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_json_object)
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
