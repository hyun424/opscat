"""Deterministic, fail-closed release evidence for P134."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import validate_exact_zero_authority, zero_authority_counters
from app.services.p134_observation_authority import validate_contract, validate_receipt_ledger

P134_RELEASE_SCHEMA_VERSION = "p134.release_evidence.v1"
P134_READY_STATUS = "p134_observation_authority_contract_qualified"
P134_BLOCKED_STATUS = "p134_blocked"
AUTHORITY_LEDGER_SCHEMA_VERSION = "p134.authority_ledger.v1"
INDEPENDENT_REVIEW_SCHEMA_VERSION = "p134.independent_review.v1"
PRODUCT_CLAIM = (
    "P134 qualifies deterministic observation-authority policy decisions and immutable accounting receipts "
    "without performing observation."
)
PUBLIC_LIMITATION = (
    "Policy-only, credential-free, network-free local evidence: no file ingestion, provider attachment, live GET, "
    "authenticated reviewer identity, notification delivery, remediation, mutation, production observation, "
    "operator replacement, or action authority is claimed."
)

EXPECTED_SOURCE_BINDINGS = frozenset(
    {
        "app/services/p134_observation_authority.py",
        "app/services/p134_release_evidence.py",
        "scripts/run_p134_observation_authority.py",
        "scripts/verify.sh",
        "evals/p134/input/authority-profile.json",
    }
)
REQUIRED_CONTRACT_CASES = (
    "oa0_default_deny",
    "oa1_allowed",
    "deterministic_duplicate",
    "capability_denied",
    "host_denied",
    "method_denied",
    "level_escalation_denied",
    "kill_switch_deny",
    "contract_not_yet_valid",
    "contract_expired",
    "allowed_request_budget_exhausted",
    "byte_budget_exhausted",
    "record_budget_exhausted",
    "host_budget_exhausted",
    "capability_budget_exhausted",
    "response_byte_estimate_too_large",
    "timeout_too_large",
    "attempt_budget_exhausted",
)
REQUIRED_FAULT_CASES = (
    "tampered_review_receipt",
    "changed_request_id_replay",
    "boolean_counter_rejected",
    "url_credential_input_rejected",
    "ledger_reorder_rejected",
    "nonzero_action_authority_rejected",
)
EXPECTED_DENIAL_REASONS = {
    "oa0_default_deny": "contract_only_level",
    "capability_denied": "capability_not_allowlisted",
    "host_denied": "host_not_allowlisted",
    "method_denied": "method_not_allowlisted",
    "level_escalation_denied": "authority_level_not_qualified",
    "kill_switch_deny": "kill_switch_active",
    "contract_not_yet_valid": "contract_not_yet_valid",
    "contract_expired": "contract_expired",
    "allowed_request_budget_exhausted": "allowed_request_budget_exceeded",
    "byte_budget_exhausted": "cumulative_byte_budget_exceeded",
    "record_budget_exhausted": "cumulative_record_budget_exceeded",
    "host_budget_exhausted": "host_budget_exceeded",
    "capability_budget_exhausted": "capability_budget_exceeded",
    "response_byte_estimate_too_large": "single_response_byte_budget_exceeded",
    "timeout_too_large": "timeout_budget_exceeded",
    "attempt_budget_exhausted": "attempt_budget_exceeded",
}
EXPECTED_FAULT_ERRORS = {
    "tampered_review_receipt": "review_receipt_hash_invalid",
    "changed_request_id_replay": "request_id_reuse_conflict",
    "boolean_counter_rejected": "invalid_counter:evaluated_count",
    "url_credential_input_rejected": "unsafe_host_label",
    "ledger_reorder_rejected": "receipt_sequence_mismatch",
    "nonzero_action_authority_rejected": "production_mutation_count_nonzero",
}
RUNTIME_OBSERVATION_COUNTERS = (
    "telemetry_source_read_count",
    "file_source_read_count",
    "credential_read_count",
    "network_call_count",
    "provider_call_count",
    "socket_call_count",
    "subprocess_launch_count",
    "shell_execution_count",
    "delivery_count",
    "remediation_count",
    "staging_mutation_count",
    "production_mutation_count",
)
EVALUATOR_ACTIVITY_COUNTERS = (
    "runner_invocation_count",
    "profile_read_count",
    "artifact_write_count",
)
EVALUATOR_AUTHORITY_COUNTERS = (
    "subprocess_launch_count",
    "signal_count",
    "socket_call_count",
    "credential_read_count",
    "telemetry_source_read_count",
)
INDEPENDENT_REVIEW_LIMITATIONS = (
    "policy_only_no_io",
    "reviewer_identity_unauthenticated",
)

_AUTHORITY_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "runtime_action_authority",
        "runtime_observation",
        "evaluator_activity",
        "evaluator_authority",
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
        "runtime_action_authority",
        "runtime_observation",
        "evaluator_activity",
        "evaluator_authority",
        "reasons",
        "release_evidence_hash",
    }
)
_CONTRACT_MATRIX_FIELDS = frozenset(
    {
        "schema_version",
        "required_cases",
        "cases",
        "totals",
        "canonical_contract",
        "resource_usage",
        "contract_matrix_hash",
    }
)
_FAULT_MATRIX_FIELDS = frozenset(
    {"schema_version", "required_cases", "cases", "totals", "fault_matrix_hash"}
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


class P134ReleaseEvidenceError(ValueError):
    """Raised when P134 evidence is malformed, stale, or optimistic."""


def build_authority_ledger(*, evaluator_activity: Mapping[str, Any]) -> dict[str, Any]:
    """Build separate runtime, evaluator activity, and evaluator authority ledgers."""

    activity = _exact_counter_mapping(evaluator_activity, EVALUATOR_ACTIVITY_COUNTERS, zero=False)
    ledger: dict[str, Any] = {
        "schema_version": AUTHORITY_LEDGER_SCHEMA_VERSION,
        "runtime_action_authority": zero_authority_counters(),
        "runtime_observation": {key: 0 for key in RUNTIME_OBSERVATION_COUNTERS},
        "evaluator_activity": activity,
        "evaluator_authority": {key: 0 for key in EVALUATOR_AUTHORITY_COUNTERS},
    }
    ledger["authority_ledger_hash"] = stable_hash(ledger)
    return ledger


def validate_authority_ledger(ledger: Mapping[str, Any]) -> None:
    value = _mapping(ledger, "authority_ledger")
    _expect_exact_fields(value, _AUTHORITY_LEDGER_FIELDS, "authority_ledger")
    if value.get("schema_version") != AUTHORITY_LEDGER_SCHEMA_VERSION:
        raise P134ReleaseEvidenceError("invalid_authority_ledger_schema")
    _validate_self_hash(value, "authority_ledger_hash", "authority_ledger_hash_invalid")
    try:
        validate_exact_zero_authority(value.get("runtime_action_authority"))
    except ValueError as exc:
        raise P134ReleaseEvidenceError("runtime_action_authority_not_zero") from exc
    _exact_counter_mapping(value.get("runtime_observation"), RUNTIME_OBSERVATION_COUNTERS, zero=True, error="runtime_observation_not_zero")
    activity = _exact_counter_mapping(value.get("evaluator_activity"), EVALUATOR_ACTIVITY_COUNTERS, zero=False)
    if (
        activity["runner_invocation_count"] != 1
        or activity["profile_read_count"] != 1
        or activity["artifact_write_count"] != 5
    ):
        raise P134ReleaseEvidenceError("evaluator_activity_invalid")
    _exact_counter_mapping(value.get("evaluator_authority"), EVALUATOR_AUTHORITY_COUNTERS, zero=True, error="evaluator_authority_not_zero")


def build_independent_review_artifact(
    *,
    reviewed_source_hashes: Mapping[str, str],
    reviewer_context_hash: str,
    implementation_context_hash: str,
    findings: Mapping[str, Any],
) -> dict[str, Any]:
    """Build independently authored review evidence; the release runner must not call this."""

    review: dict[str, Any] = {
        "schema_version": INDEPENDENT_REVIEW_SCHEMA_VERSION,
        "reviewer_role": "independent_code_reviewer",
        "implementation_role": "implementation_agent",
        "reviewer_context_hash": reviewer_context_hash,
        "implementation_context_hash": implementation_context_hash,
        "reviewed_source_hashes": dict(sorted(reviewed_source_hashes.items())),
        "findings": dict(findings),
        "decision": "approve",
        "limitations": list(INDEPENDENT_REVIEW_LIMITATIONS),
    }
    review["independent_review_hash"] = stable_hash(review)
    return review


def validate_independent_review_artifact(
    review: Mapping[str, Any], *, expected_source_hashes: Mapping[str, str]
) -> None:
    value = _mapping(review, "independent_review")
    _expect_exact_fields(value, _INDEPENDENT_REVIEW_FIELDS, "independent_review")
    if value.get("schema_version") != INDEPENDENT_REVIEW_SCHEMA_VERSION:
        raise P134ReleaseEvidenceError("invalid_independent_review_schema")
    _validate_self_hash(value, "independent_review_hash", "independent_review_hash_invalid")
    if value.get("reviewer_role") != "independent_code_reviewer" or value.get("implementation_role") != "implementation_agent":
        raise P134ReleaseEvidenceError("review_role_invalid")
    reviewer_context = _require_hash(value.get("reviewer_context_hash"), "reviewer_context_hash")
    implementation_context = _require_hash(value.get("implementation_context_hash"), "implementation_context_hash")
    if reviewer_context == implementation_context:
        raise P134ReleaseEvidenceError("review_context_not_independent")
    source_hashes = _mapping(value.get("reviewed_source_hashes"), "reviewed_source_hashes")
    if dict(source_hashes) != dict(sorted(expected_source_hashes.items())):
        raise P134ReleaseEvidenceError("review_source_binding_stale")
    for path, digest in source_hashes.items():
        if path not in EXPECTED_SOURCE_BINDINGS:
            raise P134ReleaseEvidenceError("review_source_binding_unexpected")
        _require_hash(digest, "reviewed_source_hash")
    findings = _exact_counter_mapping(value.get("findings"), ("p0", "p1", "p2", "p3"), zero=False)
    if any(findings[key] != 0 for key in ("p0", "p1", "p2")):
        raise P134ReleaseEvidenceError("review_blocking_findings")
    if value.get("decision") != "approve":
        raise P134ReleaseEvidenceError("review_not_approved")
    if value.get("limitations") != list(INDEPENDENT_REVIEW_LIMITATIONS):
        raise P134ReleaseEvidenceError("review_limitations_invalid")


def build_p134_release_evidence(
    contract_matrix: Mapping[str, Any],
    fault_matrix: Mapping[str, Any],
    receipt_ledger: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
    independent_review: Mapping[str, Any],
    *,
    project_root: Path | str,
) -> dict[str, Any]:
    """Build current, source-bound P134 release evidence without optimistic claims."""

    source_bindings = current_source_hashes(project_root)
    gates = {
        "contract_matrix_substantive": _contract_matrix_substantive(contract_matrix),
        "fault_matrix_substantive": _fault_matrix_substantive(fault_matrix),
        "receipt_ledger_semantic": _receipt_ledger_semantic(receipt_ledger, contract_matrix),
        "authority_exact_zero": _valid_authority_ledger(authority_ledger),
        "independent_review_current": _valid_independent_review(independent_review, source_bindings),
        "resource_usage_within_limits": _resource_usage_valid(contract_matrix),
        "principal_denominator_exact": _principal_denominator_exact(contract_matrix, fault_matrix),
        "claim_boundary_exact": True,
    }
    passed_cases = _passed_case_count(contract_matrix) + _passed_case_count(fault_matrix)
    totals = {"expected_cases": 24, "passed_cases": passed_cases, "failed_cases": 24 - passed_cases}
    passed = all(gates.values()) and totals["passed_cases"] == 24 and totals["failed_cases"] == 0
    evidence: dict[str, Any] = {
        "schema_version": P134_RELEASE_SCHEMA_VERSION,
        "release_id": "P134-observation-authority-contract",
        "release_status": P134_READY_STATUS if passed else P134_BLOCKED_STATUS,
        "product_claim": PRODUCT_CLAIM,
        "public_limitation": PUBLIC_LIMITATION,
        "gates": gates,
        "totals": totals,
        "artifact_hashes": {
            "contract_matrix": stable_hash(contract_matrix),
            "fault_matrix": stable_hash(fault_matrix),
            "receipt_ledger": stable_hash(receipt_ledger),
            "authority_ledger": stable_hash(authority_ledger),
            "independent_review": stable_hash(independent_review),
        },
        "source_bindings": source_bindings,
        "runtime_action_authority": dict(_mapping(authority_ledger.get("runtime_action_authority"), "runtime_action_authority")),
        "runtime_observation": dict(_mapping(authority_ledger.get("runtime_observation"), "runtime_observation")),
        "evaluator_activity": dict(_mapping(authority_ledger.get("evaluator_activity"), "evaluator_activity")),
        "evaluator_authority": dict(_mapping(authority_ledger.get("evaluator_authority"), "evaluator_authority")),
        "reasons": [f"{name} failed closed" for name, value in gates.items() if value is not True],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p134_release_evidence(
    evidence: Mapping[str, Any],
    *,
    contract_matrix: Mapping[str, Any],
    fault_matrix: Mapping[str, Any],
    receipt_ledger: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
    independent_review: Mapping[str, Any],
    project_root: Path | str,
) -> None:
    """Reject stale, tampered, blocked, or execution-claiming P134 evidence."""

    value = _mapping(evidence, "release_evidence")
    _expect_exact_fields(value, _RELEASE_FIELDS, "release_evidence")
    if value.get("schema_version") != P134_RELEASE_SCHEMA_VERSION:
        raise P134ReleaseEvidenceError("invalid_release_schema")
    _validate_self_hash(value, "release_evidence_hash", "release_evidence_hash_invalid")
    if value.get("product_claim") != PRODUCT_CLAIM or value.get("public_limitation") != PUBLIC_LIMITATION:
        raise P134ReleaseEvidenceError("release_claim_mismatch")
    gates = _mapping(value.get("gates"), "gates")
    if not gates or not all(item is True for item in gates.values()):
        raise P134ReleaseEvidenceError("release_gate_failed")
    if value.get("release_status") != P134_READY_STATUS:
        raise P134ReleaseEvidenceError("release_status_blocked")
    current = current_source_hashes(project_root)
    if dict(_mapping(value.get("source_bindings"), "source_bindings")) != current:
        raise P134ReleaseEvidenceError("release_evidence_source_stale")
    _validate_contract_matrix(contract_matrix)
    _validate_fault_matrix(fault_matrix)
    contract = _mapping(contract_matrix.get("canonical_contract"), "canonical_contract")
    validate_receipt_ledger(receipt_ledger, contract=contract)
    validate_authority_ledger(authority_ledger)
    validate_independent_review_artifact(independent_review, expected_source_hashes=current)
    rebuilt = build_p134_release_evidence(
        contract_matrix,
        fault_matrix,
        receipt_ledger,
        authority_ledger,
        independent_review,
        project_root=project_root,
    )
    if dict(value) != rebuilt:
        raise P134ReleaseEvidenceError("release_evidence_semantic_mismatch")


def current_source_hashes(project_root: Path | str) -> dict[str, str]:
    root = Path(project_root).expanduser().resolve()
    bindings: dict[str, str] = {}
    for relative in sorted(EXPECTED_SOURCE_BINDINGS):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise P134ReleaseEvidenceError(f"source_binding_missing:{relative}")
        bindings[relative] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    return bindings


def _contract_matrix_substantive(matrix: Mapping[str, Any]) -> bool:
    try:
        _validate_contract_matrix(matrix)
    except (P134ReleaseEvidenceError, ValueError):
        return False
    return True


def _validate_contract_matrix(matrix: Mapping[str, Any]) -> None:
    value = _mapping(matrix, "contract_matrix")
    _expect_exact_fields(value, _CONTRACT_MATRIX_FIELDS, "contract_matrix")
    if value.get("schema_version") != "p134.contract_matrix.v1":
        raise P134ReleaseEvidenceError("invalid_contract_matrix_schema")
    _validate_self_hash(value, "contract_matrix_hash", "contract_matrix_hash_invalid")
    if value.get("required_cases") != list(REQUIRED_CONTRACT_CASES):
        raise P134ReleaseEvidenceError("contract_matrix_required_cases_invalid")
    cases = _mapping(value.get("cases"), "contract_cases")
    if set(cases) != set(REQUIRED_CONTRACT_CASES):
        raise P134ReleaseEvidenceError("contract_matrix_case_set_invalid")
    for name in REQUIRED_CONTRACT_CASES:
        case = _validated_case(cases.get(name))
        if name == "oa1_allowed":
            if case["outcome"] != "allowed" or case["decision"] != "allowed" or case["reasons"]:
                raise P134ReleaseEvidenceError(f"contract_case_invalid:{name}")
        elif name == "deterministic_duplicate":
            if not (
                case["outcome"] == "duplicate"
                and case["decision"] == "allowed"
                and case["duplicate"] is True
                and case["ledger_unchanged"] is True
            ):
                raise P134ReleaseEvidenceError(f"contract_case_invalid:{name}")
        else:
            expected_reason = EXPECTED_DENIAL_REASONS[name]
            if case["outcome"] != "denied" or case["decision"] != "denied" or expected_reason not in case["reasons"]:
                raise P134ReleaseEvidenceError(f"contract_case_invalid:{name}")
    expected_totals = {
        "expected_cases": 18,
        "passed_cases": 18,
        "failed_cases": 0,
        "allowed_cases": 1,
        "denied_cases": 16,
        "duplicate_cases": 1,
        "denominator_scope": "principal_contract_assertions",
    }
    if dict(_mapping(value.get("totals"), "contract_totals")) != expected_totals:
        raise P134ReleaseEvidenceError("contract_matrix_totals_invalid")
    validate_contract(_mapping(value.get("canonical_contract"), "canonical_contract"))
    if not _resource_usage_valid(value):
        raise P134ReleaseEvidenceError("resource_usage_invalid")


def _fault_matrix_substantive(matrix: Mapping[str, Any]) -> bool:
    try:
        _validate_fault_matrix(matrix)
    except P134ReleaseEvidenceError:
        return False
    return True


def _validate_fault_matrix(matrix: Mapping[str, Any]) -> None:
    value = _mapping(matrix, "fault_matrix")
    _expect_exact_fields(value, _FAULT_MATRIX_FIELDS, "fault_matrix")
    if value.get("schema_version") != "p134.fault_matrix.v1":
        raise P134ReleaseEvidenceError("invalid_fault_matrix_schema")
    _validate_self_hash(value, "fault_matrix_hash", "fault_matrix_hash_invalid")
    if value.get("required_cases") != list(REQUIRED_FAULT_CASES):
        raise P134ReleaseEvidenceError("fault_matrix_required_cases_invalid")
    cases = _mapping(value.get("cases"), "fault_cases")
    if set(cases) != set(REQUIRED_FAULT_CASES):
        raise P134ReleaseEvidenceError("fault_matrix_case_set_invalid")
    for name in REQUIRED_FAULT_CASES:
        case = _validated_case(cases.get(name))
        if not (
            case["outcome"] == "rejected"
            and case["decision"] is None
            and case["ledger_unchanged"] is True
            and case["error"] == EXPECTED_FAULT_ERRORS[name]
        ):
            raise P134ReleaseEvidenceError(f"fault_case_invalid:{name}")
    expected_totals = {
        "expected_cases": 6,
        "passed_cases": 6,
        "failed_cases": 0,
        "rejected_cases": 6,
        "denominator_scope": "principal_fault_assertions",
    }
    if dict(_mapping(value.get("totals"), "fault_totals")) != expected_totals:
        raise P134ReleaseEvidenceError("fault_matrix_totals_invalid")


def _validated_case(value: Any) -> Mapping[str, Any]:
    case = _mapping(value, "case")
    expected = frozenset(
        {"passed", "outcome", "decision", "reasons", "duplicate", "ledger_unchanged", "error", "case_hash"}
    )
    _expect_exact_fields(case, expected, "case")
    _validate_self_hash(case, "case_hash", "case_hash_invalid")
    if case.get("passed") is not True:
        raise P134ReleaseEvidenceError("case_not_passed")
    if type(case.get("duplicate")) is not bool or type(case.get("ledger_unchanged")) is not bool:
        raise P134ReleaseEvidenceError("case_boolean_invalid")
    reasons = case.get("reasons")
    if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
        raise P134ReleaseEvidenceError("case_reasons_invalid")
    return case


def _receipt_ledger_semantic(ledger: Mapping[str, Any], matrix: Mapping[str, Any]) -> bool:
    try:
        validate_receipt_ledger(ledger, contract=_mapping(matrix.get("canonical_contract"), "canonical_contract"))
    except (ValueError, P134ReleaseEvidenceError):
        return False
    return True


def _valid_authority_ledger(ledger: Mapping[str, Any]) -> bool:
    try:
        validate_authority_ledger(ledger)
    except P134ReleaseEvidenceError:
        return False
    return True


def _valid_independent_review(review: Mapping[str, Any], source_bindings: Mapping[str, str]) -> bool:
    try:
        validate_independent_review_artifact(review, expected_source_hashes=source_bindings)
    except P134ReleaseEvidenceError:
        return False
    return True


def _resource_usage_valid(matrix: Mapping[str, Any]) -> bool:
    try:
        usage = _mapping(matrix.get("resource_usage"), "resource_usage")
        _expect_exact_fields(usage, _RESOURCE_USAGE_FIELDS, "resource_usage")
        expected_limits = {
            "wall_limit_ms": 20_000,
            "cpu_limit_ms": 10_000,
            "peak_memory_limit_bytes": 67_108_864,
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
    except (P134ReleaseEvidenceError, KeyError):
        return False


def _principal_denominator_exact(contract_matrix: Mapping[str, Any], fault_matrix: Mapping[str, Any]) -> bool:
    return _passed_case_count(contract_matrix) == 18 and _passed_case_count(fault_matrix) == 6


def _passed_case_count(matrix: Mapping[str, Any]) -> int:
    try:
        cases = _mapping(matrix.get("cases"), "cases")
    except P134ReleaseEvidenceError:
        return 0
    return sum(1 for case in cases.values() if isinstance(case, Mapping) and case.get("passed") is True)


def _exact_counter_mapping(
    value: Any,
    keys: tuple[str, ...],
    *,
    zero: bool,
    error: str = "invalid_counter_mapping",
) -> dict[str, int]:
    mapping = _mapping(value, "counter_mapping")
    if set(mapping) != set(keys):
        raise P134ReleaseEvidenceError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = mapping[key]
        if type(item) is not int or item < 0 or (zero and item != 0):
            raise P134ReleaseEvidenceError(error)
        result[key] = item
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P134ReleaseEvidenceError(f"invalid_{label}")
    return value


def _expect_exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = {str(key) for key in value}
    if actual != expected:
        raise P134ReleaseEvidenceError(f"invalid_{label}_fields")


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise P134ReleaseEvidenceError(f"invalid_{label}")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise P134ReleaseEvidenceError(f"invalid_{label}") from exc
    return value


def _validate_self_hash(value: Mapping[str, Any], field: str, error: str) -> None:
    claimed = _require_hash(value.get(field), field)
    unsigned = {key: item for key, item in value.items() if key != field}
    if claimed != stable_hash(unsigned):
        raise P134ReleaseEvidenceError(error)


__all__ = [
    "AUTHORITY_LEDGER_SCHEMA_VERSION",
    "EXPECTED_SOURCE_BINDINGS",
    "INDEPENDENT_REVIEW_SCHEMA_VERSION",
    "P134ReleaseEvidenceError",
    "P134_BLOCKED_STATUS",
    "P134_READY_STATUS",
    "PRODUCT_CLAIM",
    "PUBLIC_LIMITATION",
    "REQUIRED_CONTRACT_CASES",
    "REQUIRED_FAULT_CASES",
    "build_authority_ledger",
    "build_independent_review_artifact",
    "build_p134_release_evidence",
    "current_source_hashes",
    "validate_authority_ledger",
    "validate_independent_review_artifact",
    "validate_p134_release_evidence",
]
