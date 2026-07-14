"""Deterministic, fail-closed release evidence for P135."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash

P135_RELEASE_SCHEMA_VERSION = "p135.release_evidence.v1"
P135_READY_STATUS = "p135_provider_shaped_export_attachment_qualified"
P135_BLOCKED_STATUS = "p135_blocked"
AUTHORITY_LEDGER_SCHEMA_VERSION = "p135.release_authority_ledger.v1"
INDEPENDENT_REVIEW_SCHEMA_VERSION = "p135.independent_review.v1"
PRODUCT_CLAIM = (
    "P135 qualifies credential-free provider-shaped local export attachment from bounded local artifacts."
)
PUBLIC_LIMITATION = (
    "Local file artifacts only: no provider call, live connector, network, DNS, socket, credential, environment, "
    "subprocess, shell, delivery, remediation, mutation, production attachment, staging attachment, authenticated "
    "provider identity, or operator replacement is claimed."
)
EXPECTED_SOURCE_BINDINGS = frozenset(
    {
        "app/services/p135_provider_export_attachment.py",
        "app/services/p135_release_evidence.py",
        "scripts/run_p135_provider_export_attachment.py",
        "scripts/verify.sh",
        "evals/p135/input/provider-export-profile.json",
        "tests/test_p135_provider_export_attachment.py",
        "tests/test_p135_release_evidence.py",
        "tests/test_p135_runner.py",
        "docs/operations/p135-provider-export-roadmap.md",
        "docs/operations/p135-test-spec.md",
        "docs/operations/p135-plan-review.md",
    }
)
CANONICAL_FIXTURE_ROOT = "evals/p135/input/exports"
CANONICAL_TICKET_ROOT = "docs/tickets/p135"
REQUIRED_CASES = (
    "prometheus_matrix_success",
    "loki_streams_success",
    "grafana_dashboard_success",
    "sentry_issues_success",
    "otlp_metrics_success",
    "deterministic_duplicate",
    "denied_p134_receipt_rejected",
    "wrong_p134_capability_rejected",
    "byte_estimate_exceeded_rejected",
    "record_estimate_exceeded_fail_closed",
    "manifest_total_byte_budget_exceeded",
    "manifest_total_record_budget_exceeded",
    "absolute_traversal_path_rejected",
    "symlink_hardlink_nonregular_rejected",
    "source_id_reuse_changed_content_rejected",
    "prometheus_wrong_result_type_rejected",
    "loki_malformed_nanosecond_rejected",
    "grafana_duplicate_panel_id_rejected",
    "sentry_duplicate_issue_identity_rejected",
    "otlp_mixed_signal_rejected",
    "duplicate_json_key_rejected",
    "nonfinite_number_rejected",
    "utf8_string_line_budget_rejected",
    "prompt_injection_text_flagged_redacted",
    "sensitive_attribute_hashed_absent",
    "content_hash_mismatch_rejected",
    "file_mutation_replacement_rejected",
    "forged_bundle_receipt_ledger_rejected",
    "nonzero_forbidden_authority_rejected",
    "live_provider_credential_action_claim_rejected",
)
EXPECTED_REJECTION_ERRORS = {
    "denied_p134_receipt_rejected": "authority_decision_not_allowed",
    "wrong_p134_capability_rejected": "authority_capability_mismatch",
    "byte_estimate_exceeded_rejected": "authority_byte_estimate_exceeded",
    "record_estimate_exceeded_fail_closed": "authority_record_estimate_exceeded",
    "manifest_total_byte_budget_exceeded": "manifest_total_byte_budget_exceeded",
    "manifest_total_record_budget_exceeded": "manifest_total_record_budget_exceeded",
    "absolute_traversal_path_rejected": "unsafe_relative_path",
    "symlink_hardlink_nonregular_rejected": "symlink_rejected",
    "source_id_reuse_changed_content_rejected": "content_hash_mismatch",
    "prometheus_wrong_result_type_rejected": "prometheus_result_type_mismatch",
    "loki_malformed_nanosecond_rejected": "malformed_loki_timestamp",
    "grafana_duplicate_panel_id_rejected": "duplicate_grafana_panel_id",
    "sentry_duplicate_issue_identity_rejected": "duplicate_sentry_issue_id",
    "otlp_mixed_signal_rejected": "otlp_signal_family_mismatch",
    "duplicate_json_key_rejected": "duplicate_json_key",
    "nonfinite_number_rejected": "non_finite_number:NaN",
    "utf8_string_line_budget_rejected": "log_line_budget_exceeded",
    "prompt_injection_text_flagged_redacted": "prompt_like_text:credential_like_text",
    "sensitive_attribute_hashed_absent": "sensitive_attribute_hashed_absent",
    "content_hash_mismatch_rejected": "content_hash_mismatch",
    "file_mutation_replacement_rejected": "file_identity_changed",
    "forged_bundle_receipt_ledger_rejected": "receipt_bundle_hash_mismatch",
    "nonzero_forbidden_authority_rejected": "network_call_count_nonzero",
    "live_provider_credential_action_claim_rejected": "authority_level_not_qualified",
}
SUCCESS_PROVIDERS = {
    "prometheus_matrix_success": "prometheus",
    "loki_streams_success": "loki",
    "grafana_dashboard_success": "grafana",
    "sentry_issues_success": "sentry",
    "otlp_metrics_success": "opentelemetry",
}
EXPECTED_PROVIDER_SUCCESSES = {
    "grafana": 1,
    "loki": 1,
    "opentelemetry": 1,
    "prometheus": 1,
    "sentry": 1,
}
FORBIDDEN_AUTHORITY_COUNTERS = (
    "provider_call_count",
    "live_connector_call_count",
    "network_call_count",
    "dns_lookup_count",
    "socket_call_count",
    "credential_read_count",
    "environment_read_count",
    "subprocess_launch_count",
    "shell_execution_count",
    "signal_count",
    "delivery_count",
    "remediation_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
)
OBSERVATION_ACTIVITY_COUNTERS = (
    "local_stat_count",
    "local_file_open_count",
    "local_file_read_count",
    "local_bytes_read",
    "local_records_parsed",
    "duplicate_validation_read_count",
)
EVALUATOR_ACTIVITY_COUNTERS = (
    "runner_invocation_count",
    "profile_read_count",
    "artifact_write_count",
)
_AUTHORITY_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "forbidden_authority",
        "observation_activity",
        "evaluator_activity",
        "authority_ledger_hash",
    }
)
_INDEPENDENT_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "reviewer_role",
        "implementation_role",
        "reviewer_context_hash",
        "implementation_context_hash",
        "reviewed_source_hashes",
        "findings",
        "decision",
        "limitations",
        "independent_review_hash",
    }
)
_CASE_MATRIX_FIELDS = frozenset(
    {
        "schema_version",
        "required_cases",
        "cases",
        "totals",
        "provider_successes",
        "resource_usage",
        "matrix_hash",
    }
)
_RESOURCE_USAGE_FIELDS = frozenset(
    {
        "wall_time_ms",
        "cpu_time_ms",
        "peak_memory_bytes",
        "wall_limit_ms",
        "cpu_limit_ms",
        "peak_memory_limit_bytes",
    }
)
_CASE_FIELDS = frozenset(
    {
        "passed",
        "outcome",
        "provider",
        "error",
        "authority_zero",
        "no_network_credentials_actions",
        "case_hash",
    }
)
_RELEASE_FIELDS = frozenset(
    {
        "schema_version",
        "release_id",
        "release_status",
        "product_claim",
        "public_limitation",
        "gates",
        "totals",
        "artifact_hashes",
        "source_bindings",
        "forbidden_authority",
        "observation_activity",
        "evaluator_activity",
        "reasons",
        "release_evidence_hash",
    }
)
_REVIEW_LIMITATIONS = (
    "reviewer_identity_unauthenticated",
    "local_artifact_only_no_live_provider_claim",
)
_OVERCLAIM_MARKERS = (
    "live production",
    "live staging",
    "credential",
    "authenticated provider",
    "provider api",
    "network",
    "socket",
    "delivery",
    "remediation",
    "mutation",
    "operator replacement",
)


class P135ReleaseEvidenceError(ValueError):
    """Raised when P135 release evidence is stale, malformed, or optimistic."""


def build_authority_ledger(
    *,
    evaluator_activity: Mapping[str, Any],
    observation_activity: Mapping[str, Any],
    forbidden_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ledger: dict[str, Any] = {
        "schema_version": AUTHORITY_LEDGER_SCHEMA_VERSION,
        "forbidden_authority": _exact_counter_mapping(
            forbidden_authority or {key: 0 for key in FORBIDDEN_AUTHORITY_COUNTERS},
            FORBIDDEN_AUTHORITY_COUNTERS,
            zero=True,
            error="forbidden_authority_not_zero",
        ),
        "observation_activity": _exact_counter_mapping(
            observation_activity,
            OBSERVATION_ACTIVITY_COUNTERS,
            zero=False,
            error="invalid_observation_activity",
        ),
        "evaluator_activity": _exact_counter_mapping(
            evaluator_activity,
            EVALUATOR_ACTIVITY_COUNTERS,
            zero=False,
            error="invalid_evaluator_activity",
        ),
    }
    ledger["authority_ledger_hash"] = stable_hash(ledger)
    return ledger


def validate_authority_ledger(ledger: Mapping[str, Any]) -> None:
    value = _mapping(ledger, "authority_ledger")
    _expect_exact_fields(value, _AUTHORITY_LEDGER_FIELDS, "authority_ledger")
    if value.get("schema_version") != AUTHORITY_LEDGER_SCHEMA_VERSION:
        raise P135ReleaseEvidenceError("invalid_authority_ledger_schema")
    _validate_self_hash(value, "authority_ledger_hash", "authority_ledger_hash_invalid")
    _exact_counter_mapping(
        value.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_COUNTERS,
        zero=True,
        error="forbidden_authority_not_zero",
    )
    _exact_counter_mapping(
        value.get("observation_activity"),
        OBSERVATION_ACTIVITY_COUNTERS,
        zero=False,
        error="invalid_observation_activity",
    )
    activity = _exact_counter_mapping(
        value.get("evaluator_activity"),
        EVALUATOR_ACTIVITY_COUNTERS,
        zero=False,
        error="invalid_evaluator_activity",
    )
    if activity != {"runner_invocation_count": 1, "profile_read_count": 1, "artifact_write_count": 5}:
        raise P135ReleaseEvidenceError("invalid_evaluator_activity")


def build_independent_review_artifact(
    *,
    reviewed_source_hashes: Mapping[str, str],
    reviewer_context_hash: str,
    implementation_context_hash: str,
    findings: Mapping[str, Any],
) -> dict[str, Any]:
    review: dict[str, Any] = {
        "schema_version": INDEPENDENT_REVIEW_SCHEMA_VERSION,
        "reviewer_role": "independent_code_reviewer",
        "implementation_role": "implementation_agent",
        "reviewer_context_hash": reviewer_context_hash,
        "implementation_context_hash": implementation_context_hash,
        "reviewed_source_hashes": dict(sorted(reviewed_source_hashes.items())),
        "findings": dict(findings),
        "decision": "approve",
        "limitations": list(_REVIEW_LIMITATIONS),
    }
    review["independent_review_hash"] = stable_hash(review)
    return review


def validate_independent_review_artifact(
    review: Mapping[str, Any], *, expected_source_hashes: Mapping[str, str]
) -> None:
    value = _mapping(review, "independent_review")
    _expect_exact_fields(value, _INDEPENDENT_REVIEW_FIELDS, "independent_review")
    if value.get("schema_version") != INDEPENDENT_REVIEW_SCHEMA_VERSION:
        raise P135ReleaseEvidenceError("invalid_independent_review_schema")
    _validate_self_hash(value, "independent_review_hash", "independent_review_hash_invalid")
    if value.get("reviewer_role") != "independent_code_reviewer" or value.get("implementation_role") != "implementation_agent":
        raise P135ReleaseEvidenceError("review_role_invalid")
    reviewer_context = _require_hash(value.get("reviewer_context_hash"), "reviewer_context_hash")
    implementation_context = _require_hash(value.get("implementation_context_hash"), "implementation_context_hash")
    if reviewer_context == implementation_context:
        raise P135ReleaseEvidenceError("review_context_not_independent")
    source_hashes = _mapping(value.get("reviewed_source_hashes"), "reviewed_source_hashes")
    if dict(source_hashes) != dict(sorted(expected_source_hashes.items())):
        raise P135ReleaseEvidenceError("review_source_binding_stale")
    for relative, digest in source_hashes.items():
        if relative not in expected_source_hashes:
            raise P135ReleaseEvidenceError("review_source_binding_unexpected")
        _require_hash(digest, "reviewed_source_hash")
    findings = _exact_counter_mapping(value.get("findings"), ("p0", "p1", "p2", "p3"), zero=False, error="invalid_review_findings")
    if any(findings[key] != 0 for key in ("p0", "p1", "p2")):
        raise P135ReleaseEvidenceError("review_blocking_findings")
    if value.get("decision") != "approve":
        raise P135ReleaseEvidenceError("review_not_approved")
    if value.get("limitations") != list(_REVIEW_LIMITATIONS):
        raise P135ReleaseEvidenceError("review_limitations_invalid")


def build_p135_release_evidence(
    case_matrix: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
    independent_review: Mapping[str, Any],
    *,
    project_root: Path | str,
) -> dict[str, Any]:
    source_bindings = current_source_hashes(project_root)
    gates = {
        "case_matrix_substantive": _case_matrix_substantive(case_matrix),
        "principal_denominator_exact": _principal_denominator_exact(case_matrix),
        "all_providers_represented": _all_providers_represented(case_matrix),
        "authority_exact_zero": _valid_authority_ledger(authority_ledger),
        "independent_review_current": _valid_independent_review(independent_review, source_bindings),
        "claim_boundary_exact": _claim_boundary_exact(PRODUCT_CLAIM, PUBLIC_LIMITATION),
    }
    passed_cases = _passed_case_count(case_matrix)
    totals = {"expected_cases": 30, "passed_cases": passed_cases, "failed_cases": 30 - passed_cases}
    passed = all(gates.values()) and totals["passed_cases"] == 30 and totals["failed_cases"] == 0
    evidence: dict[str, Any] = {
        "schema_version": P135_RELEASE_SCHEMA_VERSION,
        "release_id": "P135-provider-shaped-export-attachment",
        "release_status": P135_READY_STATUS if passed else P135_BLOCKED_STATUS,
        "product_claim": PRODUCT_CLAIM,
        "public_limitation": PUBLIC_LIMITATION,
        "gates": gates,
        "totals": totals,
        "artifact_hashes": {
            "case_matrix": stable_hash(case_matrix),
            "authority_ledger": stable_hash(authority_ledger),
            "independent_review": stable_hash(independent_review),
        },
        "source_bindings": source_bindings,
        "forbidden_authority": dict(_mapping(authority_ledger.get("forbidden_authority"), "forbidden_authority")),
        "observation_activity": dict(_mapping(authority_ledger.get("observation_activity"), "observation_activity")),
        "evaluator_activity": dict(_mapping(authority_ledger.get("evaluator_activity"), "evaluator_activity")),
        "reasons": [f"{name} failed closed" for name, value in gates.items() if value is not True],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p135_release_evidence(
    evidence: Mapping[str, Any],
    *,
    case_matrix: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
    independent_review: Mapping[str, Any],
    project_root: Path | str,
) -> None:
    value = _mapping(evidence, "release_evidence")
    _expect_exact_fields(value, _RELEASE_FIELDS, "release_evidence")
    if value.get("schema_version") != P135_RELEASE_SCHEMA_VERSION:
        raise P135ReleaseEvidenceError("invalid_release_schema")
    _validate_self_hash(value, "release_evidence_hash", "release_evidence_hash_invalid")
    if (
        value.get("product_claim") != PRODUCT_CLAIM
        or value.get("public_limitation") != PUBLIC_LIMITATION
        or not _claim_boundary_exact(str(value.get("product_claim", "")), str(value.get("public_limitation", "")))
    ):
        raise P135ReleaseEvidenceError("release_claim_mismatch")
    gates = _mapping(value.get("gates"), "gates")
    if not gates or not all(item is True for item in gates.values()):
        raise P135ReleaseEvidenceError("release_gate_failed")
    if value.get("release_status") != P135_READY_STATUS:
        raise P135ReleaseEvidenceError("release_status_blocked")
    current = current_source_hashes(project_root)
    if dict(_mapping(value.get("source_bindings"), "source_bindings")) != current:
        raise P135ReleaseEvidenceError("release_evidence_source_stale")
    _validate_case_matrix(case_matrix)
    validate_authority_ledger(authority_ledger)
    validate_independent_review_artifact(independent_review, expected_source_hashes=current)
    rebuilt = build_p135_release_evidence(
        case_matrix,
        authority_ledger,
        independent_review,
        project_root=project_root,
    )
    if dict(value) != rebuilt:
        raise P135ReleaseEvidenceError("release_evidence_semantic_mismatch")


def current_source_hashes(project_root: Path | str) -> dict[str, str]:
    root = Path(project_root).expanduser().resolve()
    bindings: dict[str, str] = {}
    recursive_bindings: set[str] = set()
    for relative_root in (CANONICAL_FIXTURE_ROOT, CANONICAL_TICKET_ROOT):
        binding_root = root / relative_root
        if binding_root.is_dir() and not binding_root.is_symlink():
            for path in binding_root.rglob("*"):
                if path.is_symlink():
                    raise P135ReleaseEvidenceError(
                        f"source_binding_symlink:{path.relative_to(root).as_posix()}"
                    )
                if path.is_file():
                    recursive_bindings.add(path.relative_to(root).as_posix())
    for relative in sorted(set(EXPECTED_SOURCE_BINDINGS) | recursive_bindings):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise P135ReleaseEvidenceError(f"source_binding_missing:{relative}")
        bindings[relative] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    return bindings


def _case_matrix_substantive(matrix: Mapping[str, Any]) -> bool:
    try:
        _validate_case_matrix(matrix)
    except P135ReleaseEvidenceError:
        return False
    return True


def _validate_case_matrix(matrix: Mapping[str, Any]) -> None:
    value = _mapping(matrix, "case_matrix")
    _expect_exact_fields(value, _CASE_MATRIX_FIELDS, "case_matrix")
    if value.get("schema_version") != "p135.release_case_matrix.v1":
        raise P135ReleaseEvidenceError("invalid_case_matrix_schema")
    _validate_self_hash(value, "matrix_hash", "case_matrix_hash_invalid")
    if value.get("required_cases") != list(REQUIRED_CASES):
        raise P135ReleaseEvidenceError("case_matrix_required_cases_invalid")
    cases = _mapping(value.get("cases"), "cases")
    if set(cases) != set(REQUIRED_CASES):
        raise P135ReleaseEvidenceError("case_matrix_case_set_invalid")
    for name in REQUIRED_CASES:
        case = _validated_case(cases.get(name), name)
        expected_outcome = "success" if name in SUCCESS_PROVIDERS else "duplicate" if name == "deterministic_duplicate" else "rejected"
        if case["outcome"] != expected_outcome:
            raise P135ReleaseEvidenceError(f"case_outcome_invalid:{name}")
        if name in SUCCESS_PROVIDERS:
            if case["provider"] != SUCCESS_PROVIDERS[name] or case["error"] is not None:
                raise P135ReleaseEvidenceError(f"case_provider_invalid:{name}")
        elif name == "deterministic_duplicate":
            if case["provider"] is not None or case["error"] is not None:
                raise P135ReleaseEvidenceError(f"duplicate_case_invalid:{name}")
        elif case["provider"] is not None or case["error"] != EXPECTED_REJECTION_ERRORS[name]:
            raise P135ReleaseEvidenceError(f"rejection_case_invalid:{name}")
    expected_totals = {
        "expected_cases": 30,
        "passed_cases": 30,
        "failed_cases": 0,
        "successful_provider_attachments": 5,
        "duplicate_cases": 1,
        "rejected_cases": 24,
        "denominator_scope": "principal_provider_export_assertions",
    }
    if dict(_mapping(value.get("totals"), "totals")) != expected_totals:
        raise P135ReleaseEvidenceError("case_matrix_totals_invalid")
    if dict(_mapping(value.get("provider_successes"), "provider_successes")) != EXPECTED_PROVIDER_SUCCESSES:
        raise P135ReleaseEvidenceError("provider_successes_invalid")
    if not _resource_usage_valid(value):
        raise P135ReleaseEvidenceError("resource_usage_invalid")


def _validated_case(value: Any, name: str) -> Mapping[str, Any]:
    case = _mapping(value, "case")
    _expect_exact_fields(case, _CASE_FIELDS, "case")
    _validate_self_hash(case, "case_hash", "case_hash_invalid")
    if case.get("passed") is not True:
        raise P135ReleaseEvidenceError(f"case_not_passed:{name}")
    if case.get("authority_zero") is not True or case.get("no_network_credentials_actions") is not True:
        raise P135ReleaseEvidenceError(f"case_authority_invalid:{name}")
    if case.get("provider") is not None and not isinstance(case.get("provider"), str):
        raise P135ReleaseEvidenceError(f"case_provider_invalid:{name}")
    if case.get("error") is not None and not isinstance(case.get("error"), str):
        raise P135ReleaseEvidenceError(f"case_error_invalid:{name}")
    return case


def _valid_authority_ledger(ledger: Mapping[str, Any]) -> bool:
    try:
        validate_authority_ledger(ledger)
    except P135ReleaseEvidenceError:
        return False
    return True


def _valid_independent_review(review: Mapping[str, Any], source_bindings: Mapping[str, str]) -> bool:
    try:
        validate_independent_review_artifact(review, expected_source_hashes=source_bindings)
    except P135ReleaseEvidenceError:
        return False
    return True


def _principal_denominator_exact(matrix: Mapping[str, Any]) -> bool:
    try:
        totals = _mapping(matrix.get("totals"), "totals")
    except P135ReleaseEvidenceError:
        return False
    return totals.get("expected_cases") == 30 and totals.get("passed_cases") == 30 and totals.get("failed_cases") == 0


def _all_providers_represented(matrix: Mapping[str, Any]) -> bool:
    try:
        return dict(_mapping(matrix.get("provider_successes"), "provider_successes")) == EXPECTED_PROVIDER_SUCCESSES
    except P135ReleaseEvidenceError:
        return False


def _passed_case_count(matrix: Mapping[str, Any]) -> int:
    try:
        cases = _mapping(matrix.get("cases"), "cases")
    except P135ReleaseEvidenceError:
        return 0
    return sum(1 for case in cases.values() if isinstance(case, Mapping) and case.get("passed") is True)


def _resource_usage_valid(matrix: Mapping[str, Any]) -> bool:
    try:
        usage = _mapping(matrix.get("resource_usage"), "resource_usage")
        _expect_exact_fields(usage, _RESOURCE_USAGE_FIELDS, "resource_usage")
        expected_limits = {
            "wall_limit_ms": 30_000,
            "cpu_limit_ms": 10_000,
            "peak_memory_limit_bytes": 100_663_296,
        }
        for key, expected in expected_limits.items():
            if usage.get(key) != expected or type(usage.get(key)) is not int:
                return False
        for key in ("wall_time_ms", "cpu_time_ms", "peak_memory_bytes"):
            if type(usage.get(key)) is not int or usage[key] < 0:
                return False
        return (
            usage["wall_time_ms"] <= usage["wall_limit_ms"]
            and usage["cpu_time_ms"] <= usage["cpu_limit_ms"]
            and usage["peak_memory_bytes"] <= usage["peak_memory_limit_bytes"]
        )
    except P135ReleaseEvidenceError:
        return False


def _claim_boundary_exact(product_claim: str, public_limitation: str) -> bool:
    if product_claim == PRODUCT_CLAIM and public_limitation == PUBLIC_LIMITATION:
        return True
    product_lower = product_claim.lower()
    return not any(marker in product_lower for marker in _OVERCLAIM_MARKERS) and public_limitation == PUBLIC_LIMITATION


def _exact_counter_mapping(
    value: Any,
    keys: tuple[str, ...],
    *,
    zero: bool,
    error: str,
) -> dict[str, int]:
    mapping = _mapping(value, "counter_mapping")
    if set(mapping) != set(keys):
        raise P135ReleaseEvidenceError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = mapping[key]
        if type(item) is not int or item < 0 or (zero and item != 0):
            raise P135ReleaseEvidenceError(error)
        result[key] = item
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P135ReleaseEvidenceError(f"invalid_{label}")
    return value


def _expect_exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        raise P135ReleaseEvidenceError(f"invalid_{label}_fields")


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise P135ReleaseEvidenceError(f"invalid_{label}")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise P135ReleaseEvidenceError(f"invalid_{label}") from exc
    return value


def _validate_self_hash(value: Mapping[str, Any], field: str, error: str) -> None:
    claimed = _require_hash(value.get(field), field)
    unsigned = {key: item for key, item in value.items() if key != field}
    if claimed != stable_hash(unsigned):
        raise P135ReleaseEvidenceError(error)


__all__ = [
    "AUTHORITY_LEDGER_SCHEMA_VERSION",
    "EXPECTED_SOURCE_BINDINGS",
    "EXPECTED_REJECTION_ERRORS",
    "FORBIDDEN_AUTHORITY_COUNTERS",
    "INDEPENDENT_REVIEW_SCHEMA_VERSION",
    "OBSERVATION_ACTIVITY_COUNTERS",
    "P135ReleaseEvidenceError",
    "P135_BLOCKED_STATUS",
    "P135_READY_STATUS",
    "PRODUCT_CLAIM",
    "PUBLIC_LIMITATION",
    "REQUIRED_CASES",
    "build_authority_ledger",
    "build_independent_review_artifact",
    "build_p135_release_evidence",
    "current_source_hashes",
    "validate_authority_ledger",
    "validate_independent_review_artifact",
    "validate_p135_release_evidence",
]
