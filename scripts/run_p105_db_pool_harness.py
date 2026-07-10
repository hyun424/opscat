from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import sqlite3
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

PROGRAM_VERSION = "p105.database.pool.v1"
PUBLIC_TELEMETRY = "p105-db-pool-public-telemetry.jsonl"
PRIVATE_LEDGER = "p105-db-pool-private-saturation-ledger.json"
PRE_LABEL_PARTITIONS = "p105-db-pool-pre-label-partitions.json"
COVERAGE = "p105-db-pool-coverage.json"
RAW_ATTESTATION = "p105-db-pool-runtime-attestation.raw.json"
MANIFEST = "p105-db-pool-harness-manifest.json"
PROVENANCE_HASHES = "p105-db-pool-provenance-hashes.json"
SATURATION_SCHEDULE: Final[dict[str, dict[str, tuple[int, int]]]] = {
    "dbpool-svc-00": {"saturation": (600, 899), "stall": (2100, 2159)},
    "dbpool-svc-01": {"saturation": (1200, 1499), "stall": (2700, 2759)},
    "dbpool-svc-02": {"saturation": (1800, 2099), "stall": (3300, 3359)},
    "dbpool-svc-03": {"saturation": (2400, 2699), "stall": (3900, 3959)},
    "dbpool-svc-04": {"saturation": (900, 1199), "stall": (3000, 3059)},
    "dbpool-svc-05": {"saturation": (1500, 1799), "stall": (3600, 3659)},
    "dbpool-svc-06": {"saturation": (2100, 2399), "stall": (4200, 4259)},
    "dbpool-svc-07": {"saturation": (2700, 2999), "stall": (4800, 4859)},
}
CANONICAL_ARG_VALUE_FLAGS: Final[set[str]] = {"--sqlite-db", "--output-dir"}


@dataclass
class PoolStats:
    attempts: int = 0
    success: int = 0
    failed: int = 0
    timeout: int = 0
    sql_insert: int = 0
    sql_select: int = 0
    sql_update: int = 0
    sql_error: int = 0
    checked_out_peak: int = 0


class SQLiteServicePool:
    def __init__(self, service_id: str, db_path: Path, pool_size: int) -> None:
        self.service_id = service_id
        self.semaphore = threading.BoundedSemaphore(pool_size)
        self.connections: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
        self.sql_lock = threading.Lock()
        self.checkout_lock = threading.Lock()
        self.checked_out = 0
        for _ in range(pool_size):
            connection = sqlite3.connect(db_path, timeout=30.0, isolation_level=None, check_same_thread=False)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            self.connections.put(connection)

    def close(self) -> None:
        while not self.connections.empty():
            self.connections.get_nowait().close()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(_stable_json(row) + "\n" for row in rows), encoding="utf-8")


def _canonical_argv(argv: list[str]) -> list[str]:
    canonical: list[str] = []
    skip_next = False
    for index, item in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        canonical.append("python" if index == 0 else item)
        if item in CANONICAL_ARG_VALUE_FLAGS and index + 1 < len(argv):
            canonical.append(f"<{item.removeprefix('--').upper().replace('-', '_')}>")
            skip_next = True
    return canonical


def _source_window_id(service_id: str, tick: int) -> str:
    return _sha256_text(_stable_json({"program_version": PROGRAM_VERSION, "service_id": service_id, "tick": tick}))


def _event_time(created_at: str, tick: int) -> str:
    return f"{created_at}+{tick:04d}s"


def _latency_bucket_ms(elapsed_ms: float) -> str:
    if elapsed_ms < 10:
        return "000-009"
    if elapsed_ms < 50:
        return "010-049"
    if elapsed_ms < 100:
        return "050-099"
    if elapsed_ms < 250:
        return "100-249"
    if elapsed_ms < 500:
        return "250-499"
    return "500-plus"


def _bucket_lower_bound(bucket: str) -> int:
    return 500 if bucket == "500-plus" else int(bucket.split("-", 1)[0])


def _percentile_bucket(buckets: Counter[str], percentile: float) -> str:
    if not buckets:
        return "000-009"
    total = sum(buckets.values())
    threshold = max(1, int(total * percentile + 0.999999))
    seen = 0
    for bucket in ("000-009", "010-049", "050-099", "100-249", "250-499", "500-plus"):
        seen += buckets.get(bucket, 0)
        if seen >= threshold:
            return bucket
    return "500-plus"


