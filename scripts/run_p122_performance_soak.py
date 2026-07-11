#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import importlib
import json
import multiprocessing as mp
import os
import platform
import resource
import shutil
import sys
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p121_execution import prove_p121_restart_recovery  # noqa: E402
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS, zero_authority_counters  # noqa: E402
from app.services.redaction import redact_value  # noqa: E402

PERFORMANCE_SOAK_SCHEMA_VERSION = "p122.performance_soak.v2"
PROMOTED_REPORT_RELATIVE = Path("evals/p122/performance-soak.json")
PROMOTED_ARTIFACTS_RELATIVE = Path("evals/p122/performance-artifacts")
PERFORMANCE_RECORD_BUNDLE = "observed-records.jsonl"
PERFORMANCE_RECORD_CLASSES = (
    "incident_records",
    "audit_records",
    "timeline_records",
    "replay_records",
    "authority_records",
)
INSTALL_MANIFEST_SCHEMA = "p122.canonical_wheel_install.v1"
CRASH_EXIT_CODE = 86
RELEASE_STAGE_CRASH_POINTS = (
    "install",
    "demo_startup",
    "incident_ingest",
    "evidence_request",
    "decision",
    "approval",
    "validation",
    "rollback",
    "replay_write",
    "eval_write",
    "release_evidence_write",
    "report_write",
)
RELEASE_STAGE_OPERATIONS = {
    "install": "package_install",
    "demo_startup": "demo_bootstrap",
    "incident_ingest": "incident_record_ingest",
    "evidence_request": "evidence_request_dispatch",
    "decision": "bounded_decision_commit",
    "approval": "approval_receipt_commit",
    "validation": "validation_result_commit",
    "rollback": "rollback_result_commit",
    "replay_write": "replay_artifact_commit",
    "eval_write": "frozen_eval_commit",
    "release_evidence_write": "release_evidence_commit",
    "report_write": "performance_report_commit",
}
RELEASE_STAGE_ADAPTER_NAMES = {
    "install": "wheel_install_transaction_v1",
    "demo_startup": "local_cli_demo_start_v1",
    "incident_ingest": "p115_incident_case_ingest_v1",
    "evidence_request": "p121_evidence_receipt_v1",
    "decision": "p121_prevention_decision_v1",
    "approval": "p121_local_approval_v1",
    "validation": "p121_validation_outcome_v1",
    "rollback": "p121_rollback_outcome_v1",
    "replay_write": "p121_restart_recovery_bundle_v1",
    "eval_write": "p121_frozen_evaluation_v1",
    "release_evidence_write": "p122_release_evidence_snapshot_v1",
    "report_write": "p122_docs_report_v1",
}
RELEASE_STAGE_OUTPUT_SCHEMAS = {
    "install": "p122.wheel_install_transaction.v1",
    "demo_startup": "opscat.local_demo.v1",
    "incident_ingest": "p115.incident_case.v1",
    "evidence_request": "p121.evidence_receipt.v1",
    "decision": "p121.prevention_decision.v1",
    "approval": "p121.approval.v1",
    "validation": "p121.validation_outcome.v1",
    "rollback": "p121.validation_outcome.v1",
    "replay_write": "p121.restart_recovery_proof.v1",
    "eval_write": "p121.frozen_prevention_evaluation.v1",
    "release_evidence_write": "p122.release_evidence.v1",
    "report_write": "p122.docs_verification.v1",
}
RELEASE_STAGE_PHASES = {
    stage: {"pending": f"{operation}_pending", "recovered": f"{operation}_recovered"}
    for stage, operation in RELEASE_STAGE_OPERATIONS.items()
}


@dataclass(frozen=True)
class ReleaseStageAdapter:
    name: str
    artifact_name: str
    output_schema: str
    prepare: Callable[[Path], Path]
    validate: Callable[[Path], dict[str, object]]


def run_soak(*, iterations: int, workdir: Path) -> dict[str, object]:
    if iterations < 10:
        raise ValueError("iterations_must_be_at_least_10")
    workdir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    cpu_start = time.process_time()
    install_seconds, install_method = _measure_local_install(workdir / "install-probe")
    cold_start_seconds, cli_module = _measure_cold_start()
    hashes: list[str] = []
    demo_durations: list[float] = []
    expected = {key: 0 for key in ("incident_records", "audit_records", "timeline_records", "replay_records", "authority_records")}
    for index in range(iterations):
        demo_start = time.perf_counter()
        artifact = cli_module.run_local_demo(workdir / f"replay-{index:04d}.json")
        demo_durations.append(time.perf_counter() - demo_start)
        hashes.append(str(artifact["replay_hash"]))
        _persist_independent_records(workdir=workdir, index=index, artifact=artifact)
        events = artifact.get("events")
        event_count = len(events) if isinstance(events, list) else 0
        expected["incident_records"] += 1
        expected["audit_records"] += event_count
        expected["timeline_records"] += event_count
        expected["replay_records"] += 1
        expected["authority_records"] += 1
    observed = _observed_records(workdir=workdir, expected=expected)
    release_crash_replay = _execute_release_stage_crash_matrix(workdir / "release-stage-crash-replay")
    recovery_proof = _execute_p121_crash_replay(workdir / "p121-crash-replay.wal")
    p121_receipts = _mapping(recovery_proof.get("crash_replay_receipts"))
    replayed_count = sum(1 for receipt in p121_receipts.values() if isinstance(receipt, Mapping) and receipt.get("replayed") is True)
    rollback_begin = p121_receipts.get("rollback_begin", {})
    wal_recovered = _mapping(recovery_proof.get("wal_recovered"))
    authority_rejection = _observe_authority_rejection(cli_module, workdir / "authority-rejection.json")
    elapsed = time.perf_counter() - start
    cpu_seconds = time.process_time() - cpu_start
    storage = _storage_envelope(workdir=workdir, iterations=iterations)
    ready = not any(observed["lost"].values()) and release_crash_replay["verified"] is True and authority_rejection["observed"] is True
    correlated_logs = [
        {
            "timestamp_monotonic_seconds": point["recovered_at_seconds"],
            "level": "INFO",
            "event": "release_stage_crash_recovered",
            "stage": point["stage"],
            "correlation_id": point["correlation_id"],
        }
        for point in release_crash_replay["points"]
    ]
    correlated_logs.append(
        {
            "timestamp_monotonic_seconds": elapsed,
            "level": "WARNING",
            "event": "authority_rejected",
            "reason": authority_rejection["reason"],
            "correlation_id": authority_rejection["correlation_id"],
        }
    )
    redacted_diagnostic = redact_value(
        {
            "api_key": "p122-secret-fixture",
            "message": "Authorization: Bearer p122-secret-fixture",
            "scope": "local-fixture",
        }
    )
    report: dict[str, object] = {
        "schema_version": PERFORMANCE_SOAK_SCHEMA_VERSION,
        "iterations": iterations,
        "elapsed_seconds": elapsed,
        "duration_seconds": elapsed,
        "cpu_seconds": cpu_seconds,
        "cpu_utilization_ratio": cpu_seconds / max(elapsed, 1e-9),
        "events_per_second": observed["expected"]["audit_records"] / max(elapsed, 1e-9),
        "replays_per_second": iterations / max(elapsed, 1e-9),
        "expected_records": observed["expected"],
        "observed_records": observed["observed"],
        "lost_incident_records": observed["lost"]["incident_records"],
        "lost_audit_records": observed["lost"]["audit_records"],
        "lost_timeline_records": observed["lost"]["timeline_records"],
        "lost_replay_records": observed["lost"]["replay_records"],
        "lost_authority_records": observed["lost"]["authority_records"],
        "unique_replay_files": observed["observed"]["replay_records"],
        "deterministic_content_hash_count": len(set(hashes)),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "context": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count()},
        "timings_seconds": {
            "install": install_seconds,
            "install_method": install_method,
            "cold_start": cold_start_seconds,
            "demo_total": sum(demo_durations),
            "demo_min": min(demo_durations),
            "demo_max": max(demo_durations),
            "demo_mean": sum(demo_durations) / len(demo_durations),
            "demo_samples": len(demo_durations),
        },
        "storage_envelope": storage,
        "release_stage_crash_inventory": list(RELEASE_STAGE_CRASH_POINTS),
        "release_stage_crash_replay": release_crash_replay,
        "upstream_executed_crash_replay": {
            "source": "app.services.p121_execution.prove_p121_restart_recovery",
            "proof_hash": recovery_proof["proof_hash"],
            "point_count": recovery_proof["point_count"],
            "replayed_count": replayed_count,
            "pending_rollback_replayed": rollback_begin.get("rollback_pending_replayed") is True if isinstance(rollback_begin, dict) else False,
            "pending_rollback_count_after_replay": wal_recovered.get("pending_rollback_count") if isinstance(wal_recovered, dict) else None,
        },
        "observability": {
            "health": {"status": "healthy" if ready else "degraded", "local_fixture": True},
            "readiness": {
                "ready": ready,
                "checks": {
                    "record_loss_zero": not any(observed["lost"].values()),
                    "release_crashes_recovered": release_crash_replay["verified"],
                    "authority_rejection_observed": authority_rejection["observed"],
                },
            },
            "metrics": {
                "iterations_total": iterations,
                "records_observed_total": sum(observed["observed"].values()),
                "records_lost_total": sum(observed["lost"].values()),
                "release_stage_crashes_injected_total": release_crash_replay["injected_count"],
                "release_stage_crashes_recovered_total": release_crash_replay["recovered_count"],
                "authority_rejections_total": int(authority_rejection["observed"] is True),
            },
            "correlated_logs": correlated_logs,
            "authority_rejection": authority_rejection,
            "diagnostics": {
                "redaction_verified": "p122-secret-fixture" not in str(redacted_diagnostic),
                "redacted_sample": redacted_diagnostic,
                "record_artifact_root": str(workdir / "records"),
                "crash_replay_artifact_root": str(workdir / "release-stage-crash-replay"),
                "replay_inspectable": observed["observed"]["replay_records"] == iterations,
            },
        },
        "authority_counters": zero_authority_counters(),
        "scope_limit": "local fixture performance only; not production capacity evidence",
    }
    report["semantic_binding"] = performance_semantic_projection(report)["projection_hash"]
    report["report_hash"] = stable_hash(report)
    return report


