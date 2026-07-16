"""Shared fail-closed evidence contracts for OpsCat P147 through P152."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HASH_PREFIX = "sha256:"
UUIDV7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

COUNTER_KEYS = (
    "read_attempt_count",
    "read_success_count",
    "model_call_count",
    "external_model_call_count",
    "investigation_tool_call_count",
    "action_intent_count",
    "action_commit_count",
    "action_execution_count",
    "rollback_count",
    "heartbeat_count",
    "deadman_count",
    "artifact_write_count",
    "credential_read_count",
    "external_network_count",
    "external_message_count",
    "shell_count",
    "staging_mutation_count",
    "production_mutation_count",
    "authority_escape_count",
)
CANONICAL_ZERO_KEYS = (
    "credential_read_count",
    "external_model_call_count",
    "external_network_count",
    "external_message_count",
    "shell_count",
    "staging_mutation_count",
    "production_mutation_count",
    "authority_escape_count",
)
REPORT_KEYS = frozenset(
    {
        "schema_version",
        "phase",
        "status",
        "claim",
        "limitations",
        "profile_hash",
        "predecessors",
        "source_hashes",
        "case_count",
        "passed",
        "failed",
        "metrics",
        "counters",
        "rows",
        "report_hash",
    }
)
ROW_KEYS = frozenset({"schema_version", "case_id", "expected", "observed", "passed", "failure_classes", "row_hash"})
RESULT_KEYS = frozenset({"schema_version", "outcome", "reason_codes", "measurements"})
PREDECESSOR_KEYS = frozenset({"phase", "path", "schema_version", "required_status", "file_hash", "evidence_hash"})
FREEZE_KEYS = frozenset(
    {
        "schema_version",
        "phase",
        "plan_hash",
        "test_spec_hash",
        "source_hashes",
        "profile_hash",
        "predecessor_file_hashes",
        "report_hash",
        "manifest_hash",
    }
)
REVIEW_KEYS = frozenset(
    {
        "schema_version",
        "phase",
        "writer_agent_id",
        "reviewer_identity",
        "reviewer_agent_id",
        "reviewed_at",
        "decision",
        "findings",
        "limitations",
        "reviewed_report_hash",
        "reviewed_manifest_hash",
        "review_hash",
    }
)
RELEASE_KEYS = frozenset(
    {
        "schema_version",
        "phase",
        "status",
        "claim",
        "limitations",
        "report_hash",
        "freeze_hash",
        "review_hash",
        "predecessors",
        "source_hashes",
        "metrics",
        "counters",
        "passed",
        "failed",
        "evidence_hash",
    }
)

PROGRAM_PLAN = "docs/operations/p147-p152-program-plan.md"
VERIFY_PATHS = ("scripts/verify_p147_p152.sh", "scripts/verify.sh")


class ContractError(ValueError):
    """Raised when phase evidence cannot prove its closed contract."""


@dataclass(frozen=True)
class PredecessorSpec:
    phase: str
    path: str
    schema_version: str
    status: str


@dataclass(frozen=True)
class PhaseContract:
    phase: str
    status: str
    claim: str
    limitations: tuple[str, ...]
    metric_keys: tuple[str, ...]
    measurement_keys: tuple[str, ...]
    predecessors: tuple[PredecessorSpec, ...]

    @property
    def report_schema(self) -> str:
        return f"{self.phase}.report.v1"

    @property
    def row_schema(self) -> str:
        return f"{self.phase}.row.v1"

    @property
    def result_schema(self) -> str:
        return f"{self.phase}.row_result.v1"

    @property
    def freeze_schema(self) -> str:
        return f"{self.phase}.freeze_manifest.v1"

    @property
    def review_schema(self) -> str:
        return f"{self.phase}.final_review.v1"

    @property
    def release_schema(self) -> str:
        return f"{self.phase}.release_evidence.v1"


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("canonical_json_invalid") from exc


def stable_hash(value: Any) -> str:
    return HASH_PREFIX + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ContractError(f"source_missing_or_unsafe:{path}")
    return HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def with_self_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result[field] = stable_hash({key: item for key, item in result.items() if key != field})
    return result


def validate_self_hash(value: Mapping[str, Any], field: str) -> None:
    if not _is_hash(value.get(field)):
        raise ContractError(f"{field}_invalid")
    expected = stable_hash({key: item for key, item in value.items() if key != field})
    if value[field] != expected:
        raise ContractError(f"{field}_canonical_self_hash_invalid")


def write_canonical_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(dict(value)) + b"\n"
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ContractError(f"artifact_missing_or_unsafe:{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"artifact_json_invalid:{path}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"artifact_object_required:{path}")
    return value


def empty_counters(**overrides: int) -> dict[str, int]:
    unknown = set(overrides) - set(COUNTER_KEYS)
    if unknown:
        raise ContractError(f"counter_unknown:{sorted(unknown)}")
    result = {key: 0 for key in COUNTER_KEYS}
    result.update(overrides)
    return validate_counters(result)


def validate_counters(counters: Mapping[str, Any]) -> dict[str, int]:
    if set(counters) != set(COUNTER_KEYS):
        raise ContractError("counter_keyset_invalid")
    result: dict[str, int] = {}
    for key in COUNTER_KEYS:
        value = counters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractError(f"counter_value_invalid:{key}")
        result[key] = value
    for key in CANONICAL_ZERO_KEYS:
        if result[key] != 0:
            raise ContractError(f"counter_must_be_zero:{key}")
    return result


def phase_source_paths(phase: str) -> tuple[str, ...]:
    if phase not in {f"p{number}" for number in range(147, 153)}:
        raise ContractError(f"phase_unsupported:{phase}")
    ticket_dir = f"docs/tickets/{phase}"
    suffixes = {
        "p147": ("P147-001-contract-red.md", "P147-002-durable-shadow.md", "P147-003-evidence-verification.md"),
        "p148": ("P148-001-contract-red.md", "P148-002-reversible-lab.md", "P148-003-evidence-verification.md"),
        "p149": ("P149-001-contract-red.md", "P149-002-canary-control.md", "P149-003-evidence-verification.md"),
        "p150": ("P150-001-contract-red.md", "P150-002-chaos-soak.md", "P150-003-evidence-verification.md"),
        "p151": ("P151-001-contract-red.md", "P151-002-quality-qualification.md", "P151-003-evidence-verification.md"),
        "p152": ("P152-001-contract-red.md", "P152-002-readiness-gate.md", "P152-003-final-verification.md"),
    }[phase]
    owned_modules = {
        "p147": "p147_durable_shadow",
        "p148": "p148_reversible_lab",
        "p149": "p149_canary_control",
        "p150": "p150_unattended_soak",
        "p151": "p151_ground_truth_quality",
        "p152": "p152_operator_readiness",
    }
    stem = owned_modules[phase]
    paths = (
        PROGRAM_PLAN,
        f"docs/operations/{phase}-test-spec.md",
        f"{ticket_dir}/README.md",
        *(f"{ticket_dir}/{suffix}" for suffix in suffixes),
        "app/services/p147_p152_contracts.py",
        f"app/services/{stem}.py",
        f"scripts/run_{phase}_qualification.py",
        f"tests/test_{stem}.py",
        *VERIFY_PATHS,
    )
    canonical_inputs = {
        "p149": ("evals/p149/input/canary-cases.json",),
        "p150": ("evals/p150/input/fast-schedule.json",),
        "p151": (
            "evals/p151/input/sealed-corpus.json",
            "evals/p151/input/prediction-packet.json",
            "evals/p151/input/prediction-commit.json",
        ),
        "p152": ("evals/p152/input/integration-cases.json",),
    }.get(phase, ())
    paths = (*paths, *canonical_inputs)
    return tuple(paths)


def current_source_hashes(project_root: Path, phase: str) -> dict[str, str]:
    return {relative: file_hash(project_root / relative) for relative in sorted(phase_source_paths(phase))}


def validate_predecessor_entry(entry: Mapping[str, Any], spec: PredecessorSpec) -> dict[str, Any]:
    value = deepcopy(dict(entry))
    if set(value) != PREDECESSOR_KEYS:
        raise ContractError(f"predecessor_field_keyset_invalid:{spec.phase}")
    expected = {
        "phase": spec.phase,
        "path": spec.path,
        "schema_version": spec.schema_version,
        "required_status": spec.status,
    }
    for key, required in expected.items():
        if value.get(key) != required:
            raise ContractError(f"predecessor_{key}_invalid:{spec.phase}")
    if not _is_hash(value.get("file_hash")) or not _is_hash(value.get("evidence_hash")):
        raise ContractError(f"predecessor_hash_invalid:{spec.phase}")
    return value


def validate_predecessors(entries: Sequence[Mapping[str, Any]], contract: PhaseContract) -> list[dict[str, Any]]:
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ContractError("predecessor_list_required")
    if len(entries) != len(contract.predecessors):
        raise ContractError(f"predecessor_count_invalid:{contract.phase}")
    result = [validate_predecessor_entry(entry, spec) for entry, spec in zip(entries, contract.predecessors, strict=True)]
    phases = [entry["phase"] for entry in result]
    if len(set(phases)) != len(phases):
        raise ContractError("predecessor_duplicate_or_order_invalid")
    return result


def predecessor_from_release_evidence(evidence: Mapping[str, Any], spec: PredecessorSpec) -> dict[str, Any]:
    value = deepcopy(dict(evidence))
    if value.get("schema_version") != spec.schema_version or value.get("phase") != spec.phase or value.get("status") != spec.status:
        raise ContractError(f"predecessor_release_status_or_schema_invalid:{spec.phase}")
    if spec.phase in {f"p{number}" for number in range(147, 153)}:
        _validate_exact_phase_release_evidence(value, spec)
    else:
        if not _is_hash(value.get("evidence_hash")):
            raise ContractError(f"predecessor_evidence_hash_invalid:{spec.phase}")
        validate_self_hash(value, "evidence_hash")
    return {
        "phase": spec.phase,
        "path": spec.path,
        "schema_version": spec.schema_version,
        "required_status": spec.status,
        "file_hash": value["evidence_hash"],
        "evidence_hash": value["evidence_hash"],
    }


def predecessor_from_path(project_root: Path, spec: PredecessorSpec) -> dict[str, Any]:
    path = project_root / spec.path
    evidence = load_json(path)
    phase_mismatch = spec.phase in {f"p{number}" for number in range(147, 153)} and evidence.get("phase") != spec.phase
    if phase_mismatch or evidence.get("schema_version") != spec.schema_version or evidence.get("status") != spec.status:
        raise ContractError(f"predecessor_file_schema_or_status_invalid:{spec.phase}")
    if not _is_hash(evidence.get("evidence_hash")):
        raise ContractError(f"predecessor_file_evidence_hash_invalid:{spec.phase}")
    validate_self_hash(evidence, "evidence_hash")
    if spec.phase == "p146":
        _validate_p146_release_evidence(project_root, evidence)
    elif spec.phase in {f"p{number}" for number in range(147, 153)}:
        _validate_exact_phase_release_evidence(evidence, spec, project_root=project_root)
        expected_sources = current_source_hashes(project_root, spec.phase)
        if evidence.get("source_hashes") != expected_sources:
            raise ContractError(f"predecessor_release_source_files_stale:{spec.phase}")
    return {
        "phase": spec.phase,
        "path": spec.path,
        "schema_version": spec.schema_version,
        "required_status": spec.status,
        "file_hash": file_hash(path),
        "evidence_hash": evidence["evidence_hash"],
    }


def build_result(schema: str, outcome: str, reason_codes: Sequence[str], measurements: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(outcome, str) or not outcome:
        raise ContractError("row_outcome_invalid")
    reasons = _sorted_unique_strings(reason_codes, field="reason_codes")
    return {"schema_version": schema, "outcome": outcome, "reason_codes": reasons, "measurements": deepcopy(dict(measurements))}


def build_row(
    *,
    contract: PhaseContract,
    case_id: str,
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    passed: bool,
    failure_classes: Sequence[str] = (),
) -> dict[str, Any]:
    row = {
        "schema_version": contract.row_schema,
        "case_id": case_id,
        "expected": deepcopy(dict(expected)),
        "observed": deepcopy(dict(observed)),
        "passed": passed,
        "failure_classes": _sorted_unique_strings(failure_classes, field="failure_classes"),
        "row_hash": "",
    }
    return validate_row(with_self_hash(row, "row_hash"), contract)


def validate_row(row: Mapping[str, Any], contract: PhaseContract) -> dict[str, Any]:
    value = deepcopy(dict(row))
    if set(value) != ROW_KEYS or value.get("schema_version") != contract.row_schema:
        raise ContractError(f"row_schema_invalid:{contract.phase}")
    if not isinstance(value.get("case_id"), str) or not value["case_id"]:
        raise ContractError("row_case_id_invalid")
    if not isinstance(value.get("passed"), bool):
        raise ContractError("row_passed_invalid")
    failures = _sorted_unique_strings(value.get("failure_classes"), field="failure_classes")
    if value["passed"] != (len(failures) == 0):
        raise ContractError("row_failure_class_consistency_invalid")
    value["failure_classes"] = failures
    value["expected"] = validate_result(value.get("expected"), contract)
    value["observed"] = validate_result(value.get("observed"), contract)
    validate_self_hash(value, "row_hash")
    return value


def validate_result(result: Any, contract: PhaseContract) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ContractError("row_result_object_required")
    value = deepcopy(dict(result))
    if set(value) != RESULT_KEYS or value.get("schema_version") != contract.result_schema:
        raise ContractError("row_result_schema_invalid")
    if not isinstance(value.get("outcome"), str) or not value["outcome"]:
        raise ContractError("row_result_outcome_invalid")
    value["reason_codes"] = _sorted_unique_strings(value.get("reason_codes"), field="reason_codes")
    measurements = value.get("measurements")
    if not isinstance(measurements, Mapping) or set(measurements) != set(contract.measurement_keys):
        raise ContractError(f"row_measurement_keyset_invalid:{contract.phase}")
    value["measurements"] = {key: deepcopy(measurements[key]) for key in contract.measurement_keys}
    return value


def build_report(
    *,
    contract: PhaseContract,
    profile: Mapping[str, Any],
    predecessors: Sequence[Mapping[str, Any]],
    source_hashes: Mapping[str, str],
    rows: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    counters: Mapping[str, Any],
) -> dict[str, Any]:
    validated_rows = [validate_row(row, contract) for row in rows]
    report: dict[str, Any] = {
        "schema_version": contract.report_schema,
        "phase": contract.phase,
        "status": contract.status,
        "claim": contract.claim,
        "limitations": list(contract.limitations),
        "profile_hash": stable_hash(profile),
        "predecessors": validate_predecessors(predecessors, contract),
        "source_hashes": dict(sorted(source_hashes.items())),
        "case_count": len(validated_rows),
        "passed": sum(1 for row in validated_rows if row["passed"]),
        "failed": sum(1 for row in validated_rows if not row["passed"]),
        "metrics": deepcopy(dict(metrics)),
        "counters": validate_counters(counters),
        "rows": validated_rows,
        "report_hash": "",
    }
    return validate_report(with_self_hash(report, "report_hash"), contract)


def validate_report(report: Mapping[str, Any], contract: PhaseContract) -> dict[str, Any]:
    value = deepcopy(dict(report))
    if set(value) != REPORT_KEYS:
        raise ContractError(f"report_keyset_invalid:{contract.phase}")
    if value.get("schema_version") != contract.report_schema or value.get("phase") != contract.phase:
        raise ContractError(f"report_schema_or_phase_invalid:{contract.phase}")
    if value.get("status") != contract.status or value.get("claim") != contract.claim:
        raise ContractError(f"report_status_or_claim_invalid:{contract.phase}")
    if value.get("limitations") != list(contract.limitations):
        raise ContractError(f"report_limitations_invalid:{contract.phase}")
    if not _is_hash(value.get("profile_hash")):
        raise ContractError("report_profile_hash_invalid")
    value["predecessors"] = validate_predecessors(value.get("predecessors", []), contract)
    value["source_hashes"] = _validate_hash_mapping(value.get("source_hashes"), field="source_hashes")
    if set(value["source_hashes"]) != set(phase_source_paths(contract.phase)):
        raise ContractError(f"report_source_hash_keyset_invalid:{contract.phase}")
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping) or set(metrics) != set(contract.metric_keys):
        raise ContractError(f"report_metric_keyset_invalid:{contract.phase}")
    value["metrics"] = {key: deepcopy(metrics[key]) for key in contract.metric_keys}
    value["counters"] = validate_counters(value.get("counters", {}))
    rows = value.get("rows")
    if not isinstance(rows, list):
        raise ContractError("report_rows_invalid")
    value["rows"] = [validate_row(row, contract) for row in rows]
    case_ids = [row["case_id"] for row in value["rows"]]
    if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        raise ContractError("report_row_order_or_duplicate_invalid")
    if value.get("case_count") != len(rows) or value.get("passed") != sum(1 for row in rows if row["passed"]) or value.get("failed") != sum(1 for row in rows if not row["passed"]):
        raise ContractError("report_denominator_invalid")
    validate_self_hash(value, "report_hash")
    return value


def validate_current_release_bindings(
    project_root: Path,
    report: Mapping[str, Any],
    contract: PhaseContract,
    *,
    require_companion_artifacts: bool = False,
) -> dict[str, Any]:
    """Revalidate report bindings against current source and predecessor files."""

    validated = _validate_exact_phase_report(report, contract)
    expected_sources = current_source_hashes(project_root, contract.phase)
    if validated["source_hashes"] != expected_sources:
        raise ContractError(f"current_release_source_hashes_stale:{contract.phase}")
    if require_companion_artifacts:
        for spec in contract.predecessors:
            if spec.phase in {f"p{number}" for number in range(147, 153)}:
                _validate_canonical_phase_artifact_set(project_root, spec)
    expected_predecessors = [predecessor_from_path(project_root, spec) for spec in contract.predecessors]
    if validated["predecessors"] != expected_predecessors:
        raise ContractError(f"current_release_predecessor_bindings_stale:{contract.phase}")
    return validated


def _validate_canonical_phase_artifact_set(project_root: Path, spec: PredecessorSpec) -> None:
    """Reopen a predecessor's report, freeze, review, and release as one set."""

    phase_root = project_root / "evals" / spec.phase
    report_path = phase_root / "output" / "report.json"
    freeze_path = phase_root / "output" / "freeze-manifest.json"
    review_path = phase_root / "final-implementation-review.json"
    release_path = project_root / spec.path
    module = importlib.import_module(f"app.services.{_phase_module_stem(spec.phase)}")
    phase_contract = getattr(module, f"{spec.phase.upper()}_CONTRACT")
    report_validator = getattr(module, f"validate_{spec.phase}_report")
    freeze_validator = getattr(module, f"validate_{spec.phase}_freeze_manifest")
    review_validator = getattr(module, f"validate_{spec.phase}_final_review")
    release_validator = getattr(module, f"validate_{spec.phase}_release_evidence")

    report = report_validator(load_json(report_path))
    validate_current_release_bindings(
        project_root,
        report,
        phase_contract,
        require_companion_artifacts=True,
    )
    freeze = freeze_validator(load_json(freeze_path))
    review = review_validator(load_json(review_path), report=report, freeze_manifest=freeze)
    release = (
        release_validator(load_json(release_path), project_root=project_root)
        if spec.phase == "p150"
        else release_validator(load_json(release_path))
    )
    expected_bindings = {
        "report_hash": report["report_hash"],
        "freeze_hash": freeze["manifest_hash"],
        "review_hash": review["review_hash"],
        "predecessors": report["predecessors"],
        "source_hashes": report["source_hashes"],
        "metrics": report["metrics"],
        "counters": report["counters"],
        "passed": report["passed"],
        "failed": report["failed"],
    }
    for field, expected in expected_bindings.items():
        if release.get(field) != expected:
            raise ContractError(f"predecessor_companion_artifact_binding_invalid:{spec.phase}:{field}")


