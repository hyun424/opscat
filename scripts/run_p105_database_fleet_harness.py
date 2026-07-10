from __future__ import annotations

import argparse
import concurrent.futures
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

PROGRAM_VERSION = "p105.database.fleet.v1"
PROFILE = "p105.actual-fleet-soak.256x1h.v1"
DIAGNOSTIC_PROFILE = "p105.database-fleet.diagnostic.fast.v1"
SCHEMA_VERSION = "p105.database.fleet_harness.v1"
ADAPTER_KEY = "database_fleet"
ADAPTER_VERSION = "p105.adapter.sqlite-pool-fleet-harness.v1"
RUNTIME_KIND = "actual_sqlite_pool"

PUBLIC_TELEMETRY = "p105-database-fleet-public-telemetry.jsonl"
PRIVATE_LEDGER = "p105-database-fleet-private-injection-ledger.json"
PRE_LABEL_PARTITIONS = "p105-database-fleet-pre-label-partitions.json"
COVERAGE = "p105-database-fleet-coverage.json"
RAW_ATTESTATION = "p105-database-fleet-runtime-attestation.raw.json"
MANIFEST = "p105-database-fleet-harness-manifest.json"
PROVENANCE_HASHES = "p105-database-fleet-provenance-hashes.json"

SERVICE_COUNT: Final[int] = 256
HELD_OUT_COUNT: Final[int] = 128
SHADOW_COUNT: Final[int] = 128
REQUESTED_SECONDS: Final[int] = 3600
CADENCE_SECONDS: Final[int] = 5
SAMPLES_PER_SERVICE: Final[int] = 720
HEARTBEAT_INTERVAL_SECONDS: Final[int] = 30
SQL_SHARDS: Final[int] = 64
SERVICES_PER_SHARD: Final[int] = 4
POOL_SIZE: Final[int] = 3
MAX_LIVE_SQLITE_CONNECTIONS: Final[int] = 192
MAX_SQL_TRANSACTION_CYCLES: Final[int] = 40_000
WORKER_THREADS: Final[int] = 64
CANONICAL_ARG_VALUE_FLAGS: Final[set[str]] = {
    "--diagnostic-samples",
    "--output-dir",
    "--profile",
    "--requested-seconds",
    "--sample-cadence-seconds",
    "--samples-per-service",
    "--seed",
}
DATABASE_KINDS: Final[tuple[str, ...]] = (
    "pool_saturation",
    "slow_transaction",
    "lock_contention",
    "checkout_timeout",
)


@dataclass
class ShardStats:
    acquire_attempts: int = 0
    acquire_failures: int = 0
    checked_out_peak: int = 0
    sql_insert: int = 0
    sql_select: int = 0
    sql_update: int = 0
    sql_errors: int = 0
    timeout_count: int = 0
    transaction_cycles: int = 0


class SQLiteShardPool:
    def __init__(self, shard_id: int, db_path: Path, pool_size: int) -> None:
        self.shard_id = shard_id
        self.db_path = db_path
        self.semaphore = threading.BoundedSemaphore(pool_size)
        self.connections: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
        self.checkout_lock = threading.Lock()
        self.sql_lock = threading.Lock()
        self.checked_out = 0
        self.stats = ShardStats()
        for _ in range(pool_size):
            connection = sqlite3.connect(db_path, timeout=30.0, isolation_level=None, check_same_thread=False)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            self.connections.put(connection)

    def acquire(self, timeout_seconds: float) -> sqlite3.Connection | None:
        self.stats.acquire_attempts += 1
        acquired = self.semaphore.acquire(timeout=timeout_seconds)
        if not acquired:
            self.stats.acquire_failures += 1
            self.stats.timeout_count += 1
            return None
        connection = self.connections.get()
        with self.checkout_lock:
            self.checked_out += 1
            self.stats.checked_out_peak = max(self.stats.checked_out_peak, self.checked_out)
        return connection

    def release(self, connection: sqlite3.Connection) -> None:
        self.connections.put(connection)
        with self.checkout_lock:
            self.checked_out -= 1
        self.semaphore.release()

    def close(self) -> bool:
        closed = 0
        while not self.connections.empty():
            self.connections.get_nowait().close()
            closed += 1
        return closed == POOL_SIZE


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


def _service_id(index: int) -> str:
    return f"p105.fleet.database.{index:03d}"


def _split_for_index(index: int) -> str:
    return "held_out" if index < HELD_OUT_COUNT else "real_derived_shadow"