def _observed_records(*, workdir: Path, expected: Mapping[str, int]) -> dict[str, dict[str, int]]:
    observed = {key: 0 for key in expected}
    for replay in workdir.glob("replay-*.json"):
        try:
            artifact = json.loads(replay.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(artifact, dict):
            continue
        observed["replay_records"] += 1
    records = workdir / "records"
    observed["incident_records"] = sum(1 for path in records.glob("incident-*.json") if _json_mapping(path).get("schema_version") == "opscat.local_demo.v1")
    observed["audit_records"] = sum(len(value) for path in records.glob("audit-*.json") for value in [_json_list(path)])
    observed["timeline_records"] = sum(len(value) for path in records.glob("timeline-*.json") for value in [_json_list(path)])
    observed["authority_records"] = sum(1 for path in records.glob("authority-*.json") if _exact_zero_p121(_json_mapping(path)))
    lost = {key: max(expected[key] - observed[key], 0) for key in expected}
    return {"expected": dict(expected), "observed": observed, "lost": lost}


def _persist_independent_records(*, workdir: Path, index: int, artifact: Mapping[str, object]) -> None:
    records = workdir / "records"
    events = artifact.get("events")
    _atomic_json_write(records / f"incident-{index:04d}.json", {"schema_version": artifact.get("schema_version"), "replay_hash": artifact.get("replay_hash")})
    _atomic_json_write(records / f"audit-{index:04d}.json", list(events) if isinstance(events, list) else [])
    timeline = [{"ordinal": ordinal, **dict(event)} for ordinal, event in enumerate(events) if isinstance(event, Mapping)] if isinstance(events, list) else []
    _atomic_json_write(records / f"timeline-{index:04d}.json", timeline)
    counters = artifact.get("authority_counters")
    _atomic_json_write(records / f"authority-{index:04d}.json", dict(counters) if isinstance(counters, Mapping) else {})


def _execute_release_stage_crash_matrix(root: Path) -> dict[str, Any]:
    points: list[dict[str, object]] = []
    matrix_start = time.perf_counter()
    for ordinal, stage in enumerate(RELEASE_STAGE_CRASH_POINTS):
        stage_root = root / f"{ordinal:02d}-{stage}"
        prepared = prepare_release_stage_crash(stage_root, stage=stage, ordinal=ordinal)
        recovered = recover_release_stage_crash(prepared)
        receipt = _mapping(recovered["receipt"])
        verified = recovered["verified"] is True
        points.append(
            {
                "stage": stage,
                "operation": RELEASE_STAGE_OPERATIONS[stage],
                "operation_adapter": RELEASE_STAGE_ADAPTER_NAMES[stage],
                "output_schema": RELEASE_STAGE_OUTPUT_SCHEMAS[stage],
                "correlation_id": prepared["correlation_id"],
                "crash_injected": prepared["crash_exit_code"] == CRASH_EXIT_CODE,
                "crash_exit_code": prepared["crash_exit_code"],
                "recovery_exit_code": recovered["recovery_exit_code"],
                "crash_worker_pid": prepared["crash_worker_pid"],
                "recovery_worker_pid": recovered["recovery_worker_pid"],
                "recovered": verified,
                "restart_verified": verified,
                "restart_count": receipt.get("restart_count"),
                "pending_record_hash": receipt.get("pending_record_hash"),
                "restart_receipt_hash": receipt.get("record_hash"),
                "adapter_invoked": receipt.get("adapter_invoked"),
                "precommit_hash": receipt.get("precommit_hash"),
                "output_hash": receipt.get("output_hash"),
                "post_restart_validation": receipt.get("post_restart_validation"),
                "pending_ref": str(stage_root / "pending.json"),
                "output_ref": str(stage_root / "committed" / _release_stage_adapter(stage).artifact_name),
                "restart_receipt_ref": str(stage_root / "restart-receipt.json"),
                "recovered_at_seconds": time.perf_counter() - matrix_start,
            }
        )
    injected_count = sum(1 for point in points if point["crash_injected"] is True)
    recovered_count = sum(1 for point in points if point["recovered"] is True)
    return {
        "schema_version": "p122.release_stage_crash_replay.v1",
        "protocol": "multiprocessing-spawn-exit-restart",
        "point_count": len(RELEASE_STAGE_CRASH_POINTS),
        "injected_count": injected_count,
        "recovered_count": recovered_count,
        "observed_restart_receipt_count": sum(1 for _ in root.glob("*/restart-receipt.json")),
        "verified": injected_count == len(RELEASE_STAGE_CRASH_POINTS) == recovered_count,
        "points": points,
    }


def prepare_release_stage_crash(stage_root: Path, *, stage: str, ordinal: int) -> dict[str, object]:
    _release_stage_adapter(stage)
    if stage_root.exists():
        shutil.rmtree(stage_root)
    correlation_id = f"p122-crash-{ordinal:02d}-{stage}"
    context = mp.get_context("spawn")
    crash_worker = context.Process(
        target=_release_stage_crash_worker,
        args=(str(stage_root), stage, ordinal, correlation_id),
        name=f"p122-crash-{stage}",
    )
    crash_worker.start()
    crash_worker_pid = crash_worker.pid
    _join_worker(crash_worker, stage=stage, phase="crash")
    if crash_worker.exitcode != CRASH_EXIT_CODE or not isinstance(crash_worker_pid, int):
        raise RuntimeError(f"release_stage_crash_worker_failed:{stage}:{crash_worker.exitcode}")
    return {
        "stage_root": str(stage_root),
        "stage": stage,
        "ordinal": ordinal,
        "correlation_id": correlation_id,
        "crash_worker_pid": crash_worker_pid,
        "crash_exit_code": crash_worker.exitcode,
    }


def recover_release_stage_crash(prepared: Mapping[str, object]) -> dict[str, object]:
    stage_root = Path(str(prepared["stage_root"]))
    stage = str(prepared["stage"])
    ordinal = _required_int(prepared["ordinal"], "ordinal")
    correlation_id = str(prepared["correlation_id"])
    crash_worker_pid = _required_int(prepared["crash_worker_pid"], "crash_worker_pid")
    _release_stage_adapter(stage)
    context = mp.get_context("spawn")
    recovery_worker = context.Process(
        target=_release_stage_recovery_worker,
        args=(str(stage_root), stage, ordinal, correlation_id),
        name=f"p122-recovery-{stage}",
    )
    recovery_worker.start()
    recovery_worker_pid = recovery_worker.pid
    _join_worker(recovery_worker, stage=stage, phase="recovery")
    if recovery_worker.exitcode != 0 or not isinstance(recovery_worker_pid, int):
        raise RuntimeError(f"release_stage_recovery_worker_failed:{stage}:{recovery_worker.exitcode}")
    receipt = _json_mapping(stage_root / "restart-receipt.json")
    verified = crash_worker_pid != recovery_worker_pid and _restart_receipt_valid(
        receipt,
        stage=stage,
        ordinal=ordinal,
        correlation_id=correlation_id,
        crash_worker_pid=crash_worker_pid,
        recovery_worker_pid=recovery_worker_pid,
        stage_root=stage_root,
    )
    return {
        "receipt": dict(receipt),
        "recovery_worker_pid": recovery_worker_pid,
        "recovery_exit_code": recovery_worker.exitcode,
        "verified": verified,
    }


def _release_stage_crash_worker(stage_root_value: str, stage: str, ordinal: int, correlation_id: str) -> None:
    stage_root = Path(stage_root_value)
    adapter = _release_stage_adapter(stage)
    operation = RELEASE_STAGE_OPERATIONS[stage]
    precommit_root = stage_root / "precommit"
    precommit_root.mkdir(parents=True, exist_ok=True)
    precommit_path = adapter.prepare(precommit_root)
    expected_precommit = precommit_root / adapter.artifact_name
    if precommit_path != expected_precommit or not precommit_path.exists():
        raise RuntimeError(f"release_stage_adapter_missing_precommit:{stage}")
    precommit_validation = adapter.validate(precommit_path)
    if precommit_validation.get("schema_version") != adapter.output_schema:
        raise RuntimeError(f"release_stage_adapter_schema_mismatch:{stage}")
    _fsync_artifact(precommit_path)
    pending: dict[str, object] = {
        "schema_version": "p122.release_stage_pending.v1",
        "stage": stage,
        "operation": operation,
        "operation_adapter": adapter.name,
        "output_schema": adapter.output_schema,
        "durable_phase": RELEASE_STAGE_PHASES[stage]["pending"],
        "correlation_id": correlation_id,
        "ordinal": ordinal,
        "status": "pending",
        "adapter_invoked": True,
        "precommit_ref": f"precommit/{adapter.artifact_name}",
        "output_ref": f"committed/{adapter.artifact_name}",
        "precommit_kind": "directory" if precommit_path.is_dir() else "file",
        "precommit_hash": _artifact_hash(precommit_path),
        "precommit_validation_hash": stable_hash(precommit_validation),
        "worker_pid": os.getpid(),
        "parent_pid": os.getppid(),
    }
    pending["record_hash"] = stable_hash(pending)
    _durable_json_write(stage_root / "pending.json", pending)
    os._exit(CRASH_EXIT_CODE)


def _release_stage_recovery_worker(stage_root_value: str, stage: str, ordinal: int, correlation_id: str) -> None:
    stage_root = Path(stage_root_value)
    adapter = _release_stage_adapter(stage)
    pending = _json_mapping(stage_root / "pending.json")
    if not _pending_record_valid(pending, stage=stage, ordinal=ordinal, correlation_id=correlation_id):
        raise RuntimeError(f"invalid_pending_release_stage_record:{stage}")
    precommit_path = stage_root / "precommit" / adapter.artifact_name
    output_path = stage_root / "committed" / adapter.artifact_name
    if _artifact_hash(precommit_path) != pending.get("precommit_hash"):
        raise RuntimeError(f"release_stage_precommit_hash_mismatch:{stage}")
    precommit_validation = adapter.validate(precommit_path)
    if stable_hash(precommit_validation) != pending.get("precommit_validation_hash"):
        raise RuntimeError(f"release_stage_precommit_validation_mismatch:{stage}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(precommit_path, output_path)
    _fsync_directory(output_path.parent)
    output_validation = adapter.validate(output_path)
    output_hash = _artifact_hash(output_path)
    post_restart_validation = (
        output_hash == pending.get("precommit_hash")
        and output_validation == precommit_validation
        and output_validation.get("schema_version") == adapter.output_schema
    )
    if not post_restart_validation:
        raise RuntimeError(f"release_stage_post_restart_validation_failed:{stage}")
    receipt: dict[str, object] = {
        "schema_version": "p122.release_stage_restart_receipt.v1",
        "stage": stage,
        "operation": RELEASE_STAGE_OPERATIONS[stage],
        "operation_adapter": adapter.name,
        "output_schema": adapter.output_schema,
        "durable_phase": RELEASE_STAGE_PHASES[stage]["recovered"],
        "correlation_id": correlation_id,
        "ordinal": ordinal,
        "status": "recovered_after_restart",
        "adapter_invoked": pending["adapter_invoked"],
        "precommit_hash": pending["precommit_hash"],
        "precommit_validation_hash": pending["precommit_validation_hash"],
        "output_hash": output_hash,
        "output_validation": output_validation,
        "post_restart_validation": post_restart_validation,
        "pending_record_hash": pending["record_hash"],
        "pending_worker_pid": pending["worker_pid"],
        "recovery_worker_pid": os.getpid(),
        "restart_count": 1,
    }
    receipt["record_hash"] = stable_hash(receipt)
    _durable_json_write(stage_root / "restart-receipt.json", receipt)


def _join_worker(worker: Any, *, stage: str, phase: str) -> None:
    worker.join(timeout=15)
    if worker.is_alive():
        worker.kill()
        worker.join(timeout=5)
        raise RuntimeError(f"release_stage_{phase}_worker_timeout:{stage}")


def _pending_record_valid(record: Mapping[str, object], *, stage: str, ordinal: int, correlation_id: str) -> bool:
    adapter = _release_stage_adapter(stage)
    return (
        record.get("schema_version") == "p122.release_stage_pending.v1"
        and record.get("stage") == stage
        and record.get("operation") == RELEASE_STAGE_OPERATIONS[stage]
        and record.get("operation_adapter") == adapter.name
        and record.get("output_schema") == adapter.output_schema
        and record.get("durable_phase") == RELEASE_STAGE_PHASES[stage]["pending"]
        and record.get("correlation_id") == correlation_id
        and record.get("ordinal") == ordinal
        and record.get("status") == "pending"
        and record.get("adapter_invoked") is True
        and record.get("precommit_ref") == f"precommit/{adapter.artifact_name}"
        and record.get("output_ref") == f"committed/{adapter.artifact_name}"
        and record.get("precommit_kind") in {"file", "directory"}
        and isinstance(record.get("precommit_hash"), str)
        and isinstance(record.get("precommit_validation_hash"), str)
        and isinstance(record.get("worker_pid"), int)
        and _record_hash_valid(record)
    )


def _restart_receipt_valid(
    receipt: Mapping[str, object],
    *,
    stage: str,
    ordinal: int,
    correlation_id: str,
    crash_worker_pid: int,
    recovery_worker_pid: int,
    stage_root: Path,
) -> bool:
    adapter = _release_stage_adapter(stage)
    output_path = stage_root / "committed" / adapter.artifact_name
    output_validation = receipt.get("output_validation")
    return (
        receipt.get("schema_version") == "p122.release_stage_restart_receipt.v1"
        and receipt.get("stage") == stage
        and receipt.get("operation") == RELEASE_STAGE_OPERATIONS[stage]
        and receipt.get("operation_adapter") == adapter.name
        and receipt.get("output_schema") == adapter.output_schema
        and receipt.get("durable_phase") == RELEASE_STAGE_PHASES[stage]["recovered"]
        and receipt.get("correlation_id") == correlation_id
        and receipt.get("ordinal") == ordinal
        and receipt.get("status") == "recovered_after_restart"
        and receipt.get("pending_worker_pid") == crash_worker_pid
        and receipt.get("recovery_worker_pid") == recovery_worker_pid
        and receipt.get("restart_count") == 1
        and receipt.get("adapter_invoked") is True
        and isinstance(receipt.get("precommit_hash"), str)
        and receipt.get("output_hash") == receipt.get("precommit_hash") == _artifact_hash(output_path)
        and receipt.get("post_restart_validation") is True
        and isinstance(output_validation, Mapping)
        and output_validation.get("schema_version") == adapter.output_schema
        and dict(output_validation) == adapter.validate(output_path)
        and _record_hash_valid(receipt)
    )


def _record_hash_valid(record: Mapping[str, object]) -> bool:
    expected = record.get("record_hash")
    payload = {key: value for key, value in record.items() if key != "record_hash"}
    return isinstance(expected, str) and expected == stable_hash(payload)


def _required_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"release_stage_invalid_integer:{field}")
    return value


def _artifact_hash(path: Path) -> str:
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        return ""
    entries: list[dict[str, object]] = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise RuntimeError(f"release_stage_symlink_forbidden:{item}")
        if item.is_file():
            entries.append(
                {
                    "path": item.relative_to(path).as_posix(),
                    "size": item.stat().st_size,
                    "hash": "sha256:" + hashlib.sha256(item.read_bytes()).hexdigest(),
                }
            )
    return stable_hash({"kind": "directory", "entries": entries})


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _fsync_artifact(path: Path) -> None:
    files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
    for item in files:
        with item.open("rb") as handle:
            os.fsync(handle.fileno())
    directories = [path] if path.is_dir() else []
    if path.is_dir():
        directories.extend(item for item in path.rglob("*") if item.is_dir())
    for directory in reversed(directories):
        _fsync_directory(directory)


def _prepare_wheel_install(root: Path) -> Path:
    wheel = _current_wheel_path()
    target = root / "installed-wheel"
    site_packages = target / "site-packages"
    site_packages.mkdir(parents=True)
    with zipfile.ZipFile(wheel) as archive:
        target_root = site_packages.resolve()
        for member in archive.infolist():
            destination = (site_packages / member.filename).resolve()
            try:
                destination.relative_to(target_root)
            except ValueError as exc:
                raise RuntimeError("release_stage_wheel_path_escape") from exc
        archive.extractall(site_packages)
    entry_points = sorted(site_packages.glob("*.dist-info/entry_points.txt"))
    if len(entry_points) != 1 or "opscat = app.cli:main" not in entry_points[0].read_text(encoding="utf-8"):
        raise RuntimeError("release_stage_wheel_entrypoint_missing")
    record_files = sorted(site_packages.glob("*.dist-info/RECORD"))
    if len(record_files) != 1:
        raise RuntimeError("release_stage_wheel_record_missing")
    verified_record_count = _verify_wheel_record(site_packages, record_files[0])
    launcher = target / "bin/opscat"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/usr/bin/env python3\nfrom app.cli import main\nraise SystemExit(main())\n", encoding="utf-8")
    launcher.chmod(0o755)
    record_files[0].unlink()
    install_manifest: dict[str, object] = {
        "schema_version": INSTALL_MANIFEST_SCHEMA,
        "wheel_checksum": _file_sha256(wheel),
        "operation": "package_install",
        "installed_package": "opscat",
        "console_entrypoint": "opscat=app.cli:main",
        "record_entries_verified": verified_record_count,
        "entries": _canonical_file_entries(target, excluded={"install-manifest.json"}),
    }
    install_manifest["manifest_hash"] = stable_hash(install_manifest)
    _durable_json_write(target / "install-manifest.json", install_manifest)
    _fsync_directory(target)
    return target


def _validate_wheel_install(path: Path) -> dict[str, object]:
    site_packages = path / "site-packages"
    metadata_files = sorted(site_packages.glob("*.dist-info/METADATA"))
    record_files = sorted(site_packages.glob("*.dist-info/RECORD"))
    entry_points = sorted(site_packages.glob("*.dist-info/entry_points.txt"))
    installed_files = [item for item in path.rglob("*") if item.is_file()]
    launcher = path / "bin/opscat"
    manifest = _json_mapping(path / "install-manifest.json")
    manifest_payload = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if (
        not (site_packages / "app").is_dir()
        or len(metadata_files) != 1
        or record_files
        or len(entry_points) != 1
        or not launcher.is_file()
        or manifest.get("schema_version") != INSTALL_MANIFEST_SCHEMA
        or manifest.get("manifest_hash") != stable_hash(manifest_payload)
        or manifest.get("wheel_checksum") != _file_sha256(_current_wheel_path())
        or manifest.get("operation") != "package_install"
        or manifest.get("installed_package") != "opscat"
        or manifest.get("console_entrypoint") != "opscat=app.cli:main"
        or manifest.get("entries") != _canonical_file_entries(path, excluded={"install-manifest.json"})
    ):
        raise RuntimeError("release_stage_wheel_install_invalid")
    verified_record_count = _required_int(manifest.get("record_entries_verified"), "record_entries_verified")
    if verified_record_count <= 0:
        raise RuntimeError("release_stage_wheel_record_empty")
    parser = configparser.ConfigParser()
    parser.read(entry_points[0], encoding="utf-8")
    if parser.get("console_scripts", "opscat", fallback="").strip() != "app.cli:main":
        raise RuntimeError("release_stage_wheel_entrypoint_invalid")
    if "from app.cli import main" not in launcher.read_text(encoding="utf-8"):
        raise RuntimeError("release_stage_wheel_launcher_invalid")
    return {
        "schema_version": RELEASE_STAGE_OUTPUT_SCHEMAS["install"],
        "installed_package": "opscat",
        "installed_file_count": len(installed_files),
        "record_entries_verified": verified_record_count,
        "console_entrypoint": "opscat=app.cli:main",
        "metadata_hash": _artifact_hash(metadata_files[0]),
        "app_package_present": True,
    }


def _current_wheel_path() -> Path:
    wheels = sorted((ROOT / "dist").glob("opscat-*.whl"))
    if not wheels:
        raise RuntimeError("release_stage_wheel_missing")
    return wheels[-1]


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_file_entries(root: Path, *, excluded: set[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            raise RuntimeError(f"release_stage_symlink_forbidden:{item}")
        if item.is_file() and item.relative_to(root).as_posix() not in excluded:
            entries.append(
                {
                    "path": item.relative_to(root).as_posix(),
                    "size": item.stat().st_size,
                    "hash": _file_sha256(item),
                }
            )
    return entries


def _verify_wheel_record(site_packages: Path, record_path: Path) -> int:
    verified = 0
    with record_path.open(newline="", encoding="utf-8") as handle:
        for relative, digest, size in csv.reader(handle):
            artifact = site_packages / relative
            if not artifact.is_file():
                raise RuntimeError("release_stage_wheel_record_path_missing")
            if not digest:
                if artifact != record_path:
                    raise RuntimeError("release_stage_wheel_record_digest_missing")
                continue
            algorithm, encoded = digest.split("=", 1)
            if algorithm != "sha256":
                raise RuntimeError("release_stage_wheel_record_algorithm_invalid")
            actual = base64.urlsafe_b64encode(hashlib.sha256(artifact.read_bytes()).digest()).rstrip(b"=").decode("ascii")
            if actual != encoded or _required_int(int(size), "wheel_record_size") != artifact.stat().st_size:
                raise RuntimeError("release_stage_wheel_record_mismatch")
            verified += 1
    if verified == 0:
        raise RuntimeError("release_stage_wheel_record_empty")
    return verified


def _prepare_local_demo(root: Path) -> Path:
    from app.cli import run_local_demo

    path = root / "local-demo.json"
    run_local_demo(path)
    return path


def _validate_local_demo(path: Path) -> dict[str, object]:
    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["demo_startup"], hash_field="replay_hash")
    events = payload.get("events")
    if payload.get("network_calls") != 0 or payload.get("production_mutations") != 0 or not _exact_zero_p121(_mapping(payload.get("authority_counters"))):
        raise RuntimeError("release_stage_local_demo_authority_invalid")
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["replay_hash"]),
        "event_count": len(events) if isinstance(events, list) else 0,
        "exact_nonlocal_authority_zero": True,
    }


