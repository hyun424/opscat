"""Strict release-evidence validation for P137 local triage qualification."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_contracts import (
    ALLOWED_REQUEST_CATALOG,
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RESOURCE_USAGE_KEYS,
    RUNTIME_ACTIVITY_KEYS,
    P137ContractError,
    validate_triage_agent_config,
)

SCHEMA_VERSION = "p137.release_evidence.v1"
FINAL_REVIEW_SCHEMA_VERSION = "p137.final_implementation_review.v1"
PROFILE_SCHEMA_VERSION = "p137.local_triage_profile.v1"
FREEZE_MANIFEST_SCHEMA_VERSION = "p137.freeze_manifest.v2"
PRELIMINARY_MATRIX_SCHEMA_VERSION = "p137.preliminary_matrix.v2"
P137_READY_STATUS = "p137_local_evidence_triage_qualified"
REQUIRED_CASE_COUNT = 60
REQUIRED_PROVIDER_PROFILES = ("prometheus", "loki", "grafana", "sentry", "opentelemetry")
RESOURCE_LIMITS = {
    "wall_limit_ms": 30_000,
    "cpu_limit_ms": 15_000,
    "peak_memory_limit_bytes": 134_217_728,
}
EXPECTED_OUTPUT_ARTIFACTS = ["canonical-matrix.json", "freeze-manifest.json", "release-evidence.json"]

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_RE = re.compile(
    r"(?:bearer\s+|api[_-]?key\s*[:=]|authorization\s*[:=]|password\s*[:=]|credential\s*[:=]|secret\s*[-_:]|https?://)",
    re.IGNORECASE,
)
_RELEASE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "cases",
        "totals",
        "classification_totals",
        "request_catalog",
        "provider_profiles",
        "denominator_cases",
        "original_provider_artifact_reads",
        "exact_schema_gates",
        "release_gates",
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
        "resource_overhead_usage",
        "expected_resource_overhead_usage",
        "source_bindings",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
        "final_implementation_review_hash",
        "evidence_hash",
    }
)
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "category",
        "semantic",
        "expected",
        "actual",
        "status",
        "expected_label",
        "expected_error",
        "termination_reason",
        "scope",
        "delta_profile",
        "request_catalog_entry",
        "provider_profile",
        "evidence",
        "case_evidence_hash",
    }
)
_CASE_EVIDENCE_FIELDS = frozenset(
    {
        "executed",
        "observation_source",
        "api_calls",
        "output_dir_ref_hash",
        "actual_label",
        "actual_error",
        "termination_reason",
        "scope",
        "delta_profile",
        "provider_profile",
        "request_catalog_entry",
        "request_record_hashes",
        "probe_invocation",
        "probe_exception",
        "handoff_bundle_hash",
        "promotion_record_count",
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
_TOTAL_FIELDS = frozenset({"expected", "passed", "failed"})
_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "reviewer_role",
        "implementation_role",
        "reviewed_source_hashes",
        "reviewed_profile_hash",
        "reviewed_fixture_hash",
        "reviewed_matrix_hash",
        "findings",
        "decision",
        "limitations",
        "implementation_review_hash",
    }
)
_PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "case_matrix_version",
        "fixture_root",
        "output_artifacts",
        "required_case_ids",
        "resource_limits",
        "allowed_request_catalog",
        "root_ref_hash",
    }
)
_FREEZE_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "source_bindings",
        "profile_hash",
        "fixture_hash",
        "matrix_hash",
        "case_input_hash",
        "case_config_hash",
        "case_evidence_hash",
        "freeze_manifest_hash",
    }
)


class P137ReleaseEvidenceError(ValueError):
    """Raised when P137 release evidence is malformed or stale."""


def validate_p137_release_evidence(
    evidence: Mapping[str, Any],
    *,
    expected_source_hashes: Mapping[str, str] | None = None,
    final_implementation_review: Mapping[str, Any] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
    expected_matrix_hash: str | None = None,
) -> dict[str, Any]:
    if final_implementation_review is None:
        raise P137ReleaseEvidenceError("final_implementation_review_required")
    value = _mapping(evidence, "release_evidence")
    _expect_exact_fields(value, _RELEASE_FIELDS, "release_evidence")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise P137ReleaseEvidenceError("invalid_p137_release_schema")
    if value.get("status") != P137_READY_STATUS:
        raise P137ReleaseEvidenceError("invalid_p137_release_status")
    _scan_leaks(value)

    cases = _sequence(value.get("cases"), "cases")
    if len(cases) != REQUIRED_CASE_COUNT:
        raise P137ReleaseEvidenceError("p137_release_case_count_must_equal_60")
    seen_ids: set[str] = set()
    passed = 0
    failed = 0
    classification_totals = {"confirmed_incident": 0, "insufficient_evidence": 0, "benign_anomaly": 0, "aborted_fail_closed": 0, "none": 0}
    request_entries: list[str] = []
    provider_profiles: list[str] = []
    denominator_categories: set[str] = set()
    runtime_activity = _zero_counter(RUNTIME_ACTIVITY_KEYS)
    expected_runtime_activity = _zero_counter(RUNTIME_ACTIVITY_KEYS)
    forbidden_authority = _zero_counter(FORBIDDEN_AUTHORITY_KEYS)
    expected_forbidden_authority = _zero_counter(FORBIDDEN_AUTHORITY_KEYS)
    evaluator_activity = _zero_counter(EVALUATOR_ACTIVITY_KEYS)
    expected_evaluator_activity = _zero_counter(EVALUATOR_ACTIVITY_KEYS)
    resource_usage = _zero_counter(RESOURCE_USAGE_KEYS)
    expected_resource_usage = _zero_counter(RESOURCE_USAGE_KEYS)

    for raw_case in cases:
        case = _mapping(raw_case, "case")
        _expect_exact_fields(case, _CASE_FIELDS, "case")
        case_id = _text(case.get("case_id"), "case_id")
        if case_id in seen_ids:
            raise P137ReleaseEvidenceError("invalid_or_duplicate_case_id")
        seen_ids.add(case_id)
        if case.get("actual") != "pass" or case.get("expected") != "pass":
            raise P137ReleaseEvidenceError("case_actual_expected_mismatch")
        status = case.get("status")
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        else:
            raise P137ReleaseEvidenceError("invalid_case_status")
        label = _text(case.get("expected_label"), "expected_label")
        if label not in classification_totals:
            raise P137ReleaseEvidenceError("invalid_classification_total_label")
        classification_totals[label] += 1
        request_entry = case.get("request_catalog_entry")
        if request_entry is not None:
            request_entries.append(_text(request_entry, "request_catalog_entry"))
        provider_profile = case.get("provider_profile")
        if provider_profile is not None:
            provider_profiles.append(_text(provider_profile, "provider_profile"))
        denominator_categories.add(_text(case.get("category"), "category"))
        evidence_value = _mapping(case.get("evidence"), "case_evidence")
        _validate_case_evidence(case, evidence_value)
        _merge_counter(runtime_activity, _exact_counters(evidence_value.get("runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_case_runtime_activity_schema"))
        _merge_counter(expected_runtime_activity, _exact_counters(evidence_value.get("expected_runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_case_expected_runtime_activity_schema"))
        _merge_counter(forbidden_authority, _exact_counters(evidence_value.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_case_forbidden_authority_schema", require_zero=True))
        _merge_counter(
            expected_forbidden_authority,
            _exact_counters(
                evidence_value.get("expected_forbidden_authority"),
                FORBIDDEN_AUTHORITY_KEYS,
                "invalid_case_expected_forbidden_authority_schema",
                require_zero=True,
            ),
        )
        _merge_counter(evaluator_activity, _exact_counters(evidence_value.get("evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_case_evaluator_activity_schema"))
        _merge_counter(expected_evaluator_activity, _exact_counters(evidence_value.get("expected_evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_case_expected_evaluator_activity_schema"))
        _merge_counter(resource_usage, _exact_counters(evidence_value.get("resource_usage"), RESOURCE_USAGE_KEYS, "invalid_case_resource_usage_schema"))
        _merge_counter(expected_resource_usage, _exact_counters(evidence_value.get("expected_resource_usage"), RESOURCE_USAGE_KEYS, "invalid_case_expected_resource_usage_schema"))
        if case.get("case_evidence_hash") != stable_hash({key: item for key, item in case.items() if key != "case_evidence_hash"}):
            raise P137ReleaseEvidenceError("case_evidence_hash_invalid")

    expected_ids = {f"p137-case-{index:02d}" for index in range(1, REQUIRED_CASE_COUNT + 1)}
    if seen_ids != expected_ids:
        raise P137ReleaseEvidenceError("required_case_ids_mismatch")
    totals = _mapping(value.get("totals"), "totals")
    _expect_exact_fields(totals, _TOTAL_FIELDS, "totals")
    if dict(totals) != {"expected": REQUIRED_CASE_COUNT, "passed": passed, "failed": failed}:
        raise P137ReleaseEvidenceError("rebuilt_totals_mismatch")
    if dict(totals) != {"expected": 60, "passed": 60, "failed": 0}:
        raise P137ReleaseEvidenceError("release_cases_not_all_passed")
    if dict(_mapping(value.get("classification_totals"), "classification_totals")) != classification_totals:
        raise P137ReleaseEvidenceError("classification_totals_mismatch")
    if value.get("request_catalog") != list(ALLOWED_REQUEST_CATALOG) or request_entries != list(ALLOWED_REQUEST_CATALOG):
        raise P137ReleaseEvidenceError("request_catalog_coverage_mismatch")
    if tuple(_sequence(value.get("provider_profiles"), "provider_profiles")) != REQUIRED_PROVIDER_PROFILES or set(provider_profiles[:5]) != set(REQUIRED_PROVIDER_PROFILES):
        raise P137ReleaseEvidenceError("provider_profile_coverage_mismatch")
    if value.get("original_provider_artifact_reads") != 0:
        raise P137ReleaseEvidenceError("original_provider_artifact_reads_nonzero")
    _required_denominators(value.get("denominator_cases"), denominator_categories)
    if value.get("exact_schema_gates") is not True or value.get("release_gates") is not True:
        raise P137ReleaseEvidenceError("release_gate_not_satisfied")
    if _exact_counters(value.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_forbidden_authority_schema", require_zero=True) != forbidden_authority:
        raise P137ReleaseEvidenceError("forbidden_authority_totals_mismatch")
    if _exact_counters(value.get("expected_forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_expected_forbidden_authority_schema", require_zero=True) != expected_forbidden_authority:
        raise P137ReleaseEvidenceError("expected_forbidden_authority_totals_mismatch")
    if forbidden_authority != expected_forbidden_authority:
        raise P137ReleaseEvidenceError("release_forbidden_authority_delta_profile_mismatch")
    if _exact_counters(value.get("runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_runtime_activity_schema") != runtime_activity:
        raise P137ReleaseEvidenceError("runtime_activity_totals_mismatch")
    if _exact_counters(value.get("expected_runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_expected_runtime_activity_schema") != expected_runtime_activity:
        raise P137ReleaseEvidenceError("expected_runtime_activity_totals_mismatch")
    if runtime_activity != expected_runtime_activity:
        raise P137ReleaseEvidenceError("release_runtime_activity_delta_profile_mismatch")
    top_evaluator_activity = _exact_counters(value.get("evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_evaluator_activity_schema")
    evaluator_overhead_activity = _exact_counters(value.get("evaluator_overhead_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_evaluator_overhead_activity_schema")
    expected_evaluator_overhead_activity = _exact_counters(value.get("expected_evaluator_overhead_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_expected_evaluator_overhead_activity_schema")
    if evaluator_overhead_activity != expected_evaluator_overhead_activity:
        raise P137ReleaseEvidenceError("evaluator_overhead_activity_delta_profile_mismatch")
    rebuilt_evaluator_activity = _sum_counter(evaluator_activity, evaluator_overhead_activity)
    rebuilt_expected_evaluator_activity = _sum_counter(expected_evaluator_activity, expected_evaluator_overhead_activity)
    if top_evaluator_activity != rebuilt_evaluator_activity:
        raise P137ReleaseEvidenceError("evaluator_activity_totals_mismatch")
    if _exact_counters(value.get("expected_evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_expected_evaluator_activity_schema") != rebuilt_expected_evaluator_activity:
        raise P137ReleaseEvidenceError("expected_evaluator_activity_totals_mismatch")
    if top_evaluator_activity != rebuilt_expected_evaluator_activity:
        raise P137ReleaseEvidenceError("release_evaluator_activity_delta_profile_mismatch")
    resources = _exact_counters(value.get("resource_usage"), RESOURCE_USAGE_KEYS, "invalid_resource_usage_schema")
    resource_overhead_usage = _exact_counters(value.get("resource_overhead_usage"), RESOURCE_USAGE_KEYS, "invalid_resource_overhead_usage_schema")
    expected_resource_overhead_usage = _exact_counters(value.get("expected_resource_overhead_usage"), RESOURCE_USAGE_KEYS, "invalid_expected_resource_overhead_usage_schema")
    if not _resource_within_budget(resource_overhead_usage, expected_resource_overhead_usage):
        raise P137ReleaseEvidenceError("resource_overhead_usage_delta_profile_mismatch")
    rebuilt_resource_usage = _sum_counter(resource_usage, resource_overhead_usage)
    rebuilt_expected_resource_usage = _sum_counter(expected_resource_usage, expected_resource_overhead_usage)
    if resources != rebuilt_resource_usage:
        raise P137ReleaseEvidenceError("resource_usage_totals_mismatch")
    if _exact_counters(value.get("expected_resource_usage"), RESOURCE_USAGE_KEYS, "invalid_expected_resource_usage_schema") != rebuilt_expected_resource_usage:
        raise P137ReleaseEvidenceError("expected_resource_usage_totals_mismatch")
    if not _resource_within_budget(resources, rebuilt_expected_resource_usage):
        raise P137ReleaseEvidenceError("release_resource_usage_delta_profile_mismatch")
    _validate_resource_limits(resources)

    source_bindings = _validate_source_bindings(value.get("source_bindings"))
    if expected_source_hashes is not None and source_bindings != dict(sorted(expected_source_hashes.items())):
        raise P137ReleaseEvidenceError("release_evidence_source_stale")
    review = validate_final_implementation_review(
        final_implementation_review,
        expected_source_hashes=source_bindings,
        expected_profile_hash=expected_profile_hash,
        expected_fixture_hash=expected_fixture_hash,
    )
    if value.get("final_implementation_review_hash") != review["implementation_review_hash"]:
        raise P137ReleaseEvidenceError("final_implementation_review_hash_mismatch")
    if value.get("matrix_hash") != stable_hash(list(cases)):
        raise P137ReleaseEvidenceError("matrix_hash_invalid")
    _hash(value.get("case_input_hash"), "case_input_hash")
    _hash(value.get("case_config_hash"), "case_config_hash")
    if value.get("case_evidence_hash") != stable_hash([_mapping(case, "case")["case_evidence_hash"] for case in cases]):
        raise P137ReleaseEvidenceError("case_evidence_hash_invalid")
    if expected_matrix_hash is not None and value.get("matrix_hash") != _hash(expected_matrix_hash, "expected_matrix_hash"):
        raise P137ReleaseEvidenceError("release_evidence_matrix_stale")
    if expected_matrix_hash is not None and review["reviewed_matrix_hash"] != value.get("matrix_hash"):
        raise P137ReleaseEvidenceError("implementation_review_matrix_stale")
    if value.get("evidence_hash") != stable_hash({key: item for key, item in value.items() if key != "evidence_hash"}):
        raise P137ReleaseEvidenceError("evidence_hash_invalid")
    return deepcopy(dict(value))


def validate_final_implementation_review(
    review: Mapping[str, Any],
    *,
    expected_source_hashes: Mapping[str, str] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
) -> dict[str, Any]:
    value = _mapping(review, "final_implementation_review")
    _expect_exact_fields(value, _REVIEW_FIELDS, "final_implementation_review")
    if value.get("schema_version") != FINAL_REVIEW_SCHEMA_VERSION:
        raise P137ReleaseEvidenceError("invalid_final_implementation_review_schema")
    findings = _mapping(value.get("findings"), "findings")
    if set(findings) != {"p0", "p1", "p2", "p3"}:
        raise P137ReleaseEvidenceError("invalid_review_findings")
    for raw in findings.values():
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise P137ReleaseEvidenceError("invalid_review_findings")
    if findings["p0"] or findings["p1"] or findings["p2"] or value.get("decision") != "approve":
        raise P137ReleaseEvidenceError("implementation_review_blocking_findings")
    sources = _validate_source_bindings(value.get("reviewed_source_hashes"))
    if expected_source_hashes is not None and sources != dict(sorted(expected_source_hashes.items())):
        raise P137ReleaseEvidenceError("implementation_review_source_stale")
    reviewed_profile_hash = _hash(value.get("reviewed_profile_hash"), "reviewed_profile_hash")
    reviewed_fixture_hash = _hash(value.get("reviewed_fixture_hash"), "reviewed_fixture_hash")
    _hash(value.get("reviewed_matrix_hash"), "reviewed_matrix_hash")
    if expected_profile_hash is not None and reviewed_profile_hash != _hash(expected_profile_hash, "expected_profile_hash"):
        raise P137ReleaseEvidenceError("implementation_review_profile_stale")
    if expected_fixture_hash is not None and reviewed_fixture_hash != _hash(expected_fixture_hash, "expected_fixture_hash"):
        raise P137ReleaseEvidenceError("implementation_review_fixture_stale")
    limitations = tuple(_text(item, "limitation") for item in _sequence(value.get("limitations"), "limitations"))
    if "no_auth_no_credentials_no_network_no_provider_api_no_notification_no_action_no_remediation" not in limitations:
        raise P137ReleaseEvidenceError("missing_no_authority_limitation")
    if value.get("implementation_review_hash") != stable_hash({key: item for key, item in value.items() if key != "implementation_review_hash"}):
        raise P137ReleaseEvidenceError("implementation_review_hash_invalid")
    return deepcopy(dict(value))


def p137_profile_hash(profile: Mapping[str, Any]) -> str:
    return stable_hash(validate_local_triage_profile(profile))


def p137_fixture_hash(profile: Mapping[str, Any], *, project_root: Path | None = None) -> str:
    validated = validate_local_triage_profile(profile)
    root = (project_root or Path.cwd()).resolve()
    fixture_root = root / str(validated["fixture_root"])
    if not fixture_root.is_dir() or fixture_root.is_symlink():
        raise P137ReleaseEvidenceError("fixture_root_missing_or_unsafe")
    files: list[dict[str, Any]] = []
    for path in sorted(fixture_root.rglob("*")):
        if path.is_symlink():
            raise P137ReleaseEvidenceError("fixture_tree_symlink_forbidden")
        if path.is_file():
            relative = path.relative_to(fixture_root).as_posix()
            raw = path.read_bytes()
            files.append(
                {
                    "relative_path": relative,
                    "byte_count": len(raw),
                    "content_hash": "sha256:" + hashlib.sha256(raw).hexdigest(),
                }
            )
    if not files:
        raise P137ReleaseEvidenceError("fixture_tree_empty")
    return stable_hash(
        {
            "schema_version": "p137.fixture_binding.v1",
            "fixture_root": validated["fixture_root"],
            "root_ref_hash": validated["root_ref_hash"],
            "files": files,
        }
    )


def build_p137_freeze_manifest(
    *,
    source_bindings: Mapping[str, str],
    profile: Mapping[str, Any],
    matrix_hash: str,
    case_input_hash: str,
    case_config_hash: str,
    case_evidence_hash: str,
    project_root: Path | None = None,
) -> dict[str, Any]:
    manifest = {
        "schema_version": FREEZE_MANIFEST_SCHEMA_VERSION,
        "source_bindings": _validate_source_bindings(source_bindings),
        "profile_hash": p137_profile_hash(profile),
        "fixture_hash": p137_fixture_hash(profile, project_root=project_root),
        "matrix_hash": _hash(matrix_hash, "matrix_hash"),
        "case_input_hash": _hash(case_input_hash, "case_input_hash"),
        "case_config_hash": _hash(case_config_hash, "case_config_hash"),
        "case_evidence_hash": _hash(case_evidence_hash, "case_evidence_hash"),
    }
    manifest["freeze_manifest_hash"] = stable_hash(manifest)
    return manifest


def validate_p137_freeze_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_source_hashes: Mapping[str, str] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
    expected_matrix_hash: str | None = None,
) -> dict[str, Any]:
    value = _mapping(manifest, "freeze_manifest")
    _expect_exact_fields(value, _FREEZE_MANIFEST_FIELDS, "freeze_manifest")
    if value.get("schema_version") != FREEZE_MANIFEST_SCHEMA_VERSION:
        raise P137ReleaseEvidenceError("invalid_freeze_manifest_schema")
    source_bindings = _validate_source_bindings(value.get("source_bindings"))
    if expected_source_hashes is not None and source_bindings != dict(sorted(expected_source_hashes.items())):
        raise P137ReleaseEvidenceError("freeze_manifest_source_stale")
    profile_hash = _hash(value.get("profile_hash"), "profile_hash")
    fixture_hash = _hash(value.get("fixture_hash"), "fixture_hash")
    matrix_hash = _hash(value.get("matrix_hash"), "matrix_hash")
    _hash(value.get("case_input_hash"), "case_input_hash")
    _hash(value.get("case_config_hash"), "case_config_hash")
    _hash(value.get("case_evidence_hash"), "case_evidence_hash")
    if expected_profile_hash is not None and profile_hash != _hash(expected_profile_hash, "expected_profile_hash"):
        raise P137ReleaseEvidenceError("freeze_manifest_profile_stale")
    if expected_fixture_hash is not None and fixture_hash != _hash(expected_fixture_hash, "expected_fixture_hash"):
        raise P137ReleaseEvidenceError("freeze_manifest_fixture_stale")
    if expected_matrix_hash is not None and matrix_hash != _hash(expected_matrix_hash, "expected_matrix_hash"):
        raise P137ReleaseEvidenceError("freeze_manifest_matrix_stale")
    if value.get("freeze_manifest_hash") != stable_hash({key: item for key, item in value.items() if key != "freeze_manifest_hash"}):
        raise P137ReleaseEvidenceError("freeze_manifest_hash_invalid")
    return deepcopy(dict(value))


def assemble_p137_release_evidence_from_frozen_matrix(
    canonical_matrix: Mapping[str, Any],
    *,
    freeze_manifest: Mapping[str, Any],
    final_implementation_review: Mapping[str, Any],
    expected_source_hashes: Mapping[str, str] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
) -> dict[str, Any]:
    raw_matrix = _mapping(canonical_matrix, "canonical_matrix")
    _expect_exact_fields(
        raw_matrix,
        frozenset(
            {
                "schema_version",
                "status",
                "cases",
                "case_inputs",
                "evaluator_activity",
                "evaluator_overhead_activity",
                "expected_evaluator_overhead_activity",
                "resource_usage",
                "resource_overhead_usage",
                "expected_resource_overhead_usage",
                "matrix_hash",
                "case_input_hash",
                "case_config_hash",
                "case_evidence_hash",
            }
        ),
        "canonical_matrix",
    )
    if raw_matrix.get("schema_version") != PRELIMINARY_MATRIX_SCHEMA_VERSION:
        raise P137ReleaseEvidenceError("invalid_preliminary_matrix_schema")
    if raw_matrix.get("status") != "p137_preliminary_matrix_frozen":
        raise P137ReleaseEvidenceError("invalid_preliminary_matrix_status")
    cases = list(_sequence(raw_matrix.get("cases"), "cases"))
    case_inputs = list(_sequence(raw_matrix.get("case_inputs"), "case_inputs"))
    if len(case_inputs) != REQUIRED_CASE_COUNT:
        raise P137ReleaseEvidenceError("frozen_case_input_count_invalid")
    expected_case_ids = [f"p137-case-{index:02d}" for index in range(1, REQUIRED_CASE_COUNT + 1)]
    validated_case_inputs: list[Mapping[str, Any]] = []
    for item in case_inputs:
        binding = _mapping(item, "case_input")
        _expect_exact_fields(
            binding,
            frozenset({"case_id", "schema_version", "bindings", "runtime_input_hash"}),
            "case_input",
        )
        if binding.get("schema_version") != "p137.case_input_binding.v2":
            raise P137ReleaseEvidenceError("invalid_case_input_binding_schema")
        bindings = _mapping(binding.get("bindings"), "case_input_bindings")
        config = _mapping(bindings.get("effective_p137_config"), "effective_p137_config")
        try:
            validate_triage_agent_config(config)
        except P137ContractError as exc:
            raise P137ReleaseEvidenceError("invalid_frozen_effective_p137_config") from exc
        _exact_counters(
            bindings.get("expected_runtime_activity"),
            RUNTIME_ACTIVITY_KEYS,
            "invalid_frozen_expected_runtime_activity_schema",
        )
        _exact_counters(
            bindings.get("expected_evaluator_activity"),
            EVALUATOR_ACTIVITY_KEYS,
            "invalid_frozen_expected_evaluator_activity_schema",
        )
        _exact_counters(
            bindings.get("expected_resource_usage"),
            RESOURCE_USAGE_KEYS,
            "invalid_frozen_expected_resource_usage_schema",
        )
        if binding.get("runtime_input_hash") != stable_hash(bindings):
            raise P137ReleaseEvidenceError("case_input_binding_hash_invalid")
        validated_case_inputs.append(binding)
    if [item.get("case_id") for item in validated_case_inputs] != expected_case_ids:
        raise P137ReleaseEvidenceError("frozen_case_input_ids_invalid")
    matrix_evaluator_activity = _exact_counters(
        raw_matrix.get("evaluator_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_matrix_evaluator_activity_schema",
    )
    matrix_evaluator_overhead_activity = _exact_counters(
        raw_matrix.get("evaluator_overhead_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_matrix_evaluator_overhead_activity_schema",
    )
    matrix_expected_evaluator_overhead_activity = _exact_counters(
        raw_matrix.get("expected_evaluator_overhead_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_matrix_expected_evaluator_overhead_activity_schema",
    )
    if matrix_evaluator_overhead_activity != matrix_expected_evaluator_overhead_activity:
        raise P137ReleaseEvidenceError("matrix_evaluator_overhead_delta_profile_mismatch")
    matrix_resource_usage = _exact_counters(
        raw_matrix.get("resource_usage"),
        RESOURCE_USAGE_KEYS,
        "invalid_matrix_resource_usage_schema",
    )
    matrix_resource_overhead_usage = _exact_counters(
        raw_matrix.get("resource_overhead_usage"),
        RESOURCE_USAGE_KEYS,
        "invalid_matrix_resource_overhead_usage_schema",
    )
    matrix_expected_resource_overhead_usage = _exact_counters(
        raw_matrix.get("expected_resource_overhead_usage"),
        RESOURCE_USAGE_KEYS,
        "invalid_matrix_expected_resource_overhead_usage_schema",
    )
    if not _resource_within_budget(matrix_resource_overhead_usage, matrix_expected_resource_overhead_usage):
        raise P137ReleaseEvidenceError("matrix_resource_overhead_delta_profile_mismatch")
    _validate_resource_limits(matrix_resource_usage)
    matrix_hash = _hash(raw_matrix.get("matrix_hash"), "matrix_hash")
    if matrix_hash != stable_hash(cases):
        raise P137ReleaseEvidenceError("frozen_matrix_hash_invalid")
    case_input_hash = _hash(raw_matrix.get("case_input_hash"), "case_input_hash")
    if case_input_hash != stable_hash(case_inputs):
        raise P137ReleaseEvidenceError("frozen_case_input_hash_invalid")
    case_config_hash = _hash(raw_matrix.get("case_config_hash"), "case_config_hash")
    rebuilt_case_config_hash = stable_hash(
        [
            {
                "case_id": _text(binding.get("case_id"), "case_id"),
                "config_hash": _hash(
                    _mapping(_mapping(binding.get("bindings"), "case_input_bindings").get("effective_p137_config"), "effective_p137_config").get("config_hash"),
                    "effective_p137_config_hash",
                ),
            }
            for binding in validated_case_inputs
        ]
    )
    if case_config_hash != rebuilt_case_config_hash:
        raise P137ReleaseEvidenceError("frozen_case_config_hash_invalid")
    case_evidence_hash = _hash(raw_matrix.get("case_evidence_hash"), "case_evidence_hash")
    if case_evidence_hash != stable_hash([_mapping(case, "case")["case_evidence_hash"] for case in cases]):
        raise P137ReleaseEvidenceError("frozen_case_evidence_hash_invalid")
    manifest = validate_p137_freeze_manifest(
        freeze_manifest,
        expected_source_hashes=expected_source_hashes,
        expected_profile_hash=expected_profile_hash,
        expected_fixture_hash=expected_fixture_hash,
        expected_matrix_hash=matrix_hash,
    )
    if manifest["case_input_hash"] != case_input_hash:
        raise P137ReleaseEvidenceError("freeze_manifest_case_input_stale")
    if manifest["case_config_hash"] != case_config_hash:
        raise P137ReleaseEvidenceError("freeze_manifest_case_config_stale")
    if manifest["case_evidence_hash"] != case_evidence_hash:
        raise P137ReleaseEvidenceError("freeze_manifest_case_evidence_stale")
    review = validate_final_implementation_review(
        final_implementation_review,
        expected_source_hashes=manifest["source_bindings"],
        expected_profile_hash=manifest["profile_hash"],
        expected_fixture_hash=manifest["fixture_hash"],
    )
    if review["reviewed_matrix_hash"] != matrix_hash:
        raise P137ReleaseEvidenceError("implementation_review_matrix_stale")
    evidence = _release_evidence_from_cases(
        cases,
        source_bindings=manifest["source_bindings"],
        final_implementation_review_hash=review["implementation_review_hash"],
        matrix_hash=matrix_hash,
        case_input_hash=case_input_hash,
        case_config_hash=case_config_hash,
        case_evidence_hash=case_evidence_hash,
        case_inputs=validated_case_inputs,
        matrix_evaluator_activity=matrix_evaluator_activity,
        matrix_evaluator_overhead_activity=matrix_evaluator_overhead_activity,
        matrix_expected_evaluator_overhead_activity=matrix_expected_evaluator_overhead_activity,
        matrix_resource_usage=matrix_resource_usage,
        matrix_resource_overhead_usage=matrix_resource_overhead_usage,
        matrix_expected_resource_overhead_usage=matrix_expected_resource_overhead_usage,
    )
    return validate_p137_release_evidence(
        evidence,
        expected_source_hashes=expected_source_hashes or manifest["source_bindings"],
        final_implementation_review=review,
        expected_profile_hash=manifest["profile_hash"],
        expected_fixture_hash=manifest["fixture_hash"],
        expected_matrix_hash=matrix_hash,
    )


def validate_local_triage_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(profile, "profile")
    _expect_exact_fields(value, _PROFILE_FIELDS, "profile")
    if value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise P137ReleaseEvidenceError("invalid_profile_schema")
    if value.get("case_matrix_version") != 1:
        raise P137ReleaseEvidenceError("invalid_case_matrix_version")
    if value.get("required_case_ids") != [f"p137-case-{index:02d}" for index in range(1, REQUIRED_CASE_COUNT + 1)]:
        raise P137ReleaseEvidenceError("required_case_ids_mismatch")
    if value.get("output_artifacts") != EXPECTED_OUTPUT_ARTIFACTS:
        raise P137ReleaseEvidenceError("output_artifacts_mismatch")
    if value.get("allowed_request_catalog") != list(ALLOWED_REQUEST_CATALOG):
        raise P137ReleaseEvidenceError("allowed_request_catalog_mismatch")
    if dict(_mapping(value.get("resource_limits"), "resource_limits")) != RESOURCE_LIMITS:
        raise P137ReleaseEvidenceError("resource_limits_mismatch")
    fixture_root = _relative_path(value.get("fixture_root"), "fixture_root")
    expected_root_hash = stable_hash({"schema_version": "p137.fixture_root_ref.v1", "fixture_root": fixture_root})
    if value.get("root_ref_hash") != expected_root_hash:
        raise P137ReleaseEvidenceError("root_ref_hash_mismatch")
    return deepcopy(dict(value))


def _release_evidence_from_cases(
    cases: Sequence[Any],
    *,
    source_bindings: Mapping[str, str],
    final_implementation_review_hash: str,
    matrix_hash: str,
    case_input_hash: str,
    case_config_hash: str,
    case_evidence_hash: str,
    case_inputs: Sequence[Mapping[str, Any]],
    matrix_evaluator_activity: Mapping[str, int],
    matrix_evaluator_overhead_activity: Mapping[str, int],
    matrix_expected_evaluator_overhead_activity: Mapping[str, int],
    matrix_resource_usage: Mapping[str, int],
    matrix_resource_overhead_usage: Mapping[str, int],
    matrix_expected_resource_overhead_usage: Mapping[str, int],
) -> dict[str, Any]:
    classification_totals = {"confirmed_incident": 0, "insufficient_evidence": 0, "benign_anomaly": 0, "aborted_fail_closed": 0, "none": 0}
    runtime_activity = _zero_counter(RUNTIME_ACTIVITY_KEYS)
    expected_runtime_activity = _zero_counter(RUNTIME_ACTIVITY_KEYS)
    forbidden_authority = _zero_counter(FORBIDDEN_AUTHORITY_KEYS)
    expected_forbidden_authority = _zero_counter(FORBIDDEN_AUTHORITY_KEYS)
    case_evaluator_activity = _zero_counter(EVALUATOR_ACTIVITY_KEYS)
    expected_case_evaluator_activity = _zero_counter(EVALUATOR_ACTIVITY_KEYS)
    case_resource_usage = _zero_counter(RESOURCE_USAGE_KEYS)
    expected_case_resource_usage = _zero_counter(RESOURCE_USAGE_KEYS)
    input_by_case_id = {
        _text(item.get("case_id"), "case_id"): _mapping(item.get("bindings"), "case_input_bindings")
        for item in case_inputs
    }
    for raw_case in cases:
        case = _mapping(raw_case, "case")
        case_id = _text(case.get("case_id"), "case_id")
        input_bindings = input_by_case_id.get(case_id)
        if input_bindings is None:
            raise P137ReleaseEvidenceError("missing_case_input_oracle")
        label = _text(case.get("expected_label"), "expected_label")
        if label not in classification_totals:
            raise P137ReleaseEvidenceError("invalid_classification_total_label")
        classification_totals[label] += 1
        case_evidence = _mapping(case.get("evidence"), "case_evidence")
        _validate_case_evidence(case, case_evidence)
        _merge_counter(runtime_activity, _exact_counters(case_evidence.get("runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_case_runtime_activity_schema"))
        embedded_expected_runtime = _exact_counters(case_evidence.get("expected_runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_case_expected_runtime_activity_schema")
        oracle_expected_runtime = _exact_counters(input_bindings.get("expected_runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_frozen_expected_runtime_activity_schema")
        if embedded_expected_runtime != oracle_expected_runtime:
            raise P137ReleaseEvidenceError("case_expected_runtime_oracle_mismatch")
        _merge_counter(expected_runtime_activity, oracle_expected_runtime)
        _merge_counter(forbidden_authority, _exact_counters(case_evidence.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_case_forbidden_authority_schema", require_zero=True))
        _merge_counter(
            expected_forbidden_authority,
            _exact_counters(
                case_evidence.get("expected_forbidden_authority"),
                FORBIDDEN_AUTHORITY_KEYS,
                "invalid_case_expected_forbidden_authority_schema",
                require_zero=True,
            ),
        )
        _merge_counter(case_evaluator_activity, _exact_counters(case_evidence.get("evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_case_evaluator_activity_schema"))
        embedded_expected_evaluator = _exact_counters(case_evidence.get("expected_evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_case_expected_evaluator_activity_schema")
        oracle_expected_evaluator = _exact_counters(input_bindings.get("expected_evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_frozen_expected_evaluator_activity_schema")
        if embedded_expected_evaluator != oracle_expected_evaluator:
            raise P137ReleaseEvidenceError("case_expected_evaluator_oracle_mismatch")
        _merge_counter(expected_case_evaluator_activity, oracle_expected_evaluator)
        _merge_counter(case_resource_usage, _exact_counters(case_evidence.get("resource_usage"), RESOURCE_USAGE_KEYS, "invalid_case_resource_usage_schema"))
        embedded_expected_resource = _exact_counters(case_evidence.get("expected_resource_usage"), RESOURCE_USAGE_KEYS, "invalid_case_expected_resource_usage_schema")
        oracle_expected_resource = _exact_counters(input_bindings.get("expected_resource_usage"), RESOURCE_USAGE_KEYS, "invalid_frozen_expected_resource_usage_schema")
        if embedded_expected_resource != oracle_expected_resource:
            raise P137ReleaseEvidenceError("case_expected_resource_oracle_mismatch")
        _merge_counter(expected_case_resource_usage, oracle_expected_resource)
    validated_evaluator_activity = _exact_counters(
        matrix_evaluator_activity,
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_matrix_evaluator_activity_schema",
    )
    validated_evaluator_overhead = _exact_counters(
        matrix_evaluator_overhead_activity,
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_matrix_evaluator_overhead_activity_schema",
    )
    validated_expected_evaluator_overhead = _exact_counters(
        matrix_expected_evaluator_overhead_activity,
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_matrix_expected_evaluator_overhead_activity_schema",
    )
    if validated_evaluator_overhead != validated_expected_evaluator_overhead:
        raise P137ReleaseEvidenceError("matrix_evaluator_overhead_delta_profile_mismatch")
    rebuilt_evaluator_activity = _sum_counter(case_evaluator_activity, validated_evaluator_overhead)
    rebuilt_expected_evaluator_activity = _sum_counter(expected_case_evaluator_activity, validated_expected_evaluator_overhead)
    if validated_evaluator_activity != rebuilt_evaluator_activity or validated_evaluator_activity != rebuilt_expected_evaluator_activity:
        raise P137ReleaseEvidenceError("matrix_evaluator_activity_totals_mismatch")
    validated_resources = _exact_counters(
        matrix_resource_usage,
        RESOURCE_USAGE_KEYS,
        "invalid_matrix_resource_usage_schema",
    )
    validated_resource_overhead = _exact_counters(
        matrix_resource_overhead_usage,
        RESOURCE_USAGE_KEYS,
        "invalid_matrix_resource_overhead_usage_schema",
    )
    validated_expected_resource_overhead = _exact_counters(
        matrix_expected_resource_overhead_usage,
        RESOURCE_USAGE_KEYS,
        "invalid_matrix_expected_resource_overhead_usage_schema",
    )
    if not _resource_within_budget(validated_resource_overhead, validated_expected_resource_overhead):
        raise P137ReleaseEvidenceError("matrix_resource_overhead_delta_profile_mismatch")
    rebuilt_resource_usage = _sum_counter(case_resource_usage, validated_resource_overhead)
    rebuilt_expected_resource_usage = _sum_counter(expected_case_resource_usage, validated_expected_resource_overhead)
    if validated_resources != rebuilt_resource_usage or not _resource_within_budget(validated_resources, rebuilt_expected_resource_usage):
        raise P137ReleaseEvidenceError("matrix_resource_usage_totals_mismatch")
    _validate_resource_limits(validated_resources)
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": P137_READY_STATUS,
        "cases": deepcopy(list(cases)),
        "totals": {"expected": REQUIRED_CASE_COUNT, "passed": REQUIRED_CASE_COUNT, "failed": 0},
        "classification_totals": classification_totals,
        "request_catalog": list(ALLOWED_REQUEST_CATALOG),
        "provider_profiles": list(REQUIRED_PROVIDER_PROFILES),
        "denominator_cases": sorted({_text(_mapping(case, "case").get("category"), "category") for case in cases}),
        "original_provider_artifact_reads": 0,
        "exact_schema_gates": True,
        "release_gates": True,
        "forbidden_authority": forbidden_authority,
        "expected_forbidden_authority": expected_forbidden_authority,
        "runtime_activity": runtime_activity,
        "expected_runtime_activity": expected_runtime_activity,
        "evaluator_activity": validated_evaluator_activity,
        "expected_evaluator_activity": rebuilt_expected_evaluator_activity,
        "evaluator_overhead_activity": validated_evaluator_overhead,
        "expected_evaluator_overhead_activity": validated_expected_evaluator_overhead,
        "resource_usage": validated_resources,
        "expected_resource_usage": rebuilt_expected_resource_usage,
        "resource_overhead_usage": validated_resource_overhead,
        "expected_resource_overhead_usage": validated_expected_resource_overhead,
        "source_bindings": dict(sorted(source_bindings.items())),
        "matrix_hash": matrix_hash,
        "case_input_hash": _hash(case_input_hash, "case_input_hash"),
        "case_config_hash": _hash(case_config_hash, "case_config_hash"),
        "case_evidence_hash": _hash(case_evidence_hash, "case_evidence_hash"),
        "final_implementation_review_hash": _hash(final_implementation_review_hash, "final_implementation_review_hash"),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def _validate_case_evidence(case: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    _expect_exact_fields(evidence, _CASE_EVIDENCE_FIELDS, "case_evidence")
    if evidence.get("executed") is not True:
        raise P137ReleaseEvidenceError("case_not_executed")
    if _text(evidence.get("actual_label"), "actual_label") != case.get("expected_label"):
        raise P137ReleaseEvidenceError("case_observed_label_mismatch")
    expected_error = str(case.get("expected_error") or "none")
    if _text(evidence.get("actual_error"), "actual_error") != expected_error:
        raise P137ReleaseEvidenceError("case_observed_error_mismatch")
    if _text(evidence.get("termination_reason"), "termination_reason") != case.get("termination_reason"):
        raise P137ReleaseEvidenceError("case_observed_termination_mismatch")
    if evidence.get("scope") != case.get("scope") or evidence.get("delta_profile") != case.get("delta_profile"):
        raise P137ReleaseEvidenceError("case_observation_scope_mismatch")
    _text(evidence.get("observation_source"), "observation_source")
    api_calls = [_text(item, "api_call") for item in _sequence(evidence.get("api_calls"), "api_calls")]
    if not api_calls:
        raise P137ReleaseEvidenceError("case_observation_api_calls_missing")
    _hash(evidence.get("output_dir_ref_hash"), "output_dir_ref_hash")
    _hash(evidence.get("handoff_bundle_hash"), "handoff_bundle_hash")
    observed_runtime_activity = _exact_counters(
        evidence.get("runtime_activity"),
        RUNTIME_ACTIVITY_KEYS,
        "invalid_case_runtime_activity_schema",
    )
    expected_runtime_activity = _exact_counters(
        evidence.get("expected_runtime_activity"),
        RUNTIME_ACTIVITY_KEYS,
        "invalid_case_expected_runtime_activity_schema",
    )
    if observed_runtime_activity != expected_runtime_activity:
        raise P137ReleaseEvidenceError("case_runtime_activity_delta_profile_mismatch")
    forbidden_authority = _exact_counters(evidence.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_case_forbidden_authority_schema", require_zero=True)
    expected_forbidden_authority = _exact_counters(evidence.get("expected_forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_case_expected_forbidden_authority_schema", require_zero=True)
    if forbidden_authority != expected_forbidden_authority:
        raise P137ReleaseEvidenceError("case_forbidden_authority_delta_profile_mismatch")
    evaluator_activity = _exact_counters(evidence.get("evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_case_evaluator_activity_schema")
    expected_evaluator_activity = _exact_counters(evidence.get("expected_evaluator_activity"), EVALUATOR_ACTIVITY_KEYS, "invalid_case_expected_evaluator_activity_schema")
    if evaluator_activity != expected_evaluator_activity:
        raise P137ReleaseEvidenceError("case_evaluator_activity_delta_profile_mismatch")
    resource_usage = _exact_counters(evidence.get("resource_usage"), RESOURCE_USAGE_KEYS, "invalid_case_resource_usage_schema")
    expected_resource_usage = _exact_counters(evidence.get("expected_resource_usage"), RESOURCE_USAGE_KEYS, "invalid_case_expected_resource_usage_schema")
    if resource_usage != expected_resource_usage:
        raise P137ReleaseEvidenceError("case_resource_usage_delta_profile_mismatch")
    promotion_count = evidence.get("promotion_record_count")
    if isinstance(promotion_count, bool) or not isinstance(promotion_count, int) or promotion_count < 0:
        raise P137ReleaseEvidenceError("invalid_promotion_record_count")
    for item in _sequence(evidence.get("request_record_hashes"), "request_record_hashes"):
        _hash(item, "request_record_hash")
    probe = evidence.get("probe_invocation")
    if probe is not None and not isinstance(probe, Mapping):
        raise P137ReleaseEvidenceError("invalid_probe_invocation")
    exception = evidence.get("probe_exception")
    if exception is not None and not isinstance(exception, Mapping):
        raise P137ReleaseEvidenceError("invalid_probe_exception")


def current_source_hashes(project_root: Path) -> dict[str, str]:
    paths = (
        "app/services/p134_observation_authority.py",
        "app/services/p135_provider_export_attachment.py",
        "app/services/p136_incremental_observer.py",
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
        "scripts/run_p137_local_triage.py",
        "scripts/verify.sh",
        "tests/fixtures/p136/builders.py",
        "tests/fixtures/p137/builders.py",
        "tests/fixtures/p137/__init__.py",
        "tests/test_p137_contracts.py",
        "tests/test_p137_p136_handoff.py",
        "tests/test_p137_correlation.py",
        "tests/test_p137_hypotheses.py",
        "tests/test_p137_requests.py",
        "tests/test_p137_classification.py",
        "tests/test_p137_ledger.py",
        "tests/test_p137_runtime.py",
        "tests/test_p137_authority_boundary.py",
        "tests/test_p137_runner.py",
        "tests/test_p137_release_evidence.py",
        "evals/p137/input/local-triage-profile.json",
        "README.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "docs/operations/p137-evidence-to-incident-roadmap.md",
        "docs/operations/p137-test-spec.md",
        "docs/operations/p137-plan-review.md",
        "docs/tickets/p137/README.md",
        "docs/tickets/p137/P137-001-contract-schema.md",
        "docs/tickets/p137/P137-002-p136-ingest.md",
        "docs/tickets/p137/P137-003-correlation.md",
        "docs/tickets/p137/P137-004-hypotheses.md",
        "docs/tickets/p137/P137-005-bounded-evidence-requests.md",
        "docs/tickets/p137/P137-006-classification-ledger.md",
        "docs/tickets/p137/P137-007-recovery-lease-signals-budgets.md",
        "docs/tickets/p137/P137-008-canonical-runner-cli.md",
        "docs/tickets/p137/P137-009-release-evidence-docs-review.md",
        "docs/tickets/p137/P137-010-final-verification.md",
    )
    result: dict[str, str] = {}
    for path in paths:
        full = project_root / path
        if not full.is_file():
            raise P137ReleaseEvidenceError(f"required_source_missing:{path}")
        result[path] = "sha256:" + hashlib.sha256(full.read_bytes()).hexdigest()
    return dict(sorted(result.items()))


def _required_denominators(raw: Any, categories: set[str]) -> None:
    values = set(_text(item, "denominator_case") for item in _sequence(raw, "denominator_cases"))
    required = {
        "guard",
        "lease",
        "continuous",
        "readiness",
        "handoff",
        "signal",
        "durability",
        "recovery",
        "resource",
    }
    if not required <= values or not required <= categories:
        raise P137ReleaseEvidenceError("denominator_coverage_mismatch")


def _validate_resource_limits(resources: Mapping[str, int]) -> None:
    for key, expected in RESOURCE_LIMITS.items():
        if resources[key] != expected:
            raise P137ReleaseEvidenceError(f"invalid_{key}")
    if resources["wall_time_ms"] > resources["wall_limit_ms"]:
        raise P137ReleaseEvidenceError("wall_time_budget_exceeded")
    if resources["cpu_time_ms"] + resources["child_cpu_time_ms"] > resources["cpu_limit_ms"]:
        raise P137ReleaseEvidenceError("self_plus_child_cpu_budget_exceeded")
    if resources["peak_memory_bytes"] > resources["peak_memory_limit_bytes"]:
        raise P137ReleaseEvidenceError("peak_memory_budget_exceeded")


def _resource_within_budget(observed: Mapping[str, int], budget: Mapping[str, int]) -> bool:
    limits = ("wall_limit_ms", "cpu_limit_ms", "peak_memory_limit_bytes")
    return (
        observed["wall_time_ms"] <= budget["wall_time_ms"]
        and observed["cpu_time_ms"] + observed["child_cpu_time_ms"] <= budget["cpu_limit_ms"]
        and observed["peak_memory_bytes"] <= budget["peak_memory_bytes"]
        and all(observed[key] == budget[key] for key in limits)
    )


def _validate_source_bindings(value: Any) -> dict[str, str]:
    raw = _mapping(value, "source_bindings")
    result: dict[str, str] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not key or key.startswith("/") or ".." in Path(key).parts:
            raise P137ReleaseEvidenceError("invalid_source_binding_path")
        result[key] = _hash(item, "source_hash")
    return dict(sorted(result.items()))


def _expect_exact_fields(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if set(value) != fields:
        raise P137ReleaseEvidenceError(f"invalid_{label}_fields")


def _exact_counters(value: Any, keys: Sequence[str], error: str, *, require_zero: bool = False) -> dict[str, int]:
    raw = _mapping(value, "counters")
    if set(raw) != set(keys):
        raise P137ReleaseEvidenceError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = raw[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P137ReleaseEvidenceError(error)
        if require_zero and item != 0:
            raise P137ReleaseEvidenceError("forbidden_authority_nonzero")
        result[key] = item
    return result


def _zero_counter(keys: Sequence[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _merge_counter(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key, value in source.items():
        target[key] += value


def _sum_counter(left: Mapping[str, int], right: Mapping[str, int]) -> dict[str, int]:
    return {key: left[key] + right[key] for key in left}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137ReleaseEvidenceError(f"invalid_{label}")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P137ReleaseEvidenceError(f"invalid_{label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise P137ReleaseEvidenceError(f"invalid_{label}")
    return value


def _hash(value: Any, label: str) -> str:
    text = _text(value, label)
    if _HASH_RE.fullmatch(text) is None:
        raise P137ReleaseEvidenceError(f"invalid_hash:{label}")
    return text


def _relative_path(value: Any, label: str) -> str:
    text = _text(value, label)
    path = Path(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P137ReleaseEvidenceError(f"unsafe_path:{label}")
    return path.as_posix()


def _scan_leaks(value: Any) -> None:
    if isinstance(value, str):
        if _SECRET_RE.search(value):
            raise P137ReleaseEvidenceError("release_evidence_forbidden_authority_text")
    elif isinstance(value, Mapping):
        for item in value.values():
            _scan_leaks(item)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            _scan_leaks(item)
