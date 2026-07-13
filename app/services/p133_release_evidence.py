"""Fail-closed release evidence for P133 local dead-man outbox qualification."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS

P133_RELEASE_SCHEMA_VERSION = "p133.release_evidence.v1"
P133_READY_STATUS = "p133_local_deadman_outbox_qualified"
P133_BLOCKED_STATUS = "p133_blocked"
_ROOT = Path(__file__).resolve().parents[2]

PUBLIC_LIMITATION = (
    "Bounded local single-host outbox persistence only; no network delivery, external paging, authentication, "
    "credential access, remediation, shell execution, production autonomy, 24/7 availability, or operator replacement "
    "is claimed."
)

REQUIRED_SCENARIOS = (
    "healthy_no_event",
    "stale_open",
    "unchanged_dedup",
    "reason_update",
    "reminder_boundary",
    "recovery",
    "stopped_open",
    "missing_open",
    "tampered_open",
    "event_cursor_crash_retry",
    "ack_does_not_resolve",
    "acknowledged_retention",
    "retention_partial_delete_recovery",
    "low_space_preservation",
    "budget_exhaustion_preservation",
    "tampered_retention_block",
    "symlink_retention_block",
    "hardlink_retention_block",
    "unsafe_retention_directory_block",
    "post_replace_reload_rewrite",
)
SUBPROCESS_CASES = (
    "deadman_check_stale_open",
    "deadman_run_dedup",
    "deadman_check_reminder",
    "deadman_check_recovery",
    "outbox_list_redacted",
    "outbox_ack_local",
    "restart_dedup",
    "graceful_stop",
)
ZERO_AUTHORITY_COUNTERS = (
    "arbitrary_command_count",
    "credential_read_count",
    "network_call_count",
    "connector_write_count",
    "remediation_count",
    "shell_execution_count",
    "staging_mutation_count",
    "production_mutation_count",
)
EVALUATOR_ACTIVITY_COUNTERS = (
    "process_launch_count",
    "signal_count",
    "sigterm_count",
    "sigint_count",
    "forced_kill_count",
)
EXPECTED_ARTIFACTS = (
    "outbox-report.json",
    "process-matrix.json",
    "supervisor-validation.json",
    "authority-ledger.json",
    "release-evidence.json",
)
EXPECTED_SOURCE_BINDINGS = frozenset(
    {
        "app/services/p131_always_on_monitor.py",
        "app/services/p133_deadman_outbox.py",
        "app/services/p133_release_evidence.py",
        "scripts/run_p133_deadman_outbox.py",
        "app/monitor_cli.py",
        "evals/p133/input/outbox-profile.json",
    }
)
EXPECTED_MANIFEST_BINDINGS = frozenset(
    {
        "deploy/p133/opscat-deadman.service",
        "deploy/p133/io.opscat.deadman.plist",
        "deploy/p133/compose.deadman.yaml",
    }
)
EXPECTED_TOTALS = {
    "expected_scenarios": 20,
    "expected_emitted_events": 10,
    "expected_deduplicated_checks": 2,
    "expected_recoveries": 1,
    "expected_acknowledgements": 2,
    "expected_retained_events": 2,
    "expected_pruned_events": 1,
}


class P133ReleaseEvidenceError(ValueError):
    """Raised when P133 release evidence is stale, malformed, or unsafe."""


def build_p133_release_evidence(
    outbox_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind transition, subprocess, supervisor, authority, source, and raw evidence."""

    runtime_authority = _mapping(outbox_report.get("runtime_authority"))
    evaluator_authority = _mapping(authority_ledger.get("evaluator_authority"))
    gates = {
        "outbox_report_self_hash_current": _self_hash_current(outbox_report, "outbox_report_hash"),
        "process_matrix_self_hash_current": _self_hash_current(process_matrix, "process_matrix_hash"),
        "supervisor_validation_self_hash_current": _self_hash_current(supervisor_validation, "supervisor_validation_hash"),
        "authority_ledger_self_hash_current": _self_hash_current(authority_ledger, "authority_ledger_hash"),
        "transition_matrix_passed": _transition_matrix_passed(outbox_report),
        "raw_evidence_bounded_and_relative": _raw_evidence_bounded(outbox_report),
        "subprocess_smoke_passed": _subprocess_smoke_passed(process_matrix),
        "resource_usage_within_profile": _resource_usage_within_profile(process_matrix),
        "supervisor_validation_passed": _supervisor_validation_passed(supervisor_validation),
        "runtime_authority_exact_zero": _runtime_authority_exact_zero(runtime_authority),
        "ledger_runtime_authority_exact_zero": _runtime_authority_exact_zero(_mapping(authority_ledger.get("runtime_authority"))),
        "evaluator_activity_disclosed": _evaluator_activity_disclosed(authority_ledger),
        "evaluator_zero_authority": _evaluator_authority_exact_zero(evaluator_authority),
        "semantic_artifact_binding_present": _semantic_binding_present(
            outbox_report,
            process_matrix,
            supervisor_validation,
            authority_ledger,
        ),
    }
    passed = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P133_RELEASE_SCHEMA_VERSION,
        "release_id": "P133-local-deadman-outbox",
        "release_status": P133_READY_STATUS if passed else P133_BLOCKED_STATUS,
        "product_claim": (
            "P133 persists redacted local dead-man outbox evidence for bounded P131 watchdog unhealthy transitions."
        ),
        "public_limitation": PUBLIC_LIMITATION,
        "gates": gates,
        "artifact_hashes": {
            "outbox_report": stable_hash(outbox_report),
            "process_matrix": stable_hash(process_matrix),
            "supervisor_validation": stable_hash(supervisor_validation),
            "authority_ledger": stable_hash(authority_ledger),
        },
        "semantic_binding": _semantic_binding(
            outbox_report,
            process_matrix,
            supervisor_validation,
            authority_ledger,
        ),
        "runtime_authority": {
            "exact_zero": runtime_authority.get("exact_zero") is True,
            "counters": dict(_mapping(runtime_authority.get("counters"))),
        },
        "evaluator_activity": dict(_mapping(authority_ledger.get("evaluator_activity"))),
        "evaluator_authority": dict(_mapping(evaluator_authority.get("counters"))),
        "reasons": [f"{name} failed closed" for name, value in gates.items() if value is not True],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p133_release_evidence(
    evidence: Mapping[str, Any],
    *,
    outbox_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
    project_root: Path | str = _ROOT,
    artifact_root: Path | str | None = None,
) -> None:
    """Reject non-current, blocked, unsafe, optimistic, or semantically stale P133 evidence."""

    if evidence.get("schema_version") != P133_RELEASE_SCHEMA_VERSION:
        raise P133ReleaseEvidenceError("invalid_release_schema")
    claimed_hash = evidence.get("release_evidence_hash")
    unsigned = {key: value for key, value in evidence.items() if key != "release_evidence_hash"}
    if claimed_hash != stable_hash(unsigned):
        raise P133ReleaseEvidenceError("release_evidence_hash_invalid")
    gates = _mapping(evidence.get("gates"))
    if not gates or not all(value is True for value in gates.values()):
        raise P133ReleaseEvidenceError("release_gate_failed")
    if evidence.get("release_status") != P133_READY_STATUS:
        raise P133ReleaseEvidenceError("release_status_blocked")
    if not _runtime_authority_exact_zero(_mapping(evidence.get("runtime_authority"))):
        raise P133ReleaseEvidenceError("authority_not_exact_zero")
    if not _evaluator_activity_disclosed(authority_ledger) or not _evaluator_authority_exact_zero(
        _mapping(authority_ledger.get("evaluator_authority"))
    ):
        raise P133ReleaseEvidenceError("evaluator_activity_invalid")

    rebuilt = build_p133_release_evidence(outbox_report, process_matrix, supervisor_validation, authority_ledger)
    if dict(evidence) != rebuilt:
        raise P133ReleaseEvidenceError("release_evidence_semantic_mismatch")

    root = Path(project_root).expanduser().resolve()
    promoted_root = (root / "evals/p133" if artifact_root is None else Path(artifact_root)).expanduser().resolve()
    if not _current_sources_and_artifacts(
        evidence,
        outbox_report,
        process_matrix,
        supervisor_validation,
        authority_ledger,
        project_root=root,
        artifact_root=promoted_root,
    ):
        raise P133ReleaseEvidenceError("release_evidence_artifact_stale")