def _prepare_incident(root: Path) -> Path:
    from app.services.p115_ontology import build_incident_case

    payload = build_incident_case(
        {
            "case_id": "p122-crash-incident",
            "source_family": "controlled_local_fixture",
            "scenario_family": "release_stage_crash_recovery",
            "topology_handle": "fixture:topology:p122",
            "time_window": {"start": "2026-07-12T00:00:00Z", "end": "2026-07-12T00:05:00Z"},
            "visible_evidence_handle": "fixture:evidence:p122",
            "diagnosis_handle": "fixture:diagnosis:p122",
            "eligible_action_pack_ids": ["p122-local-noop"],
            "required_evidence_classes": ["metric", "log"],
            "partition_group": "p122-release-stage",
            "release_role": "development",
        }
    ).to_dict()
    path = root / "incident.json"
    _durable_json_write(path, payload)
    return path


def _validate_incident(path: Path) -> dict[str, object]:
    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["incident_ingest"], hash_field="artifact_hash")
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["artifact_hash"]),
        "case_id": str(payload.get("case_id", "")),
        "release_role": str(payload.get("release_role", "")),
    }


def _fixture_evidence() -> dict[str, object]:
    from app.services.p121_forecasting import build_evidence_receipt

    return build_evidence_receipt(
        {
            "evidence_id": "p122-evidence-1",
            "source_ref": "fixture://p122/metrics",
            "source_kind": "local_fixture",
            "taxonomy_version": "p122-local-v1",
            "artifact_hash": stable_hash({"fixture": "p122-metrics"}),
            "observed_at": "2026-07-12T00:00:00Z",
            "cutoff_at": "2026-07-12T00:01:00Z",
            "collected_at": "2026-07-12T00:00:30Z",
            "staleness_seconds": 30,
            "max_staleness_seconds": 60,
            "contradiction_status": "none",
            "post_intervention": False,
            "denominator_visible": True,
            "authority_counters": zero_authority_counters(),
        }
    )


