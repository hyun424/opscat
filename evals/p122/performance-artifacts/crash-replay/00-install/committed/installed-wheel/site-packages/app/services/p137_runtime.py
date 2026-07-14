"""Crash-safe local-only runtime control for P137.

This module owns only P137 durability/control concerns: nonblocking local lease,
fixed-path handoff reads, deterministic state writes, checkpoint sequencing,
ledger CAS, heartbeat/readiness records, and signal stop boundaries.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import resource
import signal
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import FrameType
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_classification import build_classification_record, derive_classification, validate_classification_record
from app.services.p137_contracts import (
    CHECKPOINT_SCHEMA_VERSION,
    EVIDENCE_ATOM_SCHEMA_VERSION,
    HEARTBEAT_SCHEMA_VERSION,
    INTENT_SCHEMA_VERSION,
    READINESS_SCHEMA_VERSION,
    TERMINATION_SCHEMA_VERSION,
    validate_evidence_atom,
    validate_triage_agent_config,
    zero_evaluator_activity,
    zero_forbidden_authority,
    zero_runtime_activity,
)
from app.services.p137_correlation import P137CorrelationError, correlate_incident_state, transition_incident_status
from app.services.p137_hypotheses import P137HypothesisError, rank_incident_hypotheses
from app.services.p137_ledger import advance_investigation_ledger, new_investigation_ledger, validate_investigation_ledger
from app.services.p137_requests import build_request_budget, derive_evidence_request_record, execute_evidence_request, validate_evidence_request

_CRASH_POINTS = frozenset({"ingest_intent", "incident_write", "request_write", "classification_write", "ledger_write"})
_HASH_NONE = "sha256:" + ("0" * 64)

ValidateHandoff = Callable[..., dict[str, Any]]
ResourceProbe = Callable[[], Mapping[str, int]]


class P137RuntimeError(ValueError):
    """Raised when P137 runtime control must fail closed."""


class P137StopController:
    """Signal-safe stop flag; handlers only record the requested signal."""

    def __init__(self) -> None:
        self.stop_requested = False
        self.signal_name: str | None = None

    def handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        self.stop_requested = True
        self.signal_name = _signal_name(signum)


def run_p137_runtime_once(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    validate_handoff: ValidateHandoff | None = None,
    crash_after: str | None = None,
    stop_controller: P137StopController | None = None,
    stop_before: str = "handoff",
    resource_probe: ResourceProbe | None = None,
    now: str = "2026-07-14T00:00:00Z",
) -> dict[str, Any]:
    validate_triage_agent_config(config)
    if crash_after is not None and crash_after not in _CRASH_POINTS:
        raise P137RuntimeError("unknown_crash_point")
    if stop_before not in {"handoff", "classification"}:
        raise P137RuntimeError("unknown_stop_boundary")
    started_wall = time.monotonic()
    started_self = resource.getrusage(resource.RUSAGE_SELF)
    started_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    activity = zero_runtime_activity()
    authority = zero_forbidden_authority()
    evaluator = zero_evaluator_activity()
    checkpoint: dict[str, Any] | None = None
    ledger: dict[str, Any] | None = None
    split_commit_pending = False
    root = Path(base_path)
    lease_path = _resolve(root, config["lease_path"])
    lease = _Lease(lease_path, config_hash=str(config["config_hash"]), now=now)
    if not lease.acquire():
        return _result(
            status="failed_closed",
            expected_error="lease_conflict",
            termination_reason="lease_conflict",
            classification="none",
            runtime_activity=activity,
            authority_counters=authority,
            evaluator_activity=evaluator,
        )
    activity["lease_acquire_count"] += 1
    try:
        checkpoint = _read_optional_json(_resolve(root, config["checkpoint_path"]), activity)
        if checkpoint is not None:
            _validate_checkpoint(checkpoint, config)
        ledger = _read_optional_json(_resolve(root, config["ledger_path"]), activity)
        if ledger is not None:
            validate_investigation_ledger(ledger)
            if ledger.get("config_hash") != config["config_hash"]:
                raise P137RuntimeError("ledger_config_mismatch")
        split_commit_pending = _split_commit_pending(checkpoint, ledger)
        durable = _load_durable_state(root, config, activity)
        _validate_durable_ledger_membership(ledger, durable)

        if stop_before == "handoff" and stop_controller is not None and stop_controller.stop_requested:
            signal_name = stop_controller.signal_name or "unknown"
            return _stop_result(
                root=root,
                config=config,
                now=now,
                expected_error="signal_before_handoff_safe_boundary",
                stop_reason=signal_name,
                safe_boundary="before_handoff_read",
                checkpoint=checkpoint,
                ledger=ledger,
                activity=activity,
                authority=authority,
                evaluator=evaluator,
            )

        handoff_path = _resolve(root, config["p136_handoff_bundle_path"])
        handoff_bytes = _read_required_bytes(handoff_path, activity)
        canonical_handoff_bytes = _canonical_payload_from_framed_file(handoff_bytes)
        validator = validate_handoff or _default_handoff_validator()
        handoff = validator(canonical_handoff_bytes, config=dict(config), p137_checkpoint=checkpoint)
        continuous = _mapping(config.get("continuous_mode"), "continuous_mode")
        if (
            continuous.get("enabled") is True
            and continuous.get("handoff_version_polling") is True
            and handoff.get("bundle_version") != continuous.get("expected_bundle_version")
        ):
            return _stop_result(
                root=root,
                config=config,
                now=now,
                expected_error="handoff_version_stale",
                stop_reason="handoff_version_stale",
                safe_boundary="after_handoff_validation_before_ingest",
                checkpoint=checkpoint,
                ledger=ledger,
                activity=activity,
                authority=authority,
                evaluator=evaluator,
            )
        validator_calls = _mapping(handoff.get("p136_validator_calls", {}), "p136_validator_calls")
        activity["p136_validator_invocation_count"] += sum(
            int(value) for value in validator_calls.values() if isinstance(value, int) and not isinstance(value, bool)
        ) or 1
        activity["promotion_record_read_count"] += int(handoff.get("promotion_record_count", 0))
        activity["promotion_bytes_validated"] += int(
            handoff.get("promotion_bytes_validated", _promotion_bytes_validated(handoff))
        )

        if split_commit_pending:
            _validate_split_commit_intent(durable["intents"], handoff, ledger)
            assert ledger is not None
            checkpoint_next = _checkpoint(config=config, handoff=handoff, ledger=ledger, prior=checkpoint)
            _replace_json(_resolve(root, config["checkpoint_path"]), checkpoint_next, activity, None)
            _replace_json(
                _resolve(root, config["readiness_path"]),
                _readiness(config, now, "ready", checkpoint_next, None),
                activity,
                "readiness_write_count",
            )
            activity["recovery_replay_count"] += 1
            last_classification = _last_durable_classification(ledger, durable["classifications"])
            return _result(
                status="ok",
                expected_error=None,
                termination_reason="recovered_split_commit",
                classification=last_classification,
                runtime_activity=activity,
                authority_counters=authority,
                evaluator_activity=evaluator,
                checkpoint=checkpoint_next,
                ledger=ledger,
                reused_bundle=True,
            )

        sequence_status = _check_handoff_sequence(handoff, checkpoint, config)
        if sequence_status != "accept":
            if sequence_status == "reuse":
                for atom in _sequence(handoff.get("evidence_atoms"), "evidence_atoms"):
                    atom_path = _resolve(root, config["journal_dir"]) / "atoms" / f"{_hash(atom.get('atom_hash'), 'atom_hash')}.json"
                    if atom_path.exists():
                        activity["duplicate_atom_count"] += 1
                activity["recovery_replay_count"] += 1
                return _result(
                    status="ok",
                    expected_error=None,
                    termination_reason="reused_bundle",
                    classification="none",
                    runtime_activity=activity,
                    authority_counters=authority,
                    evaluator_activity=evaluator,
                    checkpoint=checkpoint,
                    ledger=ledger,
                    reused_bundle=True,
                )
            return _result(
                status="failed_closed",
                expected_error=sequence_status,
                termination_reason=sequence_status,
                classification="none",
                runtime_activity=activity,
                authority_counters=authority,
                evaluator_activity=evaluator,
                checkpoint=checkpoint,
                ledger=ledger,
            )

        intent = _intent(config=config, now=now, handoff=handoff, handoff_bytes=handoff_bytes)
        _write_named_json(root, config["journal_dir"], f"intents/{intent['intent_hash']}.json", intent, activity, counter="ingest_intent_write_count")
        _maybe_crash(crash_after, "ingest_intent", activity, authority, evaluator)

        for atom in _sequence(handoff.get("evidence_atoms"), "evidence_atoms"):
            activity["evidence_atom_count"] += 1
            duplicate = _write_named_json(
                root,
                config["journal_dir"],
                f"atoms/{_hash(atom.get('atom_hash'), 'atom_hash')}.json",
                _mapping(atom, "evidence_atom"),
                activity,
                counter="evidence_atom_write_count",
            )
            if duplicate:
                activity["duplicate_atom_count"] += 1

        measured_resources = (
            _validated_resource_probe(resource_probe())
            if resource_probe is not None
            else _measured_resource_usage(config, started_wall, started_self, started_children)
        )
        triage = _triage_handoff(
            config=config,
            handoff=handoff,
            ledger=ledger,
            now=now,
            activity=activity,
            authority=authority,
            resource_usage=_resource_usage(config),
            existing_requests=durable["requests_by_attempt"],
        )
        _write_stage_collection(root, config, triage["incident_records"], "incident", "incident_write_count", activity)
        _maybe_crash(crash_after, "incident_write", activity, authority, evaluator)
        _write_stage_collection(root, config, triage["hypotheses"], "hypothesis", "hypothesis_write_count", activity)
        request_writes_before = activity["evidence_request_write_count"]
        _write_stage_collection(root, config, triage["requests"], "request", "evidence_request_write_count", activity)
        activity["attempted_request_hash_write_count"] += activity["evidence_request_write_count"] - request_writes_before
        _maybe_crash(crash_after, "request_write", activity, authority, evaluator)
        if stop_before == "classification" and stop_controller is not None and stop_controller.stop_requested:
            signal_name = stop_controller.signal_name or "unknown"
            return _stop_result(
                root=root,
                config=config,
                now=now,
                expected_error="signal_before_classification_unsafe",
                stop_reason=signal_name,
                safe_boundary="before_classification_write",
                checkpoint=checkpoint,
                ledger=ledger,
                activity=activity,
                authority=authority,
                evaluator=evaluator,
                open_incident_hashes=[str(item["incident_hash"]) for item in triage["incidents"]],
            )
        if _resource_limit_exceeded(measured_resources):
            return _stop_result(
                root=root,
                config=config,
                now=now,
                expected_error="resource_limit_exceeded",
                stop_reason="budget_exhausted",
                safe_boundary="before_classification_write",
                checkpoint=checkpoint,
                ledger=ledger,
                activity=activity,
                authority=authority,
                evaluator=evaluator,
                resource_usage=measured_resources,
                termination_reason="resource_exhausted",
                open_incident_hashes=[str(item["incident_hash"]) for item in triage["incidents"]],
            )
        _write_stage_collection(root, config, triage["classifications"], "classification", "classification_write_count", activity)
        _maybe_crash(crash_after, "classification_write", activity, authority, evaluator)

        next_ledger = _new_or_reused_ledger(
            config,
            ledger,
            activity,
            authority,
            evaluator,
            incidents=triage["incidents"],
            requests=triage["requests"],
            classifications=triage["classifications"],
        )
        _replace_json(_resolve(root, config["ledger_path"]), next_ledger, activity, "ledger_write_count")
        _maybe_crash(crash_after, "ledger_write", activity, authority, evaluator)
        checkpoint_next = _checkpoint(config=config, handoff=handoff, ledger=next_ledger, prior=checkpoint)
        _replace_json(_resolve(root, config["checkpoint_path"]), checkpoint_next, activity, None)
        _replace_json(_resolve(root, config["readiness_path"]), _readiness(config, now, "ready", checkpoint_next, None), activity, "readiness_write_count")

        classifications = [str(record["classification"]) for record in triage["classifications"]]
        classification = classifications[0] if len(classifications) == 1 else ("insufficient_evidence" if classifications else "none")

        return _result(
            status="ok",
            expected_error=None,
            termination_reason="aborted_fail_closed" if classification == "aborted_fail_closed" else "cycle_complete",
            classification=classification,
            runtime_activity=activity,
            authority_counters=authority,
            evaluator_activity=evaluator,
            checkpoint=checkpoint_next,
            ledger=next_ledger,
            incidents=triage["incidents"],
            hypotheses=triage["hypotheses"],
            requests=triage["requests"],
            classifications=triage["classifications"],
            reused_bundle=False,
        )
    except (P137RuntimeError, ValueError) as exc:
        error = str(exc)
        if error.startswith("crash_after_"):
            return _result(
                status="failed_closed",
                expected_error=error,
                termination_reason=error,
                classification="none",
                runtime_activity=activity,
                authority_counters=authority,
                evaluator_activity=evaluator,
            )
        if _is_corrupt_state_error(error):
            return _stop_result(
                root=root,
                config=config,
                now=now,
                expected_error="p137_state_corrupt_hash_mismatch",
                stop_reason="aborted_fail_closed",
                safe_boundary="state_validation",
                checkpoint=checkpoint,
                ledger=ledger,
                activity=activity,
                authority=authority,
                evaluator=evaluator,
                termination_reason="corrupt_state",
            )
        return _result(
            status="failed_closed",
            expected_error=error,
            termination_reason=error,
            classification="none",
            runtime_activity=activity,
            authority_counters=authority,
            evaluator_activity=evaluator,
        )
    finally:
        lease.release()


def run_p137_runtime_loop(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    validate_handoff: ValidateHandoff | None = None,
    now_values: Sequence[str] = (),
    stop_controller: P137StopController | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    validate_triage_agent_config(config)
    mode = _mapping(config.get("continuous_mode"), "continuous_mode")
    if mode.get("enabled") is not True:
        raise P137RuntimeError("continuous_mode_not_enabled")
    max_cycles = int(mode["max_cycles"])
    cycles_requested = min(max_cycles, len(now_values) if now_values else max_cycles)
    last: dict[str, Any] | None = None
    control_activity = zero_runtime_activity()
    consecutive_failures = 0
    started = monotonic()
    last_heartbeat_elapsed = -int(mode["heartbeat_interval_ms"])
    stale_readiness = _existing_readiness_is_stale(
        _resolve(Path(base_path), str(mode["readiness_path"])),
        now_values[0] if now_values else "2026-07-14T00:00:00Z",
        int(mode["readiness_stale_after_ms"]),
    )
    if stale_readiness:
        last = _stop_result(
            root=Path(base_path),
            config=config,
            now=now_values[0] if now_values else "2026-07-14T00:00:00Z",
            expected_error="readiness_stale",
            stop_reason="readiness_stale",
            safe_boundary="before_handoff_read",
            checkpoint=None,
            ledger=None,
            activity=control_activity,
            authority=zero_forbidden_authority(),
            evaluator=zero_evaluator_activity(),
        )
        return _loop_result(0, max_cycles, last, False, "readiness_stale")

    cycles_completed = 0
    stop_reason = "max_cycles_reached"
    for index in range(cycles_requested):
        now = now_values[index] if index < len(now_values) else "2026-07-14T00:00:00Z"
        if stop_controller is not None and stop_controller.stop_requested:
            signal_name = stop_controller.signal_name or "unknown"
            stop_reason = signal_name
            last = _stop_result(
                root=Path(base_path),
                config=config,
                now=now,
                expected_error="signal_before_handoff_safe_boundary",
                stop_reason=signal_name,
                safe_boundary="between_cycles",
                checkpoint=last.get("checkpoint") if last else None,
                ledger=last.get("ledger") if last else None,
                activity=control_activity,
                authority=zero_forbidden_authority(),
                evaluator=zero_evaluator_activity(),
            )
            break
        last = run_p137_runtime_once(
            base_path=base_path,
            config=config,
            validate_handoff=validate_handoff,
            now=now,
        )
        cycles_completed += 1
        if last.get("expected_error") == "handoff_version_stale":
            stop_reason = "handoff_version_stale"
        elif last.get("status") == "failed_closed":
            consecutive_failures += 1
            if consecutive_failures >= int(config["limits"]["max_consecutive_failures"]):
                stop_reason = "failure_threshold_reached"
        else:
            consecutive_failures = 0
        elapsed_ms = max(0, int((monotonic() - started) * 1_000))
        readiness_state = "stale" if bool(last.get("reused_bundle")) else ("degraded" if last.get("status") != "ok" else "ready")
        if elapsed_ms - last_heartbeat_elapsed >= int(mode["heartbeat_interval_ms"]):
            heartbeat = _heartbeat(
                config,
                index + 1,
                last,
                monotonic_elapsed_ms=elapsed_ms,
                readiness_state=readiness_state,
            )
            _replace_json(
                _resolve(Path(base_path), config["heartbeat_path"]),
                heartbeat,
                control_activity,
                "heartbeat_write_count",
            )
            last_heartbeat_elapsed = elapsed_ms
        readiness = _readiness(
            config,
            now,
            readiness_state,
            last.get("checkpoint"),
            stop_reason if stop_reason != "max_cycles_reached" else None,
        )
        _replace_json(
            _resolve(Path(base_path), config["readiness_path"]),
            readiness,
            control_activity,
            "readiness_write_count",
        )
        if stop_reason != "max_cycles_reached":
            break
        if index + 1 < cycles_requested:
            deadline = started + ((index + 1) * int(mode["poll_interval_ms"]) / 1_000)
            delay = deadline - monotonic()
            if delay > 0:
                sleep(delay)
    stale = bool(last and last.get("reused_bundle"))
    result = _loop_result(cycles_completed, max_cycles, last, stale, stop_reason)
    result["control_runtime_activity"] = control_activity
    return result


def _triage_handoff(
    *,
    config: Mapping[str, Any],
    handoff: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
    now: str,
    activity: Mapping[str, int],
    authority: Mapping[str, int],
    resource_usage: Mapping[str, int],
    existing_requests: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    atoms = [dict(_mapping(item, "atom")) for item in _sequence(handoff.get("evidence_atoms"), "evidence_atoms")]
    limits = _mapping(config.get("limits"), "limits")
    if len(atoms) > int(limits["max_promotions_per_cycle"]):
        raise P137RuntimeError("promotion_cycle_budget_exceeded")
    if len(atoms) > int(limits["max_records_per_cycle"]):
        raise P137RuntimeError("record_cycle_budget_exceeded")

    correlation_limits = {
        "max_open_incidents": int(limits["max_incidents_open"]),
        "max_atoms_per_incident": int(limits["max_records_per_cycle"]),
        "max_correlation_window_seconds": max(1, int(limits["max_correlation_window_ms"]) // 1_000),
        "max_incident_duration_seconds": max(1, int(limits["max_incident_duration_ms"]) // 1_000),
        "max_journal_entries": int(limits["max_records_per_cycle"]),
        "max_ledger_edges": int(limits["max_ledger_records"]),
    }
    correlation_failure_code: str | None = None
    correlation_failure_incident: dict[str, Any] | None = None
    try:
        correlation = correlate_incident_state(atoms, now=now, limits=correlation_limits)
    except P137CorrelationError as exc:
        if str(exc) != "incident_duration_budget_exceeded":
            raise
        correlation_failure_code = str(exc)
        if exc.incident is None:
            raise P137RuntimeError("incident_duration_failure_missing_partial_incident") from exc
        correlation_failure_incident = dict(exc.incident)
        correlation = {
            "schema_version": "p137.correlation_result.v1",
            "incidents": [correlation_failure_incident],
            "incident_count": 1,
        }
    next_incident = int(ledger["next_incident_sequence"]) if ledger is not None else 1
    next_request = int(ledger["next_request_sequence"]) if ledger is not None else 1
    next_classification = int(ledger["next_classification_sequence"]) if ledger is not None else 1
    previous_classification = (
        str(ledger["classification_hashes"][-1])
        if ledger is not None and _sequence(ledger.get("classification_hashes"), "classification_hashes")
        else None
    )

    incident_records: list[dict[str, Any]] = []
    terminal_incidents: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    classifications: list[dict[str, Any]] = []

    for correlated in _sequence(correlation.get("incidents"), "incidents"):
        incident = deepcopy(dict(_mapping(correlated, "incident")))
        incident["incident_sequence"] = next_incident
        incident["incident_hash"] = _self_hash(incident, "incident_hash")
        next_incident += 1
        incident_records.append(deepcopy(incident))
        if correlation_failure_code is not None:
            classification_record = build_classification_record(
                incident_id=str(incident["incident_id"]),
                classification_sequence=next_classification,
                classification="aborted_fail_closed",
                decided_at=now,
                top_hypothesis=None,
                authority_counters=authority,
                runtime_activity=_classification_activity(handoff),
                resource_usage=resource_usage,
                previous_classification_hash=previous_classification,
                decision_reasons=["runtime_failure_closed", correlation_failure_code],
            )
            next_classification += 1
            previous_classification = str(classification_record["classification_hash"])
            classifications.append(classification_record)
            incident = _advance_incident(
                incident,
                "aborted_fail_closed",
                now=now,
                classification_hash=classification_record["classification_hash"],
            )
            incident_records.append(deepcopy(incident))
            terminal_incidents.append(incident)
            continue
        incident = _advance_incident(incident, "correlating", now=now)
        incident_records.append(deepcopy(incident))
        incident = _advance_incident(incident, "investigating", now=now)
        incident_records.append(deepcopy(incident))

        incident_atoms = [atom for atom in atoms if atom["atom_hash"] in set(incident["evidence_atom_hashes"])]
        try:
            ranking = rank_incident_hypotheses(
                incident,
                incident_atoms,
                now=now,
                limits={
                    "max_hypotheses": int(limits["max_hypotheses_per_incident"]),
                    "max_support_edges_per_hypothesis": int(limits["max_support_edges_per_hypothesis"]),
                    "max_contradiction_edges_per_hypothesis": int(limits["max_contradiction_edges_per_hypothesis"]),
                    "max_missing_evidence_items_per_hypothesis": int(limits["max_missing_evidence_items_per_hypothesis"]),
                    "correlation_window_seconds": max(1, int(limits["max_correlation_window_ms"]) // 1_000),
                },
            )
        except P137HypothesisError as exc:
            if not str(exc).endswith("_budget_exceeded"):
                raise
            classification_record = build_classification_record(
                incident_id=str(incident["incident_id"]),
                classification_sequence=next_classification,
                classification="aborted_fail_closed",
                decided_at=now,
                top_hypothesis=None,
                authority_counters=authority,
                runtime_activity=_classification_activity(handoff),
                resource_usage=resource_usage,
                previous_classification_hash=previous_classification,
                decision_reasons=["runtime_failure_closed", str(exc)],
            )
            next_classification += 1
            previous_classification = str(classification_record["classification_hash"])
            classifications.append(classification_record)
            incident = _advance_incident(
                incident,
                "aborted_fail_closed",
                now=now,
                classification_hash=classification_record["classification_hash"],
            )
            incident_records.append(deepcopy(incident))
            terminal_incidents.append(incident)
            continue
        incident_hypotheses = [dict(_mapping(item, "hypothesis")) for item in _sequence(ranking.get("hypotheses"), "hypotheses")]
        hypotheses.extend(incident_hypotheses)

        incident_requests: list[dict[str, Any]] = []
        if _has_local_selection_need(incident_hypotheses):
            request = execute_evidence_request(
                incident_id=str(incident["incident_id"]),
                incident_hash=str(incident["incident_hash"]),
                request_sequence=next_request,
                catalog_name="select_records_by_system_id",
                parameters={
                    "system_id": str(incident["primary_system_id"]),
                    "limit": min(1_000, int(limits["max_request_output_records"])),
                },
                atoms=incident_atoms,
                budget=build_request_budget(
                    {
                        "max_input_records": int(limits["max_request_input_records"]),
                        "max_output_records": int(limits["max_request_output_records"]),
                        "max_output_bytes": int(limits["max_request_output_bytes"]),
                        "max_requests_per_incident": int(limits["max_evidence_requests_per_incident"]),
                        "wall_limit_ms": int(limits["max_cycle_wall_ms"]),
                        "cpu_limit_ms": int(limits["max_cpu_ms"]),
                        "peak_memory_limit_bytes": int(limits["max_peak_memory_bytes"]),
                    }
                ),
                previous_request_hash=str(requests[-1]["request_hash"]) if requests else None,
                existing_by_attempt=existing_requests,
            ).record
            incident_requests.append(request)
            requests.append(request)
            next_request += 1

        incident = _advance_incident(
            incident,
            "ready_to_classify",
            now=now,
            hypothesis_hashes=[str(item["hypothesis_hash"]) for item in incident_hypotheses],
            request_hashes=[str(item["request_hash"]) for item in incident_requests],
            attempted_request_hashes=[str(item["attempted_request_hash"]) for item in incident_requests],
        )
        incident_records.append(deepcopy(incident))
        incident = _advance_incident(incident, "classification_pending", now=now)
        incident_records.append(deepcopy(incident))

        semantic_tie = len(_sequence(ranking.get("top_tie_hypothesis_hashes"), "top_tie_hypothesis_hashes")) > 1
        classification = derive_classification(incident_hypotheses, accepted_incident=True, semantic_tie=semantic_tie)
        if classification is None:
            raise P137RuntimeError("classification_not_derived")
        top_hypothesis = incident_hypotheses[0] if incident_hypotheses else None
        classification_record = build_classification_record(
            incident_id=str(incident["incident_id"]),
            classification_sequence=next_classification,
            classification=classification,
            decided_at=now,
            top_hypothesis=top_hypothesis,
            authority_counters=authority,
            runtime_activity=_classification_activity(handoff),
            resource_usage=resource_usage,
            previous_classification_hash=previous_classification,
            decision_reasons=_decision_reasons(classification, semantic_tie),
        )
        next_classification += 1
        previous_classification = str(classification_record["classification_hash"])
        classifications.append(classification_record)
        incident = _advance_incident(
            incident,
            classification,
            now=now,
            classification_hash=classification_record["classification_hash"],
        )
        incident_records.append(deepcopy(incident))
        terminal_incidents.append(incident)

    return {
        "incident_records": incident_records,
        "incidents": terminal_incidents,
        "hypotheses": hypotheses,
        "requests": requests,
        "classifications": classifications,
    }


def _advance_incident(incident: Mapping[str, Any], target: str, *, now: str, **updates: Any) -> dict[str, Any]:
    value = deepcopy(dict(incident))
    value["status"] = transition_incident_status(str(value["status"]), target)
    value["updated_at"] = now
    value["previous_incident_hash"] = value["incident_hash"]
    value.update(updates)
    value["incident_hash"] = _self_hash(value, "incident_hash")
    return value


def _self_hash(value: Mapping[str, Any], hash_field: str) -> str:
    return stable_hash({key: item for key, item in value.items() if key != hash_field})


def _has_local_selection_need(hypotheses: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        _mapping(item, "missing_item").get("request_need_class") == "LOCAL_SELECTION"
        for hypothesis in hypotheses
        for item in _sequence(hypothesis.get("missing_evidence"), "missing_evidence")
    )


def _decision_reasons(classification: str, semantic_tie: bool) -> list[str]:
    if semantic_tie:
        return ["semantic_top_hypothesis_tie"]
    return {
        "confirmed_incident": ["supported_non_benign_hypothesis"],
        "insufficient_evidence": ["evidence_requirements_not_satisfied"],
        "benign_anomaly": ["supported_benign_pattern"],
        "aborted_fail_closed": ["runtime_failure_closed"],
    }[classification]


def _resource_usage(config: Mapping[str, Any]) -> dict[str, int]:
    limits = _mapping(config.get("limits"), "limits")
    return {
        "wall_time_ms": 0,
        "cpu_time_ms": 0,
        "child_cpu_time_ms": 0,
        "peak_memory_bytes": 0,
        "wall_limit_ms": int(limits["max_agent_wall_ms"]),
        "cpu_limit_ms": int(limits["max_cpu_ms"]),
        "peak_memory_limit_bytes": int(limits["max_peak_memory_bytes"]),
    }


def _classification_activity(handoff: Mapping[str, Any]) -> dict[str, int]:
    validator_calls = _mapping(handoff.get("p136_validator_calls", {}), "p136_validator_calls")
    invocation_count = sum(
        int(value) for value in validator_calls.values() if isinstance(value, int) and not isinstance(value, bool)
    ) or 1
    return zero_runtime_activity(
        p136_validator_invocation_count=invocation_count,
        promotion_record_read_count=int(handoff.get("promotion_record_count", 0)),
        promotion_bytes_validated=int(handoff.get("promotion_bytes_validated", _promotion_bytes_validated(handoff))),
        evidence_atom_count=len(_sequence(handoff.get("evidence_atoms"), "evidence_atoms")),
    )


def _default_handoff_validator() -> ValidateHandoff:
    try:
        from app.services.p137_p136_handoff import validate_p136_handoff_bundle
    except ModuleNotFoundError as exc:
        raise P137RuntimeError("missing_p136_handoff_validator") from exc
    return validate_p136_handoff_bundle


class _Lease:
    def __init__(self, path: Path, *, config_hash: str, now: str) -> None:
        self.path = path
        self.config_hash = config_hash
        self.now = now
        self.acquired = False
        self.fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = _canonical_json_bytes(
            {
                "schema_version": "p137.lease.v1",
                "config_hash": self.config_hash,
                "acquired_at": self.now,
            }
        )
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        os.ftruncate(fd, 0)
        os.write(fd, payload)
        os.fsync(fd)
        _fsync_dir(self.path.parent)
        self.fd = fd
        self.acquired = True
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        assert self.fd is not None
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None
            self.acquired = False


def _new_or_reused_ledger(
    config: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
    activity: Mapping[str, int],
    authority: Mapping[str, int],
    evaluator: Mapping[str, int],
    *,
    incidents: Sequence[Mapping[str, Any]],
    requests: Sequence[Mapping[str, Any]],
    classifications: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    prior = ledger or new_investigation_ledger(
        config_hash=str(config["config_hash"]),
        counters={"cycles_completed": 0},
        authority_counters=authority,
        runtime_activity=zero_runtime_activity(),
        evaluator_activity=zero_evaluator_activity(),
        resource_usage=_resource_usage(config),
    )
    return advance_investigation_ledger(
        prior,
        expected_previous_hash=str(prior["ledger_hash"]),
        incidents=incidents,
        requests=requests,
        classifications=classifications,
        counters={"cycles_completed": int(_mapping(prior.get("counters"), "counters").get("cycles_completed", 0)) + 1},
        runtime_activity=activity,
        evaluator_activity=evaluator,
        resource_usage=_resource_usage(config),
    )


def _check_handoff_sequence(handoff: Mapping[str, Any], checkpoint: Mapping[str, Any] | None, config: Mapping[str, Any]) -> str:
    sequence = _positive_int(handoff.get("bundle_sequence"), "bundle_sequence")
    bundle_hash = _hash(handoff.get("bundle_hash"), "bundle_hash")
    previous_hash = handoff.get("previous_bundle_hash")
    if previous_hash is not None:
        previous_hash = _hash(previous_hash, "previous_bundle_hash")
    if handoff.get("fixed_handoff_path") != config["p136_handoff_bundle_path"]:
        return "fixed_handoff_path_mismatch"
    if handoff.get("handoff_chain_root_hash") != config["p136_handoff_chain_root_hash"]:
        return "handoff_chain_root_mismatch"
    if checkpoint is None:
        if sequence != 1 or previous_hash is not None:
            return "handoff_genesis_sequence_invalid"
        return "accept"
    last_sequence = _positive_int(checkpoint.get("last_accepted_bundle_sequence"), "last_accepted_bundle_sequence")
    last_hash = _hash(checkpoint.get("last_accepted_bundle_hash"), "last_accepted_bundle_hash")
    if sequence < last_sequence:
        return "p136_handoff_sequence_rollback"
    if sequence == last_sequence:
        return "reuse" if bundle_hash == last_hash else "p136_handoff_same_sequence_fork"
    if sequence != last_sequence + 1:
        return "handoff_sequence_gap"
    if previous_hash != last_hash:
        return "p136_handoff_previous_hash_discontinuity"
    return "accept"


def _split_commit_pending(checkpoint: Mapping[str, Any] | None, ledger: Mapping[str, Any] | None) -> bool:
    if checkpoint is None:
        if ledger is None:
            return False
        counters = _mapping(ledger.get("counters"), "ledger_counters")
        if counters.get("cycles_completed") == 1 and ledger.get("previous_ledger_hash") is not None:
            return True
        raise P137RuntimeError("ledger_checkpoint_lineage_mismatch")
    if ledger is None:
        raise P137RuntimeError("checkpoint_without_ledger")
    checkpoint_ledger_hash = checkpoint.get("last_accepted_ledger_hash")
    if checkpoint_ledger_hash == ledger.get("ledger_hash"):
        return False
    if checkpoint_ledger_hash == ledger.get("previous_ledger_hash"):
        return True
    raise P137RuntimeError("ledger_checkpoint_lineage_mismatch")


def _load_durable_state(root: Path, config: Mapping[str, Any], activity: dict[str, int]) -> dict[str, Any]:
    intents = _read_json_directory(_resolve(root, f"{config['journal_dir']}/intents"), activity)
    atoms = _read_json_directory(_resolve(root, f"{config['journal_dir']}/atoms"), activity)
    incidents = _read_json_directory(_resolve(root, config["incident_dir"]), activity)
    hypotheses = _read_json_directory(_resolve(root, config["hypothesis_dir"]), activity)
    requests = _read_json_directory(_resolve(root, config["request_dir"]), activity)
    classifications = _read_json_directory(_resolve(root, config["classification_dir"]), activity)

    for intent in intents:
        if set(intent) != {"schema_version", "config_hash", "created_at", "bundle_sequence", "bundle_hash", "handoff_bytes_hash", "intent_hash"}:
            raise P137RuntimeError("invalid_durable_intent_fields")
        if intent.get("schema_version") != INTENT_SCHEMA_VERSION or intent.get("config_hash") != config["config_hash"]:
            raise P137RuntimeError("invalid_durable_intent")
        if intent.get("intent_hash") != stable_hash({key: value for key, value in intent.items() if key != "intent_hash"}):
            raise P137RuntimeError("durable_intent_hash_invalid")

    atoms_by_hash: dict[str, dict[str, Any]] = {}
    for atom in atoms:
        _validate_durable_atom(atom)
        atom_hash = _hash(atom.get("atom_hash"), "atom_hash")
        if atom_hash != stable_hash({key: value for key, value in atom.items() if key != "atom_hash"}):
            raise P137RuntimeError("durable_atom_hash_invalid")
        _insert_unique(atoms_by_hash, atom_hash, atom, "durable_atom_hash_conflict")

    incidents_by_hash: dict[str, dict[str, Any]] = {}
    for incident in incidents:
        incident_hash = _hash(incident.get("incident_hash"), "incident_hash")
        if incident_hash != stable_hash({key: value for key, value in incident.items() if key != "incident_hash"}):
            raise P137RuntimeError("durable_incident_hash_invalid")
        _insert_unique(incidents_by_hash, incident_hash, incident, "durable_incident_hash_conflict")

    hypotheses_by_hash: dict[str, dict[str, Any]] = {}
    for hypothesis in hypotheses:
        hypothesis_hash = _hash(hypothesis.get("hypothesis_hash"), "hypothesis_hash")
        if hypothesis_hash != stable_hash({key: value for key, value in hypothesis.items() if key != "hypothesis_hash"}):
            raise P137RuntimeError("durable_hypothesis_hash_invalid")
        _insert_unique(hypotheses_by_hash, hypothesis_hash, hypothesis, "durable_hypothesis_hash_conflict")

    requests_by_attempt: dict[str, dict[str, Any]] = {}
    requests_by_hash: dict[str, dict[str, Any]] = {}
    for request in requests:
        validate_evidence_request(request)
        attempt_hash = _hash(request.get("attempted_request_hash"), "attempted_request_hash")
        request_hash = _hash(request.get("request_hash"), "request_hash")
        _insert_unique(requests_by_attempt, attempt_hash, request, "durable_request_attempt_conflict")
        _insert_unique(requests_by_hash, request_hash, request, "durable_request_hash_conflict")

    classifications_by_hash: dict[str, dict[str, Any]] = {}
    for classification in classifications:
        classification_hash = _hash(classification.get("classification_hash"), "classification_hash")
        top_hash = classification.get("top_hypothesis_hash")
        top_hypothesis = hypotheses_by_hash.get(str(top_hash)) if top_hash is not None else None
        if top_hash is not None and top_hypothesis is None:
            raise P137RuntimeError("durable_classification_hypothesis_missing")
        validate_classification_record(classification, top_hypothesis=top_hypothesis)
        _insert_unique(classifications_by_hash, classification_hash, classification, "durable_classification_hash_conflict")

    return {
        "intents": intents,
        "atoms_by_hash": atoms_by_hash,
        "incidents_by_hash": incidents_by_hash,
        "hypotheses_by_hash": hypotheses_by_hash,
        "requests_by_attempt": requests_by_attempt,
        "requests_by_hash": requests_by_hash,
        "classifications": classifications_by_hash,
    }


def _validate_durable_ledger_membership(ledger: Mapping[str, Any] | None, durable: Mapping[str, Any]) -> None:
    if ledger is None:
        return
    atoms = _mapping(durable.get("atoms_by_hash"), "durable_atoms")
    incidents = _mapping(durable.get("incidents_by_hash"), "durable_incidents")
    hypotheses = _mapping(durable.get("hypotheses_by_hash"), "durable_hypotheses")
    requests_by_attempt = _mapping(durable.get("requests_by_attempt"), "durable_requests_by_attempt")
    requests_by_hash = _mapping(durable.get("requests_by_hash"), "durable_requests_by_hash")
    classifications = _mapping(durable.get("classifications"), "durable_classifications")
    terminal_incidents: list[Mapping[str, Any]] = []
    for incident_hash in _sequence(ledger.get("incident_hashes"), "ledger_incident_hashes"):
        incident = incidents.get(incident_hash)
        if not isinstance(incident, Mapping):
            raise P137RuntimeError("ledger_incident_missing_from_durable_state")
        terminal_incidents.append(incident)
        incident_id = incident.get("incident_id")
        incident_atom_hashes = _incident_atom_hashes(incident, atoms)
        for hypothesis_hash in _sequence(incident.get("hypothesis_hashes"), "incident_hypothesis_hashes"):
            hypothesis = hypotheses.get(hypothesis_hash)
            if not isinstance(hypothesis, Mapping) or hypothesis.get("incident_id") != incident_id:
                raise P137RuntimeError("incident_hypothesis_detached_from_durable_state")
            _validate_hypothesis_semantics(hypothesis, incident_atom_hashes)
        incident_attempts = {
            _hash(item, "incident_attempted_request_hash")
            for item in _sequence(incident.get("attempted_request_hashes"), "incident_attempted_request_hashes")
        }
        attached_attempts: set[str] = set()
        for request_hash in _sequence(incident.get("request_hashes"), "incident_request_hashes"):
            request = requests_by_hash.get(request_hash)
            if not isinstance(request, Mapping) or request.get("incident_id") != incident_id:
                raise P137RuntimeError("incident_request_detached_from_durable_state")
            attempt_hash = _hash(request.get("attempted_request_hash"), "attempted_request_hash")
            if requests_by_attempt.get(attempt_hash) != request:
                raise P137RuntimeError("durable_request_index_mismatch")
            _validate_request_semantics(request, incident, incidents, atoms)
            attached_attempts.add(attempt_hash)
        if attached_attempts != incident_attempts:
            raise P137RuntimeError("incident_request_attempt_membership_mismatch")
    for attempt_hash in _sequence(ledger.get("attempted_request_hashes"), "ledger_attempted_request_hashes"):
        request = requests_by_attempt.get(attempt_hash)
        if not isinstance(request, Mapping):
            raise P137RuntimeError("ledger_request_missing_from_durable_state")
        matching_incidents = [
            incident
            for incident in terminal_incidents
            if incident.get("incident_id") == request.get("incident_id")
            and request.get("request_hash") in _sequence(incident.get("request_hashes"), "incident_request_hashes")
            and attempt_hash in _sequence(incident.get("attempted_request_hashes"), "incident_attempted_request_hashes")
        ]
        if len(matching_incidents) != 1:
            raise P137RuntimeError("request_detached_from_durable_incident")
    for classification_hash in _sequence(ledger.get("classification_hashes"), "ledger_classification_hashes"):
        record = classifications.get(classification_hash)
        if not isinstance(record, Mapping):
            raise P137RuntimeError("ledger_classification_missing_from_durable_state")
        matching_incidents = [
            incident
            for incident_hash in _sequence(ledger.get("incident_hashes"), "ledger_incident_hashes")
            if isinstance((incident := incidents.get(incident_hash)), Mapping)
            and incident.get("incident_id") == record.get("incident_id")
            and incident.get("classification_hash") == classification_hash
            and incident.get("status") == record.get("classification")
        ]
        if len(matching_incidents) != 1:
            raise P137RuntimeError("classification_detached_from_durable_incident")
        top_hypothesis_hash = record.get("top_hypothesis_hash")
        if top_hypothesis_hash is not None and top_hypothesis_hash not in _sequence(
            matching_incidents[0].get("hypothesis_hashes"),
            "incident_hypothesis_hashes",
        ):
            raise P137RuntimeError("classification_hypothesis_detached_from_incident")
        incident_hypotheses = [
            _mapping(hypotheses.get(hypothesis_hash), "durable_hypothesis")
            for hypothesis_hash in _sequence(matching_incidents[0].get("hypothesis_hashes"), "incident_hypothesis_hashes")
        ]
        _validate_classification_semantics(record, incident_hypotheses)


_DURABLE_ATOM_FIELDS = frozenset(
    {
        "schema_version",
        "atom_id",
        "promotion_record_hash",
        "promotion_key",
        "p136_entry_hash",
        "p135_bundle_hash",
        "source_id",
        "provider",
        "format",
        "signal_family",
        "system_id",
        "entity_ref_hash",
        "window",
        "signal_name",
        "numeric_value",
        "numeric_unit",
        "evidence_state",
        "severity_code",
        "metric_breach_code",
        "marker_code",
        "counter_signal_code",
        "state_reason_codes",
        "denominator_visible",
        "content_hash",
        "label_hashes",
        "topology_ref_hashes",
        "deploy_config_ref_hashes",
        "risk_flags",
        "redacted_preview_hash",
        "ordinal",
        "atom_hash",
    }
)


def _validate_durable_atom(atom: Mapping[str, Any]) -> None:
    if set(atom) != _DURABLE_ATOM_FIELDS or atom.get("schema_version") != EVIDENCE_ATOM_SCHEMA_VERSION:
        raise P137RuntimeError("invalid_durable_atom_fields")
    try:
        validate_evidence_atom(atom)
    except ValueError as exc:
        raise P137RuntimeError("invalid_durable_atom") from exc
    _hash(atom.get("atom_hash"), "atom_hash")
    for field in (
        "promotion_record_hash",
        "promotion_key",
        "p136_entry_hash",
        "p135_bundle_hash",
        "entity_ref_hash",
        "content_hash",
        "redacted_preview_hash",
    ):
        _hash(atom.get(field), field)
    for field in ("label_hashes", "topology_ref_hashes", "deploy_config_ref_hashes"):
        for item in _sequence(atom.get(field), field):
            _hash(item, field)
    window = _mapping(atom.get("window"), "atom_window")
    if set(window) != {"start", "end"} or not isinstance(window.get("start"), str) or not isinstance(window.get("end"), str):
        raise P137RuntimeError("invalid_durable_atom_window")
    ordinal = atom.get("ordinal")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal <= 0:
        raise P137RuntimeError("invalid_durable_atom_ordinal")


def _incident_atom_hashes(incident: Mapping[str, Any], atoms: Mapping[str, Any]) -> set[str]:
    hashes = {
        _hash(item, "incident_evidence_atom_hash")
        for item in _sequence(incident.get("evidence_atom_hashes"), "incident_evidence_atom_hashes")
    }
    if not hashes or any(not isinstance(atoms.get(atom_hash), Mapping) for atom_hash in hashes):
        raise P137RuntimeError("incident_evidence_atom_missing_from_durable_state")
    return hashes


def _validate_hypothesis_semantics(hypothesis: Mapping[str, Any], incident_atom_hashes: set[str]) -> None:
    scope = _mapping(hypothesis.get("scope"), "hypothesis_scope")
    scoped = {
        _hash(item, "hypothesis_scope_atom_hash")
        for item in _sequence(scope.get("evidence_atom_hashes"), "hypothesis_scope_atom_hashes")
    }
    if not scoped or not scoped <= incident_atom_hashes:
        raise P137RuntimeError("hypothesis_scope_atom_detached_from_incident")
    for field in ("support", "contradictions"):
        for edge in _sequence(hypothesis.get(field), field):
            edge_map = _mapping(edge, field)
            if _hash(edge_map.get("evidence_atom_hash"), f"{field}_atom_hash") not in incident_atom_hashes:
                raise P137RuntimeError("hypothesis_edge_atom_detached_from_incident")
            if edge_map.get("edge_hash") != stable_hash({key: value for key, value in edge_map.items() if key != "edge_hash"}):
                raise P137RuntimeError("durable_hypothesis_edge_hash_invalid")
    for item in _sequence(hypothesis.get("missing_evidence"), "missing_evidence"):
        missing = _mapping(item, "missing_evidence")
        if missing.get("item_hash") != stable_hash({key: value for key, value in missing.items() if key != "item_hash"}):
            raise P137RuntimeError("durable_hypothesis_missing_hash_invalid")
        need_class = missing.get("request_need_class")
        unavailable_hash = _hash(missing.get("unavailable_need_hash"), "unavailable_need_hash")
        if not any(
            unavailable_hash == stable_hash({"atom_hash": atom_hash, "request_need_class": need_class})
            for atom_hash in incident_atom_hashes
        ):
            raise P137RuntimeError("hypothesis_missing_atom_detached_from_incident")


def _validate_request_semantics(
    request: Mapping[str, Any],
    terminal_incident: Mapping[str, Any],
    incidents: Mapping[str, Any],
    atoms_by_hash: Mapping[str, Any],
) -> None:
    incident_atom_hashes = _incident_atom_hashes(terminal_incident, atoms_by_hash)
    input_hashes = {
        _hash(item, "request_input_atom_hash")
        for item in _sequence(request.get("input_atom_hashes"), "request_input_atom_hashes")
    }
    if not input_hashes <= incident_atom_hashes:
        raise P137RuntimeError("request_input_atom_detached_from_incident")
    summary = _mapping(request.get("result_summary"), "request_result_summary")
    matched = {
        _hash(item, "request_matched_atom_hash")
        for item in _sequence(summary.get("matched_atom_hashes"), "request_matched_atom_hashes")
    }
    if not matched <= input_hashes:
        raise P137RuntimeError("request_matched_atom_detached_from_input")
    if summary.get("output_count") != len(matched):
        raise P137RuntimeError("request_output_count_mismatch")
    input_atoms = [_mapping(atoms_by_hash.get(atom_hash), "request_input_atom") for atom_hash in input_hashes]
    attempt_matched = False
    for incident in incidents.values():
        if not isinstance(incident, Mapping) or incident.get("incident_id") != request.get("incident_id"):
            continue
        if not input_hashes <= _incident_atom_hashes(incident, atoms_by_hash):
            continue
        expected = derive_evidence_request_record(
            incident_id=str(request.get("incident_id")),
            incident_hash=str(incident.get("incident_hash")),
            request_sequence=_positive_int(request.get("request_sequence"), "request_sequence"),
            catalog_name=str(request.get("catalog_name")),
            parameters=_mapping(request.get("parameters"), "request_parameters"),
            atoms=input_atoms,
            budget=_mapping(request.get("budget"), "request_budget"),
            previous_request_hash=request.get("previous_request_hash") if isinstance(request.get("previous_request_hash"), str) else None,
        )
        if request.get("attempted_request_hash") != expected["attempted_request_hash"]:
            continue
        attempt_matched = True
        if request.get("result_summary") != expected["result_summary"] or request.get("runtime_activity") != expected["runtime_activity"]:
            raise P137RuntimeError("request_semantic_mismatch")
        return
    if not attempt_matched:
        raise P137RuntimeError("request_attempt_semantic_mismatch")


def _validate_classification_semantics(record: Mapping[str, Any], hypotheses: Sequence[Mapping[str, Any]]) -> None:
    if record.get("classification") == "aborted_fail_closed":
        return
    semantic_tie = _top_semantic_tie(hypotheses)
    expected = derive_classification(hypotheses, accepted_incident=True, semantic_tie=semantic_tie)
    if record.get("classification") != expected:
        raise P137RuntimeError("classification_semantic_mismatch")
    ordered = sorted(hypotheses, key=_classification_hypothesis_order, reverse=True)
    if any(hypothesis.get("rank") != rank for rank, hypothesis in enumerate(ordered, start=1)):
        raise P137RuntimeError("durable_hypothesis_rank_semantic_mismatch")
    expected_top = ordered[0] if ordered else None
    if expected_top is not None and record.get("top_hypothesis_hash") != expected_top.get("hypothesis_hash"):
        raise P137RuntimeError("classification_top_hypothesis_semantic_mismatch")


def _top_semantic_tie(hypotheses: Sequence[Mapping[str, Any]]) -> bool:
    if len(hypotheses) < 2:
        return False
    ordered = sorted(hypotheses, key=_classification_hypothesis_order, reverse=True)
    return _classification_semantic_tuple(ordered[0]) == _classification_semantic_tuple(ordered[1])


def _classification_hypothesis_order(value: Mapping[str, Any]) -> tuple[int, int, int, int, int, int, str]:
    pre_rank = dict(value)
    pre_rank["rank"] = 0
    pre_rank_hash = stable_hash({key: item for key, item in pre_rank.items() if key != "hypothesis_hash"})
    return (*_classification_semantic_tuple(value), pre_rank_hash)


def _classification_semantic_tuple(value: Mapping[str, Any]) -> tuple[int, int, int, int, int, int]:
    score = _mapping(value.get("score"), "hypothesis_score")
    return (
        int(score.get("rank_score", 0)),
        int(score.get("support_weight", 0)),
        -int(score.get("contradiction_weight", 0)),
        -int(score.get("missing_required_count", 0)),
        int(score.get("freshness_weight", 0)),
        int(score.get("source_diversity_weight", 0)),
    )


def _validate_split_commit_intent(
    intents: Any,
    handoff: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
) -> None:
    if ledger is None:
        raise P137RuntimeError("split_commit_ledger_missing")
    matches = [
        intent
        for intent in _sequence(intents, "durable_intents")
        if isinstance(intent, Mapping)
        and intent.get("bundle_sequence") == handoff.get("bundle_sequence")
        and intent.get("bundle_hash") == handoff.get("bundle_hash")
    ]
    if len(matches) != 1:
        raise P137RuntimeError("split_commit_intent_mismatch")


def _last_durable_classification(ledger: Mapping[str, Any], classifications: Any) -> str:
    hashes = _sequence(ledger.get("classification_hashes"), "ledger_classification_hashes")
    if not hashes:
        return "none"
    record = _mapping(_mapping(classifications, "durable_classifications").get(hashes[-1]), "durable_classification")
    value = record.get("classification")
    if not isinstance(value, str):
        raise P137RuntimeError("durable_classification_value_invalid")
    return value


def _insert_unique(target: dict[str, dict[str, Any]], key: str, value: Mapping[str, Any], error: str) -> None:
    materialized = dict(value)
    existing = target.get(key)
    if existing is not None and existing != materialized:
        raise P137RuntimeError(error)
    target[key] = materialized


def _checkpoint(
    *,
    config: Mapping[str, Any],
    handoff: Mapping[str, Any],
    ledger: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "last_accepted_bundle_sequence": handoff["bundle_sequence"],
        "last_accepted_bundle_hash": handoff["bundle_hash"],
        "last_accepted_ledger_hash": ledger["ledger_hash"],
        "last_accepted_checkpoint_hash": prior.get("checkpoint_hash") if prior is not None else None,
    }
    value["checkpoint_hash"] = stable_hash(value)
    return value


def _validate_checkpoint(checkpoint: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "config_hash",
        "last_accepted_bundle_sequence",
        "last_accepted_bundle_hash",
        "last_accepted_ledger_hash",
        "last_accepted_checkpoint_hash",
        "checkpoint_hash",
    }
    if set(checkpoint) != required or checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise P137RuntimeError("invalid_checkpoint_fields")
    if checkpoint.get("config_hash") != config["config_hash"]:
        raise P137RuntimeError("checkpoint_config_mismatch")
    _positive_int(checkpoint.get("last_accepted_bundle_sequence"), "last_accepted_bundle_sequence")
    _hash(checkpoint.get("last_accepted_bundle_hash"), "last_accepted_bundle_hash")
    _hash(checkpoint.get("last_accepted_ledger_hash"), "last_accepted_ledger_hash")
    previous = checkpoint.get("last_accepted_checkpoint_hash")
    if previous is not None:
        _hash(previous, "last_accepted_checkpoint_hash")
    expected = stable_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_hash"})
    if checkpoint.get("checkpoint_hash") != expected:
        raise P137RuntimeError("checkpoint_hash_invalid")


def _intent(*, config: Mapping[str, Any], now: str, handoff: Mapping[str, Any], handoff_bytes: bytes) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "created_at": now,
        "bundle_sequence": handoff["bundle_sequence"],
        "bundle_hash": handoff["bundle_hash"],
        "handoff_bytes_hash": "sha256:" + hashlib.sha256(handoff_bytes).hexdigest(),
    }
    value["intent_hash"] = stable_hash(value)
    return value


def _write_stage_collection(
    root: Path,
    config: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    kind: str,
    counter: str,
    activity: dict[str, int],
) -> None:
    for item in items:
        record = _mapping(item, kind)
        _write_named_json(
            root,
            config[f"{kind}_dir"] if f"{kind}_dir" in config else config["journal_dir"],
            f"{_payload_hash(kind, item)}.json",
            record,
            activity,
            counter=counter,
        )


def _heartbeat(
    config: Mapping[str, Any],
    cycle: int,
    result: Mapping[str, Any],
    *,
    monotonic_elapsed_ms: int,
    readiness_state: str,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": HEARTBEAT_SCHEMA_VERSION,
        "agent_id": config["agent_id"],
        "config_hash": config["config_hash"],
        "cycle_sequence": cycle,
        "monotonic_elapsed_ms": monotonic_elapsed_ms,
        "last_valid_ledger_hash": _last_ledger_hash(result.get("ledger")),
        "readiness_state": readiness_state,
    }
    value["heartbeat_hash"] = stable_hash(value)
    return value


def _readiness(config: Mapping[str, Any], now: str, status: str, checkpoint: Any, reason: str | None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "written_at": now,
        "status": status,
        "reason": reason,
        "last_accepted_bundle_hash": _last_bundle_hash(checkpoint),
    }
    value["readiness_hash"] = stable_hash(value)
    return value


def _termination(
    *,
    config: Mapping[str, Any],
    stop_reason: str,
    safe_boundary: str,
    ledger: Mapping[str, Any] | None,
    open_incident_hashes: Sequence[str],
    terminal_classification_hashes: Sequence[str],
    runtime_activity: Mapping[str, int],
    evaluator_activity: Mapping[str, int],
    resource_usage: Mapping[str, int],
    authority_counters: Mapping[str, int],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": TERMINATION_SCHEMA_VERSION,
        "agent_id": config["agent_id"],
        "config_hash": config["config_hash"],
        "stop_reason": stop_reason,
        "safe_boundary": safe_boundary,
        "last_valid_ledger_hash": _last_ledger_hash(ledger),
        "open_incident_hashes": sorted(set(open_incident_hashes)),
        "terminal_classification_hashes": sorted(set(terminal_classification_hashes)),
        "runtime_activity": dict(runtime_activity),
        "evaluator_activity": dict(evaluator_activity),
        "resource_usage": dict(resource_usage),
        "authority_counters": dict(authority_counters),
    }
    value["termination_hash"] = stable_hash(value)
    return value


def _last_bundle_hash(checkpoint: Any) -> str:
    return _mapping(checkpoint, "checkpoint").get("last_accepted_bundle_hash", _HASH_NONE) if isinstance(checkpoint, Mapping) else _HASH_NONE


def _last_ledger_hash(ledger: Any) -> str:
    return _mapping(ledger, "ledger").get("ledger_hash", _HASH_NONE) if isinstance(ledger, Mapping) else _HASH_NONE


def _stop_result(
    *,
    root: Path,
    config: Mapping[str, Any],
    now: str,
    expected_error: str,
    stop_reason: str,
    safe_boundary: str,
    checkpoint: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None,
    activity: dict[str, int],
    authority: Mapping[str, int],
    evaluator: Mapping[str, int],
    termination_reason: str | None = None,
    resource_usage: Mapping[str, int] | None = None,
    open_incident_hashes: Sequence[str] = (),
    terminal_classification_hashes: Sequence[str] = (),
) -> dict[str, Any]:
    del now, checkpoint
    resources = dict(resource_usage or _resource_usage(config))
    predicted = dict(activity)
    predicted["termination_receipt_write_count"] += 1
    predicted["directory_fsync_count"] += 1
    termination = _termination(
        config=config,
        stop_reason=stop_reason,
        safe_boundary=safe_boundary,
        ledger=ledger,
        open_incident_hashes=open_incident_hashes,
        terminal_classification_hashes=terminal_classification_hashes,
        runtime_activity=predicted,
        evaluator_activity=evaluator,
        resource_usage=resources,
        authority_counters=authority,
    )
    duplicate = _write_named_json(
        root,
        str(config["termination_dir"]),
        f"{termination['termination_hash']}.json",
        termination,
        activity,
        counter="termination_receipt_write_count",
    )
    if not duplicate and activity != predicted:
        raise P137RuntimeError("termination_activity_mismatch")
    return _result(
        status="stopped" if stop_reason in {"sigint", "sigterm"} else "failed_closed",
        expected_error=expected_error,
        termination_reason=termination_reason or stop_reason,
        classification="none",
        runtime_activity=activity,
        authority_counters=authority,
        evaluator_activity=evaluator,
        resource_usage=resources,
        termination=termination,
        duplicate_termination=duplicate,
    )


def _validated_resource_probe(value: Mapping[str, int]) -> dict[str, int]:
    expected = {
        "wall_time_ms",
        "cpu_time_ms",
        "child_cpu_time_ms",
        "peak_memory_bytes",
        "wall_limit_ms",
        "cpu_limit_ms",
        "peak_memory_limit_bytes",
    }
    if set(value) != expected:
        raise P137RuntimeError("invalid_resource_probe_schema")
    result: dict[str, int] = {}
    for key in expected:
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P137RuntimeError("invalid_resource_probe_value")
        result[key] = item
    return result


def _measured_resource_usage(
    config: Mapping[str, Any],
    started_wall: float,
    started_self: Any,
    started_children: Any,
) -> dict[str, int]:
    current_self = resource.getrusage(resource.RUSAGE_SELF)
    current_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    limits = _mapping(config.get("limits"), "limits")
    return {
        "wall_time_ms": max(0, int((time.monotonic() - started_wall) * 1_000)),
        "cpu_time_ms": max(
            0,
            int(
                (
                    (current_self.ru_utime + current_self.ru_stime)
                    - (started_self.ru_utime + started_self.ru_stime)
                )
                * 1_000
            ),
        ),
        "child_cpu_time_ms": max(
            0,
            int(
                (
                    (current_children.ru_utime + current_children.ru_stime)
                    - (started_children.ru_utime + started_children.ru_stime)
                )
                * 1_000
            ),
        ),
        "peak_memory_bytes": max(0, _normalized_peak_rss_bytes(current_self) - _normalized_peak_rss_bytes(started_self)),
        "wall_limit_ms": int(limits["max_cycle_wall_ms"]),
        "cpu_limit_ms": int(limits["max_cpu_ms"]),
        "peak_memory_limit_bytes": int(limits["max_peak_memory_bytes"]),
    }


def _normalized_peak_rss_bytes(usage: Any) -> int:
    value = int(getattr(usage, "ru_maxrss", 0))
    return value if value > 10_000_000 else value * 1_024


def _resource_limit_exceeded(resources: Mapping[str, int]) -> bool:
    return (
        resources["wall_time_ms"] > resources["wall_limit_ms"]
        or resources["cpu_time_ms"] + resources["child_cpu_time_ms"] > resources["cpu_limit_ms"]
        or resources["peak_memory_bytes"] > resources["peak_memory_limit_bytes"]
    )


def _is_corrupt_state_error(error: str) -> bool:
    return error in {
        "corrupt_state",
        "checkpoint_without_ledger",
        "classification_detached_from_durable_incident",
        "classification_hypothesis_detached_from_incident",
        "conflicting_existing_bytes",
        "durable_request_index_mismatch",
        "incident_hypothesis_detached_from_durable_state",
        "incident_request_attempt_membership_mismatch",
        "incident_request_detached_from_durable_state",
        "invalid_checkpoint_fields",
        "checkpoint_config_mismatch",
        "checkpoint_hash_invalid",
        "invalid_ledger_fields",
        "ledger_hash_invalid",
        "ledger_config_hash_invalid",
        "invalid_ledger",
        "ledger_incident_missing_from_durable_state",
        "ledger_request_missing_from_durable_state",
        "ledger_classification_missing_from_durable_state",
        "request_detached_from_durable_incident",
        "request_hash_invalid",
    } or (
        error.startswith(("durable_", "invalid_durable_", "split_commit_"))
        or error.startswith(("hypothesis_", "request_", "classification_"))
        or "ledger" in error and ("invalid" in error or "mismatch" in error)
    )


def _existing_readiness_is_stale(path: Path, now: str, stale_after_ms: int) -> bool:
    if not path.exists():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P137RuntimeError("corrupt_state") from exc
    if not isinstance(value, Mapping):
        raise P137RuntimeError("corrupt_state")
    status = value.get("status")
    if status in {"stale", "stale_handoff"}:
        return True
    written_at = value.get("written_at")
    if not isinstance(written_at, str):
        return False
    return max(0, int((_parse_timestamp(now) - _parse_timestamp(written_at)).total_seconds() * 1_000)) > stale_after_ms


def _parse_timestamp(value: str) -> datetime:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise P137RuntimeError("invalid_runtime_timestamp") from exc
    if parsed.tzinfo is None:
        raise P137RuntimeError("invalid_runtime_timestamp")
    return parsed.astimezone(UTC)


def _loop_result(
    cycles_completed: int,
    max_cycles: int,
    last: Mapping[str, Any] | None,
    stale_handoff: bool,
    stop_reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": "p137.runtime_loop_result.v1",
        "cycles_completed": cycles_completed,
        "bounded": cycles_completed <= max_cycles,
        "status": (last or {}).get("status", "stopped"),
        "stale_handoff": stale_handoff,
        "termination_reason": stop_reason,
        "last_result": dict(last) if last is not None else None,
    }


def _read_optional_json(path: Path, activity: dict[str, int]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    activity["state_read_count"] += 1
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P137RuntimeError("corrupt_state") from exc


def _read_json_directory(path: Path, activity: dict[str, int]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_dir():
        raise P137RuntimeError("corrupt_state")
    values: list[dict[str, Any]] = []
    for item in sorted(path.glob("*.json")):
        if item.is_symlink() or not item.is_file():
            raise P137RuntimeError("corrupt_state")
        value = _read_optional_json(item, activity)
        if value is None or not isinstance(value, dict):
            raise P137RuntimeError("corrupt_state")
        values.append(value)
    return values


def _read_required_bytes(path: Path, activity: dict[str, int]) -> bytes:
    try:
        activity["handoff_bundle_open_count"] += 1
        raw = path.read_bytes()
    except OSError as exc:
        raise P137RuntimeError("handoff_read_failed") from exc
    activity["handoff_bundle_read_count"] += 1
    activity["handoff_bundle_bytes_read"] += len(raw)
    if not raw.endswith(b"\n"):
        raise P137RuntimeError("p136_handoff_torn_fixed_path_replacement")
    return raw


def _canonical_payload_from_framed_file(raw: bytes) -> bytes:
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise P137RuntimeError("p136_handoff_torn_fixed_path_replacement")
    payload = raw[:-1]
    if not payload or b"\n" in payload or b"\r" in payload:
        raise P137RuntimeError("p136_handoff_torn_fixed_path_replacement")
    return payload


def _write_named_json(
    root: Path,
    directory: str,
    name: str,
    value: Mapping[str, Any],
    activity: dict[str, int],
    *,
    counter: str,
) -> bool:
    return _write_json(_resolve(root, f"{directory}/{name}"), value, activity, counter)


def _write_json(path: Path, value: Mapping[str, Any], activity: dict[str, int], counter: str | None) -> bool:
    payload = _canonical_json_bytes(value)
    duplicate = _atomic_write_bytes(path, payload, activity)
    if not duplicate and counter is not None:
        activity[counter] += 1
    return duplicate


def _replace_json(path: Path, value: Mapping[str, Any], activity: dict[str, int], counter: str | None) -> None:
    payload = _canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)
    activity["directory_fsync_count"] += 1
    if counter is not None:
        activity[counter] += 1


def _atomic_write_bytes(path: Path, payload: bytes, activity: dict[str, int]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == payload:
            return True
        raise P137RuntimeError("conflicting_existing_bytes")
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)
    activity["directory_fsync_count"] += 1
    return False


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"


def _resolve(root: Path, relative: str) -> Path:
    if root.is_symlink():
        raise P137RuntimeError("runtime_root_symlink_forbidden")
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.is_symlink():
            raise P137RuntimeError("runtime_path_symlink_forbidden")
    return current


def _maybe_crash(
    requested: str | None,
    current: str,
    activity: Mapping[str, int],
    authority: Mapping[str, int],
    evaluator: Mapping[str, int],
) -> None:
    if requested != current:
        return
    raise P137RuntimeError(f"crash_after_{current}")


def _result(
    *,
    status: str,
    expected_error: str | None,
    termination_reason: str,
    classification: str,
    runtime_activity: Mapping[str, int],
    authority_counters: Mapping[str, int],
    evaluator_activity: Mapping[str, int],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema_version": "p137.runtime_result.v1",
        "status": status,
        "expected_error": expected_error,
        "termination_reason": termination_reason,
        "classification": classification,
        "runtime_activity": dict(runtime_activity),
        "authority_counters": dict(authority_counters),
        "evaluator_activity": dict(evaluator_activity),
        **extra,
    }


def _promotion_bytes_validated(handoff: Mapping[str, Any]) -> int:
    total = 0
    for atom in _sequence(handoff.get("evidence_atoms"), "evidence_atoms"):
        total += len(_canonical_json_bytes(_mapping(atom, "atom")))
    return total


def _payload_hash(kind: str, payload: Mapping[str, Any]) -> str:
    for key in (f"{kind}_hash", "atom_hash", "request_hash", "classification_hash", "hypothesis_hash", "incident_hash"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    return stable_hash({"kind": kind, "payload": payload})


def _signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name.lower()
    except ValueError:
        return str(signum)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137RuntimeError(f"invalid_{label}")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P137RuntimeError(f"invalid_{label}")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise P137RuntimeError(f"invalid_{label}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P137RuntimeError(f"invalid_{label}")
    return value


__all__ = [
    "P137RuntimeError",
    "P137StopController",
    "run_p137_runtime_loop",
    "run_p137_runtime_once",
]
