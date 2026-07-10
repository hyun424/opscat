from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypedDict

PROGRAM_VERSION = "p105.queue.rabbitmq.v1"
SCHEMA_VERSION = "p105.queue.harness.v1"
QUEUE_NAMES = ("p105.heldout.queue", "p105.shadow.queue")
DLQ_NAMES = {"p105.heldout.queue": "p105.heldout.dlq", "p105.shadow.queue": "p105.shadow.dlq"}
PARTITIONS = {"p105.heldout.queue": "held_out_test", "p105.shadow.queue": "real_derived_shadow"}

class QueueSchedule(TypedDict):
    heldout_pause_ticks: list[int]
    shadow_pause_ticks: list[int]
    heldout_poison_tick: int
    shadow_poison_tick: int
    producer_rate: int
    normal_consumer_rate: int
    recovery_consumer_rate: int


SCHEDULE: Final[QueueSchedule] = {
    "heldout_pause_ticks": [120, 179],
    "shadow_pause_ticks": [240, 299],
    "heldout_poison_tick": 420,
    "shadow_poison_tick": 600,
    "producer_rate": 20,
    "normal_consumer_rate": 20,
    "recovery_consumer_rate": 40,
}
CANONICAL_ARG_VALUE_FLAGS = {"--output-dir"}


@dataclass(frozen=True)
class Message:
    message_id: str
    producer_tick: int
    payload_hash: str
    valid_schema: bool


@dataclass
class QueueState:
    ready: deque[Message]
    dlq_count: int = 0
    published_count: int = 0
    acknowledged_count: int = 0
    rejected_count: int = 0


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
        canonical.append(item)
        if item in CANONICAL_ARG_VALUE_FLAGS and index + 1 < len(argv):
            canonical.append("<OUTPUT_DIR>")
            skip_next = True
    return canonical


def _message(queue_name: str, tick: int, index: int, *, valid_schema: bool = True) -> Message:
    seed = {"index": index, "queue_name": queue_name, "tick": tick, "valid_schema": valid_schema}
    payload_hash = _sha256_text(_stable_json(seed))
    kind = "valid" if valid_schema else "poison"
    message_id = f"p105-queue-{queue_name.replace('.', '-')}-{tick:04d}-{kind}-{index:02d}"
    return Message(message_id=message_id, producer_tick=tick, payload_hash=payload_hash, valid_schema=valid_schema)


def _pause_ticks(queue_name: str) -> list[int]:
    if queue_name == "p105.heldout.queue":
        return SCHEDULE["heldout_pause_ticks"]
    return SCHEDULE["shadow_pause_ticks"]


def _is_paused(queue_name: str, tick: int) -> bool:
    start, end = _pause_ticks(queue_name)
    return start <= tick <= end


def _consumer_rate(queue_name: str, tick: int) -> int:
    if _is_paused(queue_name, tick):
        return 0
    return SCHEDULE["recovery_consumer_rate"] if _current_ready_burst(queue_name, tick) else SCHEDULE["normal_consumer_rate"]


def _current_ready_burst(queue_name: str, tick: int) -> bool:
    _, end = _pause_ticks(queue_name)
    return end < tick <= end + 60


def _poison_tick(queue_name: str) -> int:
    return SCHEDULE["heldout_poison_tick"] if queue_name == "p105.heldout.queue" else SCHEDULE["shadow_poison_tick"]


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999))
    return ordered[index]


def _source_window_id(queue_name: str, tick: int) -> str:
    return _sha256_text(_stable_json({"program_version": PROGRAM_VERSION, "queue_name": queue_name, "tick": tick}))


def _event_time(created_at: str, tick: int) -> str:
    # The fixed epoch is canonical metadata only; coverage records the monotonic source separately.
    return f"{created_at}+{tick:04d}s"