def _prepare_evidence(root: Path) -> Path:
    path = root / "evidence.json"
    _durable_json_write(path, _fixture_evidence())
    return path


def _validate_evidence(path: Path) -> dict[str, object]:
    from app.services.p121_forecasting import validate_evidence_receipt

    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["evidence_request"], hash_field="evidence_hash")
    validate_evidence_receipt(payload)
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["evidence_hash"]),
        "evidence_id": str(payload.get("evidence_id", "")),
        "exact_nonlocal_authority_zero": _exact_zero_p121(_mapping(payload.get("authority_counters"))),
    }


def _prepare_decision(root: Path) -> Path:
    from app.services.p121_forecasting import build_prevention_decision

    evidence = _fixture_evidence()
    payload = build_prevention_decision(
        {
            "decision_id": "p122-decision-1",
            "forecast_id": "p122-forecast-1",
            "route": "prevent_l3_local_sandbox",
            "required_evidence_ids": ["p122-evidence-1"],
            "reason": "bounded_local_fixture",
            "authority_counters": zero_authority_counters(),
        },
        [evidence],
    )
    path = root / "decision.json"
    _durable_json_write(path, payload)
    return path


def _validate_decision(path: Path) -> dict[str, object]:
    from app.services.p121_forecasting import validate_prevention_decision

    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["decision"], hash_field="decision_hash")
    validate_prevention_decision(payload)
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["decision_hash"]),
        "route": str(payload.get("route", "")),
        "exact_nonlocal_authority_zero": _exact_zero_p121(_mapping(payload.get("authority_counters"))),
    }


