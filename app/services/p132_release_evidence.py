"""Fail-closed release evidence for P132 supervised runtime qualification."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS
from app.services.p132_supervised_runtime import EXPECTED_CONSOLE_ENTRYPOINT

P132_RELEASE_SCHEMA_VERSION = "p132.release_evidence.v1"
P132_READY_STATUS = "p132_supervised_runtime_qualified"
P132_BLOCKED_STATUS = "p132_blocked"
_ROOT = Path(__file__).resolve().parents[2]

PUBLIC_LIMITATION = (
    "Bounded local single-host qualification only; no 24/7 production availability, multi-host failover, live connector, "
    "external paging, authentication, credential access, remediation, production autonomy, or operator replacement is claimed."
)

_PROCESS_CASES = ("sigterm", "sigint", "forced_crash_restart", "lease_conflict")
_STORAGE_CASES = (
    "low_space_preserves_checkpoint",
    "pre_replace_preserves_canonical",
    "post_replace_recovery",
    "report_interruption_preserves_bucket",
)
_EVALUATOR_ZERO_COUNTERS = (
    "arbitrary_command_count",
    "credential_read_count",
    "network_call_count",
    "connector_write_count",
    "remediation_count",
    "staging_mutation_count",
    "production_mutation_count",
)
_EVALUATOR_ACTIVITY_COUNTERS = (
    "process_launch_count",
    "signal_count",
    "sigterm_count",
    "sigint_count",
    "forced_kill_count",
    "watchdog_call_count",
    "status_call_count",
    "lease_conflict_count",
)


class P132ReleaseEvidenceError(ValueError):
    """Raised when P132 release evidence is stale, malformed, or unsafe."""


def build_p132_release_evidence(
    endurance_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    *,
    evaluator_activity: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind P132 endurance, process, supervisor, authority, and evaluator evidence."""

    runtime_authority = _mapping(endurance_report.get("runtime_authority"))
    runtime_counters = _mapping(runtime_authority.get("counters"))
    accounting = _mapping(endurance_report.get("accounting"))
    process_cases = _mapping(process_matrix.get("cases"))
    storage_cases = _mapping(process_matrix.get("storage_cases"))
    evaluator = _normalized_evaluator_activity(evaluator_activity)

    gates = {
        "endurance_report_self_hash_current": _self_hash_current(endurance_report, "endurance_report_hash"),
        "process_matrix_self_hash_current": _self_hash_current(process_matrix, "process_matrix_hash"),
        "supervisor_validation_self_hash_current": _supervisor_hash_current(supervisor_validation),
        "endurance_accounting_exact": (
            _exact_int(accounting.get("expected"), 1000)
            and _exact_int(accounting.get("accepted"), 1000)
            and _exact_int(accounting.get("invalid"), 0)
            and _exact_int(accounting.get("lost"), 0)
            and _exact_int(accounting.get("duplicated"), 0)
            and _accounting_denominator_consistent(accounting)
        ),
        "endurance_resource_gates_passed": _mapping(endurance_report.get("resource_gates")).get("passed") is True,
        "process_matrix_passed": _process_matrix_passed(process_matrix, process_cases),
        "storage_matrix_passed": _storage_matrix_passed(process_matrix, storage_cases),
        "supervisor_validation_passed": supervisor_validation.get("passed") is True,
        "runtime_authority_exact_zero": _runtime_authority_exact_zero(runtime_authority),
        "process_runtime_authority_exact_zero": _runtime_authority_exact_zero(
            _mapping(process_matrix.get("runtime_authority"))
        ),
        "evaluator_activity_disclosed": _evaluator_activity_disclosed(evaluator),
        "evaluator_activity_bound_to_process_matrix": evaluator == _mapping(process_matrix.get("evaluator_activity")),
        "evaluator_zero_authority": _evaluator_zero_authority(evaluator),
        "semantic_artifact_binding_present": _semantic_binding_present(endurance_report, process_matrix, supervisor_validation),
    }
    passed = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P132_RELEASE_SCHEMA_VERSION,
        "release_id": "P132-supervised-runtime-endurance",
        "release_status": P132_READY_STATUS if passed else P132_BLOCKED_STATUS,
        "product_claim": "P131's local JSONL monitor is qualified for bounded single-host external supervisor management.",
        "public_limitation": PUBLIC_LIMITATION,
        "gates": gates,
        "artifact_hashes": {
            "endurance_report": stable_hash(endurance_report),
            "process_matrix": stable_hash(process_matrix),
            "supervisor_validation": stable_hash(supervisor_validation),
        },
        "semantic_binding": _semantic_binding(endurance_report, process_matrix, supervisor_validation),
        "runtime_authority": {
            "exact_zero": runtime_authority.get("exact_zero") is True,
            "counters": dict(runtime_counters),
        },
        "evaluator_activity": evaluator,
        "reasons": [f"{name} failed closed" for name, value in gates.items() if value is not True],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p132_release_evidence(
    evidence: Mapping[str, Any],
    *,
    endurance_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    project_root: Path | str = _ROOT,
    artifact_root: Path | str | None = None,
) -> None:
    """Reject non-current, blocked, unsafe, or semantically stale P132 evidence."""

    if evidence.get("schema_version") != P132_RELEASE_SCHEMA_VERSION:
        raise P132ReleaseEvidenceError("invalid_release_schema")
    if evidence.get("release_evidence_hash") != stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"}):
        raise P132ReleaseEvidenceError("release_evidence_hash_invalid")
    gates = _mapping(evidence.get("gates"))
    if not gates or not all(value is True for value in gates.values()):
        raise P132ReleaseEvidenceError("release_gate_failed")
    if evidence.get("release_status") != P132_READY_STATUS:
        raise P132ReleaseEvidenceError("release_status_blocked")
    runtime_authority = _mapping(evidence.get("runtime_authority"))
    if not _runtime_authority_exact_zero(runtime_authority):
        raise P132ReleaseEvidenceError("authority_not_exact_zero")
    evaluator = _mapping(evidence.get("evaluator_activity"))
    if not _evaluator_activity_disclosed(evaluator) or not _evaluator_zero_authority(evaluator):
        raise P132ReleaseEvidenceError("evaluator_activity_invalid")

    rebuilt = build_p132_release_evidence(
        endurance_report,
        process_matrix,
        supervisor_validation,
        evaluator_activity=evaluator,
    )
    if dict(evidence) != rebuilt:
        raise P132ReleaseEvidenceError("release_evidence_semantic_mismatch")
    root = Path(project_root).expanduser().resolve()
    promoted_root = (root / "evals/p132" if artifact_root is None else Path(artifact_root)).expanduser().resolve()
    if not _current_sources_and_artifacts(
        endurance_report,
        process_matrix,
        supervisor_validation,
        project_root=root,
        artifact_root=promoted_root,
    ):
        raise P132ReleaseEvidenceError("release_evidence_artifact_stale")


