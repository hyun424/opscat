"""Strict release-evidence validation for P136.

The validator is deliberately pure: it validates measured evidence but performs
no observation, provider, network, credential, command, or action work.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash

SCHEMA_VERSION = "p136.release_evidence.v1"
P136_READY_STATUS = "p136_incremental_local_observation_qualified"
REQUIRED_CASE_COUNT = 50
INDEPENDENT_REVIEW_SCHEMA_VERSION = "p136.independent_review.v1"
EXPECTED_SOURCE_BINDINGS = frozenset(
    {
        "README.md",
        "app/services/p120_governance.py",
        "app/services/p120_normalization.py",
        "app/services/p121_signals.py",
        "app/services/p134_observation_authority.py",
        "app/services/p135_provider_export_attachment.py",
        "app/services/p136_incremental_observer.py",
        "app/services/p136_release_evidence.py",
        "app/services/p136_runner.py",
        "docs/operations/p136-incremental-observer-roadmap.md",
        "docs/operations/p136-plan-review.md",
        "docs/operations/p136-test-spec.md",
        "evals/p136/input/incremental-observer-profile.json",
        "scripts/run_p136_incremental_observer.py",
        "scripts/verify.sh",
        "tests/fixtures/p136/builders.py",
        "tests/test_p136_incremental_observer.py",
        "tests/test_p136_release_evidence.py",
        "tests/test_p136_runner.py",
    }
)
CANONICAL_TICKET_ROOT = "docs/tickets/p136"
CANONICAL_PROVIDER_FIXTURES = frozenset(
    {
        "evals/p135/input/exports/grafana_dashboard.json",
        "evals/p135/input/exports/loki_streams.json",
        "evals/p135/input/exports/otlp_metrics.jsonl",
        "evals/p135/input/exports/prometheus_matrix.json",
        "evals/p135/input/exports/sentry_issues.json",
    }
)

FORBIDDEN_AUTHORITY_KEYS = (
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
RUNTIME_ACTIVITY_KEYS = (
    "index_stat_count",
    "index_file_open_count",
    "index_file_read_count",
    "index_bytes_read",
    "index_complete_lines_evaluated",
    "index_partial_bytes_observed",
    "index_read_intent_write_count",
    "segment_stat_count",
    "segment_file_open_count",
    "segment_file_read_count",
    "segment_bytes_read",
    "segment_records_parsed",
    "promotion_intent_write_count",
    "promotion_record_write_count",
    "checkpoint_write_count",
    "directory_fsync_count",
    "duplicate_resolution_count",
    "recovery_replay_count",
    "rotation_count",
    "rejection_record_count",
)
EVALUATOR_ACTIVITY_KEYS = (
    "runner_invocation_count",
    "profile_read_count",
    "artifact_write_count",
    "child_process_count",
    "signal_delivery_count",
)
RESOURCE_USAGE_KEYS = (
    "wall_time_ms",
    "cpu_time_ms",
    "child_cpu_time_ms",
    "peak_memory_bytes",
    "wall_limit_ms",
    "cpu_limit_ms",
    "peak_memory_limit_bytes",
)
_RELEASE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "cases",
        "totals",
        "provider_first_batch_promotions",
        "duplicate_promotions",
        "duplicate_segment_reads",
        "exact_schema_gates",
        "release_gates",
        "forbidden_authority",
        "runtime_activity",
        "evaluator_activity",
        "resource_usage",
        "source_bindings",
        "independent_review_hash",
        "evidence_hash",
    }
)
_CASE_REQUIRED_FIELDS = frozenset(
    {
        "case_id",
        "category",
        "semantic",
        "expected",
        "actual",
        "status",
        "duplicate_segment_reads",
        "duplicate_promotions",
        "provider_first_batch_promotion",
        "evidence",
        "case_evidence_hash",
    }
)
_TOTAL_FIELDS = frozenset({"expected", "passed", "failed"})
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
_REVIEW_LIMITATIONS = (
    "reviewer_identity_unauthenticated",
    "local_artifact_only_no_live_provider_claim",
    "no_action_authority",
)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_RE = re.compile(
    r"(?:bearer\s+|api[_-]?key|authorization|password|credential|secret[-_:])",
    re.IGNORECASE,
)


class P136ReleaseEvidenceError(ValueError):
    """Raised when P136 release evidence is malformed or optimistic."""


def validate_p136_release_evidence(
    evidence: Mapping[str, Any],
    *,
    expected_source_hashes: Mapping[str, str] | None = None,
    independent_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and return an isolated copy of one canonical P136 release."""

    if independent_review is None:
        raise P136ReleaseEvidenceError("independent_review_required")
    value = _mapping(evidence, "release_evidence")
    _expect_exact_fields(value, _RELEASE_FIELDS, "release_evidence")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise P136ReleaseEvidenceError("invalid_p136_release_schema")

    cases = _sequence(value.get("cases"), "cases")
    if len(cases) != REQUIRED_CASE_COUNT:
        raise P136ReleaseEvidenceError("p136_release_case_count_must_equal_50")
    if value.get("status") != P136_READY_STATUS:
        raise P136ReleaseEvidenceError("invalid_p136_release_status")

    _scan_leaks(value)
    passed = 0
    failed = 0
    provider_promotions = 0
    provider_promotion_case_ids: set[str] = set()
    duplicate_promotions = 0
    duplicate_segment_reads = 0
    seen_ids: set[str] = set()
    expected_ids = {f"p136-case-{index:02d}" for index in range(1, REQUIRED_CASE_COUNT + 1)}
    for raw_case in cases:
        case = _mapping(raw_case, "case")
        missing = _CASE_REQUIRED_FIELDS - set(case)
        if missing:
            raise P136ReleaseEvidenceError("missing_case_field")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in seen_ids:
            raise P136ReleaseEvidenceError("invalid_or_duplicate_case_id")
        seen_ids.add(case_id)
        if not isinstance(case.get("category"), str) or not case["category"]:
            raise P136ReleaseEvidenceError("invalid_case_category")
        if not isinstance(case.get("semantic"), str) or len(case["semantic"].strip()) < 8:
            raise P136ReleaseEvidenceError("invalid_case_semantic")
        if case.get("actual") != case.get("expected"):
            raise P136ReleaseEvidenceError("case_actual_expected_mismatch")
        status = case.get("status")
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        else:
            raise P136ReleaseEvidenceError("invalid_case_status")
        evidence_value = _mapping(case.get("evidence"), "case_evidence")
        measured_duplicate_segment_reads = _nonnegative_int(
            evidence_value.get("measured_duplicate_segment_reads"),
            "measured_duplicate_segment_reads",
        )
        measured_duplicate_promotions = _nonnegative_int(
            evidence_value.get("measured_duplicate_promotions"),
            "measured_duplicate_promotions",
        )
        if case.get("duplicate_segment_reads") != measured_duplicate_segment_reads:
            raise P136ReleaseEvidenceError("duplicate_segment_reads_must_be_zero")
        if case.get("duplicate_promotions") != measured_duplicate_promotions:
            raise P136ReleaseEvidenceError("duplicate_promotions_must_be_zero")
        duplicate_segment_reads += measured_duplicate_segment_reads
        duplicate_promotions += measured_duplicate_promotions
        promoted = case.get("provider_first_batch_promotion")
        if type(promoted) is not bool:
            raise P136ReleaseEvidenceError("invalid_provider_promotion_flag")
        provider_promotions += int(promoted)
        if promoted:
            provider_promotion_case_ids.add(case_id)
    if seen_ids != expected_ids:
        raise P136ReleaseEvidenceError("required_case_ids_mismatch")

    rebuilt = {"expected": REQUIRED_CASE_COUNT, "passed": passed, "failed": failed}
    totals = _mapping(value.get("totals"), "totals")
    _expect_exact_fields(totals, _TOTAL_FIELDS, "totals")
    if dict(totals) != rebuilt:
        raise P136ReleaseEvidenceError("rebuilt_totals_mismatch")
    if rebuilt != {"expected": 50, "passed": 50, "failed": 0}:
        raise P136ReleaseEvidenceError("release_cases_not_all_passed")
    if provider_promotions != 5 or value.get("provider_first_batch_promotions") != 5:
        raise P136ReleaseEvidenceError("provider_first_batch_promotion_count_mismatch")
    if provider_promotion_case_ids != {f"p136-case-{index:02d}" for index in range(1, 6)}:
        raise P136ReleaseEvidenceError("provider_first_batch_promotion_case_mismatch")
    if duplicate_segment_reads != 0 or value.get("duplicate_segment_reads") != 0:
        raise P136ReleaseEvidenceError("duplicate_segment_reads_must_be_zero")
    if duplicate_promotions != 0 or value.get("duplicate_promotions") != 0:
        raise P136ReleaseEvidenceError("duplicate_promotions_must_be_zero")
    for raw_case in cases:
        case = _mapping(raw_case, "case")
        case_hash = case.get("case_evidence_hash")
        if case_hash != stable_hash(
            {key: item for key, item in case.items() if key != "case_evidence_hash"}
        ):
            raise P136ReleaseEvidenceError("case_evidence_hash_invalid")
    if value.get("exact_schema_gates") is not True or value.get("release_gates") is not True:
        raise P136ReleaseEvidenceError("release_gate_not_satisfied")

    _exact_counters(
        value.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_forbidden_authority_schema",
        require_zero=True,
    )
    _exact_counters(
        value.get("runtime_activity"),
        RUNTIME_ACTIVITY_KEYS,
        "invalid_runtime_activity_schema",
    )
    _exact_counters(
        value.get("evaluator_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_evaluator_activity_schema",
    )
    resources = _exact_counters(
        value.get("resource_usage"), RESOURCE_USAGE_KEYS, "invalid_resource_usage_schema"
    )
    if resources["wall_limit_ms"] != 30_000:
        raise P136ReleaseEvidenceError("invalid_wall_time_limit")
    if resources["cpu_limit_ms"] != 15_000:
        raise P136ReleaseEvidenceError("invalid_cpu_time_limit")
    if resources["peak_memory_limit_bytes"] != 134_217_728:
        raise P136ReleaseEvidenceError("invalid_peak_memory_limit")
    if resources["wall_time_ms"] > resources["wall_limit_ms"]:
        raise P136ReleaseEvidenceError("wall_time_budget_exceeded")
    if resources["cpu_time_ms"] + resources["child_cpu_time_ms"] > resources["cpu_limit_ms"]:
        raise P136ReleaseEvidenceError("self_plus_child_cpu_budget_exceeded")
    if resources["peak_memory_bytes"] > resources["peak_memory_limit_bytes"]:
        raise P136ReleaseEvidenceError("peak_memory_budget_exceeded")

    source_bindings = _validate_source_bindings(value.get("source_bindings"))
    if expected_source_hashes is not None and source_bindings != dict(
        sorted(expected_source_hashes.items())
    ):
        raise P136ReleaseEvidenceError("release_evidence_source_stale")
    independent_review_hash = _require_hash(
        value.get("independent_review_hash"), "independent_review_hash"
    )
    validate_independent_review_artifact(
        independent_review,
        expected_source_hashes=source_bindings,
    )
    if independent_review_hash != independent_review.get("independent_review_hash"):
        raise P136ReleaseEvidenceError("independent_review_hash_mismatch")

    expected_hash = value.get("evidence_hash")
    if not isinstance(expected_hash, str) or not _HASH_RE.fullmatch(expected_hash):
        raise P136ReleaseEvidenceError("invalid_evidence_hash")
    payload = {key: item for key, item in value.items() if key != "evidence_hash"}
    if stable_hash(payload) != expected_hash:
        raise P136ReleaseEvidenceError("evidence_hash_invalid")
    return deepcopy(dict(value))


def build_independent_review_artifact(
    *,
    reviewed_source_hashes: Mapping[str, str],
    reviewer_context_hash: str,
    implementation_context_hash: str,
    findings: Mapping[str, Any],
    decision: str,
) -> dict[str, Any]:
    if decision not in {"approve", "request_changes"}:
        raise P136ReleaseEvidenceError("invalid_review_decision")
    review: dict[str, Any] = {
        "schema_version": INDEPENDENT_REVIEW_SCHEMA_VERSION,
        "reviewer_role": "independent_code_reviewer",
        "implementation_role": "implementation_agent",
        "reviewer_context_hash": _require_hash(
            reviewer_context_hash, "reviewer_context_hash"
        ),
        "implementation_context_hash": _require_hash(
            implementation_context_hash, "implementation_context_hash"
        ),
        "reviewed_source_hashes": _validate_source_bindings(reviewed_source_hashes),
        "findings": _review_findings(findings),
        "decision": decision,
        "limitations": list(_REVIEW_LIMITATIONS),
    }
    review["independent_review_hash"] = stable_hash(review)
    return review


def validate_independent_review_artifact(
    review: Mapping[str, Any],
    *,
    expected_source_hashes: Mapping[str, str],
) -> None:
    value = _mapping(review, "independent_review")
    _expect_exact_fields(value, _INDEPENDENT_REVIEW_FIELDS, "independent_review")
    if value.get("schema_version") != INDEPENDENT_REVIEW_SCHEMA_VERSION:
        raise P136ReleaseEvidenceError("invalid_independent_review_schema")
    if value.get("independent_review_hash") != stable_hash(
        {key: item for key, item in value.items() if key != "independent_review_hash"}
    ):
        raise P136ReleaseEvidenceError("independent_review_hash_invalid")
    if (
        value.get("reviewer_role") != "independent_code_reviewer"
        or value.get("implementation_role") != "implementation_agent"
    ):
        raise P136ReleaseEvidenceError("review_role_invalid")
    reviewer_context = _require_hash(value.get("reviewer_context_hash"), "reviewer_context_hash")
    implementation_context = _require_hash(
        value.get("implementation_context_hash"), "implementation_context_hash"
    )
    if reviewer_context == implementation_context:
        raise P136ReleaseEvidenceError("review_context_not_independent")
    reviewed = _validate_source_bindings(value.get("reviewed_source_hashes"))
    if reviewed != dict(sorted(expected_source_hashes.items())):
        raise P136ReleaseEvidenceError("review_source_binding_stale")
    findings = _review_findings(value.get("findings"))
    if any(findings[key] != 0 for key in ("p0", "p1", "p2")):
        raise P136ReleaseEvidenceError("review_blocking_findings")
    if value.get("decision") != "approve":
        raise P136ReleaseEvidenceError("review_not_approved")
    if value.get("limitations") != list(_REVIEW_LIMITATIONS):
        raise P136ReleaseEvidenceError("review_limitations_invalid")


def current_source_hashes(project_root: Path | str) -> dict[str, str]:
    root = Path(project_root).expanduser().resolve()
    recursive: set[str] = set()
    ticket_root = root / CANONICAL_TICKET_ROOT
    if not ticket_root.is_dir() or ticket_root.is_symlink():
        raise P136ReleaseEvidenceError("source_binding_missing:docs/tickets/p136")
    for path in ticket_root.rglob("*"):
        if path.is_symlink():
            raise P136ReleaseEvidenceError(
                f"source_binding_symlink:{path.relative_to(root).as_posix()}"
            )
        if path.is_file():
            recursive.add(path.relative_to(root).as_posix())
    expected = set(EXPECTED_SOURCE_BINDINGS) | set(CANONICAL_PROVIDER_FIXTURES) | recursive
    bindings: dict[str, str] = {}
    for relative in sorted(expected):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise P136ReleaseEvidenceError(f"source_binding_missing:{relative}")
        bindings[relative] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    return bindings


def _scan_leaks(value: Any, *, key: str = "") -> None:
    if key == "raw_provider_payload":
        raise P136ReleaseEvidenceError("raw_provider_payload_leak")
    if isinstance(value, Mapping):
        for item_key, item in value.items():
            if not isinstance(item_key, str):
                raise P136ReleaseEvidenceError("non_string_evidence_key")
            _scan_leaks(item, key=item_key)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _scan_leaks(item, key=key)
        return
    if isinstance(value, str):
        if value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value):
            raise P136ReleaseEvidenceError("absolute_path_leak")
        if _SECRET_RE.search(key) or _SECRET_RE.search(value):
            raise P136ReleaseEvidenceError("secret_value_leak")