def _transition_matrix_passed(report: Mapping[str, Any]) -> bool:
    cases = _mapping(report.get("cases"))
    totals = _mapping(report.get("totals"))
    required_scenarios = report.get("required_scenarios")
    return (
        report.get("passed") is True
        and isinstance(required_scenarios, (list, tuple))
        and tuple(required_scenarios) == REQUIRED_SCENARIOS
        and set(cases) == set(REQUIRED_SCENARIOS)
        and all(_substantive_case_passed(name, _mapping(cases.get(name))) for name in REQUIRED_SCENARIOS)
        and _exact_int(totals.get("expected_scenarios"), len(REQUIRED_SCENARIOS))
        and _exact_int(totals.get("passed_scenarios"), len(REQUIRED_SCENARIOS))
        and _exact_int(totals.get("failed_scenarios"), 0)
        and totals.get("denominator_scope") == "principal_transition_assertions"
        and all(_exact_int(totals.get(key), expected) for key, expected in EXPECTED_TOTALS.items())
        and _exact_int(totals.get("observed_emitted_events"), EXPECTED_TOTALS["expected_emitted_events"])
        and _exact_int(
            totals.get("observed_deduplicated_checks"),
            EXPECTED_TOTALS["expected_deduplicated_checks"],
        )
        and _exact_int(totals.get("observed_recoveries"), EXPECTED_TOTALS["expected_recoveries"])
        and _exact_int(
            totals.get("observed_acknowledgements"),
            EXPECTED_TOTALS["expected_acknowledgements"],
        )
        and _exact_int(totals.get("observed_retained_events"), EXPECTED_TOTALS["expected_retained_events"])
        and _exact_int(totals.get("observed_pruned_events"), EXPECTED_TOTALS["expected_pruned_events"])
    )