def _p121_fixture_envelope(*, operation_id: str, idempotency_key: str) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    registry: dict[str, dict[str, object]] = {
        "fixture-p122": {"disposable": True, "target_class": "disposable_local_sandbox", "allowed_handlers": ["inject_latency"]}
    }
    envelope: dict[str, object] = {
        "operation_id": operation_id,
        "authority_level": "L3",
        "target_class": "disposable_local_sandbox",
        "fixture_id": "fixture-p122",
        "handler": "inject_latency",
        "registry_hash": stable_hash(registry),
        "idempotency_key": idempotency_key,
        "lease_owner": "p122-soak-worker",
        "lease_expires_at": 200,
        "approval_expires_at": 190,
        "authority_counters": zero_authority_counters(),
    }
    for name in ("forecast_hash", "evidence_hash", "counterfactual_hash", "guardrail_hash", "validation_plan_hash", "rollback_plan_hash"):
        envelope[name] = stable_hash({"receipt": name})
    return envelope, registry


def _prepare_approval(root: Path) -> Path:
    from app.services.p121_execution import approve_prevention_operation

    envelope, registry = _p121_fixture_envelope(operation_id="p122-approval", idempotency_key="p122-approval-idem")
    payload = approve_prevention_operation(envelope, registry=registry, now=100)
    if payload.get("approved") is not True:
        raise RuntimeError("release_stage_local_approval_rejected")
    path = root / "approval.json"
    _durable_json_write(path, payload)
    return path


def _validate_approval(path: Path) -> dict[str, object]:
    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["approval"], hash_field="approval_hash")
    if payload.get("approved") is not True or payload.get("reason") != "approved" or not _exact_zero_p121(_mapping(payload.get("authority_counters"))):
        raise RuntimeError("release_stage_local_approval_invalid")
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["approval_hash"]),
        "approved": True,
        "exact_nonlocal_authority_zero": True,
    }


def _validation_input(*, rollback: bool) -> dict[str, object]:
    return {
        "operation_id": "p122-rollback" if rollback else "p122-validation",
        "validation_plan_hash": stable_hash({"plan": "validation"}),
        "rollback_plan_hash": stable_hash({"plan": "rollback"}),
        "pre_measurement_hash": stable_hash({"measurement": "pre"}),
        "post_measurement_hash": stable_hash({"measurement": "post"}),
        "control_hash": stable_hash({"measurement": "control"}),
        "validation_passed": not rollback,
        "harm_detected": False,
        "collateral_regression": False,
        "ambiguous_attribution": False,
        "natural_recovery": False,
        "rollback_attempted": rollback,
        "rollback_passed": True if rollback else False,
        "causal_confidence": 0.9,
        "avoided_impact": 2,
        "useful_delay": 1,
        "harm_score": 0,
        "authority_counters": zero_authority_counters(),
    }


def _prepare_validation(root: Path) -> Path:
    from app.services.p121_validation import validate_prevention_outcome

    path = root / "validation.json"
    _durable_json_write(path, validate_prevention_outcome(_validation_input(rollback=False)))
    return path


def _prepare_rollback(root: Path) -> Path:
    from app.services.p121_validation import validate_prevention_outcome

    path = root / "rollback.json"
    _durable_json_write(path, validate_prevention_outcome(_validation_input(rollback=True)))
    return path


def _validate_validation_artifact(path: Path, *, rollback: bool) -> dict[str, object]:
    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["rollback" if rollback else "validation"], hash_field="report_hash")
    if bool(payload.get("rollback_attempted")) is not rollback or not _exact_zero_p121(_mapping(payload.get("authority_counters"))):
        raise RuntimeError("release_stage_validation_mode_invalid")
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["report_hash"]),
        "validation_passed": payload.get("validation_passed"),
        "rollback_attempted": payload.get("rollback_attempted"),
        "rollback_passed": payload.get("rollback_passed"),
        "exact_nonlocal_authority_zero": True,
    }


def _validate_validation(path: Path) -> dict[str, object]:
    return _validate_validation_artifact(path, rollback=False)


def _validate_rollback(path: Path) -> dict[str, object]:
    return _validate_validation_artifact(path, rollback=True)


def _prepare_replay(root: Path) -> Path:
    bundle = root / "replay-bundle"
    bundle.mkdir(parents=True)
    envelope, registry = _p121_fixture_envelope(operation_id="p122-stage-replay", idempotency_key="p122-stage-replay-idem")
    proof = prove_p121_restart_recovery(wal_path=bundle / "replay.wal", envelope=envelope, registry=registry, now=100)
    _durable_json_write(bundle / "proof.json", proof)
    return bundle


def _validate_replay(path: Path) -> dict[str, object]:
    proof = _validated_json_artifact(path / "proof.json", schema=RELEASE_STAGE_OUTPUT_SCHEMAS["replay_write"], hash_field="proof_hash")
    point_count = _required_int(proof.get("point_count"), "point_count")
    if point_count < 15 or not _exact_zero_p121(_mapping(proof.get("authority_counters"))) or not (path / "replay.wal").is_file():
        raise RuntimeError("release_stage_replay_bundle_invalid")
    return {
        "schema_version": str(proof["schema_version"]),
        "artifact_hash": str(proof["proof_hash"]),
        "point_count": point_count,
        "wal_hash": _artifact_hash(path / "replay.wal"),
        "exact_nonlocal_authority_zero": True,
    }


def _prepare_evaluation(root: Path) -> Path:
    from app.services.p121_evaluator import run_p121_frozen_evaluation

    path = root / "frozen-evaluation.json"
    _durable_json_write(path, run_p121_frozen_evaluation())
    return path


def _validate_evaluation(path: Path) -> dict[str, object]:
    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["eval_write"], hash_field="evaluation_hash")
    authority = _mapping(payload.get("authority"))
    if payload.get("first_score_consumed") is not True or not _exact_zero_p121(_mapping(authority.get("counters"))):
        raise RuntimeError("release_stage_frozen_evaluation_invalid")
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["evaluation_hash"]),
        "case_count": _required_int(payload.get("case_count"), "case_count"),
        "first_score_consumed": True,
        "exact_nonlocal_authority_zero": True,
    }


def _release_evidence_contract_fixture(operation_root: Path) -> dict[str, object]:
    from app.public_contracts import public_contract_manifest
    from app.services.p122_release_evidence import produce_p122_release_evidence, validate_p122_release_evidence

    fixture_root = operation_root / ".release-evidence-producer-inputs"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    fixture_root.mkdir(parents=True)
    (fixture_root / "uv.lock").write_text(
        'version = 1\nrevision = 1\nrequires-python = ">=3.12"\npackage = []\n',
        encoding="utf-8",
    )
    try:
        produced = produce_p122_release_evidence(
            reviewer_id="p122-fixture-reviewer",
            builder_id="p122-fixture-builder",
            root=fixture_root,
            performance_crash_receipts={},
        )
        validation = validate_p122_release_evidence(produced, root=fixture_root)
    finally:
        shutil.rmtree(fixture_root)
    checks = _mapping(validation.get("checks"))
    core_round_trip_checks = ("schema_current", "self_hash_current", "all_fields_current")
    if produced.get("schema_version") != RELEASE_STAGE_OUTPUT_SCHEMAS["release_evidence_write"] or not all(
        checks.get(name) is True for name in core_round_trip_checks
    ):
        raise RuntimeError("release_stage_release_evidence_contract_round_trip_failed")
    manifest = public_contract_manifest()
    contracts = manifest.get("contracts")
    release_contracts = [
        contract
        for contract in contracts
        if isinstance(contract, Mapping) and contract.get("name") == "release-evidence"
    ] if isinstance(contracts, list) else []
    if len(release_contracts) != 1:
        raise RuntimeError("release_stage_release_evidence_contract_missing")
    release_contract = release_contracts[0]
    excluded_mutable_fields = {
        "gates",
        "reasons",
        "release_evidence_hash",
        "release_status",
        "review",
    }
    payload: dict[str, object] = {
        "schema_version": RELEASE_STAGE_OUTPUT_SCHEMAS["release_evidence_write"],
        "fixture_id": "p122-release-evidence-contract-fixture-v1",
        "operation": RELEASE_STAGE_OPERATIONS["release_evidence_write"],
        "producer_contract": {
            "release_id": produced.get("release_id"),
            "product_claim": produced.get("product_claim"),
            "public_limitation": produced.get("public_limitation"),
            "gate_names": sorted(_mapping(produced.get("gates"))),
            "stable_field_names": sorted(key for key in produced if key not in excluded_mutable_fields),
        },
        "validator_contract": {
            "check_names": sorted(checks),
            "core_round_trip_checks": list(core_round_trip_checks),
            "core_round_trip_passed": True,
        },
        "public_contract": {
            "name": release_contract.get("name"),
            "interface_ref": release_contract.get("interface_ref"),
        },
        "excluded_mutable_fields": [
            "current_release_evidence_hash",
            "current_release_status",
            "gate_values",
            "reasons",
            "review_artifact",
            "reviewer_id",
        ],
    }
    payload["release_evidence_hash"] = stable_hash(payload)
    return payload


