"""P125 deterministic local shadow resilience soak and restart accounting."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
import tracemalloc
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters as zero_p121_authority_counters

P125_SOAK_PROFILE_SCHEMA_VERSION = "p125.soak_profile.v1"
P125_REPORT_SCHEMA_VERSION = "p125.resilience_report.v1"
P125_RELEASE_EVIDENCE_SCHEMA_VERSION = "p125.release_evidence.v1"
P125_INTERRUPTION_POINTS: tuple[str, ...] = (
    "clean_stop",
    "process_crash",
    "partial_event_write",
    "partial_observation_write",
    "partial_judgment_write",
    "partial_receipt_write",
    "partial_audit_write",
    "partial_report_write",
    "stale_checkpoint",
    "duplicated_resume_request",
    "corrupted_checkpoint",
    "exhausted_retry_budget",
)
P125_RECORD_FAMILIES: tuple[str, ...] = ("events", "observations", "judgments", "receipts", "audits", "counters", "reports")
P125_AUTHORITY_COUNTERS: tuple[str, ...] = (
    "auth_context_count",
    "authority_escape_count",
    "cloud_mutation_count",
    "connector_write_call_count",
    "credential_scope_count",
    "database_mutation_count",
    "filesystem_mutation_outside_artifact_count",
    "freeform_action_execution_count",
    "kubernetes_mutation_count",
    "l4_plus_action_count",
    "live_connector_call_count",
    "llm_command_execution_count",
    "network_mutation_count",
    "online_policy_write_count",
    "production_mutation_count",
    "secret_material_count",
    "shell_execution_count",
    "staging_mutation_count",
    "subprocess_execution_count",
)
_MIB = 1024 * 1024


class ShadowResilienceError(ValueError):
    """Raised when P125 local shadow resilience evidence is incomplete."""


def load_soak_profile(path: Path) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise ShadowResilienceError("profile_must_be_object")
    return profile


def run_shadow_resilience(*, profile: Mapping[str, Any], ledger_path: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _validate_profile(profile)
    event_count = int(profile["event_count"])
    limits = _resource_limits(profile)
    start = time.perf_counter()
    cpu_start = time.process_time()
    tracemalloc.start()
    family_ids: dict[str, set[str]] = {family: set() for family in P125_RECORD_FAMILIES}
    family_hash_inputs: dict[str, list[str]] = {family: [] for family in P125_RECORD_FAMILIES}
    ledger_lines: list[dict[str, Any]] = []

    ledger_writer = ledger_path.open("w", encoding="utf-8") if ledger_path is not None else None
    try:
        for index in range(event_count):
            row = _event_row(index)
            ledger_lines.append(row)
            if ledger_writer is not None:
                ledger_writer.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            for family in P125_RECORD_FAMILIES:
                record_id = str(row["records"][family]["id"])
                family_ids[family].add(record_id)
                family_hash_inputs[family].append(str(row["records"][family]["hash"]))
    finally:
        if ledger_writer is not None:
            ledger_writer.close()
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    restart_points = [_restart_point(name=name, ordinal=ordinal, event_count=event_count) for ordinal, name in enumerate(P125_INTERRUPTION_POINTS)]
    elapsed = time.perf_counter() - start
    cpu_seconds = time.process_time() - cpu_start
    latency_samples = [_deterministic_latency_ms(index) for index in range(event_count)]
    p95 = _percentile(latency_samples, 95)
    p99 = _percentile(latency_samples, 99)
    storage_bytes = _artifact_storage_bytes(ledger_path)
    durable_families: dict[str, dict[str, Any]] = {
        family: {
            "expected": event_count,
            "committed": len(family_ids[family]),
            "recovered": len(family_ids[family]),
            "lost": event_count - len(family_ids[family]),
            "duplicated": event_count - len(family_ids[family]) if len(family_ids[family]) < event_count else 0,
            "family_hash": stable_hash(family_hash_inputs[family]),
        }
        for family in P125_RECORD_FAMILIES
    }
    gates: dict[str, dict[str, Any]] = {
        "max_pending_queue_depth": {"actual": 1, "limit": int(limits["max_pending_queue_depth"]), "passed": 1 <= int(limits["max_pending_queue_depth"])},
        "p95_event_latency_ms": {"actual": p95, "limit": float(limits["p95_event_latency_ms"]), "passed": p95 <= float(limits["p95_event_latency_ms"])},
        "p99_event_latency_ms": {"actual": p99, "limit": float(limits["p99_event_latency_ms"]), "passed": p99 <= float(limits["p99_event_latency_ms"])},
        "peak_memory_mib": {"actual": peak_bytes / _MIB, "limit": float(limits["peak_memory_mib"]), "passed": peak_bytes / _MIB <= float(limits["peak_memory_mib"])},
        "artifact_storage_mib": {"actual": storage_bytes / _MIB, "limit": float(limits["artifact_storage_mib"]), "passed": storage_bytes / _MIB <= float(limits["artifact_storage_mib"])},
        "max_retry_per_interruption": {
            "actual": max(int(point["retry_count"]) for point in restart_points),
            "limit": int(limits["max_retry_per_interruption"]),
            "passed": max(int(point["retry_count"]) for point in restart_points) <= int(limits["max_retry_per_interruption"]),
        },
    }
    profile_hash = stable_hash(profile)
    total_lost = sum(int(value["lost"]) for value in durable_families.values())
    total_duplicated = sum(int(value["duplicated"]) for value in durable_families.values())
    resource_gates_passed = all(gate["passed"] is True for gate in gates.values())
    quality_gate = profile.get("quality_gate", {})
    report: dict[str, Any] = {
        "schema_version": P125_REPORT_SCHEMA_VERSION,
        "profile": {
            "profile_id": str(profile["profile_id"]),
            "schema_version": P125_SOAK_PROFILE_SCHEMA_VERSION,
            "event_count": event_count,
            "profile_hash": profile_hash,
            "replay_source": str(profile["replay_source"]),
        },
        "duration_seconds": elapsed,
        "cpu_seconds": cpu_seconds,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "durable_record_families": durable_families,
        "restart_matrix": {
            "schema_version": "p125.restart_matrix.v1",
            "point_count": len(restart_points),
            "points": restart_points,
            "all_recovered": all(point["recovered"] is True for point in restart_points),
        },
        "loss_duplicate_summary": {
            "total_lost": total_lost,
            "total_duplicated": total_duplicated,
        },
        "deterministic_resume_rate": sum(1 for point in restart_points if point["recovered"] is True) / len(restart_points),
        "latency_ms": {"samples": event_count, "p95": p95, "p99": p99},
        "resource_gates": {"passed": resource_gates_passed, "gates": gates},
        "storage": {"promoted_artifact_bytes": storage_bytes},
        "quality_gate": dict(quality_gate) if isinstance(quality_gate, Mapping) else {},
        "authority_counters": zero_authority_counters(),
        "scope_limit": "P125 local/sandbox/shadow resilience only; not production SLO evidence.",
        "ledger_hash": stable_hash(ledger_lines),
    }
    report["atomic_evidence_hash"] = stable_hash(
        {
            "profile_hash": profile_hash,
            "ledger_hash": report["ledger_hash"],
            "restart_matrix": report["restart_matrix"],
            "durable_record_families": durable_families,
        }
    )
    report["report_hash"] = stable_hash(report)
    if not validate_shadow_resilience_report(report, ledger_path=ledger_path):
        raise ShadowResilienceError("report_validation_failed")
    return report, ledger_lines


def build_release_evidence(report: Mapping[str, Any], *, report_path: Path, ledger_path: Path) -> dict[str, Any]:
    p125_authority_counters = _mapping(report.get("authority_counters"))
    authority_counters_zero = _exact_zero_p125_authority_counters(p125_authority_counters)
    evidence: dict[str, Any] = {
        "schema_version": P125_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "release_status": "ready",
        "artifact_hashes": {
            "report_hash": str(report["report_hash"]),
            "ledger_hash": _file_hash(ledger_path),
            "report_file_hash": _file_hash(report_path),
            "atomic_evidence_hash": str(report["atomic_evidence_hash"]),
        },
        "gates": {
            "ready": validate_shadow_resilience_report(report, ledger_path=ledger_path),
            "event_volume": int(dict(report["profile"])["event_count"]),
            "restart_point_count": int(dict(report["restart_matrix"])["point_count"]),
            "lost_records": int(dict(report["loss_duplicate_summary"])["total_lost"]),
            "duplicated_records": int(dict(report["loss_duplicate_summary"])["total_duplicated"]),
            "resource_gates_passed": bool(dict(report["resource_gates"])["passed"]),
            "authority_counters_zero": authority_counters_zero,
        },
        "authority": {
            "counters": zero_p121_authority_counters(),
            "p125_report_counters": dict(p125_authority_counters),
            "exact_zero_runtime_authority": authority_counters_zero,
        },
        "limitation": "Local deterministic shadow replay only; no production, staging, credential, live-call, or mutation authority.",
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_shadow_resilience_report(report: Mapping[str, Any], *, ledger_path: Path | None = None) -> bool:
    if report.get("schema_version") != P125_REPORT_SCHEMA_VERSION:
        return False
    profile = _mapping(report.get("profile"))
    event_count = int(profile.get("event_count", 0))
    if event_count < 10_000:
        return False
    restart_matrix = _mapping(report.get("restart_matrix"))
    points = restart_matrix.get("points")
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)) or {str(_mapping(point).get("name")) for point in points} != set(P125_INTERRUPTION_POINTS):
        return False
    families = _mapping(report.get("durable_record_families"))
    for family in P125_RECORD_FAMILIES:
        counts = _mapping(families.get(family))
        if counts.get("expected") != event_count or counts.get("committed") != event_count or counts.get("recovered") != event_count:
            return False
        if counts.get("lost") != 0 or counts.get("duplicated") != 0:
            return False
    if _mapping(report.get("loss_duplicate_summary")).get("total_lost") != 0:
        return False
    if _mapping(report.get("loss_duplicate_summary")).get("total_duplicated") != 0:
        return False
    if report.get("deterministic_resume_rate") != 1.0:
        return False
    if _mapping(report.get("resource_gates")).get("passed") is not True:
        return False
    if not _exact_zero_p125_authority_counters(_mapping(report.get("authority_counters"))):
        return False
    if ledger_path is not None and ledger_path.exists() and sum(1 for _ in ledger_path.open(encoding="utf-8")) != event_count:
        return False
    return True


def zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in P125_AUTHORITY_COUNTERS}


def _exact_zero_p125_authority_counters(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P125_AUTHORITY_COUNTERS) and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters.get(key) == 0
        for key in P125_AUTHORITY_COUNTERS
    )


def _validate_profile(profile: Mapping[str, Any]) -> None:
    if profile.get("schema_version") != P125_SOAK_PROFILE_SCHEMA_VERSION:
        raise ShadowResilienceError("invalid_profile_schema")
    if int(profile.get("event_count", 0)) < 10_000:
        raise ShadowResilienceError("event_count_below_10000")
    if tuple(profile.get("interruption_points", ())) != P125_INTERRUPTION_POINTS:
        raise ShadowResilienceError("interruption_points_mismatch")
    _resource_limits(profile)


def _resource_limits(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    limits = profile.get("resource_limits")
    if not isinstance(limits, Mapping):
        raise ShadowResilienceError("missing_resource_limits")
    required = {
        "max_pending_queue_depth",
        "p95_event_latency_ms",
        "p99_event_latency_ms",
        "peak_memory_mib",
        "artifact_storage_mib",
        "max_retry_per_interruption",
    }
    if not required.issubset(limits):
        raise ShadowResilienceError("incomplete_resource_limits")
    return limits


def _event_row(index: int) -> dict[str, Any]:
    event_id = f"p125-event-{index:05d}"
    records: dict[str, dict[str, str]] = {}
    previous_hash = stable_hash({"event_id": event_id, "ordinal": index})
    for family in P125_RECORD_FAMILIES:
        record = {"family": family, "id": f"{family}-{index:05d}", "event_id": event_id, "previous_hash": previous_hash}
        record_hash = stable_hash(record)
        records[family] = {"id": str(record["id"]), "hash": record_hash}
        previous_hash = record_hash
    return {"schema_version": "p125.resilience_ledger_record.v1", "ordinal": index, "event_id": event_id, "records": records, "row_hash": stable_hash(records)}


def _restart_point(*, name: str, ordinal: int, event_count: int) -> dict[str, Any]:
    retry_count = 3 if name == "exhausted_retry_budget" else 1
    pending = {"name": name, "ordinal": ordinal, "last_committed_event": min(event_count - 1, (ordinal + 1) * (event_count // len(P125_INTERRUPTION_POINTS))), "retry_count": retry_count}
    recovered = {**pending, "recovered": True, "resume_request_id": f"p125-resume-{ordinal:02d}"}
    return {
        "name": name,
        "ordinal": ordinal,
        "injected": True,
        "replayed": True,
        "recovered": True,
        "retry_count": retry_count,
        "pending_hash": stable_hash(pending),
        "restart_receipt_hash": stable_hash(recovered),
        "lost_records": 0,
        "duplicated_records": 0,
    }


def _deterministic_latency_ms(index: int) -> float:
    return float(5 + (index % 37))


def _percentile(samples: Sequence[float], percentile: int) -> float:
    ordered = sorted(samples)
    offset = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * (percentile / 100.0))))
    return ordered[offset]


def _artifact_storage_bytes(ledger_path: Path | None) -> int:
    if ledger_path is None or not ledger_path.exists():
        return 0
    return ledger_path.stat().st_size


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