def _substantive_case_passed(name: str, case: Mapping[str, Any]) -> bool:
    if case.get("passed") is not True or not isinstance(case.get("evidence"), Mapping):
        return False
    evidence = _mapping(case.get("evidence"))
    if name in {"healthy_no_event", "unchanged_dedup"}:
        return _exact_int(evidence.get("emitted_events"), 0) and _exact_int(evidence.get("deduplicated_checks"), 1)
    if name in {"stale_open", "stopped_open", "missing_open", "tampered_open"}:
        return evidence.get("transition_kind") == "opened" and _sha256_text(evidence.get("event_id"))
    if name == "reason_update":
        return evidence.get("transition_kind") == "updated" and _sha256_text(evidence.get("previous_event_id"))
    if name == "reminder_boundary":
        return evidence.get("transition_kind") == "reminder" and _exact_int(evidence.get("reminder_interval_seconds"), 300)
    if name == "recovery":
        return evidence.get("transition_kind") == "recovered" and evidence.get("active_incident_closed") is True
    if name == "event_cursor_crash_retry":
        return (
            _sha256_text(evidence.get("event_id"))
            and evidence.get("event_id") == evidence.get("replayed_event_id")
            and evidence.get("occurred_at") == evidence.get("replayed_occurred_at")
            and _exact_int(evidence.get("event_file_count"), 1)
            and _exact_int(evidence.get("next_sequence"), 2)
        )
    if name == "ack_does_not_resolve":
        return _sha256_text(evidence.get("ack_event_id")) and evidence.get("active_incident_after_ack") is True
    if name == "acknowledged_retention":
        return _exact_int(evidence.get("removed_events"), 1) and _exact_int(evidence.get("removed_acks"), 1)
    if name == "retention_partial_delete_recovery":
        return (
            evidence.get("crash_injected") is True
            and evidence.get("orphan_ack_observed") is True
            and _exact_int(evidence.get("orphan_acks_removed"), 1)
        )
    if name in {"low_space_preservation", "budget_exhaustion_preservation"}:
        return evidence.get("prior_cursor_preserved") is True and evidence.get("prior_events_preserved") is True
    if name in {"tampered_retention_block", "symlink_retention_block", "hardlink_retention_block"}:
        return evidence.get("blocked") is True and isinstance(evidence.get("failure"), str)
    if name == "unsafe_retention_directory_block":
        return (
            evidence.get("blocked") is True
            and evidence.get("failure") == "retention_parent_permissions_unsafe"
            and evidence.get("prior_cursor_preserved") is True
            and evidence.get("prior_event_preserved") is True
        )
    if name == "post_replace_reload_rewrite":
        return (
            evidence.get("durability_uncertainty_exposed") is True
            and _sha256_text(evidence.get("uncertain_hash"))
            and _sha256_text(evidence.get("rewritten_hash"))
        )
    return False


