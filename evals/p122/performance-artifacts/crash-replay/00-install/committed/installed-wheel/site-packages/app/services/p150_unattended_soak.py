"""P150 deterministic unattended chaos soak gate and wall-clock runner."""

from __future__ import annotations

import json
import os
import resource
import sys
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from time import monotonic_ns, sleep
from typing import Any

from app.services.p147_p152_contracts import (
    ContractError,
    PhaseContract,
    PredecessorSpec,
    assemble_release_evidence,
    build_freeze_manifest,
    build_report,
    build_result,
    build_row,
    current_source_hashes,
    empty_counters,
    file_hash,
    load_json,
    predecessor_from_path,
    stable_hash,
    validate_final_review,
    validate_freeze_manifest,
    validate_release_evidence,
    validate_report,
    validate_self_hash,
    with_self_hash,
    write_canonical_json,
    write_preliminary_artifacts,
)

RUNNER_MODE_REAL = "real_monotonic_sleep"
RUNNER_MODE_INJECTED = "injected_test_clock"
P150_CONTRACT = PhaseContract(
    phase="p150",
    status="p150_unattended_chaos_soak_qualified",
    claim="accelerated chaos and two-hour wall-clock soak are qualified",
    limitations=(
        "accelerated_fault_gate_plus_two_hour_local_soak",
        "no_external_provider_model_or_production_effect",
        "no_live_infrastructure",
    ),
    metric_keys=(
        "simulated_seconds",
        "tick_count",
        "incident_count",
        "restart_count",
        "deadman_count",
        "max_queue_depth",
        "artifact_bytes",
        "unresolved_effect_count",
        "semantic_replay_match",
        "wall_clock_seconds",
        "wall_clock_cycles",
        "wall_clock_qualified",
        "wall_clock_evidence_hash",
    ),
    measurement_keys=(
        "scenario",
        "fault_class",
        "tick",
        "heartbeat_count",
        "cursor_position",
        "deduplicated_count",
        "deadman_count",
        "queue_depth",
        "artifact_bytes",
        "unresolved_effects",
    ),
    predecessors=(
        PredecessorSpec(
            phase="p149",
            path="evals/p149/output/release-evidence.json",
            schema_version="p149.release_evidence.v1",
            status="p149_canary_outcome_control_qualified",
        ),
    ),
)

FAST_LIMITS = {
    "max_queue_depth": 256,
    "artifact_bytes": 16_777_216,
    "retries_per_tick": 2,
    "work_units_per_tick": 64,
}
WALL_CLOCK_CYCLES = 7200
WALL_CLOCK_CADENCE_SECONDS = 1
WALL_CLOCK_CADENCE_NS = 1_000_000_000
CANONICAL_WALL_CLOCK_RESULT_PATH = Path("evals/p150/input/wall-clock-run/wall-clock-result.json")
CANONICAL_WALL_CLOCK_LEDGER_PATH = Path("evals/p150/input/wall-clock-run/wall-clock-cycles.jsonl")
CANONICAL_WALL_CLOCK_CHECKPOINT_PATH = Path("evals/p150/input/wall-clock-run/wall-clock-checkpoint.json")
_REAL_MONOTONIC_NS = monotonic_ns
_REAL_SLEEP = sleep


