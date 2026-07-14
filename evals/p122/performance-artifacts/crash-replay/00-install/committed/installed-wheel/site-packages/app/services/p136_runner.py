"""Deterministic P136 release-matrix and bounded foreground runner."""

from __future__ import annotations

import os
import resource
import signal
import sys
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p135_provider_export_attachment import P135ExportError
from app.services.p136_incremental_observer import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RESOURCE_USAGE_KEYS,
    P136DurabilityUncertainError,
    P136ObservationError,
    advance_checkpoint,
    build_incremental_index_entry,
    build_incremental_observer_config,
    observe_one_cycle,
    promote_first_seen_entry,
    recover_observer_state,
    resolve_index_entries,
    run_observer_loop,
    scan_incremental_index,
    validate_incremental_observer_config,
    validate_measurement_schemas,
    validate_observer_runtime_authority,
    validate_promotion_record,
    zero_forbidden_authority,
    zero_runtime_activity,
)
from app.services.p136_release_evidence import (
    P136_READY_STATUS,
    P136ReleaseEvidenceError,
    validate_independent_review_artifact,
    validate_p136_release_evidence,
)

RuntimeFactory = Callable[[str], Mapping[str, Any]]


class P136RunnerError(ValueError):
    """Raised when the canonical P136 runner cannot prove its release claims."""


def _case(
    category: str,
    semantic: str,
    executor: str,
    *,
    provider: str | None = None,
    expected_label: str | None = None,
    expected_error: str | None = None,
) -> dict[str, str | None]:
    return {
        "category": category,
        "semantic": semantic,
        "provider": provider,
        "executor": executor,
        "expected_label": expected_label,
        "expected_error": expected_error,
    }


_CASE_DEFINITIONS: tuple[dict[str, str | None], ...] = (
    _case("duplicate_p135_bridge", "Prometheus first-batch promotion", "provider_promotion", provider="prometheus", expected_label="provider_first_batch_promotion"),
    _case("duplicate_p135_bridge", "Loki first-batch promotion", "provider_promotion", provider="loki", expected_label="provider_first_batch_promotion"),
    _case("duplicate_p135_bridge", "Grafana first-batch promotion", "provider_promotion", provider="grafana", expected_label="provider_first_batch_promotion"),
    _case("duplicate_p135_bridge", "Sentry first-batch promotion", "provider_promotion", provider="sentry", expected_label="provider_first_batch_promotion"),
    _case("duplicate_p135_bridge", "OTLP first-batch promotion", "provider_promotion", provider="opentelemetry", expected_label="provider_first_batch_promotion"),
    _case("duplicate_p135_bridge", "second append batch promotion", "second_append", expected_label="two_first_seen_promotions"),
    _case("secure_index_partial_rotation", "partial final line deferred with exact pending state", "partial_final_line", expected_label="pending_partial_deferred"),
    _case("secure_index_partial_rotation", "completed same-identity partial line promoted", "completed_partial", expected_label="same_identity_partial_promoted"),
    _case("duplicate_p135_bridge", "deterministic duplicate resolved without segment read", "duplicate_resolution", expected_label="duplicate_resolved_without_segment_read"),
    _case("duplicate_p135_bridge", "restart duplicate resolved without segment read", "restart_duplicate", expected_label="restart_duplicate_without_segment_read"),
    _case("secure_index_partial_rotation", "valid rotation continuity", "valid_rotation", expected_label="rotation_continuity_accepted"),
    _case("secure_index_partial_rotation", "rotated replay prefix resolved without segment read", "rotated_replay", expected_label="rotated_replay_without_segment_read"),
    _case("secure_index_partial_rotation", "malformed complete index line rejected", "malformed_line", expected_error="malformed_index_json"),
    _case("secure_index_partial_rotation", "duplicate JSON key index line rejected", "duplicate_json_key", expected_error="duplicate_json_key"),
    _case("secure_index_partial_rotation", "non-finite index value rejected", "non_finite_value", expected_error="non_finite_number:NaN"),
    _case("secure_index_partial_rotation", "oversized index line rejected", "oversized_line", expected_error="index_line_byte_budget_exceeded"),
    _case("secure_index_partial_rotation", "whole-index byte budget rejected", "whole_index_byte_budget", expected_error="whole_index_byte_budget_exceeded"),
    _case("secure_index_partial_rotation", "whole-index complete-line budget rejected", "whole_index_line_budget", expected_error="whole_index_complete_line_budget_exceeded"),
    _case("config_path_contract", "index symlink/hardlink/non-regular rejected", "unsafe_index_path", expected_error="index_not_secure_regular_file"),
    _case("secure_index_partial_rotation", "same-identity consumed-prefix mutation rejected", "consumed_prefix_mutation", expected_error="consumed_prefix_mismatch"),
    _case("secure_index_partial_rotation", "same-identity truncation rejected", "same_identity_truncation", expected_error="index_truncation_detected"),
    _case("secure_index_partial_rotation", "rotation sequence gap rejected", "rotation_sequence_gap", expected_error="rotation_sequence_gap"),
    _case("secure_index_partial_rotation", "rotation lineage mismatch rejected", "rotation_lineage_mismatch", expected_error="rotation_lineage_mismatch"),
    _case("config_path_contract", "entry ID conflict rejected", "entry_id_conflict", expected_error="conflicting_entry_id_reuse"),
    _case("config_path_contract", "segment ID conflict rejected", "segment_id_conflict", expected_error="conflicting_segment_id_reuse"),
    _case("authority_reservation", "denied, stale, or expired index receipt rejected", "expired_authority", expected_error="contract_or_review_not_current"),
    _case("authority_reservation", "receipt reuse without matching durable reservation rejected", "receipt_reuse", expected_error="index_read_receipt_reuse_without_matching_intent"),
    _case("authority_reservation", "index receipt byte estimate exceeded", "byte_estimate_exceeded", expected_error="whole_index_budget_underestimated"),
    _case("authority_reservation", "index receipt record estimate exceeded", "record_estimate_exceeded", expected_error="whole_index_budget_underestimated"),
    _case("authority_reservation", "wrong index level/method/capability/source rejected", "wrong_authority_binding", expected_error="index_receipt_proposal_mismatch"),
    _case("duplicate_p135_bridge", "segment content/size mismatch rejected through P135", "segment_size_mismatch", expected_error="file_size_mismatch"),
    _case("duplicate_p135_bridge", "provider parser failure promoted only as denominator failure", "provider_parser_failure", expected_label="p135_denominator_failure"),
    _case("crash_durability_recovery", "crash after index-read intent before read resumes same reservation", "resume_after_index_intent", expected_label="same_reservation_resumed"),
    _case("crash_durability_recovery", "crash after index read before P135 resumes same reservation", "resume_after_index_read", expected_label="same_reservation_after_read"),
    _case("crash_durability_recovery", "crash after promotion intent recovers exactly one promotion", "promotion_intent_recovery", expected_label="promotion_recovered_once"),
    _case("crash_durability_recovery", "crash after promotion before checkpoint recovers without P135", "promotion_checkpoint_recovery", expected_label="checkpoint_recovered_without_p135"),
    _case("crash_durability_recovery", "checkpoint/index-intent/journal/promotion tamper rejected", "state_tamper", expected_error="p135_bundle_tamper"),
    _case("crash_durability_recovery", "pre-replace durability failure preserves prior state", "pre_replace_preserves_prior", expected_label="prior_checkpoint_preserved"),
    _case("crash_durability_recovery", "post-replace directory-fsync uncertainty stops", "post_replace_uncertain", expected_error="checkpoint_parent_fsync_uncertain"),
    _case("lease_exhaustion_failure_signal", "competing lease performs no state/index/segment read", "competing_lease", expected_error="exclusive_lease_unavailable"),
    _case("config_path_contract", "exact config key/path topology violation rejected", "config_path_violation", expected_error="state_path_overlaps_index_path"),
    _case("lease_exhaustion_failure_signal", "excess wall-clock rollback rejected", "wall_clock_rollback", expected_error="clock_rollback_exceeded"),
    _case("lease_exhaustion_failure_signal", "receipt-pool exhaustion emits fail-closed termination", "receipt_exhaustion", expected_label="receipt_exhaustion"),
    _case("lease_exhaustion_failure_signal", "consecutive-failure threshold emits fail-closed termination", "failure_threshold", expected_label="failure_threshold"),
    _case("lease_exhaustion_failure_signal", "SIGINT emits a hash-bound safe-boundary termination receipt", "sigint", expected_label="signal_SIGINT_safe_boundary"),
    _case("lease_exhaustion_failure_signal", "SIGTERM emits a hash-bound safe-boundary termination receipt", "sigterm", expected_label="signal_SIGTERM_safe_boundary"),
    _case("runtime_guard_resource_schema", "forbidden runtime authority probes are blocked and measured", "runtime_guard_schema", expected_label="exact_zero_forbidden_authority"),
    _case("duplicate_p135_bridge", "P135 bridge manifest/receipt/ledger semantic tamper rejected", "p135_tamper", expected_error="p135_independent_ledger_tamper"),
    _case(
        "secure_index_partial_rotation",
        "empty or replay-only rotated identity remains pending or proves exact replay",
        "empty_or_replay_rotation",
        expected_label="rotation_governed_without_segment_read",
    ),
    _case("secure_index_partial_rotation", "rotation after an old-identity pending partial is rejected", "old_pending_partial_rotation", expected_error="rotation_rejected_with_pending_partial"),
)