def _validate_exact_phase_report(report: Mapping[str, Any], contract: PhaseContract) -> dict[str, Any]:
    module_name = f"app.services.{_phase_module_stem(contract.phase)}"
    module = importlib.import_module(module_name)
    validator = getattr(module, f"validate_{contract.phase}_report")
    return validator(report)


def build_freeze_manifest(*, project_root: Path, contract: PhaseContract, report: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_report(report, contract)
    source_hashes = current_source_hashes(project_root, contract.phase)
    if validated["source_hashes"] != source_hashes:
        raise ContractError("freeze_source_hashes_stale")
    manifest = {
        "schema_version": contract.freeze_schema,
        "phase": contract.phase,
        "plan_hash": source_hashes[PROGRAM_PLAN],
        "test_spec_hash": source_hashes[f"docs/operations/{contract.phase}-test-spec.md"],
        "source_hashes": source_hashes,
        "profile_hash": validated["profile_hash"],
        "predecessor_file_hashes": [entry["file_hash"] for entry in validated["predecessors"]],
        "report_hash": validated["report_hash"],
        "manifest_hash": "",
    }
    return validate_freeze_manifest(with_self_hash(manifest, "manifest_hash"), contract)


def validate_freeze_manifest(manifest: Mapping[str, Any], contract: PhaseContract) -> dict[str, Any]:
    value = deepcopy(dict(manifest))
    if set(value) != FREEZE_KEYS or value.get("schema_version") != contract.freeze_schema or value.get("phase") != contract.phase:
        raise ContractError(f"freeze_schema_or_keyset_invalid:{contract.phase}")
    for field in ("plan_hash", "test_spec_hash", "profile_hash", "report_hash"):
        if not _is_hash(value.get(field)):
            raise ContractError(f"freeze_{field}_invalid")
    value["source_hashes"] = _validate_hash_mapping(value.get("source_hashes"), field="source_hashes")
    if set(value["source_hashes"]) != set(phase_source_paths(contract.phase)):
        raise ContractError(f"freeze_source_hash_keyset_invalid:{contract.phase}")
    predecessor_hashes = value.get("predecessor_file_hashes")
    if not isinstance(predecessor_hashes, list) or len(predecessor_hashes) != len(contract.predecessors) or any(not _is_hash(item) for item in predecessor_hashes):
        raise ContractError("freeze_predecessor_file_hashes_invalid")
    if value["source_hashes"].get(PROGRAM_PLAN) != value["plan_hash"] or value["source_hashes"].get(f"docs/operations/{contract.phase}-test-spec.md") != value["test_spec_hash"]:
        raise ContractError("freeze_plan_or_spec_binding_invalid")
    validate_self_hash(value, "manifest_hash")
    return value


def validate_final_review(
    review: Mapping[str, Any],
    *,
    contract: PhaseContract,
    report: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
    writer_agent_id: str | None = None,
) -> dict[str, Any]:
    value = deepcopy(dict(review))
    if set(value) != REVIEW_KEYS or value.get("schema_version") != contract.review_schema or value.get("phase") != contract.phase:
        raise ContractError(f"review_schema_or_keyset_invalid:{contract.phase}")
    if value.get("decision") != "approve" or not isinstance(value.get("reviewer_identity"), str) or not value["reviewer_identity"]:
        raise ContractError("review_decision_or_identity_invalid")
    reviewer_id = value.get("reviewer_agent_id")
    if not isinstance(reviewer_id, str) or UUIDV7_RE.fullmatch(reviewer_id) is None:
        raise ContractError("review_reviewer_agent_id_invalid")
    declared_writer_id = value.get("writer_agent_id")
    if not isinstance(declared_writer_id, str) or UUIDV7_RE.fullmatch(declared_writer_id) is None:
        raise ContractError("review_writer_agent_id_invalid")
    if declared_writer_id == reviewer_id:
        raise ContractError("writer_reviewer_separation_invalid")
    if writer_agent_id is not None and declared_writer_id != writer_agent_id:
        raise ContractError("review_writer_agent_id_binding_invalid")
    reviewed_at = value.get("reviewed_at")
    if not isinstance(reviewed_at, str) or not reviewed_at.endswith("Z"):
        raise ContractError("review_reviewed_at_utc_invalid")
    try:
        datetime.fromisoformat(reviewed_at.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise ContractError("review_reviewed_at_utc_invalid") from exc
    findings = value.get("findings")
    if not isinstance(findings, Mapping) or set(findings) != {"p0", "p1", "p2", "p3"}:
        raise ContractError("review_findings_keyset_invalid")
    for key in ("p0", "p1", "p2", "p3"):
        if isinstance(findings[key], bool) or not isinstance(findings[key], int) or findings[key] != 0:
            raise ContractError(f"review_findings_must_be_zero:{key}")
    if value.get("limitations") != list(contract.limitations):
        raise ContractError("review_limitations_invalid")
    if not _is_hash(value.get("reviewed_report_hash")) or not _is_hash(value.get("reviewed_manifest_hash")):
        raise ContractError("review_binding_hash_invalid")
    if report is not None and value["reviewed_report_hash"] != report.get("report_hash"):
        raise ContractError("review_report_hash_mismatch")
    if freeze_manifest is not None and value["reviewed_manifest_hash"] != freeze_manifest.get("manifest_hash"):
        raise ContractError("review_manifest_hash_mismatch")
    validate_self_hash(value, "review_hash")
    return value


def assemble_release_evidence(
    *, contract: PhaseContract, report: Mapping[str, Any], freeze_manifest: Mapping[str, Any], final_review: Mapping[str, Any]
) -> dict[str, Any]:
    validated_report = validate_report(report, contract)
    validated_freeze = validate_freeze_manifest(freeze_manifest, contract)
    if validated_freeze["report_hash"] != validated_report["report_hash"]:
        raise ContractError("release_freeze_report_hash_mismatch")
    if validated_freeze["source_hashes"] != validated_report["source_hashes"]:
        raise ContractError("release_freeze_source_hashes_mismatch")
    if validated_freeze["predecessor_file_hashes"] != [entry["file_hash"] for entry in validated_report["predecessors"]]:
        raise ContractError("release_freeze_predecessor_hashes_mismatch")
    validated_review = validate_final_review(
        final_review,
        contract=contract,
        report=validated_report,
        freeze_manifest=validated_freeze,
    )
    evidence = {
        "schema_version": contract.release_schema,
        "phase": contract.phase,
        "status": contract.status,
        "claim": contract.claim,
        "limitations": list(contract.limitations),
        "report_hash": validated_report["report_hash"],
        "freeze_hash": validated_freeze["manifest_hash"],
        "review_hash": validated_review["review_hash"],
        "predecessors": deepcopy(validated_report["predecessors"]),
        "source_hashes": deepcopy(validated_report["source_hashes"]),
        "metrics": deepcopy(validated_report["metrics"]),
        "counters": deepcopy(validated_report["counters"]),
        "passed": validated_report["passed"],
        "failed": validated_report["failed"],
        "evidence_hash": "",
    }
    return validate_release_evidence(with_self_hash(evidence, "evidence_hash"), contract)


def validate_release_evidence(evidence: Mapping[str, Any], contract: PhaseContract) -> dict[str, Any]:
    value = deepcopy(dict(evidence))
    if set(value) != RELEASE_KEYS or value.get("schema_version") != contract.release_schema or value.get("phase") != contract.phase:
        raise ContractError(f"release_schema_or_keyset_invalid:{contract.phase}")
    if value.get("status") != contract.status or value.get("claim") != contract.claim or value.get("limitations") != list(contract.limitations):
        raise ContractError("release_status_claim_or_limitations_invalid")
    for field in ("report_hash", "freeze_hash", "review_hash"):
        if not _is_hash(value.get(field)):
            raise ContractError(f"release_{field}_invalid")
    value["predecessors"] = validate_predecessors(value.get("predecessors", []), contract)
    value["source_hashes"] = _validate_hash_mapping(value.get("source_hashes"), field="source_hashes")
    if set(value["source_hashes"]) != set(phase_source_paths(contract.phase)):
        raise ContractError(f"release_source_hash_keyset_invalid:{contract.phase}")
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping) or set(metrics) != set(contract.metric_keys):
        raise ContractError("release_metric_keyset_invalid")
    value["metrics"] = {key: deepcopy(metrics[key]) for key in contract.metric_keys}
    value["counters"] = validate_counters(value.get("counters", {}))
    if value.get("failed") != 0 or not isinstance(value.get("passed"), int) or value["passed"] <= 0:
        raise ContractError("release_denominator_invalid")
    exact_passed = {"p149": 8, "p151": 48}.get(contract.phase)
    if exact_passed is not None and value["passed"] != exact_passed:
        raise ContractError(f"release_exact_denominator_invalid:{contract.phase}")
    validate_self_hash(value, "evidence_hash")
    return value


def _validate_shared_release_evidence_shape(value: Mapping[str, Any], spec: PredecessorSpec) -> None:
    if set(value) != RELEASE_KEYS:
        raise ContractError(f"predecessor_release_keyset_invalid:{spec.phase}")
    validate_self_hash(value, "evidence_hash")
    for field in ("report_hash", "freeze_hash", "review_hash"):
        if not _is_hash(value.get(field)):
            raise ContractError(f"predecessor_release_{field}_invalid:{spec.phase}")
    predecessors = value.get("predecessors")
    if not isinstance(predecessors, list):
        raise ContractError(f"predecessor_release_predecessor_list_invalid:{spec.phase}")
    for predecessor in predecessors:
        if not isinstance(predecessor, Mapping) or set(predecessor) != PREDECESSOR_KEYS:
            raise ContractError(f"predecessor_release_predecessor_shape_invalid:{spec.phase}")
        if not all(isinstance(predecessor.get(field), str) and predecessor[field] for field in ("phase", "path", "schema_version", "required_status")):
            raise ContractError(f"predecessor_release_predecessor_identity_invalid:{spec.phase}")
        if not _is_hash(predecessor.get("file_hash")) or not _is_hash(predecessor.get("evidence_hash")):
            raise ContractError(f"predecessor_release_predecessor_hash_invalid:{spec.phase}")
    source_hashes = _validate_hash_mapping(value.get("source_hashes"), field="source_hashes")
    if set(source_hashes) != set(phase_source_paths(spec.phase)):
        raise ContractError(f"predecessor_release_source_hash_keyset_invalid:{spec.phase}")
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping) or not metrics:
        raise ContractError(f"predecessor_release_metric_keyset_invalid:{spec.phase}")
    counters = validate_counters(value.get("counters", {}))
    passed = value.get("passed")
    failed = value.get("failed")
    if isinstance(passed, bool) or not isinstance(passed, int) or passed <= 0:
        raise ContractError(f"predecessor_release_passed_invalid:{spec.phase}")
    if isinstance(failed, bool) or not isinstance(failed, int) or failed != 0:
        raise ContractError(f"predecessor_release_failed_invalid:{spec.phase}")
    if counters["read_success_count"] > counters["read_attempt_count"]:
        raise ContractError(f"predecessor_release_counter_consistency_invalid:{spec.phase}")