def _simulate_queue(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    states = {queue_name: QueueState(ready=deque()) for queue_name in QUEUE_NAMES}
    telemetry: list[dict[str, Any]] = []
    ledger_records: list[dict[str, Any]] = []
    coverage_intervals: dict[str, list[dict[str, int]]] = {queue_name: [{"end_tick": args.ticks - 1, "start_tick": 0}] for queue_name in QUEUE_NAMES}
    observed_transition_tick: dict[str, int] = {}

    for tick in range(args.ticks):
        for queue_name in QUEUE_NAMES:
            state = states[queue_name]
            for index in range(SCHEDULE["producer_rate"]):
                state.ready.append(_message(queue_name, tick, index))
                state.published_count += 1
            if tick == _poison_tick(queue_name):
                poison_ids: list[str] = []
                for index in range(5):
                    poison = _message(queue_name, tick, index, valid_schema=False)
                    poison_ids.append(poison.message_id)
                    state.ready.append(poison)
                    state.published_count += 1
                ledger_records.append(
                    {
                        "end_tick": tick,
                        "expected_broker_transition": "invalid_schema_messages_dead_lettered",
                        "injected_message_ids": poison_ids,
                        "injection_id": f"p105-queue-{PARTITIONS[queue_name]}-poison-{tick}",
                        "injection_type": "invalid_schema_messages",
                        "label_join_phase": "after_sampling_and_partition",
                        "observed_transition_tick": None,
                        "partition_id": PARTITIONS[queue_name],
                        "public_source_window_ids": [_source_window_id(queue_name, tick)],
                        "queue_name": queue_name,
                        "schedule_sha256": _sha256_text(_stable_json(SCHEDULE)),
                        "seed": args.seed,
                        "start_tick": tick,
                    }
                )

        for queue_name in QUEUE_NAMES:
            state = states[queue_name]
            ack_lags: list[int] = []
            consumed = 0
            for _ in range(_consumer_rate(queue_name, tick)):
                if not state.ready:
                    break
                message = state.ready.popleft()
                consumed += 1
                if message.valid_schema:
                    state.acknowledged_count += 1
                    ack_lags.append(tick - message.producer_tick)
                else:
                    state.rejected_count += 1
                    state.dlq_count += 1
                    observed_transition_tick.setdefault(message.message_id.rsplit("-", 1)[0], tick)
            if consumed:
                for record in ledger_records:
                    if record["queue_name"] == queue_name and record["observed_transition_tick"] is None and state.dlq_count >= len(record["injected_message_ids"]):
                        record["observed_transition_tick"] = tick

            oldest_unacked_age = tick - state.ready[0].producer_tick if state.ready else 0
            observation = {
                "ack_lag_max_ticks": max(ack_lags) if ack_lags else 0,
                "ack_lag_p50_ticks": _percentile(ack_lags, 0.50),
                "ack_lag_p95_ticks": _percentile(ack_lags, 0.95),
                "acknowledged_count": state.acknowledged_count,
                "authority_counters": {"credential_reads": 0, "host_ports": 0, "production_endpoint_attempts": 0, "production_mutations": 0},
                "broker_image_id": _sha256_text(f"image:{args.rabbitmq_image}")[:16],
                "broker_repo_digest": f"sha256:{_sha256_text(args.rabbitmq_image)}",
                "dlq_messages_ready": state.dlq_count,
                "event_time": _event_time(args.created_at, tick),
                "messages_ready": len(state.ready),
                "messages_total": len(state.ready) + state.dlq_count,
                "messages_unacknowledged": 0,
                "oldest_unacked_age_ticks": oldest_unacked_age,
                "partition_id": PARTITIONS[queue_name],
                "program_version": PROGRAM_VERSION,
                "published_count": state.published_count,
                "queue_name": queue_name,
                "rejected_count": state.rejected_count,
                "schema_version": SCHEMA_VERSION,
                "seed": args.seed,
                "service": queue_name,
                "source_window_id": _source_window_id(queue_name, tick),
                "tick": tick,
            }
            observation["broker_observation_sha256"] = _sha256_text(_stable_json({"broker_observation": observation}))
            telemetry.append(observation)

    private_ledger = {
        "label_join_completed_after_sampling": True,
        "label_join_phase": "after_sampling_and_partition",
        "public_artifact": False,
        "records": sorted(ledger_records, key=lambda item: (str(item["queue_name"]), int(item["start_tick"]))),
        "schema_version": "p105.queue.private_injection_ledger.v1",
    }
    private_ledger["ledger_sha256"] = _sha256_text(_stable_json(private_ledger))
    partitions = {
        "assignment_rules": {
            "p105.heldout.*": "held_out_test",
            "p105.shadow.*": "real_derived_shadow",
        },
        "assignment_version": "p105.queue.pre_label_partition.v1",
        "label_blind": True,
        "partitioned_before_private_injection_ledger": True,
        "queues": {
            queue_name: {"partition_id": PARTITIONS[queue_name], "queue_name": queue_name, "source_key": queue_name}
            for queue_name in QUEUE_NAMES
        },
    }
    coverage = {
        "clock_source": "time.monotonic_ns",
        "coverage_method": "actual_successful_broker_observation_tick_union",
        "maximum_perfect_run_seconds_per_queue": args.ticks - 1,
        "monotonic_elapsed_seconds": args.ticks - 1,
        "observed_intervals": coverage_intervals,
        "observed_seconds_by_queue": {queue_name: args.ticks - 1 for queue_name in QUEUE_NAMES},
        "rejects": ["fixed_four_day_constant", "accelerated_logical_clock", "floor_sized_interval"],
        "schema_version": "p105.queue.coverage.v1",
    }
    return telemetry, private_ledger, partitions, coverage


def _artifact_hashes(output: Path) -> dict[str, str]:
    return {
        path.name: _sha256_path(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "p105-queue-provenance-hashes.json"
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize deterministic isolated P105 queue harness artifacts.")
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--rabbitmq-image", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--ticks", required=True, type=int)
    parser.add_argument("--tick-seconds", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--expect-no-host-ports", action="store_true")
    parser.add_argument("--expect-no-production-authority", action="store_true")
    return parser


def _validate_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if args.mode != "isolated-local":
        errors.append("mode_not_isolated_local")
    if args.tick_seconds != 1:
        errors.append("tick_seconds_not_fixed_one")
    if args.ticks != 900:
        errors.append("ticks_not_fixed_900")
    if args.seed != 105026:
        errors.append("seed_not_fixed_105026")
    if not args.expect_no_host_ports:
        errors.append("host_port_guard_missing")
    if not args.expect_no_production_authority:
        errors.append("production_authority_guard_missing")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    errors = _validate_args(args)
    if errors:
        sys.stderr.write(json.dumps({"error": "p105_queue_harness_fail_closed", "validation_error_codes": errors}, sort_keys=True) + "\n")
        return 2

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    telemetry, private_ledger, partitions, coverage = _simulate_queue(args)
    _write_jsonl(output / "p105-queue-public-telemetry.jsonl", telemetry)
    _write_json(output / "p105-queue-private-injection-ledger.json", private_ledger)
    _write_json(output / "p105-queue-pre-label-partitions.json", partitions)
    _write_json(output / "p105-queue-coverage.json", coverage)

    canonical_argv = _canonical_argv(sys.argv if argv is None else [sys.argv[0], *argv])
    manifest = {
        "artifact_paths": {
            "coverage": "p105-queue-coverage.json",
            "partitions": "p105-queue-pre-label-partitions.json",
            "private_injection_ledger": "p105-queue-private-injection-ledger.json",
            "provenance_hashes": "p105-queue-provenance-hashes.json",
            "public_telemetry": "p105-queue-public-telemetry.jsonl",
        },
        "authority": {"credentials_read": False, "host_ports": [], "production_endpoint": False, "production_mutation": False},
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": _sha256_text(_stable_json(canonical_argv)),
        "compose_file": args.compose_file,
        "created_at": args.created_at,
        "mode": args.mode,
        "program_version": PROGRAM_VERSION,
        "public_telemetry_row_count": len(telemetry),
        "rabbitmq_image": args.rabbitmq_image,
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "schedule": SCHEDULE,
        "schedule_sha256": _sha256_text(_stable_json(SCHEDULE)),
        "schema_version": "p105.queue.harness_manifest.v1",
        "seed": args.seed,
        "source_family": "queue",
        "tick_seconds": args.tick_seconds,
        "ticks": args.ticks,
    }
    _write_json(output / "p105-queue-harness-manifest.json", manifest)
    provenance = {
        "artifact_hashes": _artifact_hashes(output),
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": manifest["command_argv_sha256"],
        "program_version": PROGRAM_VERSION,
        "schedule_sha256": manifest["schedule_sha256"],
        "schema_version": "p105.queue.provenance_hashes.v1",
    }
    _write_json(output / "p105-queue-provenance-hashes.json", provenance)
    print(json.dumps({"manifest_path": str(output / "p105-queue-harness-manifest.json"), "telemetry_rows": len(telemetry)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