def _source_window_id(service_index: int, ordinal: int) -> str:
    return f"p105-fleet-database-{_split_for_index(service_index)}-svc{service_index:03d}-sample{ordinal:03d}"


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


def _profile_hash(profile_id: str) -> str:
    return _sha256_text(
        _stable_json(
            {
                "cadence_seconds": CADENCE_SECONDS,
                "profile": profile_id,
                "requested_seconds": REQUESTED_SECONDS,
                "schema_version": SCHEMA_VERSION,
                "services": [_service_id(index) for index in range(SERVICE_COUNT)],
            }
        )
    )


def _full_profile_bounds() -> dict[str, int]:
    return {
        "adjacent_intervals_per_service": SAMPLES_PER_SERVICE - 1,
        "max_seconds_per_family": 920_320,
        "max_seconds_per_service": 3_595,
        "max_seconds_per_split": 460_160,
        "samples_per_service": SAMPLES_PER_SERVICE,
    }


def _build_schedule() -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    for split, base in (("held_out", 0), ("real_derived_shadow", 128)):
        for group in range(8):
            start = 300 + 30 * group
            end = start + 300
            failure = 3300 + 30 * group
            affected_indexes = [base + 4 * group + offset for offset in range(4)]
            schedule.append(
                {
                    "affected_service_indexes": affected_indexes,
                    "affected_services": [_service_id(index) for index in affected_indexes],
                    "group_id": f"g{group:02d}",
                    "incident_group_id": f"p105-fleet-database-{split}-g{group:02d}",
                    "kind": DATABASE_KINDS[group % 4],
                    "kind_index": group % 4,
                    "lead_range_minutes": [45, 50],
                    "positive_precursor_end_offset_seconds": end,
                    "positive_precursor_start_offset_seconds": start,
                    "private_failure_offset_seconds": failure,
                    "split": split,
                }
            )
    return schedule


def _incident_for(service_index: int, sample_offset_seconds: int, schedule: list[dict[str, Any]]) -> dict[str, Any] | None:
    for incident in schedule:
        if service_index not in incident["affected_service_indexes"]:
            continue
        if incident["positive_precursor_start_offset_seconds"] <= sample_offset_seconds <= incident["positive_precursor_end_offset_seconds"]:
            return incident
    return None


def _runtime_service_indexes(sample_offset_seconds: int, schedule: list[dict[str, Any]]) -> list[int]:
    if sample_offset_seconds % HEARTBEAT_INTERVAL_SECONDS == 0:
        return list(range(SERVICE_COUNT))
    return [service_index for service_index in range(SERVICE_COUNT) if _incident_for(service_index, sample_offset_seconds, schedule) is not None]