def _validate_exact_phase_release_evidence(
    value: Mapping[str, Any],
    spec: PredecessorSpec,
    *,
    project_root: Path | None = None,
) -> None:
    """Validate a P147-P152 predecessor with its owning phase contract.

    Imports are deliberately lazy so phase modules can import this shared module
    without creating an import cycle during module initialization.
    """

    module_name = f"app.services.{_phase_module_stem(spec.phase)}"
    module = importlib.import_module(module_name)
    validator = getattr(module, f"validate_{spec.phase}_release_evidence")
    if spec.phase == "p150":
        if project_root is None:
            raise ContractError("p150_predecessor_raw_artifact_root_required")
        validator(value, project_root=project_root)
    else:
        validator(value)


def _validate_p146_release_evidence(project_root: Path, value: Mapping[str, Any]) -> None:
    from app.services.p146_release_evidence import (
        validate_final_review as validate_p146_final_review,
    )
    from app.services.p146_release_evidence import (
        validate_freeze_manifest as validate_p146_freeze_manifest,
    )
    from app.services.p146_release_evidence import (
        validate_release_evidence as validate_p146_release,
    )
    from app.services.p146_release_evidence import (
        validate_release_matrix as validate_p146_matrix,
    )

    try:
        matrix = validate_p146_matrix(load_json(project_root / "evals/p146/output/canonical-matrix.json"))
        freeze = validate_p146_freeze_manifest(
            load_json(project_root / "evals/p146/output/freeze-manifest.json"), matrix=matrix
        )
        review = validate_p146_final_review(
            load_json(project_root / "evals/p146/final-implementation-review.json"), manifest=freeze
        )
        validate_p146_release(
            value,
            matrix=matrix,
            manifest=freeze,
            review=review,
            benchmark_report_path=project_root / "evals/p146/output/benchmark-report.json",
        )
    except (ContractError, OSError, TypeError, ValueError) as exc:
        raise ContractError("predecessor_p146_full_release_invalid") from exc