def _in_range(tick: int, bounds: tuple[int, int]) -> bool:
    return bounds[0] <= tick <= bounds[1]


def _partition_services(heldout: list[str], shadow: list[str]) -> dict[str, str]:
    return {service_id: "held_out_test" for service_id in heldout} | {service_id: "real_derived_shadow" for service_id in shadow}


def _init_database(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE pool_events(
                service_id TEXT NOT NULL,
                tick INTEGER NOT NULL,
                worker_id INTEGER NOT NULL,
                attempt_id INTEGER NOT NULL,
                started_ns INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE pool_counters(
                service_id TEXT PRIMARY KEY,
                observed_count INTEGER NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def _seed_counters(db_path: Path, services: list[str]) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executemany("INSERT INTO pool_counters(service_id, observed_count) VALUES (?, 0)", [(service_id,) for service_id in services])
        connection.commit()
    finally:
        connection.close()


def _worker_attempt(
    *,
    service_pool: SQLiteServicePool,
    tick: int,
    worker_id: int,
    attempt_id: int,
    acquire_timeout_ms: int,
    hold_ms: int,
    stats: PoolStats,
    stats_lock: threading.Lock,
    latency_buckets: Counter[str],
    raw_observations: list[dict[str, Any]],
    raw_lock: threading.Lock,
) -> None:
    with stats_lock:
        stats.attempts += 1
    acquire_started = time.monotonic_ns()
    acquired = service_pool.semaphore.acquire(timeout=acquire_timeout_ms / 1000)
    elapsed_ms = (time.monotonic_ns() - acquire_started) / 1_000_000
    bucket = _latency_bucket_ms(elapsed_ms)
    with stats_lock:
        latency_buckets[bucket] += 1
    if not acquired:
        with stats_lock:
            stats.failed += 1
            stats.timeout += 1
        return

    connection = service_pool.connections.get()
    try:
        with service_pool.checkout_lock:
            service_pool.checked_out += 1
            checked_out = service_pool.checked_out
        with stats_lock:
            stats.checked_out_peak = max(stats.checked_out_peak, checked_out)
        started_ns = time.monotonic_ns()
        try:
            with service_pool.sql_lock:
                connection.execute(
                    "INSERT INTO pool_events(service_id, tick, worker_id, attempt_id, started_ns) VALUES (?, ?, ?, ?, ?)",
                    (service_pool.service_id, tick, worker_id, attempt_id, started_ns),
                )
                connection.execute("SELECT COUNT(*) FROM pool_events WHERE service_id = ?", (service_pool.service_id,)).fetchone()
                connection.execute("UPDATE pool_counters SET observed_count = observed_count + 1 WHERE service_id = ?", (service_pool.service_id,))
            with stats_lock:
                stats.success += 1
                stats.sql_insert += 1
                stats.sql_select += 1
                stats.sql_update += 1
            with raw_lock:
                raw_observations.append(
                    {
                        "sqlite_connection_object_id": id(connection),
                        "service_id": service_pool.service_id,
                        "thread_id": threading.get_ident(),
                        "tick": tick,
                        "worker_id": worker_id,
                    }
                )
            time.sleep(hold_ms / 1000)
        except sqlite3.Error:
            with stats_lock:
                stats.sql_error += 1
    finally:
        service_pool.connections.put(connection)
        with service_pool.checkout_lock:
            service_pool.checked_out -= 1
        service_pool.semaphore.release()


def _materialize_runtime(args: argparse.Namespace, services: list[str], partitions: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    _init_database(args.sqlite_db)
    _seed_counters(args.sqlite_db, services)
    pools = {service_id: SQLiteServicePool(service_id, args.sqlite_db, args.pool_size) for service_id in services}
    raw_observations: list[dict[str, Any]] = []
    raw_lock = threading.Lock()
    monotonic_started_ns = time.monotonic_ns()
    telemetry: list[dict[str, Any]] = []
    observed_intervals: dict[str, list[dict[str, int]]] = {service_id: [] for service_id in services}

    try:
        for tick in range(args.ticks):
            tick_started = time.monotonic()
            for service_id in services:
                schedule = SATURATION_SCHEDULE.get(service_id, {"saturation": (-1, -1), "stall": (-1, -1)})
                saturating = _in_range(tick, schedule["saturation"])
                stalling = _in_range(tick, schedule["stall"])
                hold_ms = args.saturation_hold_ms if saturating or stalling else args.normal_hold_ms
                stats = PoolStats()
                stats_lock = threading.Lock()
                latency_buckets: Counter[str] = Counter()
                threads = [
                    threading.Thread(
                        target=_worker_attempt,
                        kwargs={
                            "service_pool": pools[service_id],
                            "tick": tick,
                            "worker_id": worker_id,
                            "attempt_id": tick * args.workers_per_service + worker_id,
                            "acquire_timeout_ms": args.acquire_timeout_ms,
                            "hold_ms": hold_ms if (not saturating or worker_id < max(1, args.workers_per_service - args.pool_size)) else args.normal_hold_ms,
                            "stats": stats,
                            "stats_lock": stats_lock,
                            "latency_buckets": latency_buckets,
                            "raw_observations": raw_observations,
                            "raw_lock": raw_lock,
                        },
                    )
                    for worker_id in range(args.workers_per_service)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                if stats.success:
                    observed_intervals[service_id].append({"end_tick": tick, "start_tick": tick})
                    p50_bucket = _percentile_bucket(latency_buckets, 0.50)
                    p95_bucket = _percentile_bucket(latency_buckets, 0.95)
                    row: dict[str, Any] = {
                        "acquisition_attempt_count": stats.attempts,
                        "acquisition_latency_bucket_counts": dict(sorted(latency_buckets.items())),
                        "acquisition_latency_p50_bucket_ms": p50_bucket,
                        "acquisition_latency_p95_bucket_ms": p95_bucket,
                        "available_count": max(0, args.pool_size - stats.checked_out_peak),
                        "checked_out_count": stats.checked_out_peak,
                        "coverage_bucket_seconds": args.tick_seconds,
                        "event_time": _event_time(args.created_at, tick),
                        "failed_acquisition_count": stats.failed,
                        "partition_id": partitions[service_id],
                        "program_version": PROGRAM_VERSION,
                        "runtime_attestation_capability": "sqlite3_connection_pool",
                        "runtime_attestation_kind": "actual_sqlite_pool",
                        "schema_version": "p105.database.pool.telemetry.v1",
                        "seed": args.seed,
                        "service_id": service_id,
                        "source_window_id": _source_window_id(service_id, tick),
                        "sqlite_pool_size": args.pool_size,
                        "sql_error_count": stats.sql_error,
                        "sql_insert_count": stats.sql_insert,
                        "sql_select_count": stats.sql_select,
                        "sql_update_count": stats.sql_update,
                        "successful_acquisition_count": stats.success,
                        "tick": tick,
                        "timeout_count": stats.timeout,
                        "wait_queue_length": stats.failed,
                    }
                    row["telemetry_row_sha256"] = _sha256_text(_stable_json({"db_pool_public_row": row}))
                    telemetry.append(row)
            remaining = args.tick_seconds - (time.monotonic() - tick_started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        for pool in pools.values():
            pool.close()

    monotonic_finished_ns = time.monotonic_ns()
    ledger = _private_ledger(args, services, partitions)
    coverage = {
        "actual_sqlite_pool_observations": True,
        "clock_source": "time.monotonic_ns",
        "coverage_method": "actual_successful_sql_observation_tick_union",
        "diagnostic_profile": bool(args.test_fast_runtime),
        "observed_intervals": observed_intervals,
        "observed_seconds_by_service": {service_id: len(intervals) * args.tick_seconds for service_id, intervals in observed_intervals.items()},
        "rejects": ["fixed_four_day_constant", "accelerated_logical_clock", "floor_sized_interval", "row_count_as_duration"],
        "schema_version": "p105.database.pool.coverage.v1",
    }
    raw_attestation = {
        "capability": "sqlite3_connection_pool",
        "kind": "actual_sqlite_pool",
        "monotonic_finished_ns": monotonic_finished_ns,
        "monotonic_started_ns": monotonic_started_ns,
        "process_id": os.getpid(),
        "sqlite_connection_observations": raw_observations[: min(128, len(raw_observations))],
    }
    return telemetry, ledger, coverage, raw_attestation


def _private_ledger(args: argparse.Namespace, services: list[str], partitions: dict[str, str]) -> dict[str, Any]:
    schedule_sha256 = _sha256_text(_stable_json(SATURATION_SCHEDULE))
    records: list[dict[str, Any]] = []
    for service_id in services:
        schedule = SATURATION_SCHEDULE.get(service_id)
        if not schedule:
            continue
        for injection_type, bounds in schedule.items():
            start_tick, end_tick = bounds
            public_ids = [_source_window_id(service_id, tick) for tick in range(max(0, start_tick), min(args.ticks - 1, end_tick) + 1)]
            records.append(
                {
                    "end_tick": end_tick,
                    "expected_predicate": "db_connection_limit",
                    "injection_id": f"p105-db-pool-{service_id}-{injection_type}-{start_tick}-{end_tick}",
                    "injection_type": f"connection_pool_{injection_type}",
                    "label_join_phase": "after_sampling_and_partition",
                    "partition_id": partitions[service_id],
                    "public_source_window_ids": public_ids,
                    "schedule_sha256": schedule_sha256,
                    "seed": args.seed,
                    "service_id": service_id,
                    "start_tick": start_tick,
                }
            )
    ledger: dict[str, Any] = {
        "label_join_completed_after_sampling": True,
        "label_join_phase": "after_sampling_and_partition",
        "public_artifact": False,
        "records": sorted(records, key=lambda item: (str(item["service_id"]), str(item["injection_type"]))),
        "schema_version": "p105.database.pool.private_saturation_ledger.v1",
    }
    ledger["ledger_sha256"] = _sha256_text(_stable_json(ledger))
    return ledger


def _partitions_payload(services: list[str], heldout: list[str], shadow: list[str], partitions: dict[str, str]) -> dict[str, Any]:
    return {
        "assignment_rules": {
            "dbpool-svc-00..dbpool-svc-03": "held_out_test",
            "dbpool-svc-04..dbpool-svc-07": "real_derived_shadow",
        },
        "assignment_version": "p105.database.pool.pre_label_partition.v1",
        "label_blind": True,
        "partitioned_before_private_saturation_ledger": True,
        "services": {
            service_id: {
                "partition_id": partitions[service_id],
                "service_id": service_id,
                "source_key": "p105-isolated-local-db-pool",
            }
            for service_id in services
        },
        "shadow_services": shadow,
        "heldout_services": heldout,
    }


def _artifact_hashes(output: Path, exclude: set[str] | None = None) -> dict[str, str]:
    blocked = exclude or set()
    return {
        path.name: _sha256_path(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name not in blocked
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize P105 actual SQLite bounded connection-pool harness artifacts.")
    parser.add_argument("--sqlite-db", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--services", required=True)
    parser.add_argument("--heldout-services", required=True)
    parser.add_argument("--shadow-services", required=True)
    parser.add_argument("--pool-size", required=True, type=int)
    parser.add_argument("--workers-per-service", required=True, type=int)
    parser.add_argument("--acquisitions-per-worker-per-second", required=True, type=int)
    parser.add_argument("--acquire-timeout-ms", required=True, type=int)
    parser.add_argument("--normal-hold-ms", required=True, type=int)
    parser.add_argument("--saturation-hold-ms", required=True, type=int)
    parser.add_argument("--ticks", required=True, type=int)
    parser.add_argument("--tick-seconds", required=True, type=float)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--expect-runtime-attestation-kind", required=True)
    parser.add_argument("--test-fast-runtime", action="store_true")
    parser.add_argument("--expect-no-production-authority", action="store_true")
    return parser


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate_args(args: argparse.Namespace, services: list[str], heldout: list[str], shadow: list[str]) -> list[str]:
    errors: list[str] = []
    if args.mode != "isolated-local":
        errors.append("mode_not_isolated_local")
    if args.expect_runtime_attestation_kind != "actual_sqlite_pool":
        errors.append("runtime_attestation_kind_mismatch")
    if not args.expect_no_production_authority:
        errors.append("production_authority_guard_missing")
    if args.seed != 105028:
        errors.append("seed_not_fixed_105028")
    if args.pool_size != 3:
        errors.append("pool_size_not_fixed_3")
    if args.acquisitions_per_worker_per_second != 1:
        errors.append("acquisition_rate_not_fixed_1")
    if set(services) != set(heldout) | set(shadow) or set(heldout) & set(shadow):
        errors.append("service_partition_mismatch")
    if args.sqlite_db.parent != args.output_dir:
        errors.append("sqlite_db_must_be_under_output_dir")
    if not args.test_fast_runtime:
        if args.ticks != 7200:
            errors.append("ticks_not_fixed_7200")
        if args.tick_seconds != 1:
            errors.append("tick_seconds_not_fixed_one")
        if args.workers_per_service != 12:
            errors.append("workers_per_service_not_fixed_12")
        if args.normal_hold_ms != 20:
            errors.append("normal_hold_ms_not_fixed_20")
        if args.saturation_hold_ms != 650:
            errors.append("saturation_hold_ms_not_fixed_650")
        if args.acquire_timeout_ms != 75:
            errors.append("acquire_timeout_ms_not_fixed_75")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    services = _split_csv(args.services)
    heldout = _split_csv(args.heldout_services)
    shadow = _split_csv(args.shadow_services)
    errors = _validate_args(args, services, heldout, shadow)
    if errors:
        sys.stderr.write(json.dumps({"error": "p105_db_pool_harness_fail_closed", "validation_error_codes": errors}, sort_keys=True) + "\n")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    partitions = _partition_services(heldout, shadow)
    _write_json(args.output_dir / PRE_LABEL_PARTITIONS, _partitions_payload(services, heldout, shadow, partitions))
    telemetry, private_ledger, coverage, raw_attestation = _materialize_runtime(args, services, partitions)
    _write_jsonl(args.output_dir / PUBLIC_TELEMETRY, telemetry)
    _write_json(args.output_dir / PRIVATE_LEDGER, private_ledger)
    _write_json(args.output_dir / COVERAGE, coverage)
    _write_json(args.output_dir / RAW_ATTESTATION, raw_attestation)

    canonical_argv = _canonical_argv(sys.argv if argv is None else [sys.argv[0], *argv])
    artifact_hashes = _artifact_hashes(args.output_dir, exclude={MANIFEST, PROVENANCE_HASHES, RAW_ATTESTATION})
    manifest = {
        "artifact_hashes": artifact_hashes,
        "artifact_paths": {
            "coverage": COVERAGE,
            "partitions": PRE_LABEL_PARTITIONS,
            "private_saturation_ledger": PRIVATE_LEDGER,
            "provenance_hashes": PROVENANCE_HASHES,
            "public_telemetry": PUBLIC_TELEMETRY,
        },
        "authority": {
            "auth_enabled": False,
            "credentials_read": False,
            "external_database_endpoint": False,
            "network_calls": False,
            "production_endpoint": False,
            "production_mutation": False,
            "release_counting_authority": False,
        },
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": _sha256_text(_stable_json(canonical_argv)),
        "created_at": args.created_at,
        "diagnostic_profile": {
            "non_qualifying": bool(args.test_fast_runtime),
            "reason": "test_fast_runtime" if args.test_fast_runtime else None,
        },
        "implementation_guard": {
            "uses_bounded_queue": True,
            "uses_bounded_semaphore": True,
            "uses_in_memory_database": False,
            "uses_mocked_connection": False,
            "uses_precomputed_row_generator": False,
        },
        "mode": args.mode,
        "program_version": PROGRAM_VERSION,
        "public_telemetry_row_count": len(telemetry),
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "runtime_attestation": {
            "capability": "sqlite3_connection_pool",
            "kind": "actual_sqlite_pool",
        },
        "schedule_sha256": _sha256_text(_stable_json(SATURATION_SCHEDULE)),
        "schema_version": "p105.database.pool.harness_manifest.v1",
        "seed": args.seed,
        "source_family": "database",
        "sql_operation_evidence": {
            "insert": any(row["sql_insert_count"] for row in telemetry),
            "select_count": any(row["sql_select_count"] for row in telemetry),
            "update": any(row["sql_update_count"] for row in telemetry),
        },
        "sqlite_pool_size": args.pool_size,
        "tick_seconds": args.tick_seconds,
        "ticks": args.ticks,
    }
    _write_json(args.output_dir / MANIFEST, manifest)
    provenance = {
        "artifact_hashes": _artifact_hashes(args.output_dir, exclude={PROVENANCE_HASHES}),
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": manifest["command_argv_sha256"],
        "hash_algorithm": "sha256",
        "program_version": PROGRAM_VERSION,
        "schema_version": "p105.database.pool.provenance_hashes.v1",
    }
    _write_json(args.output_dir / PROVENANCE_HASHES, provenance)
    print(json.dumps({"manifest_path": str(args.output_dir / MANIFEST), "telemetry_rows": len(telemetry)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