def _init_shard_database(db_path: Path, service_ids: list[str]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            """
            CREATE TABLE fleet_heartbeats(
                service_id TEXT NOT NULL,
                sample_ordinal INTEGER NOT NULL,
                sample_offset_seconds INTEGER NOT NULL,
                worker_thread INTEGER NOT NULL,
                monotonic_ns INTEGER NOT NULL,
                incident_kind TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE fleet_counters(
                service_id TEXT PRIMARY KEY,
                observed_count INTEGER NOT NULL,
                last_sample_ordinal INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE fleet_locks(
                lock_name TEXT PRIMARY KEY,
                touched_count INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO fleet_counters(service_id, observed_count, last_sample_ordinal) VALUES (?, 0, -1)",
            [(service_id,) for service_id in service_ids],
        )
        connection.execute("INSERT INTO fleet_locks(lock_name, touched_count) VALUES ('database_fleet_lock', 0)")
        connection.commit()
    finally:
        connection.close()


def _build_shards(output_dir: Path) -> dict[int, SQLiteShardPool]:
    shard_dir = output_dir / "sqlite-shards"
    pools: dict[int, SQLiteShardPool] = {}
    for shard_id in range(SQL_SHARDS):
        service_ids = [_service_id(shard_id * SERVICES_PER_SHARD + offset) for offset in range(SERVICES_PER_SHARD)]
        db_path = shard_dir / f"p105-database-fleet-shard-{shard_id:02d}.sqlite3"
        _init_shard_database(db_path, service_ids)
        pools[shard_id] = SQLiteShardPool(shard_id, db_path, POOL_SIZE)
    return pools


def _heartbeat_transaction(
    *,
    pool: SQLiteShardPool,
    service_id: str,
    sample_ordinal: int,
    sample_offset_seconds: int,
    incident_kind: str | None,
) -> dict[str, Any]:
    timeout_seconds = 0.001 if incident_kind == "checkout_timeout" else 0.5
    transaction_started_ns = time.monotonic_ns()
    connection = pool.acquire(timeout_seconds)
    if connection is None:
        return {
            "acquire_failed": True,
            "acquire_wait_ms": (time.monotonic_ns() - transaction_started_ns) / 1_000_000,
            "incident_kind": incident_kind,
            "sample_offset_seconds": sample_offset_seconds,
            "sample_ordinal": sample_ordinal,
            "service_id": service_id,
            "sql_ok": False,
            "transaction_duration_ms": (time.monotonic_ns() - transaction_started_ns) / 1_000_000,
        }
    acquired_ns = time.monotonic_ns()
    started_ns = time.monotonic_ns()
    try:
        try:
            if incident_kind == "lock_contention":
                with pool.sql_lock:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute("UPDATE fleet_locks SET touched_count = touched_count + 1 WHERE lock_name = 'database_fleet_lock'")
                    time.sleep(0.04)
                    connection.execute("COMMIT")
            with pool.sql_lock:
                connection.execute(
                    """
                    INSERT INTO fleet_heartbeats(
                        service_id,
                        sample_ordinal,
                        sample_offset_seconds,
                        worker_thread,
                        monotonic_ns,
                        incident_kind
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (service_id, sample_ordinal, sample_offset_seconds, threading.get_ident(), started_ns, incident_kind),
                )
                connection.execute("SELECT observed_count FROM fleet_counters WHERE service_id = ?", (service_id,)).fetchone()
                connection.execute(
                    """
                    UPDATE fleet_counters
                    SET observed_count = observed_count + 1,
                        last_sample_ordinal = ?
                    WHERE service_id = ?
                    """,
                    (sample_ordinal, service_id),
                )
            if incident_kind in {"pool_saturation", "slow_transaction", "checkout_timeout"}:
                time.sleep(0.04)
            pool.stats.sql_insert += 1
            pool.stats.sql_select += 1
            pool.stats.sql_update += 1
            pool.stats.transaction_cycles += 1
            return {
                "acquire_failed": False,
                "acquire_wait_ms": (acquired_ns - transaction_started_ns) / 1_000_000,
                "connection_object_id": id(connection),
                "incident_kind": incident_kind,
                "sample_offset_seconds": sample_offset_seconds,
                "sample_ordinal": sample_ordinal,
                "service_id": service_id,
                "sql_ok": True,
                "thread_id": threading.get_ident(),
                "transaction_duration_ms": (time.monotonic_ns() - transaction_started_ns) / 1_000_000,
            }
        except sqlite3.Error as error:
            pool.stats.sql_errors += 1
            return {
                "acquire_failed": False,
                "acquire_wait_ms": (acquired_ns - transaction_started_ns) / 1_000_000,
                "incident_kind": incident_kind,
                "sample_offset_seconds": sample_offset_seconds,
                "sample_ordinal": sample_ordinal,
                "service_id": service_id,
                "sqlite_error": error.__class__.__name__,
                "sql_ok": False,
                "transaction_duration_ms": (time.monotonic_ns() - transaction_started_ns) / 1_000_000,
            }
    finally:
        pool.release(connection)


def _run_sample(
    *,
    executor: concurrent.futures.ThreadPoolExecutor,
    pools: dict[int, SQLiteShardPool],
    sample_ordinal: int,
    sample_offset_seconds: int,
    schedule: list[dict[str, Any]],
    service_indexes: list[int],
) -> list[dict[str, Any]]:
    futures: list[concurrent.futures.Future[dict[str, Any]]] = []
    for service_index in service_indexes:
        incident = _incident_for(service_index, sample_offset_seconds, schedule)
        shard_id = service_index // SERVICES_PER_SHARD
        futures.append(
            executor.submit(
                _heartbeat_transaction,
                pool=pools[shard_id],
                service_id=_service_id(service_index),
                sample_ordinal=sample_ordinal,
                sample_offset_seconds=sample_offset_seconds,
                incident_kind=None if incident is None else str(incident["kind"]),
            )
        )
    return [future.result() for future in futures]


def _telemetry_row(
    *,
    service_index: int,
    sample_ordinal: int,
    sample_offset_seconds: int,
    sample_monotonic_ns: int,
    heartbeat_result: dict[str, Any] | None,
    heartbeat_observation_age_seconds: int | None,
    partition_id: str,
    shard: SQLiteShardPool,
) -> dict[str, Any]:
    service_id = _service_id(service_index)
    row: dict[str, Any] = {
        "adapter_key": ADAPTER_KEY,
        "adapter_version": ADAPTER_VERSION,
        "heartbeat_sql_cycle_observed": heartbeat_result is not None and heartbeat_result.get("sql_ok") is True,
        "heartbeat_observation_age_seconds": heartbeat_observation_age_seconds,
        "partition_id": partition_id,
        "profile": PROFILE,
        "program_version": PROGRAM_VERSION,
        "runtime_attestation_capability": "sqlite3_bounded_shard_pool",
        "runtime_attestation_kind": RUNTIME_KIND,
        "sample_offset_seconds": sample_offset_seconds,
        "sample_ordinal": sample_ordinal,
        "schema_version": "p105.database.fleet.telemetry.v1",
        "service_id": service_id,
        "shard_id": shard.shard_id,
        "source_window_id": _source_window_id(service_index, sample_ordinal),
        "sqlite_pool_size": POOL_SIZE,
        "sql_error_count": shard.stats.sql_errors,
    }
    if heartbeat_result is not None:
        row.update(
            {
                "acquisition_failed": heartbeat_result.get("acquire_failed") is True,
                "acquire_wait_ms": heartbeat_result.get("acquire_wait_ms"),
                "sql_insert_count": 1 if heartbeat_result.get("sql_ok") is True else 0,
                "sql_select_count": 1 if heartbeat_result.get("sql_ok") is True else 0,
                "sql_update_count": 1 if heartbeat_result.get("sql_ok") is True else 0,
                "transaction_duration_ms": heartbeat_result.get("transaction_duration_ms"),
            }
        )
    else:
        row.update(
            {
                "acquisition_failed": False,
                "sql_insert_count": 0,
                "sql_select_count": 0,
                "sql_update_count": 0,
            }
        )
    row["telemetry_row_sha256"] = _sha256_text(_stable_json({"database_fleet_public_row": row}))
    return row


def _canonical_segments(raw_samples: dict[int, list[dict[str, Any]]], diagnostic_only: bool) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for service_index, samples in sorted(raw_samples.items()):
        current: list[dict[str, Any]] = []
        for sample in samples:
            if not current:
                current = [sample]
                continue
            previous = current[-1]
            consecutive = sample["sample_ordinal"] == previous["sample_ordinal"] + 1
            delta_seconds = (sample["monotonic_ns"] - previous["monotonic_ns"]) / 1_000_000_000
            valid_delta = 4.0 <= delta_seconds <= 7.5
            if consecutive and valid_delta:
                current.append(sample)
            else:
                if len(current) >= 2:
                    segments.append(_segment_for(service_index, current, diagnostic_only))
                current = [sample]
        if len(current) >= 2:
            segments.append(_segment_for(service_index, current, diagnostic_only))
    return segments


def _segment_for(service_index: int, samples: list[dict[str, Any]], diagnostic_only: bool) -> dict[str, Any]:
    raw_elapsed = (samples[-1]["monotonic_ns"] - samples[0]["monotonic_ns"]) / 1_000_000_000
    conservative_duration = min((len(samples) - 1) * CADENCE_SECONDS, int(raw_elapsed // CADENCE_SECONDS) * CADENCE_SECONDS)
    return {
        "conservative_duration_seconds": 0 if diagnostic_only else conservative_duration,
        "diagnostic_observed_duration_seconds": conservative_duration if diagnostic_only else None,
        "endpoint_source_window_ids": [samples[0]["source_window_id"], samples[-1]["source_window_id"]],
        "family": "database",
        "sample_count": len(samples),
        "service_id": _service_id(service_index),
        "split": _split_for_index(service_index),
        "start_sample_ordinal": samples[0]["sample_ordinal"],
        "end_sample_ordinal": samples[-1]["sample_ordinal"],
    }


def _partitions_payload(services: list[str]) -> dict[str, Any]:
    return {
        "assignment_version": "p105.database.fleet.pre_label_partition.v1",
        "held_out_services": services[:HELD_OUT_COUNT],
        "label_blind": True,
        "partitioned_before_private_schedule_loading": True,
        "real_derived_shadow_services": services[HELD_OUT_COUNT:],
        "services": {
            service_id: {
                "partition_id": _split_for_index(index),
                "service_id": service_id,
                "source_key": "p105-isolated-local-database-fleet",
            }
            for index, service_id in enumerate(services)
        },
    }


def _private_ledger(schedule: list[dict[str, Any]], sampled_ordinals: set[int], profile_config_hash: str) -> dict[str, Any]:
    incidents: list[dict[str, Any]] = []
    for incident in schedule:
        start_ordinal = incident["positive_precursor_start_offset_seconds"] // CADENCE_SECONDS
        end_ordinal = incident["positive_precursor_end_offset_seconds"] // CADENCE_SECONDS
        bound_ids = [
            _source_window_id(service_index, ordinal) for service_index in incident["affected_service_indexes"] for ordinal in range(start_ordinal, end_ordinal + 1) if ordinal in sampled_ordinals
        ]
        record = {key: value for key, value in incident.items() if key != "affected_service_indexes"}
        record["bound_public_source_window_ids"] = bound_ids
        record["label_join_phase"] = "after_sampling_and_partition"
        incidents.append(record)
    ledger: dict[str, Any] = {
        "incidents": incidents,
        "label_join_phase": "after_sampling_and_partition",
        "private_schedule_loaded_after_profile_hash": True,
        "profile_config_hash": profile_config_hash,
        "public_artifact": False,
        "schema_version": "p105.database.fleet.private_injection_ledger.v1",
    }
    ledger["ledger_sha256"] = _sha256_text(_stable_json(ledger))
    return ledger


def _artifact_hashes(output: Path, exclude: set[str] | None = None) -> dict[str, str]:
    blocked = exclude or set()
    return {path.name: _sha256_path(path) for path in sorted(output.iterdir()) if path.is_file() and path.name not in blocked}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize P105 isolated-local SQLite database fleet harness artifacts.")
    parser.add_argument("--seed", type=int, default=105032)
    parser.add_argument("--profile", default=PROFILE)
    parser.add_argument("--requested-seconds", type=int, default=REQUESTED_SECONDS)
    parser.add_argument("--sample-cadence-seconds", type=int, default=CADENCE_SECONDS)
    parser.add_argument("--samples-per-service", type=int, default=SAMPLES_PER_SERVICE)
    parser.add_argument("--services", type=int, default=SERVICE_COUNT)
    parser.add_argument("--heldout-services", type=int, default=HELD_OUT_COUNT)
    parser.add_argument("--shadow-services", type=int, default=SHADOW_COUNT)
    parser.add_argument("--sqlite-shards", type=int, default=SQL_SHARDS)
    parser.add_argument("--services-per-shard", type=int, default=SERVICES_PER_SHARD)
    parser.add_argument("--pool-size", type=int, default=POOL_SIZE)
    parser.add_argument("--max-live-sqlite-connections", type=int, default=MAX_LIVE_SQLITE_CONNECTIONS)
    parser.add_argument("--heartbeat-sql-transaction-interval-seconds", type=int, default=HEARTBEAT_INTERVAL_SECONDS)
    parser.add_argument("--max-sql-transaction-cycles", type=int, default=MAX_SQL_TRANSACTION_CYCLES)
    parser.add_argument("--worker-threads", type=int, default=WORKER_THREADS)
    parser.add_argument("--max-memory-mib", type=int, default=1024)
    parser.add_argument("--max-sqlite-files-wal-mib", type=int, default=512)
    parser.add_argument("--max-output-mib", type=int, default=256)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", default="isolated-local")
    parser.add_argument("--created-at", default="2024-03-09T16:25:00Z")
    parser.add_argument("--expect-runtime-attestation-kind", default=RUNTIME_KIND)
    parser.add_argument("--expect-no-production-authority", action="store_true")
    parser.add_argument("--test-fast-diagnostic", action="store_true")
    parser.add_argument("--test-fast-runtime", action="store_true", dest="test_fast_diagnostic")
    parser.add_argument("--diagnostic-samples", type=int, default=2)
    parser.add_argument("--inject-telemetry-loss-at-sample", type=int)
    return parser


def _validate_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if args.mode != "isolated-local":
        errors.append("mode_not_isolated_local")
    if args.expect_runtime_attestation_kind != RUNTIME_KIND:
        errors.append("runtime_attestation_kind_mismatch")
    if not args.expect_no_production_authority:
        errors.append("production_authority_guard_missing")
    if args.profile != PROFILE:
        errors.append("database_fleet_profile_required")
    if args.requested_seconds != REQUESTED_SECONDS:
        errors.append("requested_seconds_not_frozen_3600")
    if args.sample_cadence_seconds != CADENCE_SECONDS:
        errors.append("sample_cadence_seconds_not_frozen_5")
    if args.samples_per_service != SAMPLES_PER_SERVICE:
        errors.append("samples_per_service_not_frozen_720")
    if args.services != SERVICE_COUNT:
        errors.append("service_count_not_frozen_256")
    if args.heldout_services != HELD_OUT_COUNT:
        errors.append("heldout_service_count_not_frozen_128")
    if args.shadow_services != SHADOW_COUNT:
        errors.append("shadow_service_count_not_frozen_128")
    if args.sqlite_shards != SQL_SHARDS:
        errors.append("sqlite_shard_count_not_frozen_64")
    if args.services_per_shard != SERVICES_PER_SHARD:
        errors.append("services_per_shard_not_frozen_4")
    if args.pool_size != POOL_SIZE:
        errors.append("pool_size_not_frozen_3")
    if args.max_live_sqlite_connections != MAX_LIVE_SQLITE_CONNECTIONS:
        errors.append("max_live_sqlite_connections_not_frozen_192")
    if args.heartbeat_sql_transaction_interval_seconds != HEARTBEAT_INTERVAL_SECONDS:
        errors.append("heartbeat_sql_transaction_interval_not_frozen_30")
    if args.max_sql_transaction_cycles != MAX_SQL_TRANSACTION_CYCLES:
        errors.append("max_sql_transaction_cycles_not_frozen_40000")
    if args.worker_threads != WORKER_THREADS:
        errors.append("worker_threads_not_frozen_64")
    if args.max_memory_mib != 1024:
        errors.append("max_memory_mib_not_frozen_1024")
    if args.max_sqlite_files_wal_mib != 512:
        errors.append("max_sqlite_files_wal_mib_not_frozen_512")
    if args.max_output_mib != 256:
        errors.append("max_output_mib_not_frozen_256")
    if args.diagnostic_samples < 2:
        errors.append("diagnostic_samples_must_allow_adjacent_interval")
    return errors


def _materialize_runtime(
    args: argparse.Namespace,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    services = [_service_id(index) for index in range(SERVICE_COUNT)]
    schedule = _build_schedule()
    profile_config_hash = _profile_hash(PROFILE)
    pools = _build_shards(args.output_dir)
    sample_count = args.diagnostic_samples if args.test_fast_diagnostic else SAMPLES_PER_SERVICE
    sampled_ordinals: set[int] = set()
    telemetry: list[dict[str, Any]] = []
    raw_samples: dict[int, list[dict[str, Any]]] = {index: [] for index in range(SERVICE_COUNT)}
    raw_heartbeat_observations: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    monotonic_started_ns = time.monotonic_ns()
    cleanup_complete = False

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKER_THREADS) as executor:
            for sample_ordinal in range(sample_count):
                sample_started_monotonic = time.monotonic()
                sample_monotonic_ns = time.monotonic_ns()
                sample_offset_seconds = sample_ordinal * CADENCE_SECONDS
                sampled_ordinals.add(sample_ordinal)
                heartbeat_results_by_service: dict[str, dict[str, Any]] = {}
                runtime_service_indexes = _runtime_service_indexes(sample_offset_seconds, schedule)
                if runtime_service_indexes:
                    heartbeat_results = _run_sample(
                        executor=executor,
                        pools=pools,
                        sample_ordinal=sample_ordinal,
                        sample_offset_seconds=sample_offset_seconds,
                        schedule=schedule,
                        service_indexes=runtime_service_indexes,
                    )
                    heartbeat_results_by_service = {str(result["service_id"]): result for result in heartbeat_results}
                    raw_heartbeat_observations.extend(heartbeat_results[: min(16, len(heartbeat_results))])

                if args.inject_telemetry_loss_at_sample == sample_ordinal:
                    validation_errors.append("telemetry_loss")
                    continue

                for service_index, service_id in enumerate(services):
                    shard = pools[service_index // SERVICES_PER_SHARD]
                    heartbeat_result = heartbeat_results_by_service.get(service_id)
                    heartbeat_observation_age_seconds = 0 if heartbeat_result is not None else None
                    source_window_id = _source_window_id(service_index, sample_ordinal)
                    raw_sample = {
                        "monotonic_ns": sample_monotonic_ns,
                        "sample_offset_seconds": sample_offset_seconds,
                        "sample_ordinal": sample_ordinal,
                        "service_id": service_id,
                        "source_window_id": source_window_id,
                    }
                    raw_samples[service_index].append(raw_sample)
                    telemetry.append(
                        _telemetry_row(
                            service_index=service_index,
                            sample_ordinal=sample_ordinal,
                            sample_offset_seconds=sample_offset_seconds,
                            sample_monotonic_ns=sample_monotonic_ns,
                            heartbeat_result=heartbeat_result,
                            heartbeat_observation_age_seconds=heartbeat_observation_age_seconds,
                            partition_id=_split_for_index(service_index),
                            shard=shard,
                        )
                    )

                if sample_ordinal + 1 < sample_count:
                    remaining = CADENCE_SECONDS - (time.monotonic() - sample_started_monotonic)
                    if remaining > 0:
                        time.sleep(remaining)
    finally:
        cleanup_complete = all(pool.close() for pool in pools.values())

    monotonic_finished_ns = time.monotonic_ns()
    if not cleanup_complete:
        validation_errors.append("sqlite_pool_cleanup_incomplete")

    total_cycles = sum(pool.stats.transaction_cycles for pool in pools.values())
    if total_cycles > MAX_SQL_TRANSACTION_CYCLES:
        validation_errors.append("sql_transaction_cycle_bound_breach")
    if any(pool.stats.sql_errors for pool in pools.values()):
        validation_errors.append("sqlite_sql_error")
    if len(telemetry) != SERVICE_COUNT * sample_count and "telemetry_loss" not in validation_errors:
        validation_errors.append("telemetry_loss")
    if args.test_fast_diagnostic:
        validation_errors.append("fast_diagnostic_non_counting")

    raw_adjacent_deltas = []
    for samples in raw_samples.values():
        for left, right in zip(samples, samples[1:], strict=False):
            raw_adjacent_deltas.append(round((right["monotonic_ns"] - left["monotonic_ns"]) / 1_000_000_000, 6))
        break

    canonical_segments = _canonical_segments(raw_samples, args.test_fast_diagnostic)
    observed_seconds_by_split = Counter(
        {
            "held_out": 0,
            "real_derived_shadow": 0,
        }
    )
    for segment in canonical_segments:
        observed_seconds_by_split[str(segment["split"])] += int(segment["conservative_duration_seconds"])
    family_seconds = {"database": int(sum(observed_seconds_by_split.values()))}
    partitions = _partitions_payload(services)
    private_ledger = _private_ledger(schedule, sampled_ordinals, profile_config_hash)
    coverage = {
        "canonical_segments": canonical_segments,
        "coverage_source": "receipt_bound_adjacent_monotonic_samples",
        "diagnostic_only": bool(args.test_fast_diagnostic),
        "family_seconds": family_seconds,
        "full_profile_theoretical_bounds": _full_profile_bounds(),
        "legacy_created_at_tick_seconds_coverage": False,
        "observed_seconds_by_split": dict(observed_seconds_by_split),
        "release_floor_credit_seconds": 0 if args.test_fast_diagnostic or validation_errors else family_seconds["database"],
        "rejects": [
            "created_at_plus_tick_seconds",
            "fixed_duration_constants",
            "accelerated_logical_clock",
            "row_count_as_duration",
            "padded_intervals",
        ],
        "requested_duration_substitutes_for_observed_duration": False,
        "schema_version": "p105.database.fleet.coverage.v1",
    }
    raw_attestation = {
        "adjacent_deltas_seconds": raw_adjacent_deltas,
        "capability": "sqlite3_bounded_shard_pool",
        "heartbeat_observation_sample": raw_heartbeat_observations,
        "kind": RUNTIME_KIND,
        "monotonic_finished_ns": monotonic_finished_ns,
        "monotonic_started_ns": monotonic_started_ns,
        "process_id": os.getpid(),
        "raw_sample_count": sum(len(samples) for samples in raw_samples.values()),
        "sample_monotonic_observations": [sample for samples in raw_samples.values() for sample in samples],
    }
    resource_observations = {
        "cleanup_complete": cleanup_complete,
        "live_sqlite_connection_cap": MAX_LIVE_SQLITE_CONNECTIONS,
        "peak_checked_out_connections_per_shard": max(pool.stats.checked_out_peak for pool in pools.values()),
        "sqlite_shard_files": SQL_SHARDS,
        "sql_transaction_cycles": total_cycles,
    }
    status = {
        "locked": bool(validation_errors and not (args.test_fast_diagnostic and validation_errors == ["fast_diagnostic_non_counting"])),
        "release_counting": False if args.test_fast_diagnostic or validation_errors else None,
        "runtime_qualification_eligible": not args.test_fast_diagnostic and not validation_errors,
        "validation_error_codes": sorted(set(validation_errors)),
    }
    return telemetry, partitions, private_ledger, coverage, raw_attestation, resource_observations, status


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    errors = _validate_args(args)
    if errors:
        sys.stderr.write(json.dumps({"error": "p105_database_fleet_harness_fail_closed", "validation_error_codes": errors}, sort_keys=True) + "\n")
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    telemetry, partitions, private_ledger, coverage, raw_attestation, resource_observations, status = _materialize_runtime(args)

    _write_json(args.output_dir / PRE_LABEL_PARTITIONS, partitions)
    _write_jsonl(args.output_dir / PUBLIC_TELEMETRY, telemetry)
    _write_json(args.output_dir / PRIVATE_LEDGER, private_ledger)
    _write_json(args.output_dir / COVERAGE, coverage)
    _write_json(args.output_dir / RAW_ATTESTATION, raw_attestation)

    canonical_argv = _canonical_argv(sys.argv if argv is None else [sys.argv[0], *argv])
    artifact_hashes = _artifact_hashes(args.output_dir, exclude={MANIFEST, PROVENANCE_HASHES, RAW_ATTESTATION})
    manifest = {
        "adapter_key": ADAPTER_KEY,
        "adapter_version": ADAPTER_VERSION,
        "artifact_hashes": artifact_hashes,
        "artifact_paths": {
            "coverage": COVERAGE,
            "partitions": PRE_LABEL_PARTITIONS,
            "private_injection_ledger": PRIVATE_LEDGER,
            "provenance_hashes": PROVENANCE_HASHES,
            "public_telemetry": PUBLIC_TELEMETRY,
        },
        "authority": {
            "action_executed": False,
            "action_plan_created": False,
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
            "enabled": bool(args.test_fast_diagnostic),
            "runtime_qualification_eligible": False if args.test_fast_diagnostic else status["runtime_qualification_eligible"],
        },
        "heartbeat_sql_transaction_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        "implementation_guard": {
            "uses_actual_sqlite_files": True,
            "uses_bounded_queue": True,
            "uses_bounded_semaphore": True,
            "uses_in_memory_database": False,
            "uses_mocked_connection": False,
            "uses_precomputed_row_generator": False,
        },
        "mode": args.mode,
        "partitions": {
            "held_out": [_service_id(index) for index in range(HELD_OUT_COUNT)],
            "real_derived_shadow": [_service_id(index) for index in range(HELD_OUT_COUNT, SERVICE_COUNT)],
        },
        "profile": PROFILE,
        "profile_config_hash": _profile_hash(PROFILE),
        "program_version": PROGRAM_VERSION,
        "public_telemetry_row_count": len(telemetry),
        "requested_seconds": REQUESTED_SECONDS,
        "resource_limits": {
            "max_live_sqlite_connections": MAX_LIVE_SQLITE_CONNECTIONS,
            "max_memory_bytes": 1024 * 1024 * 1024,
            "max_memory_mib": 1024,
            "max_output_mib": 256,
            "max_sql_transaction_cycles": MAX_SQL_TRANSACTION_CYCLES,
            "pool_size": POOL_SIZE,
            "process_memory_bytes": 1024 * 1024 * 1024,
            "required_sql_operations": ["insert", "select", "update"],
            "services_per_shard": SERVICES_PER_SHARD,
            "sqlite_files_and_wal_bytes": 512 * 1024 * 1024,
            "sqlite_files_and_wal_mib": 512,
            "sqlite_shard_files": SQL_SHARDS,
            "worker_threads": WORKER_THREADS,
        },
        "resource_observations": resource_observations,
        "runtime_attestation": {
            "capability": "sqlite3_bounded_shard_pool",
            "kind": RUNTIME_KIND,
        },
        "runtime_candidate_status": status,
        "sample_cadence_seconds": CADENCE_SECONDS,
        "sample_offsets_seconds": list(range(0, REQUESTED_SECONDS, CADENCE_SECONDS)),
        "samples_per_service": SAMPLES_PER_SERVICE,
        "schema_version": SCHEMA_VERSION,
        "service_count": SERVICE_COUNT,
        "services": [_service_id(index) for index in range(SERVICE_COUNT)],
        "source_family": "database",
    }
    _write_json(args.output_dir / MANIFEST, manifest)
    provenance = {
        "artifact_hashes": _artifact_hashes(args.output_dir, exclude={PROVENANCE_HASHES}),
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": manifest["command_argv_sha256"],
        "hash_algorithm": "sha256",
        "program_version": PROGRAM_VERSION,
        "schema_version": "p105.database.fleet.provenance_hashes.v1",
    }
    _write_json(args.output_dir / PROVENANCE_HASHES, provenance)
    print(json.dumps({"manifest_path": str(args.output_dir / MANIFEST), "telemetry_rows": len(telemetry)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