def _semantic_binding(
    endurance_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
) -> dict[str, Any]:
    endurance_artifacts = _mapping(endurance_report.get("artifacts"))
    endurance_runtime_source = _mapping(endurance_report.get("runtime_source"))
    endurance_evaluator_source = _mapping(endurance_report.get("evaluator_source"))
    supervisor_sources = _mapping(supervisor_validation.get("source_hashes"))
    return {
        "endurance": {
            "runtime_id": endurance_report.get("runtime_id"),
            "config_hash": endurance_report.get("config_hash"),
            "profile_id": endurance_report.get("profile_id"),
            "state_hash": endurance_artifacts.get("state_hash"),
            "source_hash": endurance_artifacts.get("source_hash"),
            "report_hashes": dict(_mapping(endurance_artifacts.get("report_hashes"))),
            "runtime_source_hash": endurance_runtime_source.get("self_hash"),
            "evaluator_source_hash": endurance_evaluator_source.get("self_hash"),
            "artifact_paths": {
                key: endurance_artifacts.get(key)
                for key in ("workspace", "source_path", "state_path", "report_dir")
            },
        },
        "process": {
            "cases_hash": stable_hash(_mapping(process_matrix.get("cases"))),
            "storage_cases_hash": stable_hash(_mapping(process_matrix.get("storage_cases"))),
            "source_hashes": dict(_mapping(process_matrix.get("source_hashes"))),
            "artifact_hashes": dict(_mapping(process_matrix.get("artifact_hashes"))),
            "artifact_paths": dict(_mapping(process_matrix.get("artifact_paths"))),
        },
        "supervisor": {
            "console_entrypoint": supervisor_validation.get("console_entrypoint"),
            "manifests": dict(_mapping(supervisor_validation.get("manifests"))),
            "source_hashes": dict(supervisor_sources),
        },
    }


def _semantic_binding_present(
    endurance_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
) -> bool:
    binding = _semantic_binding(endurance_report, process_matrix, supervisor_validation)
    endurance = _mapping(binding.get("endurance"))
    process = _mapping(binding.get("process"))
    supervisor = _mapping(binding.get("supervisor"))
    return (
        bool(endurance.get("runtime_id"))
        and bool(endurance.get("config_hash"))
        and bool(endurance.get("runtime_source_hash"))
        and bool(endurance.get("evaluator_source_hash"))
        and bool(process.get("cases_hash"))
        and bool(process.get("storage_cases_hash"))
        and bool(process.get("source_hashes"))
        and bool(process.get("artifact_hashes"))
        and bool(process.get("artifact_paths"))
        and bool(supervisor.get("manifests"))
        and bool(supervisor.get("source_hashes"))
    )