def _raw_evidence_bounded(report: Mapping[str, Any]) -> bool:
    raw = _mapping(report.get("raw_evidence"))
    files = _mapping(raw.get("files"))
    total_bytes = raw.get("total_bytes")
    return (
        raw.get("root") == "raw"
        and type(total_bytes) is int
        and 0 < total_bytes <= 2_097_152
        and bool(files)
        and all(_safe_relative_text(path) and _sha256_text(value) for path, value in files.items())
        and raw.get("root_hash") == stable_hash(files)
    )


def _subprocess_smoke_passed(process_matrix: Mapping[str, Any]) -> bool:
    cases = _mapping(process_matrix.get("subprocess_cases"))
    activity = _mapping(process_matrix.get("evaluator_activity"))
    commands = process_matrix.get("commands")
    return (
        process_matrix.get("passed") is True
        and set(cases) == set(SUBPROCESS_CASES)
        and all(_substantive_subprocess_case(case, _mapping(cases.get(case))) for case in SUBPROCESS_CASES)
        and type(commands) is list
        and _exact_int(activity.get("process_launch_count"), len(commands))
        and len(commands) >= len(SUBPROCESS_CASES)
        and all(_closed_module_command(command) for command in commands)
        and _evaluator_activity_counters_valid(activity)
        and _exact_int(activity.get("forced_kill_count"), 0)
    )


def _resource_usage_within_profile(process_matrix: Mapping[str, Any]) -> bool:
    limits = _mapping(process_matrix.get("resource_limits"))
    usage = _mapping(process_matrix.get("resource_usage"))
    expected_limit_fields = {
        "max_wall_milliseconds",
        "max_cpu_milliseconds",
        "max_peak_memory_bytes",
    }
    expected_usage_fields = {"wall_milliseconds", "cpu_milliseconds", "peak_memory_bytes"}
    return (
        set(limits) == expected_limit_fields
        and set(usage) == expected_usage_fields
        and _exact_int(limits.get("max_wall_milliseconds"), 60_000)
        and _exact_int(limits.get("max_cpu_milliseconds"), 30_000)
        and _exact_int(limits.get("max_peak_memory_bytes"), 64 * 1024 * 1024)
        and all(type(usage.get(field)) is int and int(usage[field]) >= 0 for field in expected_usage_fields)
        and int(usage["wall_milliseconds"]) <= int(limits["max_wall_milliseconds"])
        and int(usage["cpu_milliseconds"]) <= int(limits["max_cpu_milliseconds"])
        and int(usage["peak_memory_bytes"]) <= int(limits["max_peak_memory_bytes"])
    )