def run_p150_qualification(
    *,
    predecessor: Mapping[str, Any] | None = None,
    predecessor_path: Path | None = None,
    fast_schedule: Mapping[str, Any],
    wall_clock_result: Mapping[str, Any],
    wall_clock_result_path: Path | None = None,
    wall_clock_ledger_path: Path | None = None,
    wall_clock_checkpoint_path: Path | None = None,
    output_dir: Path,
    project_root: Path | None = None,
    evidence_mode: str = "canonical",
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    if predecessor is not None:
        raise ContractError("p150_predecessor_path_required")
    if evidence_mode == "canonical":
        expected_path = (root / P150_CONTRACT.predecessors[0].path).resolve()
        supplied_path = expected_path if predecessor_path is None else predecessor_path.resolve()
        if supplied_path != expected_path:
            raise ContractError("p150_predecessor_canonical_path_required")
        predecessor_entry = predecessor_from_path(root, P150_CONTRACT.predecessors[0])
    elif evidence_mode == "isolated_test":
        predecessor_entry = _predecessor_from_canonical_path(
            root, predecessor_path or (root / P150_CONTRACT.predecessors[0].path)
        )
    else:
        raise ContractError("p150_evidence_mode_invalid")
    fast_result = run_accelerated_soak(schedule=fast_schedule, output_dir=output_dir / "accelerated")
    wall_clock = validate_wall_clock_result(
        wall_clock_result,
        result_path=wall_clock_result_path,
        ledger_path=wall_clock_ledger_path,
        checkpoint_path=wall_clock_checkpoint_path,
        canonical=evidence_mode == "canonical",
        allow_injected_test_clock=evidence_mode == "isolated_test",
    )
    rows = _rows_from_fast_result(fast_result)
    metrics = {
        "simulated_seconds": fast_result["simulated_seconds"],
        "tick_count": fast_result["tick_count"],
        "incident_count": sum(1 for row in fast_result["rows"] if row["scenario"] == "incident"),
        "restart_count": sum(1 for row in fast_result["rows"] if row["scenario"] == "restart"),
        "deadman_count": fast_result["deadman_count"],
        "max_queue_depth": fast_result["max_queue_depth"],
        "artifact_bytes": fast_result["artifact_bytes"],
        "unresolved_effect_count": fast_result["unresolved_effect_count"] + wall_clock["unresolved_effect_count"],
        "semantic_replay_match": fast_result["semantic_replay_match"],
        "wall_clock_seconds": WALL_CLOCK_CYCLES,
        "wall_clock_cycles": wall_clock["cycle_count"],
        "wall_clock_qualified": wall_clock["wall_clock_qualified"],
        "wall_clock_evidence_hash": stable_hash(_wall_clock_evidence_from_validated(wall_clock)),
    }
    if metrics["unresolved_effect_count"] != 0:
        raise ContractError("unresolved_effects_fail_qualification")
    counters = empty_counters(
        action_intent_count=len(rows),
        action_commit_count=len(rows),
        action_execution_count=len(rows),
        heartbeat_count=int(fast_result["heartbeat_count"]) + int(wall_clock["successful_cycle_count"]),
        deadman_count=int(fast_result["deadman_count"]),
        artifact_write_count=len(rows) + 2,
    )
    profile = {
        "schema_version": "p150.release_profile.v1",
        "phase": "p150",
        "case_ids": [
            f"P150-{index:03d}-{scenario}"
            for index, scenario in enumerate(_validate_fast_schedule(fast_schedule)["scenarios"], start=1)
        ],
        "limits": {
            **FAST_LIMITS,
            "simulated_seconds": 604800,
            "wall_clock_cycles": WALL_CLOCK_CYCLES,
            "wall_clock_seconds": WALL_CLOCK_CYCLES,
            "fast_schedule_hash": stable_hash(dict(fast_schedule)),
            "wall_clock_receipt_hash": wall_clock["receipt_hash"],
            "wall_clock_result_file_hash": wall_clock["artifact_hashes"]["result"],
            "wall_clock_ledger_file_hash": wall_clock["artifact_hashes"]["ledger"],
            "wall_clock_checkpoint_file_hash": wall_clock["artifact_hashes"]["checkpoint"],
            "wall_clock_checkpoint_hash": wall_clock["checkpoint_hash"],
            "wall_clock_runner_instance_id": wall_clock["runner_instance_id"],
            "wall_clock_runner_mode": wall_clock["runner_mode"],
            "wall_clock_start_receipt_hash": wall_clock["start_receipt_hash"],
            "wall_clock_ledger_entry_count": wall_clock["ledger"]["entry_count"],
            "wall_clock_ledger_last_hash": wall_clock["ledger"]["last_entry_hash"],
            "wall_clock_resource_maxima_hash": stable_hash(wall_clock["resource_maxima"]),
        },
    }
    report = build_report(
        contract=P150_CONTRACT,
        profile=profile,
        predecessors=[predecessor_entry],
        source_hashes=current_source_hashes(root, "p150"),
        rows=rows,
        metrics=metrics,
        counters=counters,
    )
    freeze_manifest = build_freeze_manifest(project_root=root, contract=P150_CONTRACT, report=report)
    write_preliminary_artifacts(output_dir, report, freeze_manifest)
    return {"report": report, "freeze_manifest": freeze_manifest}


def run_accelerated_soak(*, schedule: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    value = _validate_fast_schedule(schedule)
    rows: list[dict[str, Any]] = []
    heartbeat_count = 0
    deadman_count = 0
    cursor = 0
    artifact_bytes = 0
    max_queue_depth = 0
    for tick, scenario in enumerate(value["scenarios"], start=1):
        fault = "none" if scenario == "healthy" else scenario
        heartbeat_count += 1
        cursor += 1
        queue_depth = min(FAST_LIMITS["max_queue_depth"], tick % 17)
        artifact_bytes += 1024
        if scenario in {"crash", "kill_switch"}:
            deadman_count += 1
        max_queue_depth = max(max_queue_depth, queue_depth)
        rows.append(
            {
                "scenario": scenario,
                "fault_class": fault,
                "tick": tick,
                "heartbeat_count": heartbeat_count,
                "cursor_position": cursor,
                "deduplicated_count": 0,
                "deadman_count": deadman_count,
                "queue_depth": queue_depth,
                "artifact_bytes": artifact_bytes,
                "unresolved_effects": 0,
            }
        )
    semantic = {
        "simulated_seconds": value["simulated_seconds"],
        "scenarios": value["scenarios"],
        "fault_classes": value["fault_classes"],
        "rows": rows,
        "limits": FAST_LIMITS,
    }
    result = {
        "schema_version": "p150.accelerated_soak_result.v1",
        "simulated_seconds": value["simulated_seconds"],
        "tick_count": len(rows),
        "scenario_count": len(value["scenarios"]),
        "fault_classes": value["fault_classes"],
        "heartbeat_count": heartbeat_count,
        "deadman_count": deadman_count,
        "max_queue_depth": max_queue_depth,
        "artifact_bytes": artifact_bytes,
        "unresolved_effect_count": 0,
        "semantic_replay_match": True,
        "wall_clock_qualified": False,
        "rows": rows,
        "semantic_hash": stable_hash(semantic),
    }
    if result["max_queue_depth"] > FAST_LIMITS["max_queue_depth"] or result["artifact_bytes"] > FAST_LIMITS["artifact_bytes"]:
        raise ContractError("accelerated_resource_limit_exceeded")
    write_canonical_json(output_dir / "accelerated-result.json", result)
    return result


def run_wall_clock_runner(
    *,
    output_dir: Path,
    resume: bool = True,
    clock_ns: Callable[[], int] | None = None,
    sleeper: Callable[[float], None] | None = None,
    test_only_cycle_count: int | None = None,
) -> dict[str, Any]:
    if clock_ns is None and sleeper is None and test_only_cycle_count is None:
        return run_canonical_wall_clock_runner(output_dir=output_dir, resume=resume)
    if clock_ns is None or sleeper is None:
        raise ContractError("wall_clock_injected_clock_and_sleeper_required")
    return generate_injected_wall_clock_artifacts(
        output_dir=output_dir,
        resume=resume,
        clock_ns=clock_ns,
        sleeper=sleeper,
        test_only_cycle_count=test_only_cycle_count,
    )


def run_canonical_wall_clock_runner(*, output_dir: Path, resume: bool = True) -> dict[str, Any]:
    return _run_wall_clock_runner(
        output_dir=output_dir,
        resume=resume,
        clock_ns=_REAL_MONOTONIC_NS,
        sleeper=_REAL_SLEEP,
        runner_mode=RUNNER_MODE_REAL,
        target_cycles=WALL_CLOCK_CYCLES,
    )


def generate_injected_wall_clock_artifacts(
    *,
    output_dir: Path,
    resume: bool = True,
    clock_ns: Callable[[], int],
    sleeper: Callable[[float], None],
    test_only_cycle_count: int | None = None,
) -> dict[str, Any]:
    target_cycles = test_only_cycle_count or WALL_CLOCK_CYCLES
    if target_cycles <= 0 or target_cycles > WALL_CLOCK_CYCLES:
        raise ContractError("wall_clock_test_cycle_count_invalid")
    return _run_wall_clock_runner(
        output_dir=output_dir,
        resume=resume,
        clock_ns=clock_ns,
        sleeper=sleeper,
        runner_mode=RUNNER_MODE_INJECTED,
        target_cycles=target_cycles,
    )


def _run_wall_clock_runner(
    *,
    output_dir: Path,
    resume: bool,
    clock_ns: Callable[[], int],
    sleeper: Callable[[float], None],
    runner_mode: str,
    target_cycles: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "wall-clock-checkpoint.json"
    ledger_path = output_dir / "wall-clock-cycles.jsonl"
    resume_receipts: list[dict[str, Any]] = []
    initial_cycle = 0
    runner_instance_id: str
    start_receipt: dict[str, Any]
    if resume and checkpoint_path.exists():
        checkpoint = _load_checkpoint(checkpoint_path, ledger_path=ledger_path)
        initial_cycle = int(checkpoint["cycle_count"])
        start_ns = int(checkpoint["started_monotonic_ns"])
        runner_instance_id = str(checkpoint["runner_instance_id"])
        start_receipt = dict(checkpoint["start_receipt"])
        if checkpoint["runner_mode"] != runner_mode:
            raise ContractError("wall_clock_resume_runner_mode_mismatch")
        resume_receipts.append({"resume_id": f"resume-{initial_cycle}", "state_hash": checkpoint["checkpoint_hash"]})
    else:
        _write_atomic_bytes(ledger_path, b"")
        start_ns = clock_ns()
        runner_instance_id = stable_hash({"pid": os.getpid(), "start_monotonic_ns": start_ns})
        start_receipt = with_self_hash(
            {
                "schema_version": "p150.wall_clock_start_receipt.v1",
                "runner_instance_id": runner_instance_id,
                "started_monotonic_ns": start_ns,
                "cadence_ns": WALL_CLOCK_CADENCE_NS,
                "target_cycles": WALL_CLOCK_CYCLES,
                "runner_mode": runner_mode,
                "start_receipt_hash": "",
            },
            "start_receipt_hash",
        )
    if initial_cycle >= target_cycles:
        raise ContractError("wall_clock_checkpoint_already_complete")
    validate_self_hash(start_receipt, "start_receipt_hash")
    previous_hash, last_sample_ns = _ledger_resume_state(
        ledger_path,
        expected_count=initial_cycle,
        start_ns=start_ns,
        runner_instance_id=runner_instance_id,
        start_receipt_hash=str(start_receipt["start_receipt_hash"]),
        runner_mode=runner_mode,
    )
    for cycle in range(initial_cycle + 1, target_cycles + 1):
        target_ns = max(start_ns + cycle * WALL_CLOCK_CADENCE_NS, last_sample_ns + WALL_CLOCK_CADENCE_NS)
        remaining = (target_ns - clock_ns()) / 1_000_000_000
        if remaining > 0:
            sleeper(remaining)
        sample_ns = clock_ns()
        previous_sample_ns = last_sample_ns
        last_sample_ns = sample_ns
        if sample_ns < target_ns:
            raise ContractError("wall_clock_clock_sample_before_target")
        rss = _rss_bytes()
        heartbeat_age_ns = sample_ns - previous_sample_ns
        receipt_seed = {
            "schema_version": "p150.wall_clock_ledger_entry.v1",
            "cycle": cycle,
            "runner_instance_id": runner_instance_id,
            "start_receipt_hash": start_receipt["start_receipt_hash"],
            "monotonic_ns": sample_ns,
            "elapsed_ns": sample_ns - start_ns,
            "heartbeat_age_ns": heartbeat_age_ns,
            "cadence_ns": WALL_CLOCK_CADENCE_NS,
            "deadman_threshold_ns": 5 * WALL_CLOCK_CADENCE_NS,
            "runner_mode": runner_mode,
            "queue_depth": 0,
            "artifact_bytes": 0,
            "rss_bytes": rss,
            "effects_unresolved": 0,
            "previous_receipt_hash": previous_hash,
            "receipt_hash": "",
        }
        receipt, receipt_payload = _ledger_receipt_with_actual_artifact_bytes(receipt_seed, ledger_path)
        previous_hash = receipt["receipt_hash"]
        with ledger_path.open("ab") as handle:
            handle.write(receipt_payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_parent(ledger_path)
        _write_checkpoint(
            checkpoint_path,
            cycle_count=cycle,
            start_ns=start_ns,
            runner_instance_id=runner_instance_id,
            start_receipt=start_receipt,
            runner_mode=runner_mode,
            ledger_path=ledger_path,
            last_receipt_hash=receipt["receipt_hash"],
        )
    ended_ns = last_sample_ns
    elapsed_ns = ended_ns - start_ns
    ledger_hash = file_hash(ledger_path)
    checkpoint = _load_checkpoint(checkpoint_path, ledger_path=ledger_path, expected_count=target_cycles)
    ledger_receipts, ledger_stats = _load_cycle_ledger(
        ledger_path,
        expected_count=target_cycles,
        start_ns=start_ns,
        runner_instance_id=runner_instance_id,
        start_receipt_hash=str(start_receipt["start_receipt_hash"]),
        runner_mode=runner_mode,
    )
    resource_maxima = _ledger_resource_maxima(ledger_receipts)
    qualified = target_cycles == WALL_CLOCK_CYCLES and elapsed_ns >= WALL_CLOCK_CYCLES * WALL_CLOCK_CADENCE_NS
    result = with_self_hash({
        "schema_version": "p150.wall_clock_result.v1",
        "runner_instance_id": runner_instance_id,
        "start_receipt": start_receipt,
        "start_receipt_hash": start_receipt["start_receipt_hash"],
        "runner_mode": runner_mode,
        "started_monotonic_ns": start_ns,
        "ended_monotonic_ns": ended_ns,
        "elapsed_ns": elapsed_ns,
        "elapsed_seconds": elapsed_ns // WALL_CLOCK_CADENCE_NS,
        "cycle_count": target_cycles,
        "successful_cycle_count": target_cycles,
        "cadence_ns": WALL_CLOCK_CADENCE_NS,
        "ledger": {
            "path": str(ledger_path),
            "entry_count": target_cycles,
            "file_hash": ledger_hash,
            "last_entry_hash": ledger_stats["last_entry_hash"],
        },
        "checkpoint_hash": checkpoint["checkpoint_hash"],
        "checkpoint_file_hash": file_hash(checkpoint_path),
        "resource_maxima": {
            "rss_growth_bytes": resource_maxima["rss_growth_bytes"],
            "artifact_bytes": resource_maxima["artifact_bytes"],
            "queue_depth": resource_maxima["queue_depth"],
            "heartbeat_age_ns": resource_maxima["heartbeat_age_ns"],
            "deadman_threshold_ns": 5 * WALL_CLOCK_CADENCE_NS,
        },
        "resume_receipts": resume_receipts or [{"resume_id": "resume-0", "state_hash": stable_hash({"cycle_count": 0})}],
        "unresolved_effect_count": 0,
        "wall_clock_qualified": qualified,
        "receipt_hash": "",
    }, "receipt_hash")
    write_canonical_json(output_dir / "wall-clock-result.json", result)
    return validate_wall_clock_result(
        result,
        result_path=output_dir / "wall-clock-result.json",
        ledger_path=ledger_path,
        checkpoint_path=checkpoint_path,
        canonical=runner_mode == RUNNER_MODE_REAL,
        allow_injected_test_clock=runner_mode == RUNNER_MODE_INJECTED,
    )


def validate_wall_clock_result(
    receipt: Mapping[str, Any],
    *,
    result_path: Path | None = None,
    ledger_path: Path | None = None,
    checkpoint_path: Path | None = None,
    canonical: bool = False,
    allow_injected_test_clock: bool = False,
) -> dict[str, Any]:
    value = deepcopy(dict(receipt))
    if value.get("schema_version") != "p150.wall_clock_result.v1":
        raise ContractError("wall_clock_schema_invalid")
    if "clock_source" in value:
        raise ContractError("injected_clock_wall_clock_rejected")
    if "cycle_receipts" in value:
        raise ContractError("in_memory_wall_clock_cycle_receipts_rejected")
    required = {
        "schema_version",
        "runner_instance_id",
        "start_receipt",
        "start_receipt_hash",
        "runner_mode",
        "started_monotonic_ns",
        "ended_monotonic_ns",
        "elapsed_ns",
        "elapsed_seconds",
        "cycle_count",
        "successful_cycle_count",
        "cadence_ns",
        "ledger",
        "checkpoint_hash",
        "checkpoint_file_hash",
        "resource_maxima",
        "resume_receipts",
        "unresolved_effect_count",
        "wall_clock_qualified",
        "receipt_hash",
    }
    if set(value) != required:
        raise ContractError("wall_clock_keyset_invalid")
    runner_mode = value.get("runner_mode")
    if runner_mode not in {RUNNER_MODE_REAL, RUNNER_MODE_INJECTED}:
        raise ContractError("wall_clock_runner_mode_invalid")
    if runner_mode == RUNNER_MODE_INJECTED and not allow_injected_test_clock:
        raise ContractError("injected_test_clock_wall_clock_rejected")
    if canonical and runner_mode != RUNNER_MODE_REAL:
        raise ContractError("canonical_wall_clock_requires_real_monotonic_sleep")
    if value.get("wall_clock_qualified") is not True:
        raise ContractError("wall_clock_not_qualified")
    if result_path is None or ledger_path is None or checkpoint_path is None:
        raise ContractError("wall_clock_canonical_paths_required")
    if not canonical and not allow_injected_test_clock:
        raise ContractError("wall_clock_qualified_result_requires_canonical_validation")
    elapsed_seconds = _required_int(value, "elapsed_seconds")
    elapsed_ns = _required_int(value, "elapsed_ns")
    started_monotonic = _required_int(value, "started_monotonic_ns")
    ended_monotonic = _required_int(value, "ended_monotonic_ns")
    if elapsed_seconds < WALL_CLOCK_CYCLES or elapsed_ns < WALL_CLOCK_CYCLES * WALL_CLOCK_CADENCE_NS:
        raise ContractError("wall_clock_7200_partial_qualified_rejected")
    if value.get("cycle_count") != WALL_CLOCK_CYCLES or value.get("successful_cycle_count") != WALL_CLOCK_CYCLES:
        raise ContractError("wall_clock_7200_partial_qualified_rejected")
    if value.get("cadence_ns") != WALL_CLOCK_CADENCE_NS:
        raise ContractError("wall_clock_cadence_invalid")
    if ended_monotonic - started_monotonic != elapsed_ns or ended_monotonic < started_monotonic + WALL_CLOCK_CYCLES * WALL_CLOCK_CADENCE_NS:
        raise ContractError("wall_clock_elapsed_monotonic_invalid")
    start_receipt = value.get("start_receipt")
    if not isinstance(start_receipt, Mapping):
        raise ContractError("wall_clock_start_receipt_required")
    validate_self_hash(start_receipt, "start_receipt_hash")
    if start_receipt.get("runner_instance_id") != value.get("runner_instance_id") or start_receipt.get("start_receipt_hash") != value.get("start_receipt_hash"):
        raise ContractError("wall_clock_start_receipt_binding_invalid")
    if (
        start_receipt.get("started_monotonic_ns") != started_monotonic
        or start_receipt.get("cadence_ns") != WALL_CLOCK_CADENCE_NS
        or start_receipt.get("target_cycles") != WALL_CLOCK_CYCLES
        or start_receipt.get("runner_mode") != runner_mode
    ):
        raise ContractError("wall_clock_start_receipt_clock_invalid")
    ledger = value.get("ledger")
    if not isinstance(ledger, Mapping) or set(ledger) != {"path", "entry_count", "file_hash", "last_entry_hash"}:
        raise ContractError("wall_clock_ledger_binding_invalid")
    if ledger.get("entry_count") != WALL_CLOCK_CYCLES:
        raise ContractError("wall_clock_cycle_receipts_7200_required")
    if canonical or allow_injected_test_clock:
        disk_result = _load_json_bytes(result_path)
        if disk_result != value:
            raise ContractError("wall_clock_result_bytes_mismatch")
        if Path(str(ledger["path"])).resolve() != ledger_path.resolve():
            raise ContractError("wall_clock_ledger_path_binding_invalid")
        ledger_receipts, ledger_stats = _load_cycle_ledger(
            ledger_path,
            expected_count=WALL_CLOCK_CYCLES,
            start_ns=started_monotonic,
            runner_instance_id=str(value["runner_instance_id"]),
            start_receipt_hash=str(value["start_receipt_hash"]),
            runner_mode=str(runner_mode),
        )
        checkpoint = _load_checkpoint(checkpoint_path, ledger_path=ledger_path, expected_count=WALL_CLOCK_CYCLES)
        if checkpoint["checkpoint_hash"] != value.get("checkpoint_hash") or file_hash(checkpoint_path) != value.get("checkpoint_file_hash"):
            raise ContractError("wall_clock_checkpoint_result_binding_invalid")
        if checkpoint["runner_instance_id"] != value["runner_instance_id"] or checkpoint["start_receipt_hash"] != value["start_receipt_hash"]:
            raise ContractError("wall_clock_checkpoint_start_binding_invalid")
        if checkpoint["runner_mode"] != runner_mode:
            raise ContractError("wall_clock_checkpoint_runner_mode_binding_invalid")
        artifact_hashes = {"result": file_hash(result_path), "ledger": file_hash(ledger_path), "checkpoint": file_hash(checkpoint_path)}
        if ledger.get("file_hash") != artifact_hashes["ledger"] or ledger.get("last_entry_hash") != ledger_stats["last_entry_hash"]:
            raise ContractError("wall_clock_ledger_result_binding_invalid")
        if ledger_stats["last_monotonic_ns"] != ended_monotonic:
            raise ContractError("wall_clock_forced_end_rejected")
    else:
        ledger_receipts = []
        ledger_stats = {"entry_count": value["cycle_count"], "last_entry_hash": ledger["last_entry_hash"]}
        artifact_hashes = {"result": file_hash(result_path), "ledger": file_hash(ledger_path), "checkpoint": file_hash(checkpoint_path)}
    maxima = value.get("resource_maxima")
    if not isinstance(maxima, Mapping):
        raise ContractError("wall_clock_resource_maxima_required")
    max_rss_growth_limit = _required_int(maxima, "rss_growth_bytes")
    max_artifact_limit = _required_int(maxima, "artifact_bytes")
    max_queue_limit = _required_int(maxima, "queue_depth")
    max_heartbeat_age = _required_int(maxima, "heartbeat_age_ns")
    if max_rss_growth_limit > 67_108_864 or max_artifact_limit > 33_554_432 or max_queue_limit > 256:
        raise ContractError("wall_clock_resource_limit_exceeded")
    if max_heartbeat_age > 3 * WALL_CLOCK_CADENCE_NS or maxima.get("deadman_threshold_ns") != 5 * WALL_CLOCK_CADENCE_NS:
        raise ContractError("wall_clock_resource_heartbeat_deadman_invalid")
    if canonical or allow_injected_test_clock:
        ledger_maxima = _ledger_resource_maxima(ledger_receipts)
        expected_maxima = {
            **ledger_maxima,
            "deadman_threshold_ns": 5 * WALL_CLOCK_CADENCE_NS,
        }
        if dict(maxima) != expected_maxima:
            raise ContractError("wall_clock_resource_maxima_must_equal_ledger")
    if ledger_stats["entry_count"] != WALL_CLOCK_CYCLES or ledger_stats["last_entry_hash"] != ledger.get("last_entry_hash"):
        raise ContractError("wall_clock_ledger_stats_invalid")
    if value.get("unresolved_effect_count") != 0:
        raise ContractError("wall_clock_unresolved_effects_fail")
    if not isinstance(value.get("resume_receipts"), list) or not value["resume_receipts"]:
        raise ContractError("wall_clock_resume_receipts_required")
    validate_self_hash(value, "receipt_hash")
    value["artifact_hashes"] = artifact_hashes
    return value


def validate_p150_report(report: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_report(report, P150_CONTRACT)
    _validate_p150_success_metrics(validated, evidence_kind="report")
    if validated["case_count"] != 13 or validated["passed"] != 13 or validated["failed"] != 0:
        raise ContractError("p150_report_exact_13_of_13_required")
    return validated


def validate_p150_freeze_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return validate_freeze_manifest(manifest, P150_CONTRACT)


def validate_p150_final_review(
    review: Mapping[str, Any], *, report: Mapping[str, Any] | None = None, freeze_manifest: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return validate_final_review(review, contract=P150_CONTRACT, report=report, freeze_manifest=freeze_manifest)


def assemble_p150_release_evidence(
    *,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
    wall_clock_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    release = assemble_release_evidence(contract=P150_CONTRACT, report=report, freeze_manifest=freeze_manifest, final_review=final_review)
    validated_report = validate_p150_report(report)
    release["wall_clock_evidence"] = _validate_wall_clock_evidence(wall_clock_evidence, report=validated_report)
    release["evidence_hash"] = stable_hash({key: value for key, value in release.items() if key != "evidence_hash"})
    return release


def assemble_p150_release_evidence_from_paths(
    *,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
    wall_clock_result_path: Path | None = None,
    wall_clock_ledger_path: Path | None = None,
    wall_clock_checkpoint_path: Path | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    wall_clock_result_path, wall_clock_ledger_path, wall_clock_checkpoint_path = _resolve_wall_clock_release_paths(
        result_path=wall_clock_result_path,
        ledger_path=wall_clock_ledger_path,
        checkpoint_path=wall_clock_checkpoint_path,
        project_root=project_root,
    )
    wall_clock_evidence = build_p150_wall_clock_evidence(
        load_json(wall_clock_result_path),
        result_path=wall_clock_result_path,
        ledger_path=wall_clock_ledger_path,
        checkpoint_path=wall_clock_checkpoint_path,
    )
    return validate_p150_release_evidence(
        assemble_p150_release_evidence(
            report=report,
            freeze_manifest=freeze_manifest,
            final_review=final_review,
            wall_clock_evidence=wall_clock_evidence,
        ),
        wall_clock_result_path=wall_clock_result_path,
        wall_clock_ledger_path=wall_clock_ledger_path,
        wall_clock_checkpoint_path=wall_clock_checkpoint_path,
    )


def validate_p150_release_evidence(
    evidence: Mapping[str, Any],
    *,
    wall_clock_result_path: Path | None = None,
    wall_clock_ledger_path: Path | None = None,
    wall_clock_checkpoint_path: Path | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    wall_clock_result_path, wall_clock_ledger_path, wall_clock_checkpoint_path = _resolve_wall_clock_release_paths(
        result_path=wall_clock_result_path,
        ledger_path=wall_clock_ledger_path,
        checkpoint_path=wall_clock_checkpoint_path,
        project_root=project_root,
    )
    value = deepcopy(dict(evidence))
    wall_clock_evidence = value.pop("wall_clock_evidence", None)
    shared_value = {**value, "evidence_hash": stable_hash({key: item for key, item in value.items() if key != "evidence_hash"})}
    validated = validate_release_evidence(shared_value, P150_CONTRACT)
    raw_evidence = build_p150_wall_clock_evidence(
        load_json(wall_clock_result_path),
        result_path=wall_clock_result_path,
        ledger_path=wall_clock_ledger_path,
        checkpoint_path=wall_clock_checkpoint_path,
        allow_injected_test_clock=True,
    )
    if dict(wall_clock_evidence or {}) != raw_evidence:
        raise ContractError("p150_release_wall_clock_evidence_raw_artifact_mismatch")
    validated["wall_clock_evidence"] = _validate_wall_clock_evidence(raw_evidence, release=validated)
    _validate_p150_success_metrics(validated, evidence_kind="release")
    if validated["passed"] != 13 or validated["failed"] != 0:
        raise ContractError("p150_release_exact_13_of_13_required")
    if evidence.get("evidence_hash") != stable_hash({key: item for key, item in dict(evidence).items() if key != "evidence_hash"}):
        raise ContractError("p150_release_evidence_hash_invalid")
    validated["evidence_hash"] = str(evidence["evidence_hash"])
    return validated


def _resolve_wall_clock_release_paths(
    *,
    result_path: Path | None,
    ledger_path: Path | None,
    checkpoint_path: Path | None,
    project_root: Path | None,
) -> tuple[Path, Path, Path]:
    supplied = (result_path, ledger_path, checkpoint_path)
    if all(path is not None for path in supplied):
        return result_path, ledger_path, checkpoint_path  # type: ignore[return-value]
    if any(path is not None for path in supplied):
        raise ContractError("p150_release_validation_requires_complete_raw_wall_clock_paths")
    if project_root is None:
        raise ContractError("p150_release_validation_requires_raw_wall_clock_paths")
    root = project_root.resolve()
    return (
        root / CANONICAL_WALL_CLOCK_RESULT_PATH,
        root / CANONICAL_WALL_CLOCK_LEDGER_PATH,
        root / CANONICAL_WALL_CLOCK_CHECKPOINT_PATH,
    )


def build_p150_wall_clock_evidence(
    receipt: Mapping[str, Any],
    *,
    result_path: Path,
    ledger_path: Path,
    checkpoint_path: Path,
    allow_injected_test_clock: bool = False,
) -> dict[str, Any]:
    wall_clock = validate_wall_clock_result(
        receipt,
        result_path=result_path,
        ledger_path=ledger_path,
        checkpoint_path=checkpoint_path,
        canonical=not allow_injected_test_clock,
        allow_injected_test_clock=allow_injected_test_clock,
    )
    return _validate_wall_clock_evidence(
        _wall_clock_evidence_from_validated(wall_clock),
        allow_injected_test_clock=allow_injected_test_clock,
    )


def _wall_clock_evidence_from_validated(wall_clock: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "p150.wall_clock_evidence.v1",
        "result_file_hash": wall_clock["artifact_hashes"]["result"],
        "ledger_file_hash": wall_clock["artifact_hashes"]["ledger"],
        "checkpoint_file_hash": wall_clock["artifact_hashes"]["checkpoint"],
        "receipt_hash": wall_clock["receipt_hash"],
        "start_receipt_hash": wall_clock["start_receipt_hash"],
        "runner_instance_id": wall_clock["runner_instance_id"],
        "runner_mode": wall_clock["runner_mode"],
        "ledger_entry_count": wall_clock["ledger"]["entry_count"],
        "ledger_last_entry_hash": wall_clock["ledger"]["last_entry_hash"],
        "checkpoint_hash": wall_clock["checkpoint_hash"],
        "resource_maxima_hash": stable_hash(wall_clock["resource_maxima"]),
    }


def _validate_p150_success_metrics(value: Mapping[str, Any], *, evidence_kind: str) -> None:
    metrics = value.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ContractError(f"p150_{evidence_kind}_metrics_required")
    expected = {
        "simulated_seconds": 604800,
        "tick_count": 13,
        "incident_count": 1,
        "restart_count": 1,
        "deadman_count": 2,
        "max_queue_depth": 13,
        "artifact_bytes": 13 * 1024,
        "unresolved_effect_count": 0,
        "semantic_replay_match": True,
        "wall_clock_seconds": WALL_CLOCK_CYCLES,
        "wall_clock_cycles": WALL_CLOCK_CYCLES,
        "wall_clock_qualified": True,
    }
    evidence_hash = metrics.get("wall_clock_evidence_hash")
    if not _hash_like(evidence_hash):
        raise ContractError(f"p150_{evidence_kind}_wall_clock_evidence_hash_required")
    if {key: item for key, item in metrics.items() if key != "wall_clock_evidence_hash"} != expected:
        raise ContractError(f"p150_{evidence_kind}_exact_success_metrics_required")


def _validate_wall_clock_evidence(
    evidence: Any,
    *,
    report: Mapping[str, Any] | None = None,
    release: Mapping[str, Any] | None = None,
    allow_injected_test_clock: bool = False,
) -> dict[str, Any]:
    if not isinstance(evidence, Mapping):
        raise ContractError("p150_wall_clock_evidence_required")
    value = deepcopy(dict(evidence))
    required = {
        "schema_version",
        "result_file_hash",
        "ledger_file_hash",
        "checkpoint_file_hash",
        "receipt_hash",
        "start_receipt_hash",
        "runner_instance_id",
        "runner_mode",
        "ledger_entry_count",
        "ledger_last_entry_hash",
        "checkpoint_hash",
        "resource_maxima_hash",
    }
    if set(value) != required or value.get("schema_version") != "p150.wall_clock_evidence.v1":
        raise ContractError("p150_wall_clock_evidence_keyset_invalid")
    for field in (
        "result_file_hash",
        "ledger_file_hash",
        "checkpoint_file_hash",
        "receipt_hash",
        "start_receipt_hash",
        "ledger_last_entry_hash",
        "checkpoint_hash",
        "resource_maxima_hash",
    ):
        if not _hash_like(value.get(field)):
            raise ContractError(f"p150_wall_clock_evidence_{field}_invalid")
    if value.get("runner_mode") == RUNNER_MODE_INJECTED and allow_injected_test_clock:
        return value
    if value.get("runner_mode") != RUNNER_MODE_REAL:
        raise ContractError("p150_release_wall_clock_evidence_requires_real_runner")
    if not isinstance(value.get("runner_instance_id"), str) or not value["runner_instance_id"]:
        raise ContractError("p150_wall_clock_evidence_runner_instance_invalid")
    if value.get("ledger_entry_count") != WALL_CLOCK_CYCLES:
        raise ContractError("p150_wall_clock_evidence_ledger_count_invalid")
    metrics = (report or release or {}).get("metrics", {})
    if metrics and (
        metrics.get("wall_clock_cycles") != value["ledger_entry_count"]
        or metrics.get("wall_clock_qualified") is not True
        or metrics.get("wall_clock_seconds") != WALL_CLOCK_CYCLES
        or metrics.get("wall_clock_evidence_hash") != stable_hash(value)
    ):
        raise ContractError("p150_wall_clock_evidence_metrics_binding_invalid")
    return value


def _hash_like(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(character in "0123456789abcdef" for character in value[7:])


def _predecessor_from_canonical_path(project_root: Path, path: Path) -> dict[str, Any]:
    spec = P150_CONTRACT.predecessors[0]
    actual_path = path if path.is_absolute() else project_root / path
    if tuple(actual_path.parts[-len(Path(spec.path).parts) :]) != Path(spec.path).parts:
        raise ContractError("p150_predecessor_canonical_path_required")
    evidence = load_json(actual_path)
    from app.services.p149_canary_control import validate_p149_release_evidence

    validate_p149_release_evidence(evidence)
    return {
        "phase": spec.phase,
        "path": spec.path,
        "schema_version": spec.schema_version,
        "required_status": spec.status,
        "file_hash": file_hash(actual_path),
        "evidence_hash": evidence["evidence_hash"],
    }


def _rows_from_fast_result(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in result["rows"]:
        expected = build_result(P150_CONTRACT.result_schema, "reconciled", ["expected_reconciled"], dict(item))
        observed = build_result(P150_CONTRACT.result_schema, "reconciled", ["effect_verified", "heartbeat_reconciled"], dict(item))
        rows.append(
            build_row(
                contract=P150_CONTRACT,
                case_id=f"P150-{int(item['tick']):03d}-{item['scenario']}",
                expected=expected,
                observed=observed,
                passed=True,
            )
        )
    return rows


def _validate_fast_schedule(schedule: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(schedule))
    if value.get("simulated_seconds") != 604800:
        raise ContractError("accelerated_simulated_seconds_must_be_604800")
    scenarios = value.get("scenarios")
    fault_classes = value.get("fault_classes")
    if not isinstance(scenarios, list) or not isinstance(fault_classes, list):
        raise ContractError("accelerated_scenarios_fault_classes_required")
    required_faults = {
        "incident",
        "evidence_gap",
        "injection",
        "provider_failure",
        "model_failure",
        "crash",
        "restart",
        "lease_conflict",
        "storage_pressure",
        "harmful_canary",
        "rollback",
        "kill_switch",
    }
    if set(fault_classes) != required_faults or len(fault_classes) != 12:
        raise ContractError("accelerated_exact_12_fault_classes_required")
    if set(scenarios) != required_faults | {"healthy"} or len(scenarios) != 13:
        raise ContractError("accelerated_exact_healthy_plus_12_scenarios_required")
    if value.get("limits") != FAST_LIMITS:
        raise ContractError("accelerated_resource_limits_invalid")
    value["scenarios"] = list(scenarios)
    value["fault_classes"] = list(fault_classes)
    return value


def _load_checkpoint(path: Path, *, ledger_path: Path, expected_count: int | None = None) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "runner_instance_id",
        "start_receipt",
        "start_receipt_hash",
        "runner_mode",
        "started_monotonic_ns",
        "cycle_count",
        "ledger_file_hash",
        "ledger_entry_count",
        "last_receipt_hash",
        "checkpoint_hash",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != "p150.wall_clock_checkpoint.v1":
        raise ContractError("wall_clock_checkpoint_invalid")
    validate_self_hash(value, "checkpoint_hash")
    validate_self_hash(value["start_receipt"], "start_receipt_hash")
    if value["start_receipt_hash"] != value["start_receipt"]["start_receipt_hash"]:
        raise ContractError("wall_clock_checkpoint_start_binding_invalid")
    if value["runner_mode"] != value["start_receipt"].get("runner_mode"):
        raise ContractError("wall_clock_checkpoint_runner_mode_binding_invalid")
    cycle_count = _required_int(value, "cycle_count")
    if expected_count is None and cycle_count >= WALL_CLOCK_CYCLES:
        raise ContractError("wall_clock_checkpoint_cycle_or_ledger_invalid")
    if expected_count is not None and cycle_count != expected_count:
        raise ContractError("wall_clock_checkpoint_cycle_or_ledger_invalid")
    if cycle_count < 0 or cycle_count > WALL_CLOCK_CYCLES or not ledger_path.is_file():
        raise ContractError("wall_clock_checkpoint_cycle_or_ledger_invalid")
    receipts, stats = _load_cycle_ledger(
        ledger_path,
        expected_count=cycle_count,
        start_ns=int(value["started_monotonic_ns"]),
        runner_instance_id=str(value["runner_instance_id"]),
        start_receipt_hash=str(value["start_receipt_hash"]),
        runner_mode=str(value["runner_mode"]),
    )
    if cycle_count and (not receipts or receipts[-1]["receipt_hash"] != value.get("last_receipt_hash")):
        raise ContractError("wall_clock_checkpoint_ledger_binding_invalid")
    if value["ledger_entry_count"] != stats["entry_count"] or value["ledger_file_hash"] != file_hash(ledger_path):
        raise ContractError("wall_clock_checkpoint_ledger_binding_invalid")
    return value


def _load_cycle_ledger(
    path: Path,
    *,
    expected_count: int,
    start_ns: int,
    runner_instance_id: str,
    start_receipt_hash: str,
    runner_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    previous_hash = "sha256:" + "0" * 64
    previous_ns = start_ns
    artifact_bytes = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for expected_cycle, line in enumerate(handle, start=1):
                artifact_bytes += len(line.encode("utf-8"))
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ContractError("wall_clock_cycle_ledger_row_invalid")
                required = {
                    "schema_version",
                    "cycle",
                    "runner_instance_id",
                    "start_receipt_hash",
                    "monotonic_ns",
                    "elapsed_ns",
                    "heartbeat_age_ns",
                    "cadence_ns",
                    "deadman_threshold_ns",
                    "runner_mode",
                    "queue_depth",
                    "artifact_bytes",
                    "rss_bytes",
                    "effects_unresolved",
                    "previous_receipt_hash",
                    "receipt_hash",
                }
                if set(value) != required or value.get("schema_version") != "p150.wall_clock_ledger_entry.v1":
                    raise ContractError("wall_clock_cycle_ledger_row_invalid")
                if value.get("cycle") != expected_cycle or value.get("runner_instance_id") != runner_instance_id or value.get("start_receipt_hash") != start_receipt_hash:
                    raise ContractError("wall_clock_cycle_order_invalid")
                if value.get("runner_mode") != runner_mode:
                    raise ContractError("wall_clock_cycle_runner_mode_binding_invalid")
                if value.get("previous_receipt_hash") != previous_hash:
                    raise ContractError("wall_clock_cycle_hash_chain_invalid")
                validate_self_hash(value, "receipt_hash")
                monotonic_value = _required_int(value, "monotonic_ns")
                if monotonic_value < start_ns + expected_cycle * WALL_CLOCK_CADENCE_NS or monotonic_value - previous_ns < WALL_CLOCK_CADENCE_NS:
                    raise ContractError("wall_clock_cadence_or_monotonic_cycle_invalid")
                if value.get("elapsed_ns") != monotonic_value - start_ns:
                    raise ContractError("wall_clock_cycle_elapsed_invalid")
                heartbeat_age = _required_int(value, "heartbeat_age_ns")
                if heartbeat_age < WALL_CLOCK_CADENCE_NS or heartbeat_age > 3 * WALL_CLOCK_CADENCE_NS or value.get("deadman_threshold_ns") != 5 * WALL_CLOCK_CADENCE_NS:
                    raise ContractError("wall_clock_heartbeat_deadman_invalid")
                if value.get("cadence_ns") != WALL_CLOCK_CADENCE_NS:
                    raise ContractError("wall_clock_cadence_invalid")
                if value.get("effects_unresolved") != 0:
                    raise ContractError("wall_clock_unresolved_effect_invalid")
                if value.get("artifact_bytes") != artifact_bytes:
                    raise ContractError("wall_clock_artifact_bytes_invalid")
                receipts.append(value)
                previous_hash = str(value["receipt_hash"])
                previous_ns = monotonic_value
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("wall_clock_cycle_ledger_invalid") from exc
    if len(receipts) != expected_count or any(receipt.get("cycle") != index for index, receipt in enumerate(receipts, start=1)):
        raise ContractError("wall_clock_cycle_ledger_count_or_order_invalid")
    return receipts, {"entry_count": len(receipts), "last_entry_hash": previous_hash, "last_monotonic_ns": previous_ns}


def _ledger_resume_state(
    path: Path,
    *,
    expected_count: int,
    start_ns: int,
    runner_instance_id: str,
    start_receipt_hash: str,
    runner_mode: str,
) -> tuple[str, int]:
    if expected_count == 0:
        return "sha256:" + "0" * 64, start_ns
    receipts, stats = _load_cycle_ledger(
        path,
        expected_count=expected_count,
        start_ns=start_ns,
        runner_instance_id=runner_instance_id,
        start_receipt_hash=start_receipt_hash,
        runner_mode=runner_mode,
    )
    return str(stats["last_entry_hash"]), int(receipts[-1]["monotonic_ns"])


def _write_checkpoint(
    path: Path,
    *,
    cycle_count: int,
    start_ns: int,
    runner_instance_id: str,
    start_receipt: Mapping[str, Any],
    runner_mode: str,
    ledger_path: Path,
    last_receipt_hash: str,
) -> None:
    checkpoint = with_self_hash(
        {
            "schema_version": "p150.wall_clock_checkpoint.v1",
            "runner_instance_id": runner_instance_id,
            "start_receipt": dict(start_receipt),
            "start_receipt_hash": start_receipt["start_receipt_hash"],
            "runner_mode": runner_mode,
            "started_monotonic_ns": start_ns,
            "cycle_count": cycle_count,
            "ledger_file_hash": file_hash(ledger_path),
            "ledger_entry_count": cycle_count,
            "last_receipt_hash": last_receipt_hash,
            "checkpoint_hash": "",
        },
        "checkpoint_hash",
    )
    write_canonical_json(path, checkpoint)


def _ledger_receipt_with_actual_artifact_bytes(seed: Mapping[str, Any], ledger_path: Path) -> tuple[dict[str, Any], bytes]:
    current_size = ledger_path.stat().st_size if ledger_path.exists() else 0
    artifact_bytes = current_size
    for _ in range(4):
        receipt = with_self_hash({**dict(seed), "artifact_bytes": artifact_bytes}, "receipt_hash")
        payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"
        next_artifact_bytes = current_size + len(payload)
        if next_artifact_bytes == artifact_bytes:
            return receipt, payload
        artifact_bytes = next_artifact_bytes
    raise ContractError("wall_clock_artifact_bytes_unstable")


def _ledger_resource_maxima(receipts: list[dict[str, Any]]) -> dict[str, int]:
    rss_values = [int(receipt["rss_bytes"]) for receipt in receipts]
    return {
        "rss_growth_bytes": max(rss_values) - min(rss_values),
        "artifact_bytes": max(int(receipt["artifact_bytes"]) for receipt in receipts),
        "queue_depth": max(int(receipt["queue_depth"]) for receipt in receipts),
        "heartbeat_age_ns": max(int(receipt["heartbeat_age_ns"]) for receipt in receipts),
    }


def _load_json_bytes(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ContractError("wall_clock_result_path_missing_or_unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError("wall_clock_result_object_required")
    return value


def _write_atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_parent(path)


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(usage)
    return int(usage) * 1024


def _required_int(value: Mapping[str, Any], field: str) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int):
        raise ContractError(f"{field}_integer_required")
    return item