def _normalized_evaluator_activity(activity: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in activity.items()}


def _evaluator_activity_disclosed(activity: Mapping[str, Any]) -> bool:
    expected = set((*_EVALUATOR_ACTIVITY_COUNTERS, *_EVALUATOR_ZERO_COUNTERS))
    return (
        set(activity) == expected
        and all(type(activity.get(key)) is int and int(activity[key]) >= 0 for key in expected)
        and _exact_positive_int(activity.get("process_launch_count"))
        and activity.get("signal_count") == int(activity.get("sigterm_count", 0)) + int(activity.get("sigint_count", 0))
        and _exact_positive_int(activity.get("sigterm_count"))
        and _exact_positive_int(activity.get("sigint_count"))
        and _exact_positive_int(activity.get("forced_kill_count"))
        and _exact_positive_int(activity.get("watchdog_call_count"))
        and _exact_positive_int(activity.get("status_call_count"))
        and _exact_positive_int(activity.get("lease_conflict_count"))
    )


def _evaluator_zero_authority(activity: Mapping[str, Any]) -> bool:
    return all(_exact_int(activity.get(key), 0) for key in _EVALUATOR_ZERO_COUNTERS)


def _runtime_authority_exact_zero(authority: Mapping[str, Any]) -> bool:
    counters = _mapping(authority.get("counters"))
    return (
        authority.get("exact_zero") is True
        and set(counters) == set(P121_AUTHORITY_COUNTER_KEYS)
        and all(_exact_int(counters.get(key), 0) for key in P121_AUTHORITY_COUNTER_KEYS)
    )


def _self_hash_current(value: Mapping[str, Any], field: str) -> bool:
    return value.get(field) == stable_hash({key: item for key, item in value.items() if key != field})


def _accounting_denominator_consistent(accounting: Mapping[str, Any]) -> bool:
    keys = ("expected", "accepted", "invalid", "duplicated", "lost")
    if not all(type(accounting.get(key)) is int and int(accounting[key]) >= 0 for key in keys):
        return False
    return int(accounting["expected"]) == sum(int(accounting[key]) for key in keys[1:])


def _process_matrix_passed(process_matrix: Mapping[str, Any], cases: Mapping[str, Any]) -> bool:
    watchdog = _mapping(process_matrix.get("watchdog_cases"))
    expected_watchdog = {"current", "stopped", "stale", "missing", "tampered", "status_current"}
    return (
        process_matrix.get("passed") is True
        and set(cases) == set(_PROCESS_CASES)
        and all(_mapping(cases.get(case)).get("passed") is True for case in _PROCESS_CASES)
        and set(watchdog) == expected_watchdog
        and all(watchdog.get(case) is True for case in expected_watchdog)
    )


def _storage_matrix_passed(process_matrix: Mapping[str, Any], cases: Mapping[str, Any]) -> bool:
    if set(cases) != set(_STORAGE_CASES) or process_matrix.get("storage_matrix_hash") != stable_hash(cases):
        return False
    low = _mapping(cases.get("low_space_preserves_checkpoint"))
    pre = _mapping(cases.get("pre_replace_preserves_canonical"))
    post = _mapping(cases.get("post_replace_recovery"))
    report = _mapping(cases.get("report_interruption_preserves_bucket"))
    return all(
        (
            low.get("passed") is True,
            "artifact_free_space_below_floor" in str(low.get("failure", "")),
            _sha256_text(low.get("state_hash")),
            pre.get("passed") is True,
            "replace failed" in str(pre.get("failure", "")),
            _sha256_text(pre.get("canonical_hash")),
            post.get("passed") is True,
            "directory_fsync_failed_after_replace" in str(post.get("failure", "")),
            _sha256_text(post.get("uncertain_state_hash")),
            _sha256_text(post.get("recovered_state_hash")),
            post.get("uncertain_state_hash") != post.get("recovered_state_hash"),
            report.get("passed") is True,
            "report write interrupted" in str(report.get("failure", "")),
            type(report.get("prior_report_bucket")) is int,
            report.get("current_report_bucket") == report.get("prior_report_bucket"),
        )
    )


def _sha256_text(value: object) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdef" for character in value[7:]
    )