def _prepare_release_evidence_fixture(root: Path) -> Path:
    path = root / "release-evidence.json"
    _durable_json_write(path, _release_evidence_contract_fixture(root))
    return path


def _validate_release_evidence_fixture(path: Path) -> dict[str, object]:
    from app.public_contracts import public_contract_manifest

    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["release_evidence_write"], hash_field="release_evidence_hash")
    if payload != _release_evidence_contract_fixture(path.parent):
        raise RuntimeError("release_stage_release_evidence_fixture_mismatch")
    manifest = public_contract_manifest()
    contracts = manifest.get("contracts")
    release_contracts = [
        contract
        for contract in contracts
        if isinstance(contract, Mapping) and contract.get("name") == "release-evidence"
    ] if isinstance(contracts, list) else []
    if len(release_contracts) != 1 or release_contracts[0].get("interface_ref") != RELEASE_STAGE_OUTPUT_SCHEMAS["release_evidence_write"]:
        raise RuntimeError("release_stage_release_evidence_contract_missing")
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["release_evidence_hash"]),
        "contract_validation_executed": True,
        "contract_manifest_hash": manifest["manifest_hash"],
        "release_status": "excluded_from_fixture_projection",
    }


def _prepare_report(root: Path) -> Path:
    from scripts.verify_p122_docs import verify_docs

    path = root / "docs-verification.json"
    _durable_json_write(path, verify_docs())
    return path


def _validate_report(path: Path) -> dict[str, object]:
    payload = _validated_json_artifact(path, schema=RELEASE_STAGE_OUTPUT_SCHEMAS["report_write"], hash_field="report_hash")
    checked_docs = payload.get("checked_docs")
    if payload.get("valid") is not True or not isinstance(checked_docs, list):
        raise RuntimeError("release_stage_report_invalid")
    return {
        "schema_version": str(payload["schema_version"]),
        "artifact_hash": str(payload["report_hash"]),
        "valid": True,
        "checked_doc_count": len(checked_docs),
    }


def _validated_json_artifact(path: Path, *, schema: str, hash_field: str) -> dict[str, object]:
    payload = dict(_json_mapping(path))
    if payload.get("schema_version") != schema:
        raise RuntimeError(f"release_stage_output_schema_invalid:{schema}")
    expected = payload.get(hash_field)
    actual = stable_hash({key: value for key, value in payload.items() if key != hash_field})
    if not isinstance(expected, str) or expected != actual:
        raise RuntimeError(f"release_stage_output_hash_invalid:{schema}")
    return payload


_RELEASE_STAGE_ADAPTERS = {
    "install": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["install"], "installed-wheel", RELEASE_STAGE_OUTPUT_SCHEMAS["install"], _prepare_wheel_install, _validate_wheel_install),
    "demo_startup": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["demo_startup"], "local-demo.json", RELEASE_STAGE_OUTPUT_SCHEMAS["demo_startup"], _prepare_local_demo, _validate_local_demo),
    "incident_ingest": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["incident_ingest"], "incident.json", RELEASE_STAGE_OUTPUT_SCHEMAS["incident_ingest"], _prepare_incident, _validate_incident),
    "evidence_request": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["evidence_request"], "evidence.json", RELEASE_STAGE_OUTPUT_SCHEMAS["evidence_request"], _prepare_evidence, _validate_evidence),
    "decision": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["decision"], "decision.json", RELEASE_STAGE_OUTPUT_SCHEMAS["decision"], _prepare_decision, _validate_decision),
    "approval": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["approval"], "approval.json", RELEASE_STAGE_OUTPUT_SCHEMAS["approval"], _prepare_approval, _validate_approval),
    "validation": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["validation"], "validation.json", RELEASE_STAGE_OUTPUT_SCHEMAS["validation"], _prepare_validation, _validate_validation),
    "rollback": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["rollback"], "rollback.json", RELEASE_STAGE_OUTPUT_SCHEMAS["rollback"], _prepare_rollback, _validate_rollback),
    "replay_write": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["replay_write"], "replay-bundle", RELEASE_STAGE_OUTPUT_SCHEMAS["replay_write"], _prepare_replay, _validate_replay),
    "eval_write": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["eval_write"], "frozen-evaluation.json", RELEASE_STAGE_OUTPUT_SCHEMAS["eval_write"], _prepare_evaluation, _validate_evaluation),
    "release_evidence_write": ReleaseStageAdapter(
        RELEASE_STAGE_ADAPTER_NAMES["release_evidence_write"],
        "release-evidence.json",
        RELEASE_STAGE_OUTPUT_SCHEMAS["release_evidence_write"],
        _prepare_release_evidence_fixture,
        _validate_release_evidence_fixture,
    ),
    "report_write": ReleaseStageAdapter(RELEASE_STAGE_ADAPTER_NAMES["report_write"], "docs-verification.json", RELEASE_STAGE_OUTPUT_SCHEMAS["report_write"], _prepare_report, _validate_report),
}


def _release_stage_adapter(stage: str) -> ReleaseStageAdapter:
    try:
        return _RELEASE_STAGE_ADAPTERS[stage]
    except KeyError as exc:
        raise ValueError(f"unknown_release_stage:{stage}") from exc


def _measure_local_install(target: Path) -> tuple[float, str]:
    if target.exists():
        shutil.rmtree(target)
    start = time.perf_counter()
    target.mkdir(parents=True)
    wheels = sorted((ROOT / "dist").glob("opscat-*.whl"))
    if wheels:
        import zipfile

        with zipfile.ZipFile(wheels[-1]) as wheel:
            wheel.extractall(target)
        method = "wheel-extract"
    else:
        shutil.copytree(ROOT / "app", target / "app")
        _atomic_json_write(target / "opscat-local-install.json", {"source": "app", "scope": "local-package-payload", "dependency_resolution": False})
        method = "source-payload-copy"
    if not (target / "app").is_dir():
        raise RuntimeError("local_install_probe_missing_app_package")
    return time.perf_counter() - start, method


def _measure_cold_start() -> tuple[float, ModuleType]:
    importlib.invalidate_caches()
    sys.modules.pop("app.cli", None)
    start = time.perf_counter()
    module = importlib.import_module("app.cli")
    elapsed = time.perf_counter() - start
    if not callable(getattr(module, "run_local_demo", None)):
        raise RuntimeError("cold_start_missing_demo_entrypoint")
    return elapsed, module


def _observe_authority_rejection(cli_module: ModuleType, output: Path) -> dict[str, object]:
    keys = ("OPSCAT_MODE", "OPSCAT_TARGET")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["OPSCAT_MODE"] = "production"
    os.environ["OPSCAT_TARGET"] = "https://production.invalid"
    reason = "missing_authority_rejection"
    try:
        cli_module.run_local_demo(output)
    except ValueError as exc:
        reason = str(exc)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return {
        "observed": reason == "production_like_demo_configuration_denied",
        "reason": reason,
        "correlation_id": "p122-authority-rejection-00",
        "output_created": output.exists(),
        "fail_closed": not output.exists(),
    }


def _storage_envelope(*, workdir: Path, iterations: int) -> dict[str, object]:
    sizes = [path.stat().st_size for path in workdir.rglob("*") if path.is_file()]
    total = sum(sizes)
    return {
        "file_count": len(sizes),
        "total_bytes": total,
        "largest_file_bytes": max(sizes, default=0),
        "bytes_per_iteration": total / iterations,
        "scope": "workdir including install, record, WAL, and crash-replay artifacts",
    }