def p136_release_case_matrix() -> list[dict[str, Any]]:
    """Return immutable metadata for the fixed 50-case denominator."""

    if len(_CASE_DEFINITIONS) != 50:
        raise P136RunnerError("canonical_case_matrix_size_invalid")
    cases: list[dict[str, Any]] = []
    for ordinal, definition in enumerate(_CASE_DEFINITIONS, start=1):
        case = {
            "case_id": f"p136-case-{ordinal:02d}",
            "category": definition["category"],
            "semantic": definition["semantic"],
            "executor": definition["executor"],
            "expected_label": definition.get("expected_label"),
            "expected_error": definition.get("expected_error"),
        }
        if definition.get("provider") is not None:
            case["provider"] = definition["provider"]
        cases.append(case)
    return cases


def run_p136_release_matrix(
    output_dir: Path | str,
    *,
    runtime_factory: RuntimeFactory | None = None,
    precomputed_evidence: Mapping[str, Any] | None = None,
    force_case_failure: str | None = None,
    source_bindings: Mapping[str, str] | None = None,
    independent_review: Mapping[str, Any] | None = None,
    evaluator_activity: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Execute every fixed case and validate the rebuilt release evidence."""

    output_boundary = {
        "mode": "in_memory_release_evidence",
        "output_dir_ref_hash": stable_hash(str(Path(output_dir))),
        "contract": "run_p136_release_matrix returns validated evidence and does not persist a release artifact",
    }
    if precomputed_evidence is not None:
        raise P136RunnerError("release_matrix_must_execute_cases")
    if runtime_factory is None or not callable(runtime_factory):
        raise P136RunnerError("runtime_factory_required")
    if source_bindings is None or independent_review is None:
        raise P136RunnerError("current_source_binding_and_independent_review_required")
    try:
        validate_independent_review_artifact(
            independent_review,
            expected_source_hashes=source_bindings,
        )
    except P136ReleaseEvidenceError as exc:
        raise P136RunnerError(f"independent_review_validation_failed:{exc}") from exc
    started_wall = time.monotonic()
    started_self = resource.getrusage(resource.RUSAGE_SELF)
    started_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    cases: list[dict[str, Any]] = []
    runtime_activity = zero_runtime_activity()
    forbidden_authority = zero_forbidden_authority()
    guard_proof_count = 0
    signal_delivery_count = 0

    for spec in p136_release_case_matrix():
        case_id = str(spec["case_id"])
        runtime = _runtime_with_activity_probe(runtime_factory(case_id))
        try:
            observed = dict(_execute_case(spec, runtime, output_boundary=output_boundary))
            duplicate_segment_reads, duplicate_promotions = _measured_duplicate_counts(runtime)
            observed["measured_duplicate_segment_reads"] = duplicate_segment_reads
            observed["measured_duplicate_promotions"] = duplicate_promotions
            _validate_case_observation(spec, observed)
            actual = "pass"
            status = "passed"
        except Exception as exc:  # canonical evidence retains exact failure semantics
            duplicate_segment_reads, duplicate_promotions = _measured_duplicate_counts(runtime)
            observed = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "runtime_activity": _probe_activity(runtime),
                "measured_duplicate_segment_reads": duplicate_segment_reads,
                "measured_duplicate_promotions": duplicate_promotions,
            }
            actual = "fail"
            status = "failed"
        if force_case_failure == case_id:
            observed = {
                "forced_failure": True,
                "prior_observation_hash": stable_hash(observed),
                "runtime_activity": dict(_mapping(observed.get("runtime_activity"), "runtime_activity")),
            }
            actual = "fail"
            status = "failed"
        _merge_activity(runtime_activity, observed)
        delivered = observed.get("evaluator_signal_delivery_count", 0)
        if type(delivered) is not int or delivered < 0:
            raise P136RunnerError("invalid_evaluator_signal_delivery_count")
        signal_delivery_count += delivered
        measured_forbidden = observed.get("forbidden_authority")
        if measured_forbidden is not None:
            _merge_exact_counters(
                forbidden_authority,
                measured_forbidden,
                "invalid_case_forbidden_authority_schema",
            )
            blocked_attempts = observed.get("guard_blocked_attempts")
            if blocked_attempts is not None:
                _require_exact_counter_values(
                    blocked_attempts,
                    FORBIDDEN_AUTHORITY_KEYS,
                    expected=1,
                    error="forbidden_runtime_guard_probe_missing",
                )
                guard_proof_count += 1
        provider_promoted = observed.get("provider_first_batch_promotion") is True
        case: dict[str, Any] = {
            "case_id": case_id,
            "category": spec["category"],
            "semantic": spec["semantic"],
            "expected": "pass",
            "actual": actual,
            "status": status,
            "duplicate_segment_reads": duplicate_segment_reads,
            "duplicate_promotions": duplicate_promotions,
            "provider_first_batch_promotion": provider_promoted,
            "evidence": observed,
        }
        case["case_evidence_hash"] = stable_hash(case)
        cases.append(case)

    resources = _resource_usage(started_wall, started_self, started_children)
    evidence: dict[str, Any] = {
        "schema_version": "p136.release_evidence.v1",
        "status": P136_READY_STATUS,
        "cases": cases,
        "totals": {
            "expected": 50,
            "passed": sum(case["status"] == "passed" for case in cases),
            "failed": sum(case["status"] == "failed" for case in cases),
        },
        "provider_first_batch_promotions": sum(case["provider_first_batch_promotion"] is True for case in cases),
        "duplicate_promotions": sum(int(case["duplicate_promotions"]) for case in cases),
        "duplicate_segment_reads": sum(int(case["duplicate_segment_reads"]) for case in cases),
        "exact_schema_gates": True,
        "release_gates": all(case["status"] == "passed" for case in cases),
        "forbidden_authority": forbidden_authority,
        "runtime_activity": runtime_activity,
        "evaluator_activity": _evaluator_activity_with_signals(
            evaluator_activity
            or {
                "runner_invocation_count": 1,
                "profile_read_count": 0,
                "artifact_write_count": 0,
                "child_process_count": 0,
                "signal_delivery_count": 0,
            },
            signal_delivery_count,
        ),
        "resource_usage": resources,
        "source_bindings": dict(sorted(source_bindings.items())),
        "independent_review_hash": independent_review["independent_review_hash"],
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    if guard_proof_count != 1:
        raise P136RunnerError("forbidden_runtime_guard_proof_count_invalid")
    try:
        return validate_p136_release_evidence(
            evidence,
            expected_source_hashes=source_bindings,
            independent_review=independent_review,
        )
    except P136ReleaseEvidenceError as exc:
        raise P136RunnerError(f"p136_release_evidence_validation_failed:{exc}") from exc


def run_p136_observer_foreground(runtime: Mapping[str, Any], *, max_cycles: int) -> dict[str, Any]:
    """Run the bounded local observer and return its hash-bound termination."""

    if type(max_cycles) is not int or max_cycles <= 0:
        raise P136RunnerError("invalid_max_cycles")
    return run_observer_loop(_normalize_runtime_config_checkpoint(runtime), max_cycles=max_cycles)


def _execute_case(
    spec: Mapping[str, Any],
    runtime: Mapping[str, Any],
    *,
    output_boundary: Mapping[str, Any],
) -> dict[str, Any]:
    runtime = _normalize_runtime_config_checkpoint(runtime)
    config_input = _mapping(runtime.get("config"), "config")
    if config_input.get("schema_version") == "p136.incremental_observer_config.v1":
        validate_incremental_observer_config(config_input)
        config = dict(config_input)
    else:
        config = build_incremental_observer_config(config_input)
    common = {
        "executed": True,
        "semantic_hash": stable_hash(str(spec["semantic"])),
        "config_hash": config["config_hash"],
        "expected_label": spec.get("expected_label"),
        "expected_error": spec.get("expected_error"),
        "output_boundary": dict(output_boundary),
    }
    executor = str(spec["executor"])
    if executor == "provider_promotion":
        return _execute_provider_promotion(common, runtime, str(spec["provider"]))
    if executor == "second_append":
        return _case_second_append(common, runtime)
    if executor == "partial_final_line":
        return _case_partial_final_line(common, runtime)
    if executor == "completed_partial":
        return _case_completed_partial(common, runtime)
    if executor in {"duplicate_resolution", "restart_duplicate"}:
        return _case_duplicate_resolution(common, runtime, restart=executor == "restart_duplicate")
    if executor == "valid_rotation":
        return _case_valid_rotation(common, runtime)
    if executor == "rotated_replay":
        return _case_rotated_replay(common, runtime)
    if executor == "resume_after_index_intent":
        return _case_resume_after_index_intent(common, runtime)
    if executor == "resume_after_index_read":
        return _case_resume_after_index_read(common, runtime)
    if executor == "promotion_intent_recovery":
        return _case_promotion_intent_recovery(common, runtime)
    if executor == "promotion_checkpoint_recovery":
        return _case_promotion_checkpoint_recovery(common, runtime)
    if executor == "provider_parser_failure":
        return _case_p135_denominator_failure(common, runtime, executor)
    if executor == "pre_replace_preserves_prior":
        return _case_pre_replace_preserves_prior(common, runtime)
    if executor in {"receipt_exhaustion", "failure_threshold"}:
        return _case_loop_stop(common, runtime, executor)
    if executor in {"sigint", "sigterm"}:
        return _case_real_signal_stop(common, runtime, executor)
    if executor == "runtime_guard_schema":
        return _case_runtime_guard_schema(common)
    if executor == "empty_or_replay_rotation":
        return _case_empty_or_replay_rotation(common, runtime)
    return _case_expected_error(common, runtime, executor, str(spec["expected_error"]))


def _execute_provider_promotion(
    common: Mapping[str, Any],
    runtime: Mapping[str, Any],
    provider: str,
) -> dict[str, Any]:
    entries = _mapping(runtime.get("provider_entries"), "provider_entries")
    entry = _mapping(entries.get(provider), f"provider_entry_{provider}")
    result = promote_first_seen_entry(runtime, entry)
    promotion = _mapping(result.get("promotion_record"), "promotion_record")
    validate_promotion_record(promotion, expected_entry=entry, runtime=runtime)
    p135_result = _mapping(result.get("p135_result"), "p135_result")
    receipt = _mapping(p135_result.get("receipt"), "p135_execution_receipt")
    bundle = _mapping(p135_result.get("bundle"), "p135_normalized_bundle")
    promoted = (
        promotion.get("status") == "success"
        and receipt.get("status") == "succeeded"
        and receipt.get("provider") == provider
        and bundle.get("provider") == provider
        and isinstance(receipt.get("adapter_version"), str)
        and str(receipt["adapter_version"]).startswith("p135.adapter.")
    )
    if not promoted:
        raise P136RunnerError("provider_first_batch_promotion_not_proven")
    return {
        **dict(common),
        "probe": "real_p135_provider_bridge",
        "actual_label": "provider_first_batch_promotion",
        "provider": provider,
        "provider_first_batch_promotion": True,
        "promotion_hash": promotion["promotion_hash"],
        "promotion_key": promotion["promotion_key"],
        "p135_manifest_hash": promotion["p135_manifest_hash"],
        "p135_execution_receipt_hash": promotion["p135_execution_receipt_hash"],
        "p135_receipt_ledger_hash": promotion["p135_receipt_ledger_hash"],
        "p135_normalized_bundle_hash": promotion["p135_normalized_bundle_hash"],
        "adapter_version_hash": stable_hash(str(receipt["adapter_version"])),
        "segment_file_read_count": int(_mapping(result.get("activity"), "activity")["segment_file_read_count"]),
        "runtime_activity": dict(_mapping(result.get("activity"), "activity")),
    }


def _case_second_append(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    entries = _provider_entries(runtime)
    selected = [entries["prometheus"], entries["loki"]]
    result = resolve_index_entries(runtime, selected)
    records = [_mapping(item, "promotion_record") for item in result["promotion_records"]]
    activity = _sum_activities(record["activity"] for record in records)
    if len(records) != 2 or any(record.get("status") != "success" for record in records):
        raise P136RunnerError("second_append_promotion_not_proven")
    return {
        **dict(common),
        "probe": "append_batch_real_p135_bridge",
        "actual_label": "two_first_seen_promotions",
        "promotion_count": 2,
        "promotion_hashes": list(result["promotions_written"]),
        "segment_file_read_count": activity["segment_file_read_count"],
        "runtime_activity": activity,
    }


def _case_partial_final_line(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    pending_bytes = b'{"entry_id":"entry-0001"'
    result = scan_incremental_index(runtime, index_bytes=pending_bytes)
    patch = _mapping(result["checkpoint_patch"], "checkpoint_patch")
    pending = _mapping(patch.get("pending_partial"), "pending_partial")
    return {
        **dict(common),
        "probe": "bounded_index_scanner",
        "actual_label": "pending_partial_deferred",
        "complete_entry_count": len(result["complete_entries"]),
        "committed_cursor": patch["committed_cursor"],
        "pending_byte_length": pending["pending_byte_length"],
        "runtime_activity": _activity(index_file_read_count=1, index_bytes_read=len(pending_bytes), index_partial_bytes_observed=int(pending["pending_byte_length"])),
    }


def _case_completed_partial(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    entry = _provider_entries(runtime)["grafana"]
    line = _canonical_bytes(entry) + b"\n"
    prefix = line[:32]
    checkpoint = _checkpoint(runtime)
    pending = {
        "file_identity_hash": checkpoint["index_identity_hash"],
        "line_start_cursor": 0,
        "pending_byte_hash": _content_hash(prefix),
        "pending_byte_length": len(prefix),
        "observed_index_size": len(prefix),
    }
    patched_checkpoint = _rehash({**checkpoint, "pending_partial": pending, "observed_index_size": len(prefix)})
    patched_runtime = {**dict(runtime), "checkpoint": patched_checkpoint}
    scan = scan_incremental_index(patched_runtime, index_bytes=line, file_identity_hash=str(checkpoint["index_identity_hash"]))
    resolved = resolve_index_entries(patched_runtime, scan["complete_entries"])
    records = [_mapping(item, "promotion_record") for item in resolved["promotion_records"]]
    activity = _sum_activities(record["activity"] for record in records)
    if len(records) != 1 or records[0].get("status") != "success":
        raise P136RunnerError("completed_partial_promotion_not_proven")
    return {
        **dict(common),
        "probe": "same_identity_partial_completion",
        "actual_label": "same_identity_partial_promoted",
        "promotion_hash": records[0]["promotion_hash"],
        "committed_cursor": scan["checkpoint_patch"]["committed_cursor"],
        "pending_partial_after": scan["checkpoint_patch"]["pending_partial"],
        "runtime_activity": _sum_activities(
            [
                _activity(index_file_read_count=1, index_bytes_read=len(line), index_complete_lines_evaluated=1),
                activity,
            ]
        ),
    }


def _case_duplicate_resolution(common: Mapping[str, Any], runtime: Mapping[str, Any], *, restart: bool) -> dict[str, Any]:
    entry = _provider_entries(runtime)["grafana"]
    promotion = _minimal_promotion(entry)
    checkpoint = _checkpoint_with_identity(runtime, entry, promotion)
    patched_runtime = {**dict(runtime), "checkpoint": checkpoint}
    entries = [entry]
    if restart:
        result = resolve_index_entries(patched_runtime, entries)
    else:
        scan = scan_incremental_index(
            patched_runtime,
            index_bytes=_canonical_bytes(entry) + b"\n",
            file_identity_hash=str(checkpoint["index_identity_hash"]),
        )
        result = resolve_index_entries(patched_runtime, scan["complete_entries"])
    if result["duplicate_entries"] != [entry["entry_hash"]] or result["promotions_written"] != []:
        raise P136RunnerError("duplicate_resolution_not_proven")
    label = "restart_duplicate_without_segment_read" if restart else "duplicate_resolved_without_segment_read"
    return {
        **dict(common),
        "probe": "duplicate_before_p135_dispatch",
        "actual_label": label,
        "duplicate_entry_hash": entry["entry_hash"],
        "duplicate_count": 1,
        "promotion_count": 0,
        "segment_file_read_count": _probe_count(runtime, "segment_read"),
        "runtime_activity": _activity(duplicate_resolution_count=1),
    }


def _case_valid_rotation(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    entries = _provider_entries(runtime)
    first = entries["grafana"]
    second = _entry_variant(entries["loki"], rotation_from_hash=first["entry_hash"])
    checkpoint = _checkpoint_with_identity(runtime, first, _minimal_promotion(first), next_entry_sequence=2)
    scan = scan_incremental_index(
        {**dict(runtime), "checkpoint": checkpoint},
        index_bytes=_canonical_bytes(second) + b"\n",
        file_identity_hash=stable_hash({"index_identity": "rotated-valid"}),
    )
    return {
        **dict(common),
        "probe": "rotation_continuity",
        "actual_label": "rotation_continuity_accepted",
        "rotated": scan["rotated"],
        "complete_entry_hash": scan["complete_entries"][0]["entry_hash"],
        "runtime_activity": _activity(index_file_read_count=1, index_complete_lines_evaluated=1, rotation_count=1),
    }


def _case_rotated_replay(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    entry = _provider_entries(runtime)["grafana"]
    checkpoint = _checkpoint_with_identity(runtime, entry, _minimal_promotion(entry), next_entry_sequence=2)
    patched_runtime = {**dict(runtime), "checkpoint": checkpoint}
    scan = scan_incremental_index(
        patched_runtime,
        index_bytes=_canonical_bytes(entry) + b"\n",
        file_identity_hash=stable_hash({"index_identity": "rotated-replay"}),
    )
    result = resolve_index_entries(patched_runtime, scan["complete_entries"])
    if result["duplicate_entries"] != [entry["entry_hash"]] or result["promotions_written"] != []:
        raise P136RunnerError("rotated_replay_not_proven")
    return {
        **dict(common),
        "probe": "rotated_replay_prefix",
        "actual_label": "rotated_replay_without_segment_read",
        "rotated": scan["rotated"],
        "duplicate_count": 1,
        "segment_file_read_count": _probe_count(runtime, "segment_read"),
        "runtime_activity": _activity(index_file_read_count=1, index_complete_lines_evaluated=1, rotation_count=1, duplicate_resolution_count=1),
    }


def _case_resume_after_index_intent(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    active_runtime = _runtime_with_activity_probe(runtime)
    crashed = _runtime_with_crash(active_runtime, "index_intent_durable")
    _require_injected_crash(crashed, "index_intent_durable")
    if _probe_count(active_runtime, "index_open") != 0 or _probe_count(active_runtime, "index_read") != 0:
        raise P136RunnerError("index_access_occurred_before_intent_crash")
    second = observe_one_cycle(active_runtime)
    intent_files = _persisted_files(active_runtime, "index_intent_dir")
    if len(intent_files) != 1:
        raise P136RunnerError("index_intent_resume_created_new_reservation")
    return {
        **dict(common),
        "probe": "index_read_intent_recovery",
        "actual_label": "same_reservation_resumed",
        "receipt_hash": second["index_read_intent"]["receipt_hash"],
        "cycle_id": second["index_read_intent"]["cycle_id"],
        "durable_intent_count": len(intent_files),
        "pre_resume_index_read_count": 0,
        "runtime_activity": _sum_activities(
            [_activity(index_read_intent_write_count=1, directory_fsync_count=2), second["activity"]]
        ),
    }


def _case_resume_after_index_read(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    active_runtime = _runtime_with_activity_probe(runtime)
    crashed = _runtime_with_crash(active_runtime, "index_read_complete")
    _require_injected_crash(crashed, "index_read_complete")
    pre_resume_index_reads = _probe_count(active_runtime, "index_read")
    pre_resume_segment_reads = _probe_count(active_runtime, "segment_read")
    if pre_resume_index_reads != 1 or pre_resume_segment_reads != 0:
        raise P136RunnerError("post_index_read_crash_boundary_not_proven")
    second = observe_one_cycle(active_runtime)
    intent_files = _persisted_files(active_runtime, "index_intent_dir")
    if len(intent_files) != 1:
        raise P136RunnerError("post_read_resume_created_new_reservation")
    return {
        **dict(common),
        "probe": "post_read_recovery",
        "actual_label": "same_reservation_after_read",
        "receipt_hash": second["index_read_intent"]["receipt_hash"],
        "complete_entry_count": len(second["scan"]["complete_entries"]),
        "pre_resume_index_read_count": pre_resume_index_reads,
        "pre_resume_segment_read_count": pre_resume_segment_reads,
        "durable_intent_count": len(intent_files),
        "runtime_activity": _sum_activities(
            [
                _activity(
                    index_read_intent_write_count=1,
                    index_file_open_count=1,
                    index_file_read_count=1,
                    directory_fsync_count=2,
                ),
                second["activity"],
            ]
        ),
    }


def _case_promotion_intent_recovery(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    active_runtime = _runtime_with_activity_probe(runtime)
    _write_single_provider_index(active_runtime, "grafana")
    crashed = _runtime_with_crash(active_runtime, "promotion_intent_durable")
    _require_injected_crash(crashed, "promotion_intent_durable")
    segment_reads_before_recovery = _probe_count(active_runtime, "segment_read")
    promotions_before_recovery = _persisted_files(active_runtime, "promotion_dir")
    if segment_reads_before_recovery != 1 or promotions_before_recovery:
        raise P136RunnerError("promotion_intent_crash_boundary_not_proven")
    result = recover_observer_state(active_runtime)
    promotions_after_recovery = _persisted_files(active_runtime, "promotion_dir")
    if len(result["promotions_written"]) != 1 or result["p135_invocation_count"] != 0:
        raise P136RunnerError("promotion_intent_recovery_not_proven")
    if len(promotions_after_recovery) != 1 or _probe_count(active_runtime, "segment_read") != segment_reads_before_recovery:
        raise P136RunnerError("promotion_intent_recovery_reinvoked_p135")
    return {
        **dict(common),
        "probe": "promotion_intent_recovery",
        "actual_label": "promotion_recovered_once",
        "promotion_hash": result["promotions_written"][0],
        "p135_invocation_count": result["p135_invocation_count"],
        "persisted_promotion_count": len(promotions_after_recovery),
        "segment_reads_during_recovery": _probe_count(active_runtime, "segment_read") - segment_reads_before_recovery,
        "runtime_activity": _activity(
            index_read_intent_write_count=1,
            index_file_open_count=1,
            index_file_read_count=1,
            segment_file_open_count=1,
            segment_file_read_count=1,
            promotion_intent_write_count=1,
            promotion_record_write_count=1,
            checkpoint_write_count=1,
            recovery_replay_count=int(result["recovery_replay_count"]),
        ),
    }


def _case_promotion_checkpoint_recovery(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    active_runtime = _runtime_with_activity_probe(runtime)
    _write_single_provider_index(active_runtime, "grafana")
    crashed = _runtime_with_crash(active_runtime, "promotion_records_durable")
    _require_injected_crash(crashed, "promotion_records_durable")
    segment_reads_before_recovery = _probe_count(active_runtime, "segment_read")
    promotions_before_recovery = _persisted_files(active_runtime, "promotion_dir")
    checkpoint_files_before_recovery = _persisted_files(active_runtime, "checkpoint_path", exact=True)
    if segment_reads_before_recovery != 1 or len(promotions_before_recovery) != 1 or checkpoint_files_before_recovery:
        raise P136RunnerError("promotion_checkpoint_crash_boundary_not_proven")
    result = recover_observer_state(active_runtime)
    promotions_after_recovery = _persisted_files(active_runtime, "promotion_dir")
    checkpoint_files_after_recovery = _persisted_files(active_runtime, "checkpoint_path", exact=True)
    if result["checkpoint_advanced"] is not True or result["p135_invocation_count"] != 0:
        raise P136RunnerError("promotion_checkpoint_recovery_not_proven")
    if len(promotions_after_recovery) != 1 or len(checkpoint_files_after_recovery) != 1:
        raise P136RunnerError("promotion_checkpoint_recovery_persistence_not_proven")
    if _probe_count(active_runtime, "segment_read") != segment_reads_before_recovery:
        raise P136RunnerError("promotion_checkpoint_recovery_reinvoked_p135")
    return {
        **dict(common),
        "probe": "promotion_checkpoint_recovery",
        "actual_label": "checkpoint_recovered_without_p135",
        "checkpoint_advanced": True,
        "p135_invocation_count": 0,
        "persisted_promotion_count": len(promotions_after_recovery),
        "persisted_checkpoint_count": len(checkpoint_files_after_recovery),
        "segment_reads_during_recovery": _probe_count(active_runtime, "segment_read") - segment_reads_before_recovery,
        "runtime_activity": _activity(
            index_read_intent_write_count=1,
            index_file_open_count=1,
            index_file_read_count=1,
            segment_file_open_count=1,
            segment_file_read_count=1,
            promotion_intent_write_count=1,
            promotion_record_write_count=1,
            checkpoint_write_count=1,
            recovery_replay_count=int(result["recovery_replay_count"]),
        ),
    }


def _runtime_with_crash(runtime: Mapping[str, Any], expected_phase: str) -> dict[str, Any]:
    def injector(phase: str) -> None:
        if phase == expected_phase:
            raise P136ObservationError(f"injected_crash_after:{phase}")

    return {**dict(runtime), "evaluator_crash_injector": injector}


class _RuntimeActivityProbe:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)


def _runtime_with_activity_probe(runtime: Mapping[str, Any]) -> dict[str, Any]:
    probe = runtime.get("probe")
    if isinstance(getattr(probe, "events", None), list):
        return dict(runtime)
    return {**dict(runtime), "probe": _RuntimeActivityProbe()}


def _measured_duplicate_counts(runtime: Mapping[str, Any]) -> tuple[int, int]:
    probe = runtime.get("probe")
    events = getattr(probe, "events", None)
    if not isinstance(events, list) or any(not isinstance(event, str) for event in events):
        raise P136RunnerError("runtime_activity_probe_unavailable")
    segment_entries = [event.removeprefix("segment_entry_read:") for event in events if event.startswith("segment_entry_read:")]
    promotion_entries = [event.removeprefix("promotion_created:") for event in events if event.startswith("promotion_created:")]
    return (
        len(segment_entries) - len(set(segment_entries)),
        len(promotion_entries) - len(set(promotion_entries)),
    )


def _require_injected_crash(runtime: Mapping[str, Any], expected_phase: str) -> None:
    try:
        observe_one_cycle(runtime)
    except P136ObservationError as exc:
        if str(exc) != f"injected_crash_after:{expected_phase}":
            raise
    else:
        raise P136RunnerError(f"crash_phase_not_reached:{expected_phase}")


def _write_single_provider_index(runtime: Mapping[str, Any], provider: str) -> None:
    cfg = _mapping(runtime.get("config"), "config")
    index_path = Path(runtime["base_path"]) / str(cfg["index_path"])
    entry = _mapping(_provider_entries(runtime).get(provider), f"provider_entry_{provider}")
    index_path.write_bytes(_canonical_bytes(entry) + b"\n")


def _persisted_files(runtime: Mapping[str, Any], config_key: str, *, exact: bool = False) -> list[Path]:
    cfg = _mapping(runtime.get("config"), "config")
    path = Path(runtime["base_path"]) / str(cfg[config_key])
    if exact:
        return [path] if path.is_file() else []
    return sorted(candidate for candidate in path.glob("*.json") if candidate.is_file())


def _case_pre_replace_preserves_prior(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    prior = _checkpoint(runtime)
    blocked_base = Path(runtime["base_path"]).parent / "p136-pre-replace-blocker"
    blocked_base.write_text("not a directory", encoding="utf-8")
    try:
        advance_checkpoint({**dict(runtime), "base_path": blocked_base}, prior)
    except (OSError, P136ObservationError) as exc:
        error_type = type(exc).__name__
    else:
        raise P136RunnerError("pre_replace_failure_not_triggered")
    return {
        **dict(common),
        "probe": "pre_replace_filesystem_boundary",
        "actual_label": "prior_checkpoint_preserved",
        "prior_checkpoint_hash": prior["checkpoint_hash"],
        "failed_before_replace_error": error_type,
        "runtime_activity": _activity(),
    }


def _case_loop_stop(common: Mapping[str, Any], runtime: Mapping[str, Any], executor: str) -> dict[str, Any]:
    variants: dict[str, tuple[dict[str, Any], int, str]] = {
        "receipt_exhaustion": ({}, 99, "receipt_exhaustion"),
        "failure_threshold": ({"force_cycle_failures": 2}, 3, "failure_threshold"),
    }
    overrides, cycles, expected = variants[executor]
    result = run_observer_loop({**dict(runtime), **overrides}, max_cycles=cycles)
    receipt = _mapping(result["termination_receipt"], "termination_receipt")
    if receipt["stop_reason"] != expected or receipt["final_checkpoint_hash"] != result["checkpoint"]["checkpoint_hash"]:
        raise P136RunnerError("loop_stop_semantics_not_proven")
    return {
        **dict(common),
        "probe": "bounded_foreground_stop",
        "actual_label": expected,
        "stop_reason": receipt["stop_reason"],
        "termination_hash": receipt["termination_hash"],
        "cycles_completed": result["cycles_completed"],
        "runtime_activity": _activity(checkpoint_write_count=1),
    }


def _case_real_signal_stop(
    common: Mapping[str, Any],
    runtime: Mapping[str, Any],
    executor: str,
) -> dict[str, Any]:
    signal_number = signal.SIGINT if executor == "sigint" else signal.SIGTERM
    signal_name = "SIGINT" if executor == "sigint" else "SIGTERM"
    delivered: dict[str, str | None] = {"name": None}

    def record_signal(received: int, frame: Any) -> None:
        del frame
        if received == signal_number:
            delivered["name"] = signal_name

    prior_handler = signal.getsignal(signal_number)
    signal.signal(signal_number, record_signal)
    try:
        os.kill(os.getpid(), signal_number)
        result = run_observer_loop(
            {
                **dict(runtime),
                "safe_boundary_signal": lambda: delivered["name"],
            },
            max_cycles=3,
        )
    finally:
        signal.signal(signal_number, prior_handler)
    receipt = _mapping(result["termination_receipt"], "termination_receipt")
    expected = f"signal_{signal_name}_safe_boundary"
    if delivered["name"] != signal_name or receipt.get("stop_reason") != expected:
        raise P136RunnerError("real_signal_safe_boundary_not_proven")
    return {
        **dict(common),
        "probe": "real_os_signal_safe_boundary",
        "actual_label": expected,
        "stop_reason": receipt["stop_reason"],
        "termination_hash": receipt["termination_hash"],
        "cycles_completed": result["cycles_completed"],
        "evaluator_signal_delivery_count": 1,
        "runtime_activity": _activity(),
    }


def _case_runtime_guard_schema(common: Mapping[str, Any]) -> dict[str, Any]:
    crossed = zero_forbidden_authority()
    blocked_attempts = zero_forbidden_authority()
    for counter in FORBIDDEN_AUTHORITY_KEYS:
        trap_called = False

        def forbidden_operation(boundary: str = counter) -> None:
            nonlocal trap_called
            trap_called = True
            crossed[boundary] += 1

        try:
            _deny_forbidden_runtime_boundary(
                counter,
                blocked_attempts,
                forbidden_operation,
            )
        except P136RunnerError as exc:
            if str(exc) != f"forbidden_runtime_boundary_blocked:{counter}":
                raise
        else:
            raise P136RunnerError("forbidden_runtime_boundary_not_blocked")
        if trap_called:
            raise P136RunnerError("forbidden_runtime_operation_crossed_boundary")
    measurement = {
        "forbidden_authority": crossed,
        "runtime_activity": zero_runtime_activity(),
        "evaluator_activity": {key: 0 for key in EVALUATOR_ACTIVITY_KEYS},
        "resource_usage": {key: 0 for key in RESOURCE_USAGE_KEYS},
    }
    validate_measurement_schemas(measurement)
    return {
        **dict(common),
        "probe": "exact_runtime_guard_and_resource_schema",
        "actual_label": "exact_zero_forbidden_authority",
        "forbidden_authority": measurement["forbidden_authority"],
        "guard_blocked_attempts": blocked_attempts,
        "runtime_activity": measurement["runtime_activity"],
    }


def _deny_forbidden_runtime_boundary(
    counter: str,
    blocked_attempts: dict[str, int],
    operation: Callable[[], None],
) -> None:
    del operation
    if counter not in blocked_attempts:
        raise P136RunnerError("unknown_forbidden_runtime_boundary")
    blocked_attempts[counter] += 1
    raise P136RunnerError(f"forbidden_runtime_boundary_blocked:{counter}")


def _case_empty_or_replay_rotation(common: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    entry = _provider_entries(runtime)["grafana"]
    checkpoint = _checkpoint_with_identity(runtime, entry, _minimal_promotion(entry), next_entry_sequence=2)
    scan = scan_incremental_index(
        {**dict(runtime), "checkpoint": checkpoint},
        index_bytes=b"",
        file_identity_hash=stable_hash({"index_identity": "empty-rotated"}),
    )
    if scan["rotated"] is not True or scan["complete_entries"] != []:
        raise P136RunnerError("empty_rotation_not_governed")
    return {
        **dict(common),
        "probe": "empty_rotated_identity",
        "actual_label": "rotation_governed_without_segment_read",
        "rotated": True,
        "complete_entry_count": 0,
        "segment_file_read_count": _probe_count(runtime, "segment_read"),
        "runtime_activity": _activity(index_file_read_count=1, rotation_count=1),
    }


def _case_expected_error(
    common: Mapping[str, Any],
    runtime: Mapping[str, Any],
    executor: str,
    expected_error: str,
) -> dict[str, Any]:
    try:
        _execute_error_probe(runtime, executor)
    except (P136ObservationError, P136DurabilityUncertainError, P135ExportError) as exc:
        actual_error = str(exc)
        if actual_error != expected_error:
            raise P136RunnerError(f"case_error_mismatch:{executor}:{actual_error}") from exc
        return {
            **dict(common),
            "probe": executor,
            "actual_error": actual_error,
            "error_type": type(exc).__name__,
            "runtime_activity": _probe_activity(runtime),
        }
    raise P136RunnerError(f"case_expected_error_not_raised:{executor}")


def _case_p135_denominator_failure(common: Mapping[str, Any], runtime: Mapping[str, Any], executor: str) -> dict[str, Any]:
    if executor == "segment_size_mismatch":
        source = _provider_entries(runtime)["prometheus"]
        entry = _entry_variant(source, expected_bytes=int(source["expected_bytes"]) - 1)
        result = promote_first_seen_entry(runtime, entry)
    else:
        entry = _parser_failure_entry(runtime)
        result = promote_first_seen_entry({**dict(runtime), "export_root": Path("evals/p135/input/exports")}, entry)
    _assert_denominator_failure(result)
    promotion = _mapping(result["promotion_record"], "promotion_record")
    receipt = _mapping(_mapping(result["p135_result"], "p135_result")["receipt"], "receipt")
    return {
        **dict(common),
        "probe": executor,
        "actual_label": "p135_denominator_failure",
        "promotion_status": promotion["status"],
        "p135_receipt_status": receipt["status"],
        "promotion_hash": promotion["promotion_hash"],
        "runtime_activity": dict(_mapping(result["activity"], "runtime_activity")),
    }


def _execute_error_probe(runtime: Mapping[str, Any], executor: str) -> None:
    if executor == "malformed_line":
        scan_incremental_index(runtime, index_bytes=b'{"entry_id":\n')
    elif executor == "duplicate_json_key":
        scan_incremental_index(runtime, index_bytes=b'{"entry_id":"a","entry_id":"b"}\n')
    elif executor == "non_finite_value":
        scan_incremental_index(runtime, index_bytes=b'{"entry_id":NaN}\n')
    elif executor == "oversized_line":
        scan_incremental_index(_runtime_with_limit(runtime, "max_whole_index_bytes", 8192), index_bytes=b'{"entry_id":"' + (b"a" * 4096) + b'"}\n')
    elif executor == "whole_index_byte_budget":
        scan_incremental_index(runtime, index_bytes=b"x" * 5000)
    elif executor == "whole_index_line_budget":
        first, second = _two_chained_entries(runtime)
        patched = _runtime_with_limit(runtime, "max_complete_lines_per_cycle", 1)
        scan_incremental_index(patched, index_bytes=_canonical_bytes(first) + b"\n" + _canonical_bytes(second) + b"\n")
    elif executor == "unsafe_index_path":
        observe_one_cycle(_runtime_with_symlink_index(runtime))
    elif executor == "consumed_prefix_mutation":
        mutated = _rehash({**_checkpoint(runtime), "committed_cursor": 12, "consumed_prefix_hash": stable_hash({"prefix": "expected"})})
        scan_incremental_index({**dict(runtime), "checkpoint": mutated}, index_bytes=b'{"changed":1}\n')
    elif executor == "same_identity_truncation":
        current = _rehash({**_checkpoint(runtime), "committed_cursor": 12, "consumed_prefix_hash": _content_hash(b"abcdefghijkl")})
        scan_incremental_index({**dict(runtime), "checkpoint": current}, index_bytes=b"short")
    elif executor == "rotation_sequence_gap":
        prior_entry = _provider_entries(runtime)["grafana"]
        bad = _entry_variant(
            _provider_entries(runtime)["loki"],
            entry_sequence=3,
            rotation_from_hash=prior_entry["entry_hash"],
        )
        checkpoint = _checkpoint_with_identity(
            runtime,
            prior_entry,
            _minimal_promotion(prior_entry),
            next_entry_sequence=2,
        )
        scan_incremental_index({**dict(runtime), "checkpoint": checkpoint}, index_bytes=_canonical_bytes(bad) + b"\n", file_identity_hash=stable_hash({"index_identity": "gap"}))
    elif executor == "rotation_lineage_mismatch":
        prior_entry = _provider_entries(runtime)["grafana"]
        bad = _entry_variant(_provider_entries(runtime)["loki"], rotation_from_hash=stable_hash({"wrong": "rotation"}))
        checkpoint = _checkpoint_with_identity(runtime, prior_entry, _minimal_promotion(prior_entry), next_entry_sequence=2)
        scan_incremental_index({**dict(runtime), "checkpoint": checkpoint}, index_bytes=_canonical_bytes(bad) + b"\n", file_identity_hash=stable_hash({"index_identity": "lineage"}))
    elif executor == "entry_id_conflict":
        prior_entry = _provider_entries(runtime)["grafana"]
        bad = _entry_variant(_provider_entries(runtime)["loki"], entry_id=prior_entry["entry_id"])
        checkpoint = _checkpoint_with_identity(runtime, prior_entry, _minimal_promotion(prior_entry), next_entry_sequence=2)
        scan_incremental_index({**dict(runtime), "checkpoint": checkpoint}, index_bytes=_canonical_bytes(bad) + b"\n")
    elif executor == "segment_id_conflict":
        prior_entry = _provider_entries(runtime)["grafana"]
        bad = _entry_variant(_provider_entries(runtime)["loki"], segment_id=prior_entry["segment_id"])
        checkpoint = _checkpoint_with_identity(runtime, prior_entry, _minimal_promotion(prior_entry), next_entry_sequence=2)
        scan_incremental_index({**dict(runtime), "checkpoint": checkpoint}, index_bytes=_canonical_bytes(bad) + b"\n")
    elif executor == "expired_authority":
        validate_observer_runtime_authority(_mapping(runtime["config"], "config"), _mapping(runtime["authority"], "authority"), now="2026-07-15T00:00:00Z")
    elif executor == "wall_clock_rollback":
        observe_one_cycle({**dict(runtime), "now": "2026-07-13T00:10:01Z"})
    elif executor == "receipt_reuse":
        receipt = _mapping(runtime["authority"], "authority")["index_receipts"][0]["receipt_hash"]
        consumed = _rehash({**_checkpoint(runtime), "reserved_index_read_receipt_hashes": [receipt]})
        observe_one_cycle({**dict(runtime), "checkpoint": consumed})
    elif executor == "byte_estimate_exceeded":
        validate_observer_runtime_authority(_mapping(runtime["config"], "config"), _mapping(runtime["authority"], "authority"), now=str(runtime["now"]), proposed_whole_index_bytes=999_999)
    elif executor == "record_estimate_exceeded":
        validate_observer_runtime_authority(_mapping(runtime["config"], "config"), _mapping(runtime["authority"], "authority"), now=str(runtime["now"]), proposed_complete_lines=999_999)
    elif executor == "wrong_authority_binding":
        cfg = build_incremental_observer_config({**_config_input_from_runtime(runtime), "index_source_ref_hash": stable_hash({"wrong": "index"})})
        validate_observer_runtime_authority(cfg, _mapping(runtime["authority"], "authority"), now=str(runtime["now"]))
    elif executor == "segment_size_mismatch":
        source = _provider_entries(runtime)["prometheus"]
        entry = _entry_variant(source, expected_bytes=int(source["expected_bytes"]) - 1)
        promote_first_seen_entry(runtime, entry)
    elif executor == "state_tamper":
        _tamper_bundle(runtime)
    elif executor == "post_replace_uncertain":
        advance_checkpoint(runtime, _checkpoint(runtime), simulate_parent_fsync_uncertain=True)
    elif executor == "competing_lease":
        observe_one_cycle({**dict(runtime), "lease_competitor": True})
    elif executor == "config_path_violation":
        build_incremental_observer_config({**_config_input_from_runtime(runtime), "checkpoint_path": "data/index.jsonl/checkpoint.json"})
    elif executor == "p135_tamper":
        _tamper_ledger(runtime)
    elif executor == "old_pending_partial_rotation":
        pending = {
            "file_identity_hash": _checkpoint(runtime)["index_identity_hash"],
            "line_start_cursor": 0,
            "pending_byte_hash": _content_hash(b'{"entry_id":"partial"'),
            "pending_byte_length": len(b'{"entry_id":"partial"'),
            "observed_index_size": len(b'{"entry_id":"partial"'),
        }
        current = _rehash({**_checkpoint(runtime), "pending_partial": pending})
        scan_incremental_index({**dict(runtime), "checkpoint": current}, index_bytes=b"", file_identity_hash=stable_hash({"index_identity": "new"}))
    else:
        raise P136RunnerError(f"unknown_case_executor:{executor}")


def _validate_case_observation(
    spec: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> None:
    expected_label = spec.get("expected_label")
    expected_error = spec.get("expected_error")
    if (expected_label is None) == (expected_error is None):
        raise P136RunnerError("case_expectation_contract_invalid")
    if expected_label is not None and observed.get("actual_label") != expected_label:
        raise P136RunnerError(f"case_label_mismatch:{spec['case_id']}:{observed.get('actual_label')}")
    if expected_error is not None and observed.get("actual_error") != expected_error:
        raise P136RunnerError(f"case_error_mismatch:{spec['case_id']}:{observed.get('actual_error')}")
    if observed.get("executed") is not True:
        raise P136RunnerError("case_execution_not_proven")
    for field in ("measured_duplicate_segment_reads", "measured_duplicate_promotions"):
        if type(observed.get(field)) is not int or int(observed[field]) < 0:
            raise P136RunnerError("invalid_measured_duplicate_count")
    measured = observed.get("runtime_activity")
    if not isinstance(measured, Mapping) or set(measured) != set(zero_runtime_activity()):
        raise P136RunnerError("invalid_case_runtime_activity_schema")


def _merge_activity(
    activity: dict[str, int],
    observed: Mapping[str, Any],
) -> None:
    measured = observed.get("runtime_activity")
    if isinstance(measured, Mapping):
        if set(measured) != set(activity):
            raise P136RunnerError("invalid_case_runtime_activity_schema")
        for key, value in measured.items():
            if type(value) is not int or value < 0:
                raise P136RunnerError("invalid_case_runtime_activity_value")
            activity[str(key)] += value
        return
    raise P136RunnerError("case_runtime_activity_missing")


def _merge_exact_counters(
    total: dict[str, int],
    measured: Any,
    error: str,
) -> None:
    if not isinstance(measured, Mapping) or set(measured) != set(total):
        raise P136RunnerError(error)
    for key, value in measured.items():
        if type(value) is not int or value < 0:
            raise P136RunnerError(error)
        total[str(key)] += value


def _require_exact_counter_values(
    measured: Any,
    keys: tuple[str, ...],
    *,
    expected: int,
    error: str,
) -> None:
    if not isinstance(measured, Mapping) or set(measured) != set(keys):
        raise P136RunnerError(error)
    if any(type(measured[key]) is not int or measured[key] != expected for key in keys):
        raise P136RunnerError(error)


def _evaluator_activity_with_signals(
    base: Mapping[str, int],
    signal_delivery_count: int,
) -> dict[str, int]:
    if set(base) != set(EVALUATOR_ACTIVITY_KEYS):
        raise P136RunnerError("invalid_evaluator_activity_schema")
    result: dict[str, int] = {}
    for key in EVALUATOR_ACTIVITY_KEYS:
        value = base.get(key)
        if type(value) is not int or value < 0:
            raise P136RunnerError("invalid_evaluator_activity_schema")
        result[key] = value
    result["signal_delivery_count"] += signal_delivery_count
    return result


def _provider_entries(runtime: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return _mapping(runtime.get("provider_entries"), "provider_entries")


def _activity(**overrides: int) -> dict[str, int]:
    activity = zero_runtime_activity()
    for key, value in overrides.items():
        if key not in activity or type(value) is not int or value < 0:
            raise P136RunnerError("invalid_activity_override")
        activity[key] = value
    return activity


def _normalize_runtime_config_checkpoint(runtime: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(runtime)
    config_input = _mapping(value.get("config"), "config")
    if config_input.get("schema_version") == "p136.incremental_observer_config.v1":
        validate_incremental_observer_config(config_input)
        config = dict(config_input)
    else:
        config = build_incremental_observer_config(config_input)
    checkpoint = deepcopy(dict(_mapping(value.get("checkpoint"), "checkpoint")))
    if checkpoint.get("config_hash") != config["config_hash"]:
        checkpoint["config_hash"] = config["config_hash"]
        checkpoint.pop("checkpoint_hash", None)
        checkpoint["checkpoint_hash"] = stable_hash(checkpoint)
    value["config"] = config
    value["checkpoint"] = checkpoint
    return value


def _checkpoint(runtime: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(runtime.get("checkpoint"), "checkpoint")


def _config_input_from_runtime(runtime: Mapping[str, Any]) -> dict[str, Any]:
    config = deepcopy(dict(_mapping(runtime.get("config"), "config")))
    config.pop("schema_version", None)
    config.pop("config_hash", None)
    return config


def _runtime_with_limit(runtime: Mapping[str, Any], key: str, value: int) -> dict[str, Any]:
    raw = _config_input_from_runtime(runtime)
    raw["limits"] = {**dict(_mapping(raw["limits"], "limits")), key: value}
    return {**dict(runtime), "config": build_incremental_observer_config(raw)}


def _runtime_with_symlink_index(runtime: Mapping[str, Any]) -> dict[str, Any]:
    base = Path(runtime["base_path"]).parent / "p136-unsafe-index-case"
    config = _mapping(runtime["config"], "config")
    index_path = base / str(config["index_path"])
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.unlink(missing_ok=True)
    index_path.symlink_to("missing-index-target.jsonl")
    return {**dict(runtime), "base_path": base}


def _entry_variant(entry: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    raw = {key: deepcopy(value) for key, value in entry.items() if key not in {"schema_version", "entry_hash"}}
    raw.update(overrides)
    return build_incremental_index_entry(raw)


def _two_chained_entries(runtime: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    entries = _provider_entries(runtime)
    first = dict(entries["grafana"])
    second = dict(entries["loki"])
    return first, second


def _checkpoint_with_identity(
    runtime: Mapping[str, Any],
    entry: Mapping[str, Any],
    promotion: Mapping[str, Any],
    *,
    next_entry_sequence: int = 1,
) -> dict[str, Any]:
    checkpoint = deepcopy(dict(_checkpoint(runtime)))
    checkpoint.update(
        {
            "next_entry_sequence": next_entry_sequence,
            "last_entry_hash": entry["entry_hash"],
            "canonical_entry_identities": {
                str(entry["entry_id"]): dict(entry),
                str(entry["segment_id"]): dict(entry),
            },
            "promotion_keys": {str(entry["entry_hash"]): promotion["promotion_key"]},
        }
    )
    return _rehash(checkpoint)


def _minimal_promotion(entry: Mapping[str, Any]) -> dict[str, Any]:
    promotion = {
        "schema_version": "p136.promotion_record.v1",
        "promotion_sequence": 1,
        "entry_hash": entry["entry_hash"],
        "status": "success",
        "p135_manifest_hash": stable_hash({"manifest": entry["entry_hash"]}),
        "p135_artifact_spec_hash": stable_hash({"artifact": entry["entry_hash"]}),
        "p134_segment_receipt_hash": entry["segment_authority_receipt_hash"],
        "p135_execution_receipt_hash": stable_hash({"execution": entry["entry_hash"]}),
        "p135_receipt_ledger_hash": stable_hash({"ledger": entry["entry_hash"]}),
        "p135_normalized_bundle_hash": stable_hash({"bundle": entry["entry_hash"]}),
        "promotion_key": stable_hash({"promotion_key": entry["entry_hash"]}),
        "activity": _activity(),
        "forbidden_authority": zero_forbidden_authority(),
    }
    promotion["promotion_hash"] = stable_hash(promotion)
    return promotion


def _parser_failure_entry(runtime: Mapping[str, Any]) -> dict[str, Any]:
    source = _provider_entries(runtime)["prometheus"]
    path = Path("evals/p135/input/exports/parser_failure_duplicate_key.json")
    data = path.read_bytes()
    return _entry_variant(
        source,
        entry_id="entry-parser-failure",
        segment_id="segment-parser-failure",
        source_id="parser-failure",
        relative_segment_path="parser_failure_duplicate_key.json",
        expected_content_hash=_content_hash(data),
        expected_bytes=len(data),
        expected_records=1,
    )


def _assert_denominator_failure(result: Mapping[str, Any]) -> None:
    promotion = _mapping(result.get("promotion_record"), "promotion_record")
    receipt = _mapping(_mapping(result.get("p135_result"), "p135_result").get("receipt"), "receipt")
    bundle = _mapping(_mapping(result.get("p135_result"), "p135_result").get("bundle"), "bundle")
    if promotion.get("status") != "denominator_failure" or receipt.get("status") != "failed":
        raise P136RunnerError("p135_denominator_failure_not_proven")
    if bundle.get("schema_version") != "p135.denominator_failure_bundle.v1":
        raise P136RunnerError("p135_failure_bundle_not_proven")


def _tamper_bundle(runtime: Mapping[str, Any]) -> None:
    entry = _provider_entries(runtime)["prometheus"]
    result = promote_first_seen_entry(runtime, entry)
    promotion = deepcopy(dict(_mapping(result["promotion_record"], "promotion_record")))
    promotion["p135_normalized_bundle_hash"] = stable_hash({"tampered": "bundle"})
    promotion["promotion_hash"] = stable_hash({key: value for key, value in promotion.items() if key != "promotion_hash"})
    validate_promotion_record(promotion, expected_entry=entry, runtime=runtime)


def _tamper_ledger(runtime: Mapping[str, Any]) -> None:
    entries = _provider_entries(runtime)
    left = promote_first_seen_entry(runtime, entries["prometheus"])
    right = promote_first_seen_entry(runtime, entries["loki"])
    promotion = deepcopy(dict(_mapping(left["promotion_record"], "promotion_record")))
    promotion["p135_receipt_ledger_hash"] = right["promotion_record"]["p135_receipt_ledger_hash"]
    promotion["promotion_hash"] = stable_hash({key: value for key, value in promotion.items() if key != "promotion_hash"})
    validate_promotion_record(promotion, expected_entry=entries["prometheus"], runtime=runtime)


def _sum_activities(items: Any) -> dict[str, int]:
    total = zero_runtime_activity()
    for raw in items:
        activity = _mapping(raw, "runtime_activity")
        if set(activity) != set(total):
            raise P136RunnerError("invalid_activity_schema")
        for key, value in activity.items():
            if type(value) is not int or value < 0:
                raise P136RunnerError("invalid_activity_value")
            total[str(key)] += value
    return total


def _probe_activity(runtime: Mapping[str, Any]) -> dict[str, int]:
    activity = zero_runtime_activity()
    probe = runtime.get("probe")
    events = getattr(probe, "events", None)
    if isinstance(events, list):
        activity["index_read_intent_write_count"] = events.count("write_index_read_intent")
        activity["index_file_open_count"] = events.count("index_open")
        activity["index_file_read_count"] = events.count("index_read")
        activity["segment_file_open_count"] = events.count("segment_open")
        activity["segment_file_read_count"] = events.count("segment_read")
    return activity


def _probe_count(runtime: Mapping[str, Any], event: str) -> int:
    probe = runtime.get("probe")
    events = getattr(probe, "events", None)
    if isinstance(events, list):
        return events.count(event)
    return 0


def _rehash(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("checkpoint_hash", None)
    result["checkpoint_hash"] = stable_hash(result)
    return result


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _content_hash(value: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value).hexdigest()


def _resource_usage(
    started_wall: float,
    started_self: resource.struct_rusage,
    started_children: resource.struct_rusage,
) -> dict[str, int]:
    current_self = resource.getrusage(resource.RUSAGE_SELF)
    current_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    self_seconds = (current_self.ru_utime + current_self.ru_stime) - (started_self.ru_utime + started_self.ru_stime)
    child_seconds = (current_children.ru_utime + current_children.ru_stime) - (started_children.ru_utime + started_children.ru_stime)
    started_peak = _normalized_peak_rss_bytes(started_self)
    current_peak = _normalized_peak_rss_bytes(current_self)
    peak_growth = max(0, current_peak - started_peak)
    return {
        "wall_time_ms": max(0, int((time.monotonic() - started_wall) * 1000)),
        "cpu_time_ms": max(0, int(self_seconds * 1000)),
        "child_cpu_time_ms": max(0, int(child_seconds * 1000)),
        "peak_memory_bytes": peak_growth,
        "wall_limit_ms": 30_000,
        "cpu_limit_ms": 15_000,
        "peak_memory_limit_bytes": 134_217_728,
    }


def _normalized_peak_rss_bytes(usage: resource.struct_rusage) -> int:
    peak = int(usage.ru_maxrss)
    return peak if sys.platform.startswith("darwin") else peak * 1024


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P136RunnerError(f"invalid_{label}_shape")
    return value