def _substantive_subprocess_case(name: str, case: Mapping[str, Any]) -> bool:
    if case.get("passed") is not True:
        return False
    if name == "deadman_check_stale_open":
        return (
            _exact_int(case.get("returncode"), 1)
            and case.get("transition_kind") == "opened"
            and case.get("reason") == "heartbeat_stale"
            and _sha256_text(case.get("event_id"))
        )
    if name == "deadman_run_dedup":
        return (
            _exact_int(case.get("returncode"), 0)
            and _exact_int(case.get("cycles"), 2)
            and _exact_int(case.get("emitted_events"), 0)
        )
    if name == "deadman_check_reminder":
        return (
            _exact_int(case.get("returncode"), 1)
            and case.get("transition_kind") == "reminder"
            and _sha256_text(case.get("event_id"))
            and _exact_int(case.get("accelerated_cursor_seconds"), 300)
        )
    if name == "deadman_check_recovery":
        return (
            _exact_int(case.get("returncode"), 0)
            and case.get("transition_kind") == "recovered"
            and case.get("reason") == "heartbeat_current"
            and _sha256_text(case.get("event_id"))
        )
    if name == "outbox_list_redacted":
        return (
            _exact_int(case.get("returncode"), 0)
            and _exact_int(case.get("count"), 3)
            and case.get("redacted") is True
        )
    if name == "outbox_ack_local":
        return (
            _exact_int(case.get("returncode"), 0)
            and _sha256_text(case.get("event_id"))
            and _sha256_text(case.get("ack_hash"))
        )
    if name == "restart_dedup":
        return (
            _exact_int(case.get("returncode"), 0)
            and _exact_int(case.get("cycles"), 1)
            and _exact_int(case.get("emitted_events"), 0)
        )
    if name == "graceful_stop":
        latency = case.get("latency_ms")
        return (
            _exact_int(case.get("returncode"), 0)
            and case.get("lease_owner_observed") is True
            and case.get("graceful_stop") is True
            and case.get("stop_reason") == "sigterm"
            and type(latency) is int
            and 0 <= latency <= 3000
        )
    return False


def _closed_module_command(command: object) -> bool:
    if not isinstance(command, Mapping):
        return False
    argv = command.get("argv")
    if not isinstance(argv, list) or len(argv) < 5:
        return False
    if argv[1:3] != ["-m", "app.monitor_cli"]:
        return False
    if argv[3] not in {"deadman-run", "deadman-check", "outbox-list", "outbox-ack"}:
        return False
    joined = " ".join(str(part) for part in argv)
    forbidden = (" /bin/sh", " sh -c", "http://", "https://", "curl ", "token", "secret", "webhook")
    return (
        command.get("shell") is False
        and command.get("bounded") is True
        and "--config" in argv
        and not any(token in joined for token in forbidden)
        and ("--no-sleep" not in argv or ("--max-cycles" in argv and "--forever" not in argv))
    )


def _supervisor_validation_passed(validation: Mapping[str, Any]) -> bool:
    manifests = _mapping(validation.get("manifests"))
    expected = {
        "deploy/p133/opscat-deadman.service",
        "deploy/p133/io.opscat.deadman.plist",
        "deploy/p133/compose.deadman.yaml",
    }
    qualified = {
        "deploy/p133/opscat-deadman.service",
        "deploy/p133/compose.deadman.yaml",
    }
    launchd = _mapping(manifests.get("deploy/p133/io.opscat.deadman.plist"))
    qualified_manifests = validation.get("qualified_manifests")
    example_only_manifests = validation.get("example_only_manifests")
    return (
        validation.get("passed") is True
        and set(manifests) == expected
        and isinstance(qualified_manifests, (list, tuple))
        and set(qualified_manifests) == qualified
        and isinstance(example_only_manifests, (list, tuple))
        and tuple(example_only_manifests) == ("deploy/p133/io.opscat.deadman.plist",)
        and all(_mapping(manifests.get(name)).get("passed") is True for name in qualified)
        and launchd.get("passed") is False
        and launchd.get("status") == "example_only_not_qualified"
        and launchd.get("structural_checks_passed") is True
        and isinstance(launchd.get("limitation"), str)
        and all(_sha256_text(_mapping(manifests.get(name)).get("hash")) for name in expected)
    )