def _current_sources_and_artifacts(
    endurance_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    *,
    project_root: Path,
    artifact_root: Path,
) -> bool:
    endurance_runtime = _mapping(endurance_report.get("runtime_source"))
    endurance_evaluator = _mapping(endurance_report.get("evaluator_source"))
    for source in (endurance_runtime, endurance_evaluator):
        module = source.get("module")
        if not isinstance(module, str):
            return False
        relative = Path(*module.split(".")).with_suffix(".py")
        if not _bound_file_current(project_root, relative.as_posix(), source.get("self_hash")):
            return False

    if not _source_hashes_current(project_root, _mapping(process_matrix.get("source_hashes"))):
        return False
    if not _source_hashes_current(project_root, _mapping(supervisor_validation.get("source_hashes"))):
        return False
    if (
        supervisor_validation.get("console_entrypoint") != EXPECTED_CONSOLE_ENTRYPOINT
        or _current_monitor_console_entrypoint(project_root / "pyproject.toml") != EXPECTED_CONSOLE_ENTRYPOINT
    ):
        return False

    endurance_artifacts = _mapping(endurance_report.get("artifacts"))
    workspace = endurance_artifacts.get("workspace")
    source_path = endurance_artifacts.get("source_path")
    state_path = endurance_artifacts.get("state_path")
    report_dir = endurance_artifacts.get("report_dir")
    if not _bound_directory_current(artifact_root, workspace) or not _bound_directory_current(artifact_root, report_dir):
        return False
    if not _bound_file_current(artifact_root, source_path, endurance_artifacts.get("source_hash")):
        return False
    if not _bound_file_current(artifact_root, state_path, endurance_artifacts.get("state_hash")):
        return False
    report_hashes = _mapping(endurance_artifacts.get("report_hashes"))
    report_relative = Path(str(report_dir))
    if not report_hashes or any(
        not _bound_file_current(artifact_root, (report_relative / name).as_posix(), expected_hash)
        for name, expected_hash in report_hashes.items()
    ):
        return False
    report_path = _safe_relative_path(artifact_root, report_dir)
    if report_path is None:
        return False
    try:
        actual_report_names = {
            path.name for path in report_path.iterdir() if path.is_file() and not path.is_symlink()
        }
    except OSError:
        return False
    if actual_report_names != set(report_hashes):
        return False

    artifact_hashes = _mapping(process_matrix.get("artifact_hashes"))
    artifact_paths = _mapping(process_matrix.get("artifact_paths"))
    return set(artifact_hashes) == set(artifact_paths) and bool(artifact_hashes) and all(
        _bound_file_current(artifact_root, artifact_paths.get(name), expected_hash)
        for name, expected_hash in artifact_hashes.items()
    )


def _source_hashes_current(root: Path, source_hashes: Mapping[str, Any]) -> bool:
    return bool(source_hashes) and all(
        _bound_file_current(root, relative, expected_hash) for relative, expected_hash in source_hashes.items()
    )


def _current_monitor_console_entrypoint(pyproject_path: Path) -> str | None:
    try:
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = data.get("project")
    scripts = project.get("scripts") if isinstance(project, Mapping) else None
    value = scripts.get("opscat-monitor") if isinstance(scripts, Mapping) else None
    return value if isinstance(value, str) else None


def _bound_file_current(root: Path, relative: object, expected_hash: object) -> bool:
    path = _safe_relative_path(root, relative)
    if path is None or not path.is_file() or path.is_symlink() or not isinstance(expected_hash, str):
        return False
    try:
        return stable_hash(path.read_bytes().hex()) == expected_hash
    except OSError:
        return False


def _bound_directory_current(root: Path, relative: object) -> bool:
    path = _safe_relative_path(root, relative)
    return path is not None and path.is_dir() and not path.is_symlink()


def _safe_relative_path(root: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or ".." in candidate_relative.parts:
        return None
    current = root
    for component in candidate_relative.parts:
        current = current / component
        if current.is_symlink():
            return None
    try:
        resolved = current.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_relative_to(root) else None


def _supervisor_hash_current(value: Mapping[str, Any]) -> bool:
    fields = [field for field in ("supervisor_validation_hash", "validation_hash") if field in value]
    if not fields:
        return False
    return any(
        value.get(field) == stable_hash({key: item for key, item in value.items() if key != field})
        or value.get(field) == stable_hash({key: item for key, item in value.items() if key not in set(fields)})
        for field in fields
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


def _exact_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


__all__ = [
    "P132_BLOCKED_STATUS",
    "P132_READY_STATUS",
    "P132ReleaseEvidenceError",
    "build_p132_release_evidence",
    "validate_p132_release_evidence",
]
