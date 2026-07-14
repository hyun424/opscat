"""Frozen release-evidence contracts for P138 local supervisor qualification."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p136_release_evidence import validate_p136_release_evidence
from app.services.p137_release_evidence import validate_p137_release_evidence
from app.services.p138_observation_triage_supervisor import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RUNTIME_ACTIVITY_KEYS,
)
from app.services.p138_runner import (
    CASE_INPUT_SCHEMA_VERSION,
    PRELIMINARY_MATRIX_SCHEMA_VERSION,
    PRELIMINARY_STATUS,
    REAL_BOUNDARY_CASE_IDS,
    RELEASE_RESOURCE_USAGE_KEYS,
)

APPROVED_PLAN_SHA256 = "d9f76e9e08e6c0416f2f16ef818a5f2545688e37ce97bc7b13d5614c7e1cadbf"
APPROVED_PLAN_PATH = ".omx/plans/opscat-p138-observation-to-triage-supervisor.md"
SCHEMA_VERSION = "p138.release_evidence.v1"
PRELIMINARY_EVIDENCE_SCHEMA_VERSION = "p138.preliminary_release_evidence.v1"
FINAL_REVIEW_SCHEMA_VERSION = "p138.final_implementation_review.v1"
PROFILE_SCHEMA_VERSION = "p138.observation_triage_supervisor_profile.v1"
FREEZE_MANIFEST_SCHEMA_VERSION = "p138.freeze_manifest.v1"
P138_READY_STATUS = "p138_local_observation_to_triage_supervisor_qualified"
P138_PRELIMINARY_STATUS = "p138_preliminary_qualification_frozen"
P136_READY_STATUS = "p136_incremental_local_observation_qualified"
P137_READY_STATUS = "p137_local_evidence_triage_qualified"
REQUIRED_CASE_COUNT = 30
RESOURCE_LIMITS = {
    "wall_limit_ms": 30_000,
    "cpu_limit_ms": 15_000,
    "peak_memory_limit_bytes": 134_217_728,
}
EXPECTED_OUTPUT_ARTIFACTS = [
    "canonical-matrix.json",
    "freeze-manifest.json",
    "release-evidence.json",
]

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_RE = re.compile(
    r"(?:bearer\s+|api[_-]?key\s*[:=]|authorization\s*[:=]|password\s*[:=]|credential\s*[:=]|secret\s*[:=]|https?://)",
    re.IGNORECASE,
)
_NO_AUTHORITY_LIMITATION = "no_auth_no_credentials_no_environment_no_network_no_provider_api_no_notification_no_action_no_remediation"

_PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "case_matrix_version",
        "fixture_root",
        "output_artifacts",
        "required_case_ids",
        "real_boundary_case_ids",
        "resource_limits",
        "approved_plan_sha256",
        "root_ref_hash",
    }
)
_MATRIX_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "cases",
        "case_inputs",
        "totals",
        "forbidden_authority",
        "expected_forbidden_authority",
        "runtime_activity",
        "expected_runtime_activity",
        "evaluator_activity",
        "expected_evaluator_activity",
        "evaluator_overhead_activity",
        "expected_evaluator_overhead_activity",
        "resource_usage",
        "expected_resource_usage",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
    }
)
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "scenario",
        "expected",
        "actual",
        "status",
        "real_boundary",
        "evidence",
        "case_evidence_hash",
    }
)
_CASE_RESULT_FIELDS = frozenset(
    {
        "status",
        "error",
        "stop_reason",
        "phase_path",
        "component_boundaries",
        "durable_post_state",
    }
)
_CASE_EVIDENCE_FIELDS = frozenset(
    {
        "executed",
        "execution_source",
        "output_dir_ref_hash",
        "runtime_activity",
        "expected_runtime_activity",
        "forbidden_authority",
        "expected_forbidden_authority",
        "evaluator_activity",
        "expected_evaluator_activity",
        "resource_usage",
        "expected_resource_usage",
    }
)
_CASE_INPUT_FIELDS = frozenset({"schema_version", "case_id", "bindings", "runtime_input_hash"})
_TOTAL_FIELDS = frozenset({"expected", "passed", "failed"})
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "approved_plan_sha256",
        "source_bindings",
        "dependency_bindings",
        "profile_hash",
        "fixture_hash",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
        "freeze_manifest_hash",
    }
)
_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "reviewer_identity",
        "implementation_identity",
        "approved_plan_sha256",
        "reviewed_source_hashes",
        "reviewed_profile_hash",
        "reviewed_fixture_hash",
        "reviewed_matrix_hash",
        "reviewed_freeze_manifest_hash",
        "findings",
        "decision",
        "limitations",
        "review_hash",
    }
)
_RELEASE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "approved_plan_sha256",
        "dependency_bindings",
        "cases",
        "totals",
        "forbidden_authority",
        "expected_forbidden_authority",
        "runtime_activity",
        "expected_runtime_activity",
        "evaluator_activity",
        "expected_evaluator_activity",
        "evaluator_overhead_activity",
        "expected_evaluator_overhead_activity",
        "resource_usage",
        "expected_resource_usage",
        "source_bindings",
        "profile_hash",
        "fixture_hash",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
        "freeze_manifest_hash",
        "final_implementation_review_hash",
        "evidence_hash",
    }
)
_DEPENDENCY_BINDING_FIELDS = frozenset(
    {
        "p136_status",
        "p136_evidence_hash",
        "p136_review_hash",
        "p137_status",
        "p137_evidence_hash",
        "p137_review_hash",
    }
)
_PRELIMINARY_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "approved_plan_sha256",
        "totals",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
        "freeze_manifest_hash",
        "evidence_hash",
    }
)


class P138ReleaseEvidenceError(ValueError):
    """Raised when a P138 frozen release artifact is malformed or stale."""


def validate_observation_triage_supervisor_profile(
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(profile, "profile")
    _expect_exact_fields(value, _PROFILE_FIELDS, "profile")
    if value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise P138ReleaseEvidenceError("invalid_profile_schema")
    if value.get("case_matrix_version") != 1:
        raise P138ReleaseEvidenceError("invalid_case_matrix_version")
    expected_ids = _required_case_ids()
    if value.get("required_case_ids") != expected_ids:
        raise P138ReleaseEvidenceError("required_case_ids_mismatch")
    if value.get("real_boundary_case_ids") != sorted(REAL_BOUNDARY_CASE_IDS):
        raise P138ReleaseEvidenceError("real_boundary_case_ids_mismatch")
    if value.get("output_artifacts") != EXPECTED_OUTPUT_ARTIFACTS:
        raise P138ReleaseEvidenceError("output_artifacts_mismatch")
    if dict(_mapping(value.get("resource_limits"), "resource_limits")) != RESOURCE_LIMITS:
        raise P138ReleaseEvidenceError("resource_limits_mismatch")
    if value.get("approved_plan_sha256") != APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_hash_mismatch")
    fixture_root = _relative_path(value.get("fixture_root"), "fixture_root")
    expected_root_hash = stable_hash(
        {
            "schema_version": "p138.fixture_root_ref.v1",
            "fixture_root": fixture_root,
        }
    )
    if value.get("root_ref_hash") != expected_root_hash:
        raise P138ReleaseEvidenceError("root_ref_hash_mismatch")
    return deepcopy(dict(value))


def p138_profile_hash(profile: Mapping[str, Any]) -> str:
    return stable_hash(validate_observation_triage_supervisor_profile(profile))


def p138_fixture_hash(profile: Mapping[str, Any], *, project_root: Path | None = None) -> str:
    validated = validate_observation_triage_supervisor_profile(profile)
    root = (project_root or Path.cwd()).resolve()
    fixture_root = root / str(validated["fixture_root"])
    if not fixture_root.is_dir() or fixture_root.is_symlink():
        raise P138ReleaseEvidenceError("fixture_root_missing_or_unsafe")
    files: list[dict[str, Any]] = []
    for path in sorted(fixture_root.rglob("*")):
        if path.is_symlink():
            raise P138ReleaseEvidenceError("fixture_tree_symlink_forbidden")
        if path.is_file():
            raw = path.read_bytes()
            files.append(
                {
                    "relative_path": path.relative_to(fixture_root).as_posix(),
                    "byte_count": len(raw),
                    "content_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
                }
            )
    if not files:
        raise P138ReleaseEvidenceError("fixture_tree_empty")
    return stable_hash(
        {
            "schema_version": "p138.fixture_binding.v1",
            "fixture_root": validated["fixture_root"],
            "root_ref_hash": validated["root_ref_hash"],
            "files": files,
        }
    )


def current_p138_source_hashes(project_root: Path | str) -> dict[str, str]:
    root = Path(project_root)
    result: dict[str, str] = {}
    missing: list[str] = []
    for relative in P138_SOURCE_SCOPE:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        result[relative] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if missing:
        raise P138ReleaseEvidenceError(f"required_source_missing:{','.join(missing)}")
    if result[APPROVED_PLAN_PATH] != "sha256:" + APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_source_stale")
    return dict(sorted(result.items()))


def validate_p138_canonical_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(matrix, "canonical_matrix")
    _expect_exact_fields(value, _MATRIX_FIELDS, "canonical_matrix")
    if value.get("schema_version") != PRELIMINARY_MATRIX_SCHEMA_VERSION:
        raise P138ReleaseEvidenceError("invalid_canonical_matrix_schema")
    if value.get("status") != PRELIMINARY_STATUS:
        raise P138ReleaseEvidenceError("invalid_canonical_matrix_status")
    cases = list(_sequence(value.get("cases"), "cases"))
    case_inputs = list(_sequence(value.get("case_inputs"), "case_inputs"))
    if len(cases) != REQUIRED_CASE_COUNT:
        raise P138ReleaseEvidenceError("p138_release_case_count_must_equal_30")
    if len(case_inputs) != REQUIRED_CASE_COUNT:
        raise P138ReleaseEvidenceError("frozen_case_input_count_invalid")
    expected_ids = _required_case_ids()

    runtime_total = _zero(RUNTIME_ACTIVITY_KEYS)
    expected_runtime_total = _zero(RUNTIME_ACTIVITY_KEYS)
    forbidden_total = _zero(FORBIDDEN_AUTHORITY_KEYS)
    expected_forbidden_total = _zero(FORBIDDEN_AUTHORITY_KEYS)
    evaluator_case_total = _zero(EVALUATOR_ACTIVITY_KEYS)
    expected_evaluator_case_total = _zero(EVALUATOR_ACTIVITY_KEYS)
    resource_cases: list[Mapping[str, Any]] = []
    seen_ids: list[str] = []
    for raw_case in cases:
        case = _mapping(raw_case, "case")
        _expect_exact_fields(case, _CASE_FIELDS, "case")
        case_id = _text(case.get("case_id"), "case_id")
        seen_ids.append(case_id)
        expected = _validate_case_result(case.get("expected"), "case_expected")
        actual = _validate_case_result(case.get("actual"), "case_actual")
        if expected != actual or case.get("status") != "passed":
            raise P138ReleaseEvidenceError("case_actual_expected_mismatch")
        is_real = case_id in REAL_BOUNDARY_CASE_IDS
        if case.get("real_boundary") is not is_real:
            raise P138ReleaseEvidenceError("case_real_boundary_mismatch")
        evidence = _mapping(case.get("evidence"), "case_evidence")
        _expect_exact_fields(evidence, _CASE_EVIDENCE_FIELDS, "case_evidence")
        if evidence.get("executed") is not True:
            raise P138ReleaseEvidenceError("case_not_executed")
        _text(evidence.get("execution_source"), "execution_source")
        _hash(evidence.get("output_dir_ref_hash"), "output_dir_ref_hash")
        runtime_activity = _exact_counters(
            evidence.get("runtime_activity"),
            RUNTIME_ACTIVITY_KEYS,
            "invalid_case_runtime_activity_schema",
        )
        expected_runtime = _exact_counters(
            evidence.get("expected_runtime_activity"),
            RUNTIME_ACTIVITY_KEYS,
            "invalid_case_expected_runtime_activity_schema",
        )
        if runtime_activity != expected_runtime:
            raise P138ReleaseEvidenceError("case_runtime_activity_delta_mismatch")
        forbidden = _exact_counters(
            evidence.get("forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_case_forbidden_authority_schema",
            require_zero=True,
        )
        expected_forbidden = _exact_counters(
            evidence.get("expected_forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_case_expected_forbidden_authority_schema",
            require_zero=True,
        )
        if forbidden != expected_forbidden:
            raise P138ReleaseEvidenceError("case_forbidden_authority_delta_mismatch")
        evaluator = _exact_counters(
            evidence.get("evaluator_activity"),
            EVALUATOR_ACTIVITY_KEYS,
            "invalid_case_evaluator_activity_schema",
        )
        expected_evaluator = _exact_counters(
            evidence.get("expected_evaluator_activity"),
            EVALUATOR_ACTIVITY_KEYS,
            "invalid_case_expected_evaluator_activity_schema",
        )
        if evaluator != expected_evaluator:
            raise P138ReleaseEvidenceError("case_evaluator_activity_delta_mismatch")
        resources = _exact_counters(
            evidence.get("resource_usage"),
            RELEASE_RESOURCE_USAGE_KEYS,
            "invalid_case_resource_usage_schema",
        )
        expected_resources = _exact_counters(
            evidence.get("expected_resource_usage"),
            RELEASE_RESOURCE_USAGE_KEYS,
            "invalid_case_expected_resource_usage_schema",
        )
        _validate_expected_resource_budget(expected_resources)
        if not _resource_within_budget(resources, expected_resources):
            raise P138ReleaseEvidenceError("case_resource_budget_exceeded")
        _merge(runtime_total, runtime_activity)
        _merge(expected_runtime_total, expected_runtime)
        _merge(forbidden_total, forbidden)
        _merge(expected_forbidden_total, expected_forbidden)
        _merge(evaluator_case_total, evaluator)
        _merge(expected_evaluator_case_total, expected_evaluator)
        resource_cases.append(evidence)
        if case.get("case_evidence_hash") != stable_hash({key: item for key, item in case.items() if key != "case_evidence_hash"}):
            raise P138ReleaseEvidenceError("case_evidence_hash_invalid")
    if seen_ids != expected_ids:
        raise P138ReleaseEvidenceError("required_case_ids_mismatch")

    validated_inputs: list[Mapping[str, Any]] = []
    input_ids: list[str] = []
    for raw_input in case_inputs:
        case_input = _mapping(raw_input, "case_input")
        _expect_exact_fields(case_input, _CASE_INPUT_FIELDS, "case_input")
        if case_input.get("schema_version") != CASE_INPUT_SCHEMA_VERSION:
            raise P138ReleaseEvidenceError("invalid_case_input_schema")
        case_id = _text(case_input.get("case_id"), "case_input_id")
        input_ids.append(case_id)
        bindings = _mapping(case_input.get("bindings"), "case_input_bindings")
        if case_input.get("runtime_input_hash") != stable_hash(bindings):
            raise P138ReleaseEvidenceError("case_input_binding_hash_invalid")
        for field, keys, error, require_zero in (
            ("expected_runtime_activity", RUNTIME_ACTIVITY_KEYS, "invalid_frozen_expected_runtime_activity", False),
            ("expected_forbidden_authority", FORBIDDEN_AUTHORITY_KEYS, "invalid_frozen_expected_forbidden_authority", True),
            ("expected_evaluator_activity", EVALUATOR_ACTIVITY_KEYS, "invalid_frozen_expected_evaluator_activity", False),
        ):
            _exact_counters(bindings.get(field), keys, error, require_zero=require_zero)
        _validate_expected_resource_budget(
            _exact_counters(
                bindings.get("expected_resource_usage"),
                RELEASE_RESOURCE_USAGE_KEYS,
                "invalid_frozen_expected_resource_usage",
            )
        )
        executor = _mapping(bindings.get("execute"), "frozen_executor")
        if set(executor) != {"kind", "identity", "state"} or executor.get("kind") != "callable":
            raise P138ReleaseEvidenceError("invalid_frozen_executor_binding")
        _text(executor.get("identity"), "frozen_executor_identity")
        validated_inputs.append(case_input)
    if input_ids != expected_ids:
        raise P138ReleaseEvidenceError("frozen_case_input_ids_invalid")

    totals = _mapping(value.get("totals"), "totals")
    _expect_exact_fields(totals, _TOTAL_FIELDS, "totals")
    if dict(totals) != {"expected": 30, "passed": 30, "failed": 0}:
        raise P138ReleaseEvidenceError("release_cases_not_all_passed")
    _require_equal_counter(value, "runtime_activity", runtime_total, RUNTIME_ACTIVITY_KEYS)
    _require_equal_counter(value, "expected_runtime_activity", expected_runtime_total, RUNTIME_ACTIVITY_KEYS)
    _require_equal_counter(value, "forbidden_authority", forbidden_total, FORBIDDEN_AUTHORITY_KEYS, require_zero=True)
    _require_equal_counter(value, "expected_forbidden_authority", expected_forbidden_total, FORBIDDEN_AUTHORITY_KEYS, require_zero=True)
    overhead = _exact_counters(value.get("evaluator_overhead_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_evaluator_overhead_activity")
    expected_overhead = _exact_counters(value.get("expected_evaluator_overhead_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_expected_evaluator_overhead_activity")
    if overhead != expected_overhead:
        raise P138ReleaseEvidenceError("evaluator_overhead_delta_mismatch")
    evaluator_total = _sum(evaluator_case_total, overhead)
    expected_evaluator_total = _sum(expected_evaluator_case_total, expected_overhead)
    _require_equal_counter(value, "evaluator_activity", evaluator_total, EVALUATOR_ACTIVITY_KEYS)
    _require_equal_counter(value, "expected_evaluator_activity", expected_evaluator_total, EVALUATOR_ACTIVITY_KEYS)
    if evaluator_total != expected_evaluator_total:
        raise P138ReleaseEvidenceError("release_evaluator_activity_delta_mismatch")
    rebuilt_resources = _aggregate_resources(resource_cases)
    resources = _exact_counters(value.get("resource_usage"), RELEASE_RESOURCE_USAGE_KEYS, "invalid_resource_usage_schema")
    expected_resources = _exact_counters(value.get("expected_resource_usage"), RELEASE_RESOURCE_USAGE_KEYS, "invalid_expected_resource_usage_schema")
    _validate_expected_resource_budget(expected_resources)
    if resources != rebuilt_resources or not _resource_within_budget(resources, expected_resources):
        raise P138ReleaseEvidenceError("resource_usage_totals_mismatch")

    if value.get("matrix_hash") != stable_hash(cases):
        raise P138ReleaseEvidenceError("matrix_hash_invalid")
    if value.get("case_input_hash") != stable_hash(case_inputs):
        raise P138ReleaseEvidenceError("case_input_hash_invalid")
    rebuilt_case_config_hash = stable_hash(
        [
            {
                "case_id": item["case_id"],
                "input_profile_hash": stable_hash(_mapping(item["bindings"], "bindings")["input_profile"]),
            }
            for item in validated_inputs
        ]
    )
    if value.get("case_config_hash") != rebuilt_case_config_hash:
        raise P138ReleaseEvidenceError("case_config_hash_invalid")
    if value.get("case_evidence_hash") != stable_hash([_mapping(case, "case")["case_evidence_hash"] for case in cases]):
        raise P138ReleaseEvidenceError("case_evidence_hash_invalid")
    _scan_leaks(value)
    return deepcopy(dict(value))


def build_p138_freeze_manifest(
    *,
    source_bindings: Mapping[str, str],
    profile: Mapping[str, Any],
    canonical_matrix: Mapping[str, Any],
    dependency_bindings: Mapping[str, Any],
    project_root: Path | None = None,
) -> dict[str, Any]:
    matrix = validate_p138_canonical_matrix(canonical_matrix)
    sources = _validate_source_bindings(source_bindings)
    if sources.get(APPROVED_PLAN_PATH) != "sha256:" + APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_source_stale")
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_MANIFEST_SCHEMA_VERSION,
        "approved_plan_sha256": APPROVED_PLAN_SHA256,
        "source_bindings": sources,
        "dependency_bindings": _validate_dependency_bindings(dependency_bindings),
        "profile_hash": p138_profile_hash(profile),
        "fixture_hash": p138_fixture_hash(profile, project_root=project_root),
        "matrix_hash": matrix["matrix_hash"],
        "case_input_hash": matrix["case_input_hash"],
        "case_config_hash": matrix["case_config_hash"],
        "case_evidence_hash": matrix["case_evidence_hash"],
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def validate_p138_freeze_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_source_hashes: Mapping[str, str] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
    expected_matrix_hash: str | None = None,
    expected_dependency_bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = _mapping(manifest, "freeze_manifest")
    _expect_exact_fields(value, _MANIFEST_FIELDS, "freeze_manifest")
    if value.get("schema_version") != FREEZE_MANIFEST_SCHEMA_VERSION:
        raise P138ReleaseEvidenceError("invalid_freeze_manifest_schema")
    if value.get("approved_plan_sha256") != APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_hash_mismatch")
    sources = _validate_source_bindings(value.get("source_bindings"))
    dependencies = _validate_dependency_bindings(value.get("dependency_bindings"))
    if sources.get(APPROVED_PLAN_PATH) != "sha256:" + APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_source_stale")
    if expected_source_hashes is not None and sources != dict(sorted(expected_source_hashes.items())):
        raise P138ReleaseEvidenceError("freeze_manifest_source_stale")
    if expected_dependency_bindings is not None and dependencies != _validate_dependency_bindings(expected_dependency_bindings):
        raise P138ReleaseEvidenceError("freeze_manifest_dependency_stale")
    for field in (
        "profile_hash",
        "fixture_hash",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
    ):
        _hash(value.get(field), field)
    if expected_profile_hash is not None and value.get("profile_hash") != _hash(expected_profile_hash, "expected_profile_hash"):
        raise P138ReleaseEvidenceError("freeze_manifest_profile_stale")
    if expected_fixture_hash is not None and value.get("fixture_hash") != _hash(expected_fixture_hash, "expected_fixture_hash"):
        raise P138ReleaseEvidenceError("freeze_manifest_fixture_stale")
    if expected_matrix_hash is not None and value.get("matrix_hash") != _hash(expected_matrix_hash, "expected_matrix_hash"):
        raise P138ReleaseEvidenceError("freeze_manifest_matrix_stale")
    if value.get("freeze_manifest_hash") != stable_hash({key: item for key, item in value.items() if key != "freeze_manifest_hash"}):
        raise P138ReleaseEvidenceError("freeze_manifest_hash_invalid")
    return deepcopy(dict(value))


def validate_p138_final_implementation_review(
    review: Mapping[str, Any],
    *,
    expected_source_hashes: Mapping[str, str] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
    expected_matrix_hash: str | None = None,
    expected_freeze_manifest_hash: str | None = None,
) -> dict[str, Any]:
    value = _mapping(review, "final_implementation_review")
    _expect_exact_fields(value, _REVIEW_FIELDS, "final_implementation_review")
    if value.get("schema_version") != FINAL_REVIEW_SCHEMA_VERSION:
        raise P138ReleaseEvidenceError("invalid_final_implementation_review_schema")
    reviewer = _text(value.get("reviewer_identity"), "reviewer_identity")
    implementer = _text(value.get("implementation_identity"), "implementation_identity")
    if reviewer == implementer or reviewer.casefold() in {
        "p138-implementation-executor",
        "canonicalruntimefactory",
        "p138_runner",
    }:
        raise P138ReleaseEvidenceError("final_review_must_be_independent")
    if value.get("approved_plan_sha256") != APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_hash_mismatch")
    findings = _mapping(value.get("findings"), "findings")
    if set(findings) != {"p0", "p1", "p2", "p3"}:
        raise P138ReleaseEvidenceError("invalid_review_findings")
    for item in findings.values():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P138ReleaseEvidenceError("invalid_review_findings")
    if any(findings[key] != 0 for key in ("p0", "p1", "p2")) or value.get("decision") != "approve":
        raise P138ReleaseEvidenceError("implementation_review_blocking_findings")
    sources = _validate_source_bindings(value.get("reviewed_source_hashes"))
    if sources.get(APPROVED_PLAN_PATH) != "sha256:" + APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_source_stale")
    if expected_source_hashes is not None and sources != dict(sorted(expected_source_hashes.items())):
        raise P138ReleaseEvidenceError("implementation_review_source_stale")
    for field in (
        "reviewed_profile_hash",
        "reviewed_fixture_hash",
        "reviewed_matrix_hash",
        "reviewed_freeze_manifest_hash",
    ):
        _hash(value.get(field), field)
    expected_pairs = (
        ("reviewed_profile_hash", expected_profile_hash, "implementation_review_profile_stale"),
        ("reviewed_fixture_hash", expected_fixture_hash, "implementation_review_fixture_stale"),
        ("reviewed_matrix_hash", expected_matrix_hash, "implementation_review_matrix_stale"),
        ("reviewed_freeze_manifest_hash", expected_freeze_manifest_hash, "implementation_review_manifest_stale"),
    )
    for field, expected, error in expected_pairs:
        if expected is not None and value.get(field) != _hash(expected, f"expected_{field}"):
            raise P138ReleaseEvidenceError(error)
    limitations = [_text(item, "limitation") for item in _sequence(value.get("limitations"), "limitations")]
    if _NO_AUTHORITY_LIMITATION not in limitations:
        raise P138ReleaseEvidenceError("missing_no_authority_limitation")
    if value.get("review_hash") != stable_hash({key: item for key, item in value.items() if key != "review_hash"}):
        raise P138ReleaseEvidenceError("review_hash_invalid")
    return deepcopy(dict(value))


def assemble_p138_release_evidence_from_frozen_matrix(
    canonical_matrix: Mapping[str, Any],
    *,
    freeze_manifest: Mapping[str, Any],
    final_implementation_review: Mapping[str, Any],
    expected_source_hashes: Mapping[str, str] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
    expected_dependency_bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    matrix = validate_p138_canonical_matrix(canonical_matrix)
    manifest = validate_p138_freeze_manifest(
        freeze_manifest,
        expected_source_hashes=expected_source_hashes,
        expected_profile_hash=expected_profile_hash,
        expected_fixture_hash=expected_fixture_hash,
        expected_matrix_hash=matrix["matrix_hash"],
        expected_dependency_bindings=expected_dependency_bindings,
    )
    for field in ("case_input_hash", "case_config_hash", "case_evidence_hash"):
        if manifest[field] != matrix[field]:
            raise P138ReleaseEvidenceError(f"freeze_manifest_{field}_stale")
    review = validate_p138_final_implementation_review(
        final_implementation_review,
        expected_source_hashes=manifest["source_bindings"],
        expected_profile_hash=manifest["profile_hash"],
        expected_fixture_hash=manifest["fixture_hash"],
        expected_matrix_hash=manifest["matrix_hash"],
        expected_freeze_manifest_hash=manifest["freeze_manifest_hash"],
    )
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": P138_READY_STATUS,
        "approved_plan_sha256": APPROVED_PLAN_SHA256,
        "dependency_bindings": deepcopy(manifest["dependency_bindings"]),
        "cases": deepcopy(matrix["cases"]),
        "totals": deepcopy(matrix["totals"]),
        "forbidden_authority": deepcopy(matrix["forbidden_authority"]),
        "expected_forbidden_authority": deepcopy(matrix["expected_forbidden_authority"]),
        "runtime_activity": deepcopy(matrix["runtime_activity"]),
        "expected_runtime_activity": deepcopy(matrix["expected_runtime_activity"]),
        "evaluator_activity": deepcopy(matrix["evaluator_activity"]),
        "expected_evaluator_activity": deepcopy(matrix["expected_evaluator_activity"]),
        "evaluator_overhead_activity": deepcopy(matrix["evaluator_overhead_activity"]),
        "expected_evaluator_overhead_activity": deepcopy(matrix["expected_evaluator_overhead_activity"]),
        "resource_usage": deepcopy(matrix["resource_usage"]),
        "expected_resource_usage": deepcopy(matrix["expected_resource_usage"]),
        "source_bindings": deepcopy(manifest["source_bindings"]),
        "profile_hash": manifest["profile_hash"],
        "fixture_hash": manifest["fixture_hash"],
        "matrix_hash": manifest["matrix_hash"],
        "case_input_hash": manifest["case_input_hash"],
        "case_config_hash": manifest["case_config_hash"],
        "case_evidence_hash": manifest["case_evidence_hash"],
        "freeze_manifest_hash": manifest["freeze_manifest_hash"],
        "final_implementation_review_hash": review["review_hash"],
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return validate_p138_release_evidence(
        evidence,
        expected_source_hashes=expected_source_hashes or manifest["source_bindings"],
        final_implementation_review=review,
        expected_profile_hash=manifest["profile_hash"],
        expected_fixture_hash=manifest["fixture_hash"],
        expected_matrix_hash=manifest["matrix_hash"],
        expected_freeze_manifest_hash=manifest["freeze_manifest_hash"],
        expected_dependency_bindings=manifest["dependency_bindings"],
    )


def validate_p138_release_evidence(
    evidence: Mapping[str, Any],
    *,
    final_implementation_review: Mapping[str, Any] | None = None,
    expected_source_hashes: Mapping[str, str] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
    expected_matrix_hash: str | None = None,
    expected_freeze_manifest_hash: str | None = None,
    expected_dependency_bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if final_implementation_review is None:
        raise P138ReleaseEvidenceError("final_implementation_review_required")
    value = _mapping(evidence, "release_evidence")
    _expect_exact_fields(value, _RELEASE_FIELDS, "release_evidence")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise P138ReleaseEvidenceError("invalid_release_evidence_schema")
    if value.get("status") != P138_READY_STATUS:
        raise P138ReleaseEvidenceError("invalid_p138_release_status")
    if value.get("approved_plan_sha256") != APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_hash_mismatch")
    dependencies = _validate_dependency_bindings(value.get("dependency_bindings"))
    if expected_dependency_bindings is not None and dependencies != _validate_dependency_bindings(expected_dependency_bindings):
        raise P138ReleaseEvidenceError("dependency_binding_mismatch")
    cases = list(_sequence(value.get("cases"), "cases"))
    if len(cases) != 30 or [case.get("case_id") for case in cases if isinstance(case, Mapping)] != _required_case_ids():
        raise P138ReleaseEvidenceError("p138_release_case_count_must_equal_30")
    if value.get("totals") != {"expected": 30, "passed": 30, "failed": 0}:
        raise P138ReleaseEvidenceError("release_cases_not_all_passed")
    runtime_total = _zero(RUNTIME_ACTIVITY_KEYS)
    expected_runtime_total = _zero(RUNTIME_ACTIVITY_KEYS)
    forbidden_total = _zero(FORBIDDEN_AUTHORITY_KEYS)
    expected_forbidden_total = _zero(FORBIDDEN_AUTHORITY_KEYS)
    evaluator_case_total = _zero(EVALUATOR_ACTIVITY_KEYS)
    expected_evaluator_case_total = _zero(EVALUATOR_ACTIVITY_KEYS)
    resource_cases: list[Mapping[str, Any]] = []
    for raw_case in cases:
        case = _mapping(raw_case, "case")
        _expect_exact_fields(case, _CASE_FIELDS, "case")
        if _validate_case_result(case.get("expected"), "case_expected") != _validate_case_result(case.get("actual"), "case_actual"):
            raise P138ReleaseEvidenceError("case_actual_expected_mismatch")
        case_id = _text(case.get("case_id"), "case_id")
        _text(case.get("scenario"), "scenario")
        if case.get("status") != "passed":
            raise P138ReleaseEvidenceError("case_status_invalid")
        if case.get("real_boundary") is not (case_id in REAL_BOUNDARY_CASE_IDS):
            raise P138ReleaseEvidenceError("case_real_boundary_mismatch")
        evidence = _mapping(case.get("evidence"), "case_evidence")
        _expect_exact_fields(evidence, _CASE_EVIDENCE_FIELDS, "case_evidence")
        if evidence.get("executed") is not True:
            raise P138ReleaseEvidenceError("case_not_executed")
        _text(evidence.get("execution_source"), "execution_source")
        _hash(evidence.get("output_dir_ref_hash"), "output_dir_ref_hash")
        runtime_activity = _exact_counters(
            evidence.get("runtime_activity"),
            RUNTIME_ACTIVITY_KEYS,
            "invalid_case_runtime_activity_schema",
        )
        expected_runtime = _exact_counters(
            evidence.get("expected_runtime_activity"),
            RUNTIME_ACTIVITY_KEYS,
            "invalid_case_expected_runtime_activity_schema",
        )
        if runtime_activity != expected_runtime:
            raise P138ReleaseEvidenceError("case_runtime_activity_delta_mismatch")
        forbidden = _exact_counters(
            evidence.get("forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_case_forbidden_authority_schema",
            require_zero=True,
        )
        expected_forbidden = _exact_counters(
            evidence.get("expected_forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_case_expected_forbidden_authority_schema",
            require_zero=True,
        )
        if forbidden != expected_forbidden:
            raise P138ReleaseEvidenceError("case_forbidden_authority_delta_mismatch")
        evaluator = _exact_counters(
            evidence.get("evaluator_activity"),
            EVALUATOR_ACTIVITY_KEYS,
            "invalid_case_evaluator_activity_schema",
        )
        expected_evaluator = _exact_counters(
            evidence.get("expected_evaluator_activity"),
            EVALUATOR_ACTIVITY_KEYS,
            "invalid_case_expected_evaluator_activity_schema",
        )
        if evaluator != expected_evaluator:
            raise P138ReleaseEvidenceError("case_evaluator_activity_delta_mismatch")
        resources = _exact_counters(
            evidence.get("resource_usage"),
            RELEASE_RESOURCE_USAGE_KEYS,
            "invalid_case_resource_usage_schema",
        )
        expected_resources = _exact_counters(
            evidence.get("expected_resource_usage"),
            RELEASE_RESOURCE_USAGE_KEYS,
            "invalid_case_expected_resource_usage_schema",
        )
        _validate_expected_resource_budget(expected_resources)
        if not _resource_within_budget(resources, expected_resources):
            raise P138ReleaseEvidenceError("case_resource_budget_exceeded")
        _merge(runtime_total, runtime_activity)
        _merge(expected_runtime_total, expected_runtime)
        _merge(forbidden_total, forbidden)
        _merge(expected_forbidden_total, expected_forbidden)
        _merge(evaluator_case_total, evaluator)
        _merge(expected_evaluator_case_total, expected_evaluator)
        resource_cases.append(evidence)
        if case.get("case_evidence_hash") != stable_hash({key: item for key, item in case.items() if key != "case_evidence_hash"}):
            raise P138ReleaseEvidenceError("case_evidence_hash_invalid")
    _require_equal_counter(value, "runtime_activity", runtime_total, RUNTIME_ACTIVITY_KEYS)
    _require_equal_counter(
        value,
        "expected_runtime_activity",
        expected_runtime_total,
        RUNTIME_ACTIVITY_KEYS,
    )
    _require_equal_counter(
        value,
        "forbidden_authority",
        forbidden_total,
        FORBIDDEN_AUTHORITY_KEYS,
        require_zero=True,
    )
    _require_equal_counter(
        value,
        "expected_forbidden_authority",
        expected_forbidden_total,
        FORBIDDEN_AUTHORITY_KEYS,
        require_zero=True,
    )
    overhead = _exact_counters(
        value.get("evaluator_overhead_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_evaluator_overhead_activity",
    )
    expected_overhead = _exact_counters(
        value.get("expected_evaluator_overhead_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_expected_evaluator_overhead_activity",
    )
    if overhead != expected_overhead:
        raise P138ReleaseEvidenceError("evaluator_overhead_delta_mismatch")
    _require_equal_counter(
        value,
        "evaluator_activity",
        _sum(evaluator_case_total, overhead),
        EVALUATOR_ACTIVITY_KEYS,
    )
    _require_equal_counter(
        value,
        "expected_evaluator_activity",
        _sum(expected_evaluator_case_total, expected_overhead),
        EVALUATOR_ACTIVITY_KEYS,
    )
    resources = _exact_counters(value.get("resource_usage"), RELEASE_RESOURCE_USAGE_KEYS, "invalid_resource_usage_schema")
    expected_resources = _exact_counters(value.get("expected_resource_usage"), RELEASE_RESOURCE_USAGE_KEYS, "invalid_expected_resource_usage_schema")
    _validate_expected_resource_budget(expected_resources)
    if resources != _aggregate_resources(resource_cases):
        raise P138ReleaseEvidenceError("resource_usage_totals_mismatch")
    if not _resource_within_budget(resources, expected_resources):
        raise P138ReleaseEvidenceError("release_resource_budget_exceeded")
    sources = _validate_source_bindings(value.get("source_bindings"))
    if expected_source_hashes is not None and sources != dict(sorted(expected_source_hashes.items())):
        raise P138ReleaseEvidenceError("release_evidence_source_stale")
    review = validate_p138_final_implementation_review(
        final_implementation_review,
        expected_source_hashes=sources,
        expected_profile_hash=expected_profile_hash or _hash(value.get("profile_hash"), "profile_hash"),
        expected_fixture_hash=expected_fixture_hash or _hash(value.get("fixture_hash"), "fixture_hash"),
        expected_matrix_hash=expected_matrix_hash or _hash(value.get("matrix_hash"), "matrix_hash"),
        expected_freeze_manifest_hash=expected_freeze_manifest_hash or _hash(value.get("freeze_manifest_hash"), "freeze_manifest_hash"),
    )
    if value.get("final_implementation_review_hash") != review["review_hash"]:
        raise P138ReleaseEvidenceError("final_implementation_review_hash_mismatch")
    for field in (
        "profile_hash",
        "fixture_hash",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
        "freeze_manifest_hash",
    ):
        _hash(value.get(field), field)
    if value.get("matrix_hash") != stable_hash(cases):
        raise P138ReleaseEvidenceError("matrix_hash_invalid")
    if value.get("case_evidence_hash") != stable_hash([_mapping(case, "case")["case_evidence_hash"] for case in cases]):
        raise P138ReleaseEvidenceError("case_evidence_hash_invalid")
    if value.get("evidence_hash") != stable_hash({key: item for key, item in value.items() if key != "evidence_hash"}):
        raise P138ReleaseEvidenceError("evidence_hash_invalid")
    _scan_leaks(value)
    return deepcopy(dict(value))


def build_p138_preliminary_evidence(canonical_matrix: Mapping[str, Any], freeze_manifest: Mapping[str, Any]) -> dict[str, Any]:
    matrix = validate_p138_canonical_matrix(canonical_matrix)
    manifest = validate_p138_freeze_manifest(freeze_manifest, expected_matrix_hash=matrix["matrix_hash"])
    for field in ("case_input_hash", "case_config_hash", "case_evidence_hash"):
        if manifest[field] != matrix[field]:
            raise P138ReleaseEvidenceError(f"freeze_manifest_{field}_stale")
    value: dict[str, Any] = {
        "schema_version": PRELIMINARY_EVIDENCE_SCHEMA_VERSION,
        "status": P138_PRELIMINARY_STATUS,
        "approved_plan_sha256": APPROVED_PLAN_SHA256,
        "totals": deepcopy(matrix["totals"]),
        "matrix_hash": matrix["matrix_hash"],
        "case_input_hash": matrix["case_input_hash"],
        "case_config_hash": matrix["case_config_hash"],
        "case_evidence_hash": matrix["case_evidence_hash"],
        "freeze_manifest_hash": manifest["freeze_manifest_hash"],
    }
    value["evidence_hash"] = stable_hash(value)
    return validate_p138_preliminary_evidence(value)


def validate_p138_preliminary_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(evidence, "preliminary_evidence")
    _expect_exact_fields(value, _PRELIMINARY_EVIDENCE_FIELDS, "preliminary_evidence")
    if value.get("schema_version") != PRELIMINARY_EVIDENCE_SCHEMA_VERSION or value.get("status") != P138_PRELIMINARY_STATUS:
        raise P138ReleaseEvidenceError("invalid_preliminary_evidence")
    if value.get("approved_plan_sha256") != APPROVED_PLAN_SHA256:
        raise P138ReleaseEvidenceError("approved_plan_hash_mismatch")
    if value.get("totals") != {"expected": 30, "passed": 30, "failed": 0}:
        raise P138ReleaseEvidenceError("release_cases_not_all_passed")
    for field in ("matrix_hash", "case_input_hash", "case_config_hash", "case_evidence_hash", "freeze_manifest_hash"):
        _hash(value.get(field), field)
    if value.get("evidence_hash") != stable_hash({key: item for key, item in value.items() if key != "evidence_hash"}):
        raise P138ReleaseEvidenceError("evidence_hash_invalid")
    return deepcopy(dict(value))


def _validate_case_result(value: Any, label: str) -> dict[str, Any]:
    result = _mapping(value, label)
    _expect_exact_fields(result, _CASE_RESULT_FIELDS, label)
    return {
        "status": _text(result.get("status"), f"{label}_status"),
        "error": _text(result.get("error"), f"{label}_error"),
        "stop_reason": _text(result.get("stop_reason"), f"{label}_stop_reason"),
        "phase_path": [_text(item, f"{label}_phase") for item in _sequence(result.get("phase_path"), f"{label}_phase_path")],
        "component_boundaries": [_text(item, f"{label}_boundary") for item in _sequence(result.get("component_boundaries"), f"{label}_component_boundaries")],
        "durable_post_state": _text(result.get("durable_post_state"), f"{label}_durable_post_state"),
    }


def _required_case_ids() -> list[str]:
    return [f"P138-CASE-{index:02d}" for index in range(1, REQUIRED_CASE_COUNT + 1)]


def _require_equal_counter(
    value: Mapping[str, Any],
    field: str,
    expected: Mapping[str, int],
    keys: Sequence[str],
    *,
    require_zero: bool = False,
) -> None:
    actual = _exact_counters(value.get(field), keys, f"invalid_{field}_schema", require_zero=require_zero)
    if actual != expected:
        raise P138ReleaseEvidenceError(f"{field}_totals_mismatch")


def _aggregate_resources(evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    value = _resource_budget()
    for key in ("wall_time_ms", "cpu_time_ms", "child_cpu_time_ms", "peak_memory_bytes"):
        value[key] = sum(
            _exact_counters(
                row.get("resource_usage"),
                RELEASE_RESOURCE_USAGE_KEYS,
                "invalid_case_resource_usage_schema",
            )[key]
            for row in evidence_rows
        )
    return value


def _resource_budget() -> dict[str, int]:
    return {
        "wall_time_ms": 0,
        "cpu_time_ms": 0,
        "child_cpu_time_ms": 0,
        "peak_memory_bytes": 0,
        **RESOURCE_LIMITS,
    }


def _validate_expected_resource_budget(value: Mapping[str, int]) -> None:
    if dict(value) != _resource_budget():
        raise P138ReleaseEvidenceError("invalid_expected_resource_budget")


def _resource_within_budget(observed: Mapping[str, int], budget: Mapping[str, int]) -> bool:
    return (
        observed["wall_time_ms"] <= budget["wall_limit_ms"]
        and observed["cpu_time_ms"] + observed["child_cpu_time_ms"] <= budget["cpu_limit_ms"]
        and observed["peak_memory_bytes"] <= budget["peak_memory_limit_bytes"]
        and all(observed[key] == budget[key] for key in RESOURCE_LIMITS)
    )


def _validate_source_bindings(value: Any) -> dict[str, str]:
    raw = _mapping(value, "source_bindings")
    result: dict[str, str] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not key or key.startswith("/") or ".." in Path(key).parts:
            raise P138ReleaseEvidenceError("invalid_source_binding_path")
        result[key] = _hash(item, "source_hash")
    return dict(sorted(result.items()))


def _validate_dependency_bindings(value: Any) -> dict[str, str]:
    raw = _mapping(value, "dependency_bindings")
    if set(raw) != _DEPENDENCY_BINDING_FIELDS:
        raise P138ReleaseEvidenceError("invalid_dependency_binding_fields")
    result = {key: _text(raw.get(key), key) for key in _DEPENDENCY_BINDING_FIELDS}
    if result["p136_status"] != P136_READY_STATUS or result["p137_status"] != P137_READY_STATUS:
        raise P138ReleaseEvidenceError("dependency_status_mismatch")
    for key in (
        "p136_evidence_hash",
        "p136_review_hash",
        "p137_evidence_hash",
        "p137_review_hash",
    ):
        _hash(result[key], key)
    return dict(sorted(result.items()))


def current_p138_dependency_bindings(project_root: Path) -> dict[str, str]:
    """Validate and bind the exact tracked P136/P137 release artifacts."""

    p136_evidence = _read_json_file(
        project_root / "evals/p136/output/release-evidence.json",
        "p136_release_evidence",
    )
    p136_review = _read_json_file(
        project_root / "evals/p136/independent-review.json",
        "p136_independent_review",
    )
    p137_evidence = _read_json_file(
        project_root / "evals/p137/output/release-evidence.json",
        "p137_release_evidence",
    )
    p137_review = _read_json_file(
        project_root / "evals/p137/final-implementation-review.json",
        "p137_final_implementation_review",
    )
    try:
        validated_p136 = validate_p136_release_evidence(
            p136_evidence,
            independent_review=p136_review,
        )
        validated_p137 = validate_p137_release_evidence(
            p137_evidence,
            final_implementation_review=p137_review,
        )
    except Exception as exc:
        raise P138ReleaseEvidenceError(f"dependency_release_invalid:{exc}") from exc
    return _validate_dependency_bindings(
        {
            "p136_status": validated_p136["status"],
            "p136_evidence_hash": validated_p136["evidence_hash"],
            "p136_review_hash": p136_review["independent_review_hash"],
            "p137_status": validated_p137["status"],
            "p137_evidence_hash": validated_p137["evidence_hash"],
            "p137_review_hash": p137_review["implementation_review_hash"],
        }
    )


def _read_json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise P138ReleaseEvidenceError(f"{label}_unavailable") from exc
    if not isinstance(value, Mapping):
        raise P138ReleaseEvidenceError(f"{label}_invalid")
    canonical = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise P138ReleaseEvidenceError(f"{label}_noncanonical")
    return dict(value)


def _exact_counters(
    value: Any,
    keys: Sequence[str],
    error: str,
    *,
    require_zero: bool = False,
) -> dict[str, int]:
    raw = _mapping(value, "counter_map")
    if set(raw) != set(keys):
        raise P138ReleaseEvidenceError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = raw[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P138ReleaseEvidenceError(error)
        if require_zero and item != 0:
            raise P138ReleaseEvidenceError("forbidden_authority_nonzero")
        result[key] = item
    return result


def _merge(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key, item in source.items():
        target[key] += item


def _sum(left: Mapping[str, int], right: Mapping[str, int]) -> dict[str, int]:
    if set(left) != set(right):
        raise P138ReleaseEvidenceError("counter_key_mismatch")
    return {key: left[key] + right[key] for key in left}


def _zero(keys: Sequence[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _expect_exact_fields(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if set(value) != fields:
        raise P138ReleaseEvidenceError(f"invalid_{label}_fields")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P138ReleaseEvidenceError(f"invalid_{label}")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P138ReleaseEvidenceError(f"invalid_{label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise P138ReleaseEvidenceError(f"invalid_{label}")
    return value


def _hash(value: Any, label: str) -> str:
    text = _text(value, label)
    if _HASH_RE.fullmatch(text) is None:
        raise P138ReleaseEvidenceError(f"invalid_hash:{label}")
    return text


def _relative_path(value: Any, label: str) -> str:
    text = _text(value, label)
    path = Path(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P138ReleaseEvidenceError(f"unsafe_path:{label}")
    return path.as_posix()


def _scan_leaks(value: Any) -> None:
    if isinstance(value, str):
        if _SECRET_RE.search(value) or value.startswith("/"):
            raise P138ReleaseEvidenceError("release_artifact_sensitive_text")
    elif isinstance(value, Mapping):
        for item in value.values():
            _scan_leaks(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _scan_leaks(item)


P138_SOURCE_SCOPE = (
    APPROVED_PLAN_PATH,
    "app/services/p110_evaluation.py",
    "app/services/p134_observation_authority.py",
    "app/services/p135_provider_export_attachment.py",
    "app/services/p136_incremental_observer.py",
    "app/services/p136_runner.py",
    "app/services/p136_release_evidence.py",
    "app/services/p137_contracts.py",
    "app/services/p137_p136_handoff.py",
    "app/services/p137_correlation.py",
    "app/services/p137_hypotheses.py",
    "app/services/p137_requests.py",
    "app/services/p137_classification.py",
    "app/services/p137_ledger.py",
    "app/services/p137_runtime.py",
    "app/services/p137_runner.py",
    "app/services/p137_release_evidence.py",
    "app/services/p138_observation_triage_supervisor.py",
    "app/services/p138_runner.py",
    "app/services/p138_release_evidence.py",
    "scripts/run_p136_incremental_observer.py",
    "scripts/run_p137_local_triage.py",
    "scripts/run_p138_observation_triage_supervisor.py",
    "scripts/verify.sh",
    "tests/fixtures/p136/__init__.py",
    "tests/fixtures/p136/builders.py",
    "tests/fixtures/p137/__init__.py",
    "tests/fixtures/p137/builders.py",
    "tests/fixtures/p138/__init__.py",
    "tests/fixtures/p138/builders.py",
    "tests/test_p136_incremental_observer.py",
    "tests/test_p136_runner.py",
    "tests/test_p136_release_evidence.py",
    "tests/test_p137_p136_handoff.py",
    "tests/test_p137_contracts.py",
    "tests/test_p137_correlation.py",
    "tests/test_p137_hypotheses.py",
    "tests/test_p137_requests.py",
    "tests/test_p137_classification.py",
    "tests/test_p137_ledger.py",
    "tests/test_p137_authority_boundary.py",
    "tests/test_p137_runtime.py",
    "tests/test_p137_runner.py",
    "tests/test_p137_release_evidence.py",
    "tests/test_p138_observation_triage_supervisor.py",
    "tests/test_p138_runner.py",
    "tests/test_p138_release_evidence.py",
    "evals/p136/input/incremental-observer-profile.json",
    "evals/p137/input/local-triage-profile.json",
    "evals/p138/input/observation-triage-supervisor-profile.json",
    "docs/operations/p136-test-spec.md",
    "docs/operations/p137-test-spec.md",
    "docs/operations/p138-plan-review.md",
    "docs/operations/p138-test-spec.md",
    "docs/operations/p138-observation-to-triage-supervisor-roadmap.md",
)


__all__ = [
    "APPROVED_PLAN_SHA256",
    "FINAL_REVIEW_SCHEMA_VERSION",
    "FREEZE_MANIFEST_SCHEMA_VERSION",
    "P138_READY_STATUS",
    "P138ReleaseEvidenceError",
    "P138_SOURCE_SCOPE",
    "PROFILE_SCHEMA_VERSION",
    "RELEASE_RESOURCE_USAGE_KEYS",
    "assemble_p138_release_evidence_from_frozen_matrix",
    "build_p138_freeze_manifest",
    "build_p138_preliminary_evidence",
    "current_p138_dependency_bindings",
    "current_p138_source_hashes",
    "p138_fixture_hash",
    "p138_profile_hash",
    "validate_observation_triage_supervisor_profile",
    "validate_p138_canonical_matrix",
    "validate_p138_final_implementation_review",
    "validate_p138_freeze_manifest",
    "validate_p138_preliminary_evidence",
    "validate_p138_release_evidence",
]