def _validate_source_bindings(value: Any) -> dict[str, str]:
    bindings = _mapping(value, "source_bindings")
    if not bindings:
        raise P136ReleaseEvidenceError("source_bindings_empty")
    result: dict[str, str] = {}
    for relative, digest in sorted(bindings.items()):
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or Path(relative).is_absolute()
        ):
            raise P136ReleaseEvidenceError("invalid_source_binding_path")
        result[relative] = _require_hash(digest, "source_binding_hash")
    return result


def _review_findings(value: Any) -> dict[str, int]:
    findings = _mapping(value, "review_findings")
    if set(findings) != {"p0", "p1", "p2", "p3"}:
        raise P136ReleaseEvidenceError("invalid_review_findings")
    result: dict[str, int] = {}
    for key in ("p0", "p1", "p2", "p3"):
        item = findings.get(key)
        if type(item) is not int or item < 0:
            raise P136ReleaseEvidenceError("invalid_review_findings")
        result[key] = item
    return result


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P136ReleaseEvidenceError(f"invalid_{label}")
    return value


def _exact_counters(
    value: Any,
    keys: Sequence[str],
    error: str,
    *,
    require_zero: bool = False,
) -> dict[str, int]:
    counters = _mapping(value, "counters")
    if set(counters) != set(keys):
        raise P136ReleaseEvidenceError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = counters.get(key)
        if type(item) is not int or item < 0:
            raise P136ReleaseEvidenceError(error)
        if require_zero and item != 0:
            raise P136ReleaseEvidenceError("forbidden_authority_nonzero")
        result[key] = item
    return result


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise P136ReleaseEvidenceError(f"invalid_{label}")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P136ReleaseEvidenceError(f"invalid_{label}_shape")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P136ReleaseEvidenceError(f"invalid_{label}_shape")
    return list(value)


def _expect_exact_fields(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    if set(value) != fields:
        raise P136ReleaseEvidenceError(f"invalid_{label}_fields")