def _semantic_binding(
    outbox_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "outbox": {
            "profile_hash": outbox_report.get("profile_hash"),
            "config_hashes": dict(_mapping(outbox_report.get("config_hashes"))),
            "raw_evidence_hash": _mapping(outbox_report.get("raw_evidence")).get("root_hash"),
            "source_hashes": dict(_mapping(outbox_report.get("source_hashes"))),
            "artifact_paths": dict(_mapping(outbox_report.get("artifact_paths"))),
        },
        "process": {
            "cases_hash": stable_hash(_mapping(process_matrix.get("subprocess_cases"))),
            "source_hashes": dict(_mapping(process_matrix.get("source_hashes"))),
            "artifact_hashes": dict(_mapping(process_matrix.get("artifact_hashes"))),
            "artifact_paths": dict(_mapping(process_matrix.get("artifact_paths"))),
        },
        "supervisor": {
            "manifests": dict(_mapping(supervisor_validation.get("manifests"))),
            "source_hashes": dict(_mapping(supervisor_validation.get("source_hashes"))),
        },
        "authority": {
            "ledger_hash": authority_ledger.get("authority_ledger_hash"),
            "source_hashes": dict(_mapping(authority_ledger.get("source_hashes"))),
        },
    }


def _semantic_binding_present(
    outbox_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
) -> bool:
    binding = _semantic_binding(outbox_report, process_matrix, supervisor_validation, authority_ledger)
    return all(
        (
            bool(_mapping(binding.get("outbox")).get("profile_hash")),
            bool(_mapping(binding.get("outbox")).get("config_hashes")),
            bool(_mapping(binding.get("outbox")).get("raw_evidence_hash")),
            bool(_mapping(binding.get("outbox")).get("source_hashes")),
            bool(_mapping(binding.get("outbox")).get("artifact_paths")),
            bool(_mapping(binding.get("process")).get("source_hashes")),
            bool(_mapping(binding.get("process")).get("artifact_hashes")),
            bool(_mapping(binding.get("process")).get("artifact_paths")),
            bool(_mapping(binding.get("supervisor")).get("manifests")),
            bool(_mapping(binding.get("supervisor")).get("source_hashes")),
            bool(_mapping(binding.get("authority")).get("source_hashes")),
        )
    )


def _current_sources_and_artifacts(
    evidence: Mapping[str, Any],
    outbox_report: Mapping[str, Any],
    process_matrix: Mapping[str, Any],
    supervisor_validation: Mapping[str, Any],
    authority_ledger: Mapping[str, Any],
    *,
    project_root: Path,
    artifact_root: Path,
) -> bool:
    for source_hashes in (
        _mapping(outbox_report.get("source_hashes")),
        _mapping(process_matrix.get("source_hashes")),
        _mapping(authority_ledger.get("source_hashes")),
    ):
        if set(source_hashes) != EXPECTED_SOURCE_BINDINGS or not _source_hashes_current(project_root, source_hashes):
            return False
    supervisor_sources = _mapping(supervisor_validation.get("source_hashes"))
    if set(supervisor_sources) != EXPECTED_MANIFEST_BINDINGS or not _source_hashes_current(
        project_root, supervisor_sources
    ):
        return False

    outbox_paths = _mapping(outbox_report.get("artifact_paths"))
    process_paths = _mapping(process_matrix.get("artifact_paths"))
    artifact_hashes = _mapping(process_matrix.get("artifact_hashes"))
    expected_documents: dict[str, Mapping[str, Any]] = {
        "outbox_report": outbox_report,
        "process_matrix": process_matrix,
        "supervisor_validation": supervisor_validation,
        "authority_ledger": authority_ledger,
        "release_evidence": evidence,
    }
    if set(outbox_paths) != set(expected_documents):
        return False
    for name, expected_document in expected_documents.items():
        path = _safe_relative_path(artifact_root, outbox_paths.get(name))
        if path is None or not _json_document_current(path, expected_document):
            return False
    if not process_paths or set(artifact_hashes) != set(process_paths):
        return False
    if not all(_bound_file_current(artifact_root, process_paths.get(name), expected) for name, expected in artifact_hashes.items()):
        return False

    raw_files = _mapping(_mapping(outbox_report.get("raw_evidence")).get("files"))
    if not raw_files or not all(_bound_file_current(artifact_root, path, expected) for path, expected in raw_files.items()):
        return False
    if not all(_safe_relative_path(artifact_root, artifact) is not None for artifact in EXPECTED_ARTIFACTS):
        return False
    return True