def _phase_module_stem(phase: str) -> str:
    stems = {
        "p147": "p147_durable_shadow",
        "p148": "p148_reversible_lab",
        "p149": "p149_canary_control",
        "p150": "p150_unattended_soak",
        "p151": "p151_ground_truth_quality",
        "p152": "p152_operator_readiness",
    }
    try:
        return stems[phase]
    except KeyError as exc:
        raise ContractError(f"predecessor_phase_validator_missing:{phase}") from exc


def write_preliminary_artifacts(output_dir: Path, report: Mapping[str, Any], freeze_manifest: Mapping[str, Any]) -> dict[str, Path]:
    return {
        "report": write_canonical_json(output_dir / "report.json", report),
        "freeze_manifest": write_canonical_json(output_dir / "freeze-manifest.json", freeze_manifest),
    }


def write_release_evidence(output_dir: Path, evidence: Mapping[str, Any]) -> Path:
    return write_canonical_json(output_dir / "release-evidence.json", evidence)


def _validate_hash_mapping(value: Any, *, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ContractError(f"{field}_mapping_invalid")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or not _is_hash(item):
            raise ContractError(f"{field}_entry_invalid")
        result[key] = item
    if list(result) != sorted(result):
        raise ContractError(f"{field}_order_invalid")
    return result


def _sorted_unique_strings(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{field}_list_invalid")
    result = list(value)
    if result != sorted(set(result)):
        raise ContractError(f"{field}_order_or_duplicate_invalid")
    return result


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