def _atomic_json_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _durable_json_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _json_mapping(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(path: Path) -> list[object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _exact_zero_p121(value: Mapping[str, object]) -> bool:
    return set(value) == set(P121_AUTHORITY_COUNTER_KEYS) and all(isinstance(value[key], int) and not isinstance(value[key], bool) and value[key] == 0 for key in P121_AUTHORITY_COUNTER_KEYS)


def _execute_p121_crash_replay(wal_path: Path) -> dict[str, object]:
    registry: dict[str, dict[str, object]] = {"fixture-p122": {"disposable": True, "target_class": "disposable_local_sandbox", "allowed_handlers": ["inject_latency"]}}
    envelope: dict[str, object] = {
        "operation_id": "p122-soak-recovery",
        "authority_level": "L3",
        "target_class": "disposable_local_sandbox",
        "fixture_id": "fixture-p122",
        "handler": "inject_latency",
        "registry_hash": stable_hash(registry),
        "idempotency_key": "p122-soak-recovery-idem",
        "lease_owner": "p122-soak-worker",
        "lease_expires_at": 200,
        "approval_expires_at": 190,
        "authority_counters": zero_authority_counters(),
    }
    for name in ("forecast_hash", "evidence_hash", "counterfactual_hash", "guardrail_hash", "validation_plan_hash", "rollback_plan_hash"):
        envelope[name] = "sha256:" + name
    return prove_p121_restart_recovery(wal_path=wal_path, envelope=envelope, registry=registry, now=100)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def performance_semantic_projection(report: Mapping[str, object]) -> dict[str, object]:
    crash_replay = _mapping(report.get("release_stage_crash_replay"))
    points = crash_replay.get("points")
    point_projection = [
        {
            "stage": point.get("stage"),
            "operation": point.get("operation"),
            "operation_adapter": point.get("operation_adapter"),
            "output_schema": point.get("output_schema"),
            "crash_exit_code": point.get("crash_exit_code"),
            "recovery_exit_code": point.get("recovery_exit_code"),
            "adapter_invoked": point.get("adapter_invoked"),
            "precommit_hash": point.get("precommit_hash"),
            "output_hash": point.get("output_hash"),
            "post_restart_validation": point.get("post_restart_validation"),
            "restart_verified": point.get("restart_verified"),
        }
        for point in points
        if isinstance(point, Mapping)
    ] if isinstance(points, list) else []
    upstream = _mapping(report.get("upstream_executed_crash_replay"))
    observability = _mapping(report.get("observability"))
    readiness = _mapping(observability.get("readiness"))
    metrics = _mapping(observability.get("metrics"))
    diagnostics = _mapping(observability.get("diagnostics"))
    authority_rejection = _mapping(observability.get("authority_rejection"))
    projection: dict[str, object] = {
        "schema_version": report.get("schema_version"),
        "iterations": report.get("iterations"),
        "expected_records": dict(_mapping(report.get("expected_records"))),
        "observed_records": dict(_mapping(report.get("observed_records"))),
        "record_loss": {
            key: report.get(key)
            for key in (
                "lost_incident_records",
                "lost_audit_records",
                "lost_timeline_records",
                "lost_replay_records",
                "lost_authority_records",
            )
        },
        "unique_replay_files": report.get("unique_replay_files"),
        "release_stage_crash_inventory": report.get("release_stage_crash_inventory"),
        "release_stage_crash_protocol": crash_replay.get("protocol"),
        "release_stage_crash_counts": {
            key: crash_replay.get(key)
            for key in ("point_count", "injected_count", "recovered_count", "observed_restart_receipt_count", "verified")
        },
        "release_stage_restart_receipts": point_projection,
        "upstream_crash_replay": {
            key: upstream.get(key)
            for key in ("point_count", "replayed_count", "pending_rollback_replayed", "pending_rollback_count_after_replay")
        },
        "authority_counters": dict(_mapping(report.get("authority_counters"))),
        "observability": {
            "ready": readiness.get("ready"),
            "readiness_checks": dict(_mapping(readiness.get("checks"))),
            "records_lost_total": metrics.get("records_lost_total"),
            "release_stage_crashes_injected_total": metrics.get("release_stage_crashes_injected_total"),
            "release_stage_crashes_recovered_total": metrics.get("release_stage_crashes_recovered_total"),
            "authority_rejections_total": metrics.get("authority_rejections_total"),
            "authority_rejection_observed": authority_rejection.get("observed"),
            "authority_rejection_reason": authority_rejection.get("reason"),
            "authority_rejection_fail_closed": authority_rejection.get("fail_closed"),
            "redaction_verified": diagnostics.get("redaction_verified"),
            "replay_inspectable": diagnostics.get("replay_inspectable"),
        },
        "scope_limit": report.get("scope_limit"),
    }
    return {**projection, "projection_hash": stable_hash(projection)}


def compare_performance_reports(current: Mapping[str, object], promoted: Mapping[str, object]) -> dict[str, object]:
    current_projection = performance_semantic_projection(current)
    promoted_projection = performance_semantic_projection(promoted)
    current_hash = current_projection["projection_hash"]
    promoted_hash = promoted_projection["projection_hash"]
    return {
        "matches": current_projection == promoted_projection,
        "current_semantic_binding_valid": current.get("semantic_binding") == current_hash,
        "promoted_semantic_binding_valid": promoted.get("semantic_binding") == promoted_hash,
        "current_projection_hash": current_hash,
        "promoted_projection_hash": promoted_hash,
    }


def validate_promoted_performance_artifacts(report: Mapping[str, object], *, repo_root: Path = ROOT) -> bool:
    try:
        observability = _mapping(report.get("observability"))
        diagnostics = _mapping(observability.get("diagnostics"))
        crash_root = _repo_artifact_path(repo_root, diagnostics.get("crash_replay_artifact_root"))
        record_root = _repo_artifact_path(repo_root, diagnostics.get("record_artifact_root"))
        if not crash_root.is_dir() or not record_root.is_dir():
            return False

        manifest = _json_mapping(record_root / "manifest.json")
        manifest_payload = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        bundle_path = record_root / PERFORMANCE_RECORD_BUNDLE
        bundle = _mapping(manifest.get("bundle"))
        if (
            manifest.get("schema_version") != "p122.performance_record_manifest.v2"
            or manifest.get("manifest_hash") != stable_hash(manifest_payload)
            or manifest.get("iterations") != report.get("iterations")
            or manifest.get("expected_records") != report.get("expected_records")
            or manifest.get("observed_records") != report.get("observed_records")
            or manifest.get("semantic_binding") != report.get("semantic_binding")
            or bundle.get("ref") != PERFORMANCE_RECORD_BUNDLE
            or bundle.get("hash") != _file_sha256(bundle_path)
            or bundle.get("line_count") != report.get("iterations")
        ):
            return False
        entries = _read_record_bundle(bundle_path)
        classes = _record_class_summary(entries)
        if classes != manifest.get("classes") or any(
            _mapping(report.get("observed_records")).get(key) != _mapping(classes.get(key)).get("count")
            for key in PERFORMANCE_RECORD_CLASSES
        ):
            return False

        crash_replay = _mapping(report.get("release_stage_crash_replay"))
        points = crash_replay.get("points")
        if not isinstance(points, list) or len(points) != len(RELEASE_STAGE_CRASH_POINTS):
            return False
        for ordinal, (point_value, stage) in enumerate(zip(points, RELEASE_STAGE_CRASH_POINTS, strict=True)):
            if not isinstance(point_value, Mapping) or point_value.get("stage") != stage:
                return False
            adapter = _release_stage_adapter(stage)
            stage_root = crash_root / f"{ordinal:02d}-{stage}"
            pending_path = _repo_artifact_path(repo_root, point_value.get("pending_ref"))
            receipt_path = _repo_artifact_path(repo_root, point_value.get("restart_receipt_ref"))
            output_path = _repo_artifact_path(repo_root, point_value.get("output_ref"))
            if (
                pending_path != stage_root / "pending.json"
                or receipt_path != stage_root / "restart-receipt.json"
                or output_path != stage_root / "committed" / adapter.artifact_name
            ):
                return False
            pending = _json_mapping(pending_path)
            receipt = _json_mapping(receipt_path)
            output_validation = adapter.validate(output_path)
            if (
                not _record_hash_valid(pending)
                or not _record_hash_valid(receipt)
                or point_value.get("pending_record_hash") != pending.get("record_hash")
                or point_value.get("pending_record_hash") != receipt.get("pending_record_hash")
                or point_value.get("restart_receipt_hash") != receipt.get("record_hash")
                or point_value.get("precommit_hash") != pending.get("precommit_hash")
                or point_value.get("precommit_hash") != receipt.get("precommit_hash")
                or point_value.get("output_hash") != receipt.get("output_hash")
                or point_value.get("output_hash") != _artifact_hash(output_path)
                or receipt.get("output_validation") != output_validation
                or point_value.get("post_restart_validation") is not True
                or receipt.get("post_restart_validation") is not True
            ):
                return False
        return True
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return False


def _repo_artifact_path(repo_root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise RuntimeError("performance_artifact_ref_not_repo_relative")
    root = repo_root.resolve()
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("performance_artifact_ref_outside_repo") from exc
    return resolved


def _canonical_json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _record_bundle_entry(source_records: Path, index: int) -> dict[str, object]:
    return {
        "index": index,
        "incident": dict(_json_mapping(source_records / f"incident-{index:04d}.json")),
        "audit": list(_json_list(source_records / f"audit-{index:04d}.json")),
        "timeline": list(_json_list(source_records / f"timeline-{index:04d}.json")),
        "replay": dict(_json_mapping(source_records.parent / f"replay-{index:04d}.json")),
        "authority": dict(_json_mapping(source_records / f"authority-{index:04d}.json")),
    }


def _record_class_summary(entries: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    counts = {key: 0 for key in PERFORMANCE_RECORD_CLASSES}
    hashers = {key: hashlib.sha256() for key in PERFORMANCE_RECORD_CLASSES}
    expected_keys = {"index", "incident", "audit", "timeline", "replay", "authority"}
    for index, entry in enumerate(entries):
        if set(entry) != expected_keys or entry.get("index") != index:
            raise RuntimeError("performance_record_bundle_order_invalid")
        incident = _mapping(entry.get("incident"))
        audit = entry.get("audit")
        timeline = entry.get("timeline")
        replay = _mapping(entry.get("replay"))
        authority = _mapping(entry.get("authority"))
        if (
            incident.get("schema_version") != "opscat.local_demo.v1"
            or not isinstance(audit, list)
            or not isinstance(timeline, list)
            or replay.get("schema_version") != "opscat.local_demo.v1"
            or not _exact_zero_p121(authority)
        ):
            raise RuntimeError("performance_record_bundle_content_invalid")
        values: dict[str, object] = {
            "incident_records": dict(incident),
            "audit_records": audit,
            "timeline_records": timeline,
            "replay_records": dict(replay),
            "authority_records": dict(authority),
        }
        counts["incident_records"] += 1
        counts["audit_records"] += len(audit)
        counts["timeline_records"] += len(timeline)
        counts["replay_records"] += 1
        counts["authority_records"] += 1
        for class_name, value in values.items():
            hashers[class_name].update(_canonical_json_bytes({"index": index, "value": value}))
    return {
        key: {"count": counts[key], "hash": "sha256:" + hashers[key].hexdigest()}
        for key in PERFORMANCE_RECORD_CLASSES
    }


def _read_record_bundle(path: Path) -> list[Mapping[str, object]]:
    entries: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RuntimeError("performance_record_bundle_entry_invalid")
        entries.append(value)
    return entries


def promote_performance_artifacts(
    report: dict[str, object],
    *,
    artifact_dir: Path = ROOT / PROMOTED_ARTIFACTS_RELATIVE,
    repo_root: Path = ROOT,
) -> None:
    observability = report.get("observability")
    diagnostics = observability.get("diagnostics") if isinstance(observability, dict) else None
    crash_replay = report.get("release_stage_crash_replay")
    points = crash_replay.get("points") if isinstance(crash_replay, dict) else None
    if not isinstance(diagnostics, dict) or not isinstance(points, list):
        raise RuntimeError("performance_report_missing_promotion_artifacts")
    source_root = Path(str(diagnostics.get("crash_replay_artifact_root", "")))
    source_records = Path(str(diagnostics.get("record_artifact_root", "")))
    if not source_root.is_dir():
        raise RuntimeError("performance_crash_artifact_source_missing")
    if not source_records.is_dir():
        raise RuntimeError("performance_record_artifact_source_missing")
    repo_root = repo_root.resolve()
    artifact_dir = artifact_dir.resolve()
    try:
        artifact_relative = artifact_dir.relative_to(repo_root)
    except ValueError as exc:
        raise RuntimeError("performance_artifact_target_outside_repo") from exc
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    nonce = f"{os.getpid()}.{time.time_ns()}"
    staging = artifact_dir.parent / f".{artifact_dir.name}.{nonce}.tmp"
    backup = artifact_dir.parent / f".{artifact_dir.name}.{nonce}.backup"
    installed = False
    try:
        staging.mkdir()
        shutil.copytree(source_root, staging / "crash-replay")
        records = staging / "records"
        records.mkdir()
        iterations = _required_int(report.get("iterations"), "iterations")
        entries = [_record_bundle_entry(source_records, index) for index in range(iterations)]
        bundle_path = records / PERFORMANCE_RECORD_BUNDLE
        bundle_path.write_bytes(b"".join(_canonical_json_bytes(entry) for entry in entries))
        classes = _record_class_summary(entries)
        observed_records = dict(_mapping(report.get("observed_records")))
        if any(observed_records.get(key) != classes[key]["count"] for key in PERFORMANCE_RECORD_CLASSES):
            raise RuntimeError("performance_record_bundle_count_mismatch")
        record_manifest: dict[str, object] = {
            "schema_version": "p122.performance_record_manifest.v2",
            "iterations": iterations,
            "expected_records": dict(_mapping(report.get("expected_records"))),
            "observed_records": observed_records,
            "record_loss": {
                key: report.get(key)
                for key in (
                    "lost_incident_records",
                    "lost_audit_records",
                    "lost_timeline_records",
                    "lost_replay_records",
                    "lost_authority_records",
                )
            },
            "bundle": {
                "ref": PERFORMANCE_RECORD_BUNDLE,
                "hash": _file_sha256(bundle_path),
                "line_count": iterations,
            },
            "classes": classes,
            "semantic_binding": report.get("semantic_binding"),
        }
        record_manifest["manifest_hash"] = stable_hash(record_manifest)
        _durable_json_write(records / "manifest.json", record_manifest)
        _fsync_artifact(staging)
        if artifact_dir.exists():
            os.replace(artifact_dir, backup)
        os.replace(staging, artifact_dir)
        _fsync_directory(artifact_dir.parent)
        installed = True
    except BaseException:
        if backup.exists() and not artifact_dir.exists():
            os.replace(backup, artifact_dir)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if installed and backup.exists():
            shutil.rmtree(backup)

    artifact_prefix = artifact_relative.as_posix()
    crash_prefix = f"{artifact_prefix}/crash-replay"
    diagnostics["crash_replay_artifact_root"] = crash_prefix
    diagnostics["record_artifact_root"] = f"{artifact_prefix}/records"
    for ordinal, (point_value, stage) in enumerate(zip(points, RELEASE_STAGE_CRASH_POINTS, strict=True)):
        if not isinstance(point_value, dict):
            raise RuntimeError(f"performance_crash_point_invalid:{stage}")
        stage_prefix = f"{crash_prefix}/{ordinal:02d}-{stage}"
        point_value["pending_ref"] = f"{stage_prefix}/pending.json"
        point_value["restart_receipt_ref"] = f"{stage_prefix}/restart-receipt.json"
        point_value["output_ref"] = f"{stage_prefix}/committed/{_release_stage_adapter(stage).artifact_name}"
    _refresh_report_hashes(report)
    if not validate_promoted_performance_artifacts(report, repo_root=repo_root):
        raise RuntimeError("promoted_performance_artifact_validation_failed")


def _refresh_report_hashes(report: dict[str, object]) -> None:
    report.pop("semantic_binding", None)
    report.pop("report_hash", None)
    report["semantic_binding"] = performance_semantic_projection(report)["projection_hash"]
    report["report_hash"] = stable_hash(report)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--compare-report",
        "--compare-to",
        dest="compare_report",
        type=Path,
        help="require semantic equivalence with a promoted performance report",
    )
    parser.add_argument("--allow-short-test-run", action="store_true", help="permit fewer than 1000 iterations for local tests only")
    args = parser.parse_args(argv)
    if args.iterations < 1000 and not args.allow_short_test_run:
        parser.error("--iterations must be at least 1000 for release evidence")
    args.workdir.mkdir(parents=True, exist_ok=True)
    report = run_soak(iterations=args.iterations, workdir=args.workdir)
    if args.output.resolve() == (ROOT / PROMOTED_REPORT_RELATIVE).resolve():
        promote_performance_artifacts(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _durable_json_write(args.output, report)
    summary: dict[str, object] = {"iterations": report["iterations"], "report_hash": report["report_hash"], "semantic_binding": report["semantic_binding"]}
    if args.compare_report is not None:
        promoted = _json_mapping(args.compare_report)
        comparison = compare_performance_reports(report, promoted)
        comparison["promoted_artifacts_valid"] = validate_promoted_performance_artifacts(promoted)
        summary["comparison"] = comparison
        print(json.dumps(summary, sort_keys=True))
        return 0 if all(
            (
                comparison["matches"],
                comparison["current_semantic_binding_valid"],
                comparison["promoted_semantic_binding_valid"],
                comparison["promoted_artifacts_valid"],
            )
        ) else 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