def _json_document_current(path: Path, expected: Mapping[str, Any]) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value == dict(expected)


def _source_hashes_current(root: Path, source_hashes: Mapping[str, Any]) -> bool:
    return bool(source_hashes) and all(
        _bound_file_current(root, relative, expected_hash) for relative, expected_hash in source_hashes.items()
    )


def _bound_file_current(root: Path, relative: object, expected_hash: object) -> bool:
    path = _safe_relative_path(root, relative)
    if path is None or not path.is_file() or path.is_symlink() or not isinstance(expected_hash, str):
        return False
    try:
        return stable_hash(path.read_bytes().hex()) == expected_hash
    except OSError:
        return False


def _safe_relative_path(root: Path, relative: object) -> Path | None:
    if not _safe_relative_text(relative):
        return None
    current = root
    for component in Path(str(relative)).parts:
        current = current / component
        if current.is_symlink():
            return None
    try:
        resolved = current.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_relative_to(root) else None


def _safe_relative_text(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _self_hash_current(value: Mapping[str, Any], field: str) -> bool:
    return value.get(field) == stable_hash({key: item for key, item in value.items() if key != field})


def _runtime_authority_exact_zero(authority: Mapping[str, Any]) -> bool:
    counters = _mapping(authority.get("counters"))
    return (
        authority.get("exact_zero") is True
        and set(counters) == set(P121_AUTHORITY_COUNTER_KEYS)
        and all(_exact_int(counters.get(key), 0) for key in P121_AUTHORITY_COUNTER_KEYS)
    )


def _evaluator_authority_exact_zero(authority: Mapping[str, Any]) -> bool:
    counters = _mapping(authority.get("counters"))
    return (
        authority.get("exact_zero") is True
        and set(counters) == set(ZERO_AUTHORITY_COUNTERS)
        and all(_exact_int(counters.get(key), 0) for key in ZERO_AUTHORITY_COUNTERS)
    )


def _evaluator_activity_disclosed(ledger: Mapping[str, Any]) -> bool:
    return _evaluator_activity_counters_valid(_mapping(ledger.get("evaluator_activity")))


def _evaluator_activity_counters_valid(activity: Mapping[str, Any]) -> bool:
    expected = set(EVALUATOR_ACTIVITY_COUNTERS)
    return (
        set(activity) == expected
        and all(type(activity.get(key)) is int and int(activity[key]) >= 0 for key in expected)
        and _exact_positive_int(activity.get("process_launch_count"))
        and activity.get("signal_count") == int(activity.get("sigterm_count", 0)) + int(activity.get("sigint_count", 0))
        and _exact_positive_int(activity.get("sigterm_count"))
        and _exact_int(activity.get("sigint_count"), 0)
    )


def _sha256_text(value: object) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdef" for character in value[7:]
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _exact_int(value: object, expected: object) -> bool:
    return type(value) is int and type(expected) is int and value == expected


def _exact_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


__all__ = [
    "P133_BLOCKED_STATUS",
    "P133_READY_STATUS",
    "P133ReleaseEvidenceError",
    "build_p133_release_evidence",
    "validate_p133_release_evidence",
]
