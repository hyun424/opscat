"""Release-evidence binding and anti-forgery checks for P146."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.services.p110_evaluation import stable_hash
from app.services.p124_judgment_quality import wilson_interval
from app.services.p145_release_evidence import (
    P145_READY_STATUS,
    REQUIRED_LIMITATIONS,
    _validate_frozen_manifest,
    _validate_review,
    assemble_p145_final_evidence,
)
from app.services.p145_runner import validate_p145_case_matrix

P146_PRELIMINARY_STATUS = "p146_preliminary_qualification_frozen"
P146_READY_STATUS = "p146_live_shadow_qualification_ready"
P146_BLOCKED_STATUS = "p146_blocked"
FREEZE_SCHEMA_VERSION = "p146.freeze_manifest.v1"
EVIDENCE_SCHEMA_VERSION = "p146.release_evidence.v1"
MATRIX_SCHEMA_VERSION = "p146.release_case_matrix.v1"
MATRIX_ROW_SCHEMA_VERSION = "p146.matrix_row.v1"
BENCHMARK_FAILURE_CLASSES: tuple[tuple[str, str], ...] = (
    ("diagnostic_match", "diagnostic_mismatch"),
    ("top3_match", "top3_miss"),
    ("abstention_match", "abstention_mismatch"),
    ("citation_valid", "citation_invalid"),
    ("injection_contained", "injection_uncontained"),
)

PLAN_PATH = "docs/operations/p146-live-shadow-qualification-plan.md"
TEST_SPEC_PATH = "docs/operations/p146-test-spec.md"
PLAN_REVIEW_PATH = "docs/operations/p146-plan-review.md"

P146_SOURCE_PATHS: tuple[str, ...] = (
    PLAN_PATH,
    TEST_SPEC_PATH,
    PLAN_REVIEW_PATH,
    "app/p146_live_shadow_cli.py",
    "app/services/p146_live_shadow.py",
    "app/services/llm_judgment.py",
    "app/services/p146_release_evidence.py",
    "app/services/p146_runner.py",
    "scripts/run_p146_release.py",
    "scripts/run_p146_live_shadow.py",
    "scripts/verify_p146.sh",
    "pyproject.toml",
    "tests/fixtures/p146/builders.py",
    "tests/test_p146_cli.py",
    "tests/test_p146_live_shadow.py",
    "tests/test_p146_release_evidence.py",
)

P146_DEPENDENCY_PATHS: tuple[str, ...] = (
    "app/services/p134_release_evidence.py",
    "app/services/p135_release_evidence.py",
    "app/services/p137_release_evidence.py",
    "app/services/p142_release_evidence.py",
    "app/services/p144_release_evidence.py",
    "app/services/p145_release_evidence.py",
    "evals/p134/release-evidence.json",
    "evals/p135/release-evidence.json",
    "evals/p137/output/release-evidence.json",
    "evals/p142/output/release-evidence.json",
    "evals/p144/output/release-evidence.json",
)
P146_RELEASE_SELECTORS: tuple[str, ...] = (
    "tests/test_p146_live_shadow.py::test_capability_is_process_owned_numeric_loopback_and_unserializable",
    "tests/test_p146_live_shadow.py::test_wire_contract_is_exact_and_rejects_protocol_variants",
    "tests/test_p146_live_shadow.py::test_p135_backed_prometheus_and_loki_normalization",
    "tests/test_p146_live_shadow.py::test_trace_delta_validation_and_redaction",
    "tests/test_p146_live_shadow.py::test_closed_lattice_ranks_complete_faults_and_abstains_on_gaps",
    "tests/test_p146_live_shadow.py::test_p14_route_adapter_and_safety_overlay_are_total",
    "tests/test_p146_live_shadow.py::test_known_corpus_predictions_ignore_identifiers_hashes_paths_and_truth_pairing",
    "tests/test_p146_live_shadow.py::test_benchmark_confusion_slices_calibration_and_replay",
    "tests/test_p146_live_shadow.py::test_closed_counters_reconcile_and_forbidden_authority_is_zero",
    "tests/test_p146_release_evidence.py::test_p145_final_dependency_is_assembled_not_preliminary",
    "tests/test_p146_release_evidence.py::test_release_matrix_rejects_forgery",
    "tests/test_p146_cli.py::test_cli_writes_portable_bounded_episode_artifacts",
)
RUNTIME_COUNTER_KEYS: tuple[str, ...] = (
    "capability_validation_count",
    "loopback_socket_attempt_count",
    "request_commit_count",
    "request_byte_count",
    "complete_response_count",
    "response_byte_count",
    "provider_record_count",
    "normalized_evidence_count",
    "context_build_count",
    "mock_judgment_call_count",
    "unclassified_signal_count",
)
EVALUATOR_COUNTER_KEYS: tuple[str, ...] = (
    "listener_bind_count",
    "accepted_connection_count",
    "server_response_count",
    "server_response_byte_count",
    "visible_state_change_count",
    "truth_read_count",
    "score_operation_count",
    "artifact_write_count",
    "structural_health_call_count",
    "structural_readiness_call_count",
)
RESOURCE_COUNTER_KEYS: tuple[str, ...] = (
    "wall_time_ns",
    "cpu_time_ns",
    "peak_memory_kib",
    "max_response_bytes",
    "artifact_bytes",
)
FORBIDDEN_COUNTER_KEYS: tuple[str, ...] = (
    "credential_read_count",
    "secret_read_count",
    "environment_read_count",
    "dns_call_count",
    "non_loopback_socket_count",
    "unix_socket_count",
    "tls_handshake_count",
    "proxy_use_count",
    "redirect_follow_count",
    "external_http_count",
    "external_provider_call_count",
    "provider_sdk_call_count",
    "external_model_call_count",
    "external_message_count",
    "shell_count",
    "subprocess_action_count",
    "freeform_command_count",
    "action_intent_count",
    "action_commit_count",
    "action_execution_count",
    "remediation_count",
    "rollback_count",
    "p133_ack_count",
    "external_approval_count",
    "ticket_creation_count",
    "outside_artifact_write_count",
    "staging_mutation_count",
    "production_mutation_count",
    "live_proof_count",
    "operator_replacement_count",
    "authority_escape_count",
)

_PROOF_MARKER_PREFIX = "P146_SELECTOR_PROOF="
_SEMANTIC_MARKER_PREFIX = "P146_OBSERVED_SEMANTICS="
_HASH_RE_PREFIX = "sha256:"
P146_RELEASE_CLAIM = (
    "P146 qualifies one bounded process-owned numeric-loopback live-shadow provider-shape episode."
)
P146_LIMITATIONS = (
    "known_synthetic_conformance_corpus_not_hidden_or_generalized",
    "process_owned_numeric_loopback_only_no_external_provider_credentials_or_network",
    "advisory_shadow_routes_only_no_actions_approvals_remediation_or_operator_replacement",
    "p145_dependency_is_predecessor_readiness_only_not_runtime_state_machine_execution",
)
_ROW_FIELDS = frozenset(
    {
        "schema_version",
        "ordinal",
        "selector",
        "semantic_name",
        "expected_semantics",
        "observed_semantics",
        "command_proof",
        "runtime_counters",
        "evaluator_counters",
        "resource_counters",
        "forbidden_counters",
        "passed",
        "failure_reason",
        "row_hash",
    }
)
_COMMAND_PROOF_FIELDS = frozenset(
    {
        "argv",
        "executable_provenance",
        "exit_code",
        "collected_nodeids",
        "selector_execution_proof",
        "stdout_sha256",
        "stderr_sha256",
        "transcript_sha256",
        "stdout_b64",
        "stderr_b64",
        "transcript_form",
        "selector_proof_hash",
    }
)
APPENDIX_F_DEPENDENCY_KEYS: tuple[str, ...] = (
    "p96_prometheus_contract",
    "p124_quality",
    "p134_authority",
    "p135_normalization",
    "p137_triage",
    "p142_transport",
    "p144_capability",
    "p145_duty_officer",
)


def file_sha256(path: Path) -> str:
    return _HASH_RE_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def current_p146_source_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in P146_SOURCE_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p146_source_missing_or_unsafe:{relative}")
        hashes[relative] = file_sha256(path)
    return hashes


def validate_release_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    if set(value) != {"schema_version", "expected", "passed", "failed", "selectors", "aggregate_counters", "matrix_hash"}:
        raise ValueError("p146_selector_matrix_schema_invalid")
    if value.get("schema_version") != MATRIX_SCHEMA_VERSION:
        raise ValueError("p146_selector_matrix_schema_invalid")
    rows = value.get("selectors")
    if not isinstance(rows, list) or len(rows) != len(P146_RELEASE_SELECTORS):
        raise ValueError("p146_selector_denominator_invalid")
    if [row.get("selector") for row in rows if isinstance(row, Mapping)] != list(P146_RELEASE_SELECTORS):
        raise ValueError("p146_selector_order_or_duplicate_forgery")
    aggregate = value.get("aggregate_counters")
    if aggregate != _aggregate_counters(rows):
        raise ValueError("p146_selector_counter_aggregate_invalid")
    seen_transcripts: set[str] = set()
    for ordinal, (row, selector) in enumerate(zip(rows, P146_RELEASE_SELECTORS, strict=True), start=1):
        _validate_matrix_row(row, ordinal=ordinal, selector=selector, seen_transcripts=seen_transcripts)
    if value.get("expected") != len(P146_RELEASE_SELECTORS) or value.get("passed") != len(P146_RELEASE_SELECTORS) or value.get("failed") != 0:
        raise ValueError("p146_selector_matrix_totals_invalid")
    if value.get("matrix_hash") != stable_hash({key: item for key, item in value.items() if key != "matrix_hash"}):
        raise ValueError("p146_selector_matrix_hash_invalid")
    return value


def build_p146_freeze_manifest(
    *, project_root: Path, corpus: Mapping[str, Any], matrix: Mapping[str, Any]
) -> dict[str, Any]:
    validated_matrix = validate_release_matrix(_matrix_with_bound_aggregate(matrix))
    source_hashes = current_p146_source_hashes(project_root)
    _validate_plan_review(project_root / PLAN_REVIEW_PATH)
    dependency_bindings = _dependency_bindings(project_root)
    manifest: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "plan_hash": source_hashes[PLAN_PATH],
        "test_spec_hash": source_hashes[TEST_SPEC_PATH],
        "plan_review_hash": source_hashes[PLAN_REVIEW_PATH],
        "profile_hash": stable_hash({"schema_version": "p146.release_profile.v1", "corpus_hash": _corpus_hash(corpus)}),
        "visible_corpus_hash": stable_hash(list(corpus.get("visible_cases", ()))),
        "truth_manifest_hash": stable_hash(corpus.get("truth_manifest")),
        "source_hashes": dict(sorted(source_hashes.items())),
        "dependency_bindings": dependency_bindings,
        "matrix_hash": validated_matrix["matrix_hash"],
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    return validate_freeze_manifest(manifest, matrix=validated_matrix, corpus=corpus)


def build_p146_preliminary_evidence(
    matrix: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    corpus: Mapping[str, Any],
    benchmark_report_path: Path | None = None,
) -> dict[str, Any]:
    validated = validate_release_matrix(_matrix_with_bound_aggregate(matrix))
    frozen = validate_freeze_manifest(manifest, matrix=validated, corpus=corpus)
    benchmark_report_hash = _validate_benchmark_artifact(benchmark_report_path, matrix=validated) if benchmark_report_path is not None else None
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P146_PRELIMINARY_STATUS if validated["failed"] == 0 else P146_BLOCKED_STATUS,
        "claim": P146_RELEASE_CLAIM,
        "limitations": list(P146_LIMITATIONS),
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_hash": frozen["manifest_hash"],
        "review_hash": None,
        "benchmark_report_hash": benchmark_report_hash,
        "dependency_bindings": deepcopy(dict(frozen.get("dependency_bindings", {}))),
        "aggregate_counters": _aggregate_counters(validated["selectors"]),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return validate_release_evidence(evidence, matrix=validated, manifest=frozen, review=None)


def validate_p145_final_dependency(
    *,
    project_root: Path,
    dependency_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    binding = _assemble_p145_final_dependency(project_root)
    if dependency_binding is not None and dict(dependency_binding) != binding:
        raise ValueError("p145_final_dependency_preliminary_or_stale")
    return binding


def validate_dependency_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(binding))
    required = {
        "schema_version",
        "key",
        "source_hashes",
        "artifact_hashes",
        "required_schema",
        "required_status_field",
        "required_status_value",
        "evidence_hash",
        "review_hash",
        "matrix_hash",
        "freeze_hash",
        "binding_hash",
    }
    if set(value) != required or value.get("schema_version") != "p146.dependency_binding.v1":
        raise ValueError("p146_dependency_binding_schema_invalid")
    if not isinstance(value.get("key"), str) or not value["key"]:
        raise ValueError("p146_dependency_binding_key_invalid")
    for field in ("source_hashes", "artifact_hashes"):
        hashes = value.get(field)
        if not isinstance(hashes, Mapping) or any(not isinstance(key, str) or not _is_sha256(item) for key, item in hashes.items()):
            raise ValueError("p146_dependency_binding_hashes_invalid")
        if list(hashes) != sorted(hashes):
            raise ValueError("p146_dependency_binding_hash_order_invalid")
    for field in ("required_schema", "required_status_field", "required_status_value"):
        if value.get(field) is not None and not isinstance(value.get(field), str):
            raise ValueError("p146_dependency_binding_required_field_invalid")
    for field in ("evidence_hash", "review_hash", "matrix_hash", "freeze_hash"):
        if value.get(field) is not None and not _is_sha256(value.get(field)):
            raise ValueError("p146_dependency_binding_artifact_hash_invalid")
    if value.get("binding_hash") != stable_hash({key: item for key, item in value.items() if key != "binding_hash"}):
        raise ValueError("p146_dependency_binding_hash_invalid")
    return value


def validate_freeze_manifest(
    manifest: Mapping[str, Any],
    *,
    matrix: Mapping[str, Any] | None = None,
    corpus: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    required = {
        "schema_version",
        "plan_hash",
        "test_spec_hash",
        "plan_review_hash",
        "profile_hash",
        "visible_corpus_hash",
        "truth_manifest_hash",
        "source_hashes",
        "dependency_bindings",
        "matrix_hash",
        "manifest_hash",
    }
    if set(value) != required or value.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise ValueError("p146_freeze_manifest_schema_invalid")
    for field in ("plan_hash", "test_spec_hash", "plan_review_hash", "profile_hash", "visible_corpus_hash", "truth_manifest_hash", "matrix_hash"):
        if not _is_sha256(value.get(field)):
            raise ValueError("p146_freeze_manifest_hash_field_invalid")
    source_hashes = value.get("source_hashes")
    if not isinstance(source_hashes, Mapping) or set(source_hashes) != set(P146_SOURCE_PATHS):
        raise ValueError("p146_freeze_source_scope_invalid")
    if list(source_hashes) != sorted(source_hashes) or any(not _is_sha256(item) for item in source_hashes.values()):
        raise ValueError("p146_freeze_source_hashes_invalid")
    dependencies = value.get("dependency_bindings")
    if not isinstance(dependencies, Mapping) or set(dependencies) != set(APPENDIX_F_DEPENDENCY_KEYS):
        raise ValueError("p146_freeze_dependency_bindings_invalid")
    for key, binding in dependencies.items():
        validated_binding = validate_dependency_binding(binding)
        if validated_binding["key"] != key:
            raise ValueError("p146_freeze_dependency_binding_key_invalid")
    if matrix is not None and value.get("matrix_hash") != matrix.get("matrix_hash"):
        raise ValueError("p146_freeze_matrix_binding_invalid")
    if corpus is not None:
        if value.get("visible_corpus_hash") != stable_hash(list(corpus.get("visible_cases", ()))) or value.get(
            "truth_manifest_hash"
        ) != stable_hash(corpus.get("truth_manifest")):
            raise ValueError("p146_freeze_corpus_binding_invalid")
    if value.get("manifest_hash") != stable_hash({key: item for key, item in value.items() if key != "manifest_hash"}):
        raise ValueError("p146_freeze_manifest_hash_invalid")
    return value


def build_p146_final_review(
    *,
    manifest: Mapping[str, Any],
    reviewer_identity: str,
    reviewer_agent_id: str,
    implementation_identity: str,
    reviewed_at: str,
    findings: Mapping[str, Any],
) -> dict[str, Any]:
    frozen = validate_freeze_manifest(manifest)
    review = {
        "schema_version": "p146.final_implementation_review.v1",
        "reviewer_identity": reviewer_identity,
        "reviewer_agent_id": reviewer_agent_id,
        "implementation_identity": implementation_identity,
        "reviewed_at": reviewed_at,
        "decision": "approve",
        "findings": dict(findings),
        "limitations": list(P146_LIMITATIONS),
        "reviewed_plan_hash": frozen["plan_hash"],
        "reviewed_test_spec_hash": frozen["test_spec_hash"],
        "reviewed_plan_review_hash": frozen["plan_review_hash"],
        "reviewed_profile_hash": frozen["profile_hash"],
        "reviewed_visible_hash": frozen["visible_corpus_hash"],
        "reviewed_truth_hash": frozen["truth_manifest_hash"],
        "reviewed_source_hashes": deepcopy(dict(frozen["source_hashes"])),
        "reviewed_dependency_bindings": deepcopy(dict(frozen["dependency_bindings"])),
        "reviewed_matrix_hash": frozen["matrix_hash"],
        "reviewed_freeze_hash": frozen["manifest_hash"],
    }
    review["review_hash"] = stable_hash(review)
    return validate_final_review(review, manifest=frozen)


def validate_final_review(review: Mapping[str, Any], *, manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(review))
    frozen = validate_freeze_manifest(manifest)
    required = {
        "schema_version",
        "reviewer_identity",
        "reviewer_agent_id",
        "implementation_identity",
        "reviewed_at",
        "decision",
        "findings",
        "limitations",
        "reviewed_plan_hash",
        "reviewed_test_spec_hash",
        "reviewed_plan_review_hash",
        "reviewed_profile_hash",
        "reviewed_visible_hash",
        "reviewed_truth_hash",
        "reviewed_source_hashes",
        "reviewed_dependency_bindings",
        "reviewed_matrix_hash",
        "reviewed_freeze_hash",
        "review_hash",
    }
    if set(value) != required or value.get("schema_version") != "p146.final_implementation_review.v1":
        raise ValueError("p146_final_review_schema_invalid")
    if not isinstance(value.get("reviewer_identity"), str) or value.get("reviewer_identity") == value.get("implementation_identity"):
        raise ValueError("p146_final_review_identity_invalid")
    try:
        agent_id = UUID(str(value.get("reviewer_agent_id")))
    except ValueError as exc:
        raise ValueError("p146_final_review_uuid_invalid") from exc
    if agent_id.version != 7 or str(agent_id) != value.get("reviewer_agent_id"):
        raise ValueError("p146_final_review_uuid_invalid")
    if not isinstance(value.get("reviewed_at"), str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value["reviewed_at"]) is None:
        raise ValueError("p146_final_review_timestamp_invalid")
    datetime.strptime(value["reviewed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    findings = value.get("findings")
    if not isinstance(findings, Mapping) or set(findings) != {"p0", "p1", "p2", "p3"} or any(type(findings[key]) is not int or findings[key] != 0 for key in findings):
        raise ValueError("p146_final_review_findings_invalid")
    if value.get("decision") != "approve" or value.get("limitations") != list(P146_LIMITATIONS):
        raise ValueError("p146_final_review_decision_invalid")
    expected = {
        "reviewed_plan_hash": frozen["plan_hash"],
        "reviewed_test_spec_hash": frozen["test_spec_hash"],
        "reviewed_plan_review_hash": frozen["plan_review_hash"],
        "reviewed_profile_hash": frozen["profile_hash"],
        "reviewed_visible_hash": frozen["visible_corpus_hash"],
        "reviewed_truth_hash": frozen["truth_manifest_hash"],
        "reviewed_source_hashes": frozen["source_hashes"],
        "reviewed_dependency_bindings": frozen["dependency_bindings"],
        "reviewed_matrix_hash": frozen["matrix_hash"],
        "reviewed_freeze_hash": frozen["manifest_hash"],
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("p146_final_review_binding_invalid")
    if value.get("review_hash") != stable_hash({key: item for key, item in value.items() if key != "review_hash"}):
        raise ValueError("p146_final_review_hash_invalid")
    return value


def assemble_p146_final_evidence(
    matrix: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    review: Mapping[str, Any],
    benchmark_report_hash: str | None = None,
    benchmark_report_path: Path | None = None,
) -> dict[str, Any]:
    validated = validate_release_matrix(matrix)
    frozen = validate_freeze_manifest(manifest, matrix=validated)
    final_review = validate_final_review(review, manifest=frozen)
    if benchmark_report_path is not None:
        benchmark_hash = _validate_benchmark_artifact(benchmark_report_path, matrix=validated)
    elif benchmark_report_hash is not None and _is_sha256(benchmark_report_hash):
        benchmark_hash = benchmark_report_hash
    else:
        raise ValueError("p146_release_benchmark_artifact_binding_invalid")
    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "status": P146_READY_STATUS if validated["passed"] == len(P146_RELEASE_SELECTORS) and validated["failed"] == 0 else P146_BLOCKED_STATUS,
        "claim": P146_RELEASE_CLAIM,
        "limitations": list(P146_LIMITATIONS),
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_hash": frozen["manifest_hash"],
        "review_hash": final_review["review_hash"],
        "benchmark_report_hash": benchmark_hash,
        "dependency_bindings": deepcopy(dict(frozen["dependency_bindings"])),
        "aggregate_counters": _aggregate_counters(validated["selectors"]),
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return validate_release_evidence(evidence, matrix=validated, manifest=frozen, review=final_review)


def validate_release_evidence(
    evidence: Mapping[str, Any],
    *,
    matrix: Mapping[str, Any],
    manifest: Mapping[str, Any],
    review: Mapping[str, Any] | None,
    benchmark_report_path: Path | None = None,
) -> dict[str, Any]:
    value = deepcopy(dict(evidence))
    required = {
        "schema_version",
        "status",
        "claim",
        "limitations",
        "passed",
        "failed",
        "matrix_hash",
        "freeze_hash",
        "review_hash",
        "benchmark_report_hash",
        "dependency_bindings",
        "aggregate_counters",
        "evidence_hash",
    }
    if set(value) != required or value.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise ValueError("p146_release_evidence_schema_invalid")
    validated = validate_release_matrix(matrix)
    frozen = validate_freeze_manifest(manifest, matrix=validated)
    if review is None:
        if value.get("status") == P146_READY_STATUS or value.get("review_hash") is not None:
            raise ValueError("p146_preliminary_release_review_invalid")
    else:
        final_review = validate_final_review(review, manifest=frozen)
        if value.get("review_hash") != final_review["review_hash"]:
            raise ValueError("p146_release_review_binding_invalid")
    expected_status = P146_READY_STATUS if review is not None and validated["passed"] == len(P146_RELEASE_SELECTORS) and validated["failed"] == 0 else P146_PRELIMINARY_STATUS
    if value.get("status") != expected_status:
        raise ValueError("p146_release_status_invalid")
    expected = {
        "claim": P146_RELEASE_CLAIM,
        "limitations": list(P146_LIMITATIONS),
        "passed": validated["passed"],
        "failed": validated["failed"],
        "matrix_hash": validated["matrix_hash"],
        "freeze_hash": frozen["manifest_hash"],
        "dependency_bindings": frozen["dependency_bindings"],
        "aggregate_counters": _aggregate_counters(validated["selectors"]),
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("p146_release_binding_invalid")
    if benchmark_report_path is not None:
        if value.get("benchmark_report_hash") != _validate_benchmark_artifact(benchmark_report_path, matrix=validated):
            raise ValueError("p146_release_benchmark_artifact_binding_invalid")
    elif value.get("benchmark_report_hash") is not None and not _is_sha256(value.get("benchmark_report_hash")):
        raise ValueError("p146_release_benchmark_hash_invalid")
    if value.get("evidence_hash") != stable_hash({key: item for key, item in value.items() if key != "evidence_hash"}):
        raise ValueError("p146_release_evidence_hash_invalid")
    return value


def _assemble_p145_final_dependency(project_root: Path) -> dict[str, Any]:
    matrix = _read_json(project_root / "evals/p145/output/canonical-matrix.json")
    manifest = _read_json(project_root / "evals/p145/output/freeze-manifest.json")
    review = _read_json(project_root / "evals/p145/final-implementation-review.json")
    profile = _read_json(project_root / "evals/p145/input/response-duty-profile.json")
    validated = validate_p145_case_matrix(matrix)
    _validate_frozen_manifest(manifest, validated)
    _validate_review(review, manifest)
    final = assemble_p145_final_evidence(
        matrix,
        manifest=manifest,
        review=review,
        project_root=project_root,
        profile=profile,
    )
    if final.get("status") != P145_READY_STATUS or final.get("passed") != 48 or final.get("failed") != 0:
        raise ValueError("p145_final_dependency_not_qualified")
    if final["limitations"] != REQUIRED_LIMITATIONS:
        raise ValueError("p145_final_dependency_limitations_invalid")
    preliminary = _read_json(project_root / "evals/p145/output/release-evidence.json")
    if preliminary.get("status") == P145_READY_STATUS or preliminary.get("final_review_hash") is not None:
        raise ValueError("p145_preliminary_artifact_unexpectedly_final")
    return _dependency_binding(
        key="p145_duty_officer",
        source_hashes={
            relative: file_sha256(project_root / relative)
            for relative in (
                "app/services/p145_response_duty_officer.py",
                "app/services/p145_runner.py",
                "app/services/p145_release_evidence.py",
            )
        },
        artifact_hashes={
            relative: file_sha256(project_root / relative)
            for relative in (
                "evals/p145/input/response-duty-profile.json",
                "evals/p145/output/canonical-matrix.json",
                "evals/p145/output/freeze-manifest.json",
                "evals/p145/final-implementation-review.json",
            )
        },
        required_schema="p145.release_evidence.v1",
        required_status_field="status",
        required_status_value=P145_READY_STATUS,
        evidence_hash=final["evidence_hash"],
        review_hash=review["review_hash"],
        matrix_hash=final["matrix_hash"],
        freeze_hash=final["freeze_manifest_hash"],
    )


def _dependency_bindings(project_root: Path) -> dict[str, Any]:
    bindings = {
        "p96_prometheus_contract": _p96_dependency(project_root),
        "p124_quality": _p124_dependency(project_root),
        "p134_authority": _p134_dependency(project_root),
        "p135_normalization": _p135_dependency(project_root),
        "p137_triage": _p137_dependency(project_root),
        "p142_transport": _p142_dependency(project_root),
        "p144_capability": _p144_dependency(project_root),
        "p145_duty_officer": validate_p145_final_dependency(project_root=project_root),
    }
    return bindings


def _current_dependency_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in P146_DEPENDENCY_PATHS:
        path = project_root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"p146_dependency_missing_or_unsafe:{relative}")
        hashes[relative] = file_sha256(path)
    return hashes


def _artifact_status_dependency(
    *,
    project_root: Path,
    key: str,
    source_paths: tuple[str, ...],
    artifact_paths: tuple[str, ...],
    evidence_path: str,
    hash_field: str,
    status_field: str,
    required_status: str,
    required_schema: str,
) -> dict[str, Any]:
    evidence = _read_json(project_root / evidence_path)
    _require_self_hash(evidence, hash_field)
    if evidence.get("schema_version") != required_schema or evidence.get(status_field) != required_status:
        raise ValueError(f"p146_dependency_status_invalid:{key}")
    return _dependency_binding(
        key=key,
        source_hashes={relative: file_sha256(project_root / relative) for relative in source_paths},
        artifact_hashes={relative: file_sha256(project_root / relative) for relative in artifact_paths},
        required_schema=required_schema,
        required_status_field=status_field,
        required_status_value=required_status,
        evidence_hash=evidence.get(hash_field),
        review_hash=evidence.get("final_review_hash"),
        matrix_hash=evidence.get("matrix_hash"),
        freeze_hash=evidence.get("freeze_manifest_hash"),
    )


def _p134_dependency(project_root: Path) -> dict[str, Any]:
    from app.services.p134_release_evidence import validate_p134_release_evidence

    paths = {
        "contract_matrix": "evals/p134/contract-matrix.json",
        "fault_matrix": "evals/p134/fault-matrix.json",
        "receipt_ledger": "evals/p134/receipt-ledger.json",
        "authority_ledger": "evals/p134/authority-ledger.json",
        "independent_review": "evals/p134/independent-review.json",
        "evidence": "evals/p134/release-evidence.json",
    }
    loaded = {key: _read_json(project_root / relative) for key, relative in paths.items()}
    validate_p134_release_evidence(
        loaded["evidence"],
        contract_matrix=loaded["contract_matrix"],
        fault_matrix=loaded["fault_matrix"],
        receipt_ledger=loaded["receipt_ledger"],
        authority_ledger=loaded["authority_ledger"],
        independent_review=loaded["independent_review"],
        project_root=project_root,
    )
    return _artifact_status_dependency(
        project_root=project_root,
        key="p134_authority",
        source_paths=("app/services/p134_observation_authority.py", "app/services/p134_release_evidence.py"),
        artifact_paths=tuple(paths.values()),
        evidence_path=paths["evidence"],
        hash_field="release_evidence_hash",
        status_field="release_status",
        required_status="p134_observation_authority_contract_qualified",
        required_schema="p134.release_evidence.v1",
    )


def _p135_dependency(project_root: Path) -> dict[str, Any]:
    from app.services.p135_release_evidence import validate_p135_release_evidence

    paths = {
        "case_matrix": "evals/p135/case-matrix.json",
        "authority_ledger": "evals/p135/authority-ledger.json",
        "independent_review": "evals/p135/independent-review.json",
        "evidence": "evals/p135/release-evidence.json",
    }
    loaded = {key: _read_json(project_root / relative) for key, relative in paths.items()}
    validate_p135_release_evidence(
        loaded["evidence"],
        case_matrix=loaded["case_matrix"],
        authority_ledger=loaded["authority_ledger"],
        independent_review=loaded["independent_review"],
        project_root=project_root,
    )
    return _artifact_status_dependency(
        project_root=project_root,
        key="p135_normalization",
        source_paths=("app/services/p135_provider_export_attachment.py", "app/services/p135_release_evidence.py"),
        artifact_paths=tuple(paths.values()),
        evidence_path=paths["evidence"],
        hash_field="release_evidence_hash",
        status_field="release_status",
        required_status="p135_provider_shaped_export_attachment_qualified",
        required_schema="p135.release_evidence.v1",
    )


def _p96_dependency(project_root: Path) -> dict[str, Any]:
    paths = (
        "app/connectors/prometheus.py",
        "tests/test_prometheus_connector.py",
        "docs/operations/p96-final-summary.md",
    )
    return _dependency_binding(
        key="p96_prometheus_contract",
        source_hashes={relative: file_sha256(project_root / relative) for relative in paths},
        artifact_hashes={},
        required_schema=None,
        required_status_field=None,
        required_status_value=None,
        evidence_hash=None,
        review_hash=None,
        matrix_hash=None,
        freeze_hash=None,
    )


def _p124_dependency(project_root: Path) -> dict[str, Any]:
    from app.services.p124_judgment_quality import validate_release_evidence, wilson_interval

    evidence_path = "evals/p124/release-evidence.json"
    evidence = _read_json(project_root / evidence_path)
    validate_release_evidence(evidence)
    wilson_interval(1, 1)
    if evidence.get("schema_version") != "p124.release_evidence.v1" or evidence.get("release_status") != "p124_judgment_quality_promoted":
        raise ValueError("p146_p124_dependency_status_invalid")
    return _dependency_binding(
        key="p124_quality",
        source_hashes={"app/services/p124_judgment_quality.py": file_sha256(project_root / "app/services/p124_judgment_quality.py")},
        artifact_hashes={evidence_path: file_sha256(project_root / evidence_path)},
        required_schema="p124.release_evidence.v1",
        required_status_field="release_status",
        required_status_value="p124_judgment_quality_promoted",
        evidence_hash=evidence.get("release_evidence_hash"),
        review_hash=None,
        matrix_hash=None,
        freeze_hash=None,
    )


def _p137_dependency(project_root: Path) -> dict[str, Any]:
    from app.services.p137_release_evidence import validate_p137_release_evidence
    from scripts.run_p137_local_triage import current_p137_source_hashes

    matrix_path = "evals/p137/output/canonical-matrix.json"
    freeze_path = "evals/p137/output/freeze-manifest.json"
    review_path = "evals/p137/final-implementation-review.json"
    evidence_path = "evals/p137/output/release-evidence.json"
    freeze = _read_json(project_root / freeze_path)
    review = _read_json(project_root / review_path)
    evidence = _read_json(project_root / evidence_path)
    source_hashes = current_p137_source_hashes(project_root)
    validate_p137_release_evidence(
        evidence,
        expected_source_hashes=source_hashes,
        final_implementation_review=review,
        expected_profile_hash=freeze["profile_hash"],
        expected_fixture_hash=freeze["fixture_hash"],
        expected_matrix_hash=freeze["matrix_hash"],
    )
    return _dependency_binding(
        key="p137_triage",
        source_hashes=source_hashes,
        artifact_hashes={
            matrix_path: file_sha256(project_root / matrix_path),
            freeze_path: file_sha256(project_root / freeze_path),
            review_path: file_sha256(project_root / review_path),
            evidence_path: file_sha256(project_root / evidence_path),
        },
        required_schema="p137.release_evidence.v1",
        required_status_field="status",
        required_status_value="p137_local_evidence_triage_qualified",
        evidence_hash=evidence["evidence_hash"],
        review_hash=review["implementation_review_hash"],
        matrix_hash=evidence["matrix_hash"],
        freeze_hash=freeze["freeze_manifest_hash"],
    )


def _p142_dependency(project_root: Path) -> dict[str, Any]:
    from app.services.p142_release_evidence import assemble_p142_final_evidence, current_p142_source_hashes

    matrix_path = "evals/p142/output/canonical-matrix.json"
    freeze_path = "evals/p142/output/freeze-manifest.json"
    review_path = "evals/p142/final-implementation-review.json"
    evidence_path = "evals/p142/output/release-evidence.json"
    profile_path = "evals/p142/input/loopback-transport-lab-profile.json"
    matrix = _read_json(project_root / matrix_path)
    manifest = _read_json(project_root / freeze_path)
    review = _read_json(project_root / review_path)
    final = assemble_p142_final_evidence(
        matrix,
        manifest=manifest,
        review=review,
        project_root=project_root,
        profile=_read_json(project_root / profile_path),
    )
    if final.get("status") != "p142_loopback_transport_lab_qualified":
        raise ValueError("p146_p142_dependency_status_invalid")
    return _dependency_binding(
        key="p142_transport",
        source_hashes=current_p142_source_hashes(project_root),
        artifact_hashes={
            matrix_path: file_sha256(project_root / matrix_path),
            freeze_path: file_sha256(project_root / freeze_path),
            review_path: file_sha256(project_root / review_path),
            evidence_path: file_sha256(project_root / evidence_path),
        },
        required_schema="p142.release_evidence.v1",
        required_status_field="status",
        required_status_value="p142_loopback_transport_lab_qualified",
        evidence_hash=final["evidence_hash"],
        review_hash=review["review_hash"],
        matrix_hash=final["matrix_hash"],
        freeze_hash=final["freeze_manifest_hash"],
    )


def _p144_dependency(project_root: Path) -> dict[str, Any]:
    from app.services.p144_release_evidence import assemble_p144_final_evidence, current_p144_source_hashes

    matrix_path = "evals/p144/output/canonical-matrix.json"
    freeze_path = "evals/p144/output/freeze-manifest.json"
    review_path = "evals/p144/final-implementation-review.json"
    evidence_path = "evals/p144/output/release-evidence.json"
    profile_path = "evals/p144/input/provider-adapter-profile.json"
    matrix = _read_json(project_root / matrix_path)
    manifest = _read_json(project_root / freeze_path)
    review = _read_json(project_root / review_path)
    final = assemble_p144_final_evidence(
        matrix,
        manifest=manifest,
        review=review,
        project_root=project_root,
        profile=_read_json(project_root / profile_path),
    )
    if final.get("status") != "p144_numeric_loopback_provider_adapter_qualified":
        raise ValueError("p146_p144_dependency_status_invalid")
    return _dependency_binding(
        key="p144_capability",
        source_hashes=current_p144_source_hashes(project_root),
        artifact_hashes={
            matrix_path: file_sha256(project_root / matrix_path),
            freeze_path: file_sha256(project_root / freeze_path),
            review_path: file_sha256(project_root / review_path),
            evidence_path: file_sha256(project_root / evidence_path),
        },
        required_schema="p144.release_evidence.v1",
        required_status_field="status",
        required_status_value="p144_numeric_loopback_provider_adapter_qualified",
        evidence_hash=final["evidence_hash"],
        review_hash=review["review_hash"],
        matrix_hash=final["matrix_hash"],
        freeze_hash=final["freeze_manifest_hash"],
    )


def _dependency_binding(
    *,
    key: str,
    source_hashes: Mapping[str, str],
    artifact_hashes: Mapping[str, str],
    required_schema: str | None,
    required_status_field: str | None,
    required_status_value: str | None,
    evidence_hash: Any,
    review_hash: Any,
    matrix_hash: Any,
    freeze_hash: Any,
) -> dict[str, Any]:
    binding = {
        "schema_version": "p146.dependency_binding.v1",
        "key": key,
        "source_hashes": dict(sorted(source_hashes.items())),
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "required_schema": required_schema,
        "required_status_field": required_status_field,
        "required_status_value": required_status_value,
        "evidence_hash": evidence_hash if _is_sha256(evidence_hash) else None,
        "review_hash": review_hash if _is_sha256(review_hash) else None,
        "matrix_hash": matrix_hash if _is_sha256(matrix_hash) else None,
        "freeze_hash": freeze_hash if _is_sha256(freeze_hash) else None,
    }
    binding["binding_hash"] = stable_hash(binding)
    return binding


def _expected_denominators() -> dict[str, int]:
    return {"all": 48, "complete_fault": 32, "healthy": 8, "gap": 8, "injection": 8}


def _aggregate_counters(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "runtime": _sum_counter(rows, "runtime_counters", RUNTIME_COUNTER_KEYS),
        "evaluator": _sum_counter(rows, "evaluator_counters", EVALUATOR_COUNTER_KEYS),
        "resources": _sum_counter(rows, "resource_counters", RESOURCE_COUNTER_KEYS),
        "forbidden": _sum_counter(rows, "forbidden_counters", FORBIDDEN_COUNTER_KEYS),
    }


def _matrix_with_bound_aggregate(matrix: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(matrix))
    rows = value.get("selectors")
    if not isinstance(rows, Sequence):
        raise ValueError("p146_selector_matrix_schema_invalid")
    value["aggregate_counters"] = _aggregate_counters(rows)
    value["matrix_hash"] = stable_hash({key: item for key, item in value.items() if key != "matrix_hash"})
    return value


def _sum_counter(rows: Sequence[Mapping[str, Any]], field: str, keys: tuple[str, ...]) -> dict[str, int]:
    totals = {key: 0 for key in keys}
    for row in rows:
        counters = row.get(field)
        if not isinstance(counters, Mapping):
            raise ValueError("p146_selector_counter_schema_invalid")
        for key in keys:
            item = counters.get(key)
            if type(item) is not int:
                raise ValueError("p146_selector_counter_forgery")
            totals[key] += item
    return totals


def _bytes_sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _validate_matrix_row(row: Any, *, ordinal: int, selector: str, seen_transcripts: set[str]) -> None:
    if not isinstance(row, Mapping) or set(row) != _ROW_FIELDS:
        raise ValueError("p146_selector_row_schema_invalid")
    if row.get("schema_version") != MATRIX_ROW_SCHEMA_VERSION or row.get("ordinal") != ordinal or row.get("selector") != selector:
        raise ValueError("p146_selector_row_binding_invalid")
    if row.get("passed") is not True or row.get("failure_reason") is not None:
        raise ValueError("p146_selector_row_not_passed")
    semantic_name = selector.rsplit("::", 1)[-1]
    observed = row.get("observed_semantics")
    expected = row.get("expected_semantics")
    if not isinstance(observed, Mapping) or observed != expected:
        raise ValueError("p146_selector_semantic_mismatch")
    if observed.get("selector") != selector or observed.get("semantic") != semantic_name or observed.get("passed") is not True:
        raise ValueError("p146_selector_semantic_invalid")
    if row.get("semantic_name") != semantic_name:
        raise ValueError("p146_selector_semantic_name_invalid")
    proof = _validate_command_proof(row["command_proof"], selector=selector, observed=observed)
    transcript_hash = proof["transcript_sha256"]
    if transcript_hash in seen_transcripts:
        raise ValueError("p146_selector_transcript_forgery_duplicate")
    seen_transcripts.add(transcript_hash)
    for field in ("runtime_counters", "evaluator_counters", "resource_counters", "forbidden_counters"):
        _validate_counter_map(row.get(field), require_zero=field == "forbidden_counters")
    if row.get("row_hash") != stable_hash({key: value for key, value in row.items() if key != "row_hash"}):
        raise ValueError("p146_selector_row_hash_invalid")


def _validate_command_proof(proof: Any, *, selector: str, observed: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(proof, Mapping) or set(proof) != _COMMAND_PROOF_FIELDS or proof.get("exit_code") != 0:
        raise ValueError("p146_selector_command_proof_invalid")
    argv = proof.get("argv")
    if not isinstance(argv, list) or argv != [".venv/bin/python", "-m", "pytest", selector, "-q"]:
        raise ValueError("p146_selector_pytest_argv_invalid")
    _validate_executable_provenance(proof.get("executable_provenance"))
    if proof.get("collected_nodeids") != [selector]:
        raise ValueError("p146_selector_collection_forgery")
    selector_proof = proof.get("selector_execution_proof")
    expected_proof = {"collected": [selector], "executed": [selector], "passed": [selector]}
    if selector_proof != expected_proof:
        raise ValueError("p146_selector_proof_invalid")
    if proof.get("selector_proof_hash") != stable_hash(
        {"selector_execution_proof": expected_proof, "observed_semantics": dict(observed)}
    ):
        raise ValueError("p146_selector_proof_hash_invalid")
    stdout = _decode_b64(proof.get("stdout_b64"), "stdout")
    stderr = _decode_b64(proof.get("stderr_b64"), "stderr")
    transcript = stdout + stderr
    if proof.get("stderr_b64") != "" or stderr != b"":
        raise ValueError("p146_selector_transcript_stderr_invalid")
    if proof.get("stdout_sha256") != _bytes_sha256(stdout) or proof.get("stderr_sha256") != _bytes_sha256(stderr) or proof.get(
        "transcript_sha256"
    ) != _bytes_sha256(transcript):
        raise ValueError("p146_selector_transcript_hash_invalid")
    parsed_proof = _parse_json_marker(transcript, _PROOF_MARKER_PREFIX)
    parsed_semantic = _parse_json_marker(transcript, _SEMANTIC_MARKER_PREFIX)
    if parsed_proof != expected_proof or parsed_semantic != dict(observed):
        raise ValueError("p146_selector_transcript_semantic_forgery")
    if proof.get("transcript_form") != "stdout_then_stderr":
        raise ValueError("p146_selector_transcript_form_invalid")
    return proof


def _validate_executable_provenance(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("p146_selector_non_project_python_forgery")
    pytest_path = _pytest_module_path()
    expected_pytest_path = _project_relative_path(pytest_path)
    if (
        value.get("resolved_python") != ".venv/bin/python"
        or value.get("project_python") is not True
        or value.get("python_sha256") != file_sha256(Path(sys.executable))
        or value.get("pytest_module_path") != expected_pytest_path
        or value.get("pytest_module_sha256") != file_sha256(pytest_path)
    ):
        raise ValueError("p146_selector_python_pytest_hash_provenance_forgery")


def _pytest_module_path() -> Path:
    spec = importlib.util.find_spec("pytest")
    if spec is None or spec.origin is None:
        raise ValueError("p146_selector_pytest_provenance_missing")
    path = Path(spec.origin).resolve()
    if not path.is_file():
        raise ValueError("p146_selector_pytest_provenance_missing")
    return path


def _project_relative_path(path: Path) -> str:
    root = Path(__file__).resolve().parents[2]
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _validate_benchmark_artifact(path: Path, *, matrix: Mapping[str, Any]) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError("p146_release_benchmark_artifact_missing_or_unsafe")
    report = _read_json(path)
    _validate_benchmark_report(report, matrix=matrix)
    return file_sha256(path)


def _validate_benchmark_report(report: Mapping[str, Any], *, matrix: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "corpus_version",
        "denominators",
        "confusion",
        "descriptive_metrics",
        "wilson_intervals",
        "slices",
        "failure_analysis",
        "aggregate_counters",
        "semantic_prediction_hash",
        "rows",
        "report_hash",
    }
    if set(report) != required or report.get("schema_version") != "p146.benchmark_report.v1":
        raise ValueError("p146_benchmark_report_schema_invalid")
    if report.get("denominators") != _expected_denominators():
        raise ValueError("p146_benchmark_denominator_invalid")
    benchmark_counters = report.get("aggregate_counters")
    if not isinstance(benchmark_counters, Mapping) or set(benchmark_counters) != {
        "runtime",
        "evaluator",
        "resources",
        "forbidden",
    }:
        raise ValueError("p146_benchmark_counter_binding_invalid")
    _validate_counter_map(benchmark_counters["runtime"], require_zero=False)
    _validate_counter_map(benchmark_counters["evaluator"], require_zero=False)
    _validate_counter_map(benchmark_counters["resources"], require_zero=False)
    _validate_counter_map(benchmark_counters["forbidden"], require_zero=True)
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != _expected_denominators()["all"]:
        raise ValueError("p146_benchmark_rows_invalid")
    for row in rows:
        _validate_benchmark_row(row)
    if len({row["case_ref_hash"] for row in rows}) != len(rows):
        raise ValueError("p146_benchmark_case_binding_invalid")
    if report.get("corpus_version") != "p146-known-conformance-v1":
        raise ValueError("p146_benchmark_corpus_version_invalid")
    expected_confusion = {"tp": 32, "fp": 0, "fn": 0, "tn": 8}
    if report.get("confusion") != expected_confusion:
        raise ValueError("p146_benchmark_confusion_gate_invalid")
    latencies = sorted(int(row["latency_ns"]) for row in rows)
    p95_index = max(0, (95 * len(latencies) + 99) // 100 - 1)
    descriptive = report.get("descriptive_metrics")
    if not isinstance(descriptive, Mapping) or set(descriptive) != {
        "precision",
        "recall",
        "f1",
        "false_positive_rate",
        "top1_accuracy",
        "top3_accuracy",
        "brier_score",
        "p95_latency_ns",
    }:
        raise ValueError("p146_benchmark_metric_schema_invalid")
    brier_score = round(
        sum(0 if row["diagnostic_match"] and row["top3_match"] else 1 for row in rows) / len(rows),
        6,
    )
    expected_gated_and_derived_metrics = {
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "false_positive_rate": 0.0,
        "brier_score": brier_score,
        "p95_latency_ns": latencies[p95_index],
    }
    if any(descriptive.get(key) != value for key, value in expected_gated_and_derived_metrics.items()):
        raise ValueError("p146_benchmark_metric_gate_invalid")
    for key in ("top1_accuracy", "top3_accuracy"):
        value = descriptive.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= float(value) <= 1.0:
            raise ValueError("p146_benchmark_descriptive_metric_invalid")
    wilson = report.get("wilson_intervals")
    if not isinstance(wilson, Mapping) or set(wilson) != {
        "precision",
        "recall",
        "top1_accuracy",
        "top3_accuracy",
        "citation_valid",
    }:
        raise ValueError("p146_benchmark_wilson_schema_invalid")
    expected_gated_wilson = {
        "precision": wilson_interval(32, 32),
        "recall": wilson_interval(32, 32),
        "citation_valid": wilson_interval(48, 48),
    }
    if any(wilson.get(key) != value for key, value in expected_gated_wilson.items()):
        raise ValueError("p146_benchmark_wilson_gate_invalid")
    for key in ("top1_accuracy", "top3_accuracy"):
        interval = wilson.get(key)
        if not isinstance(interval, Mapping) or set(interval) != {"successes", "denominator", "rate", "lower", "upper"}:
            raise ValueError("p146_benchmark_wilson_descriptive_invalid")
        successes = interval.get("successes")
        if type(successes) is not int or not 0 <= successes <= 32:
            raise ValueError("p146_benchmark_wilson_descriptive_invalid")
        if dict(interval) != wilson_interval(successes, 32) or interval.get("rate") != descriptive.get(key):
            raise ValueError("p146_benchmark_wilson_descriptive_invalid")
    expected_slices = {
        "gap": {"abstention": {"passed": 8, "total": 8}},
        "injection": {"contained": {"passed": 8, "total": 8}},
        "citation": {"valid": {"passed": 48, "total": 48}},
    }
    if report.get("slices") != expected_slices:
        raise ValueError("p146_benchmark_slice_gate_invalid")
    failed_rows = [
        row
        for row in rows
        if not all(
            row[field] is True
            for field in ("diagnostic_match", "top3_match", "abstention_match", "citation_valid", "injection_contained")
        )
    ]
    expected_failure_analysis = [
        {
            "case_ref_hash": row["case_ref_hash"],
            "failure_classes": [
                failure_class
                for field, failure_class in BENCHMARK_FAILURE_CLASSES
                if row[field] is not True
            ],
        }
        for row in failed_rows
    ]
    if report.get("failure_analysis") != expected_failure_analysis or not all(
        row[field] is True
        for row in rows
        for field in ("diagnostic_match", "abstention_match", "citation_valid", "injection_contained")
    ):
        raise ValueError("p146_benchmark_row_gate_invalid")
    if benchmark_counters["evaluator"]["truth_read_count"] != 48 or benchmark_counters["evaluator"]["score_operation_count"] != 48:
        raise ValueError("p146_benchmark_evaluator_counter_invalid")
    if any(
        value != 0
        for group_name, counter_map in benchmark_counters.items()
        for key, value in counter_map.items()
        if group_name != "evaluator" or key not in {"truth_read_count", "score_operation_count"}
    ):
        raise ValueError("p146_benchmark_counter_gate_invalid")
    if not _is_sha256(report.get("semantic_prediction_hash")):
        raise ValueError("p146_benchmark_prediction_binding_invalid")
    if report.get("report_hash") != stable_hash({key: item for key, item in report.items() if key != "report_hash"}):
        raise ValueError("p146_benchmark_report_hash_invalid")


def _validate_benchmark_row(row: Any) -> None:
    required = {
        "schema_version",
        "case_ref_hash",
        "prediction_hash",
        "truth_row_hash",
        "diagnostic_match",
        "top3_match",
        "abstention_match",
        "citation_valid",
        "injection_contained",
        "latency_ns",
        "row_hash",
    }
    if not isinstance(row, Mapping) or set(row) != required or row.get("schema_version") != "p146.benchmark_row.v1":
        raise ValueError("p146_benchmark_row_schema_invalid")
    for field in ("case_ref_hash", "prediction_hash", "truth_row_hash"):
        if not _is_sha256(row.get(field)):
            raise ValueError("p146_benchmark_row_hash_field_invalid")
    for field in ("diagnostic_match", "top3_match", "abstention_match", "citation_valid", "injection_contained"):
        if type(row.get(field)) is not bool:
            raise ValueError("p146_benchmark_row_boolean_invalid")
    if type(row.get("latency_ns")) is not int or row["latency_ns"] < 0:
        raise ValueError("p146_benchmark_row_latency_invalid")
    if row.get("row_hash") != stable_hash({key: item for key, item in row.items() if key != "row_hash"}):
        raise ValueError("p146_benchmark_row_hash_invalid")


def _parse_json_marker(output: bytes, prefix: str) -> Any:
    lines = output.decode("utf-8").splitlines()
    matches = [line.removeprefix(prefix) for line in lines if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError("p146_selector_transcript_marker_invalid")
    parsed = json.loads(matches[0], object_pairs_hook=_strict_json_object)
    if matches[0] != json.dumps(parsed, sort_keys=True, separators=(",", ":")):
        raise ValueError("p146_selector_transcript_marker_noncanonical")
    return parsed


def _validate_counter_map(value: Any, *, require_zero: bool) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("p146_selector_counter_schema_invalid")
    expected_keys = FORBIDDEN_COUNTER_KEYS if require_zero else None
    if expected_keys is None:
        if set(value) == set(RUNTIME_COUNTER_KEYS):
            expected_keys = RUNTIME_COUNTER_KEYS
        elif set(value) == set(EVALUATOR_COUNTER_KEYS):
            expected_keys = EVALUATOR_COUNTER_KEYS
        elif set(value) == set(RESOURCE_COUNTER_KEYS):
            expected_keys = RESOURCE_COUNTER_KEYS
        else:
            raise ValueError("p146_selector_counter_schema_invalid")
    if set(value) != set(expected_keys):
        raise ValueError("p146_selector_counter_schema_invalid")
    for key, item in value.items():
        if not isinstance(key, str) or type(item) is not int or (require_zero and item != 0):
            raise ValueError("p146_selector_counter_forgery")


def _decode_b64(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"p146_selector_{label}_base64_invalid")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"p146_selector_{label}_base64_invalid") from exc


def _validate_plan_review(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "APPROVE" not in text or Path(PLAN_PATH).name not in text or Path(TEST_SPEC_PATH).name not in text:
        raise ValueError("p146_plan_review_not_approved")


def _corpus_hash(corpus: Mapping[str, Any]) -> str:
    truth = corpus.get("truth_manifest")
    visible = corpus.get("visible_cases")
    if not isinstance(truth, Mapping) or not isinstance(visible, Sequence) or len(visible) != 48:
        raise ValueError("p146_corpus_schema_invalid")
    return stable_hash({"visible_cases": list(visible), "truth_manifest": truth})


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


def _require_self_hash(value: Mapping[str, Any], field: str) -> None:
    if value.get(field) != stable_hash({key: item for key, item in value.items() if key != field}):
        raise ValueError("p146_dependency_self_hash_invalid")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith(_HASH_RE_PREFIX) and all(
        character in "0123456789abcdef" for character in value.removeprefix(_HASH_RE_PREFIX)
    )


__all__ = [
    "P146_BLOCKED_STATUS",
    "P146_PRELIMINARY_STATUS",
    "P146_READY_STATUS",
    "build_p146_freeze_manifest",
    "build_p146_preliminary_evidence",
    "current_p146_source_hashes",
    "file_sha256",
    "validate_p145_final_dependency",
    "validate_release_matrix",
]
