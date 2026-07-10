from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

PROFILE_ID: Final = "p105.actual-fleet-soak.256x1h.v1"
DIAGNOSTIC_PROFILE_ID: Final = "p105.queue-fleet.diagnostic.fast.v1"
SCHEMA_VERSION: Final = "p105.queue.fleet_harness.v1"
ADAPTER_KEY: Final = "queue_fleet"
ADAPTER_VERSION: Final = "p105.adapter.rabbitmq-fleet-harness.v1"
RABBITMQ_IMAGE: Final = "rabbitmq:3.13-management-alpine"
SERVICE_COUNT: Final = 256
DLQ_COUNT: Final = 256
CADENCE_SECONDS: Final = 5
REQUESTED_RUNTIME_SECONDS: Final = 3600
SCHEDULED_SAMPLES_PER_SERVICE: Final = 720
HEARTBEAT_PERIOD_SECONDS: Final = 30
MAX_MESSAGES: Final = 35_872
MAX_MANAGEMENT_HTTP_CALLS: Final = 80_000
MAX_OUTPUT_MIB: Final = 256
CANONICAL_ARG_VALUE_FLAGS: Final = {"--output-dir"}
QUEUE_KINDS: Final = ("consumer_slowdown", "consumer_pause", "poison_dead_letter", "bounded_producer_burst")


@dataclass(frozen=True)
class CommandAttestation:
    step: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


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


def _service_id(index: int) -> str:
    return f"p105.fleet.queue.{index:03d}"


def _queue_name(index: int) -> str:
    return f"p105-fleet-q-{index:03d}"


def _dlq_name(index: int) -> str:
    return f"p105-fleet-dlq-{index:03d}"


def _split_for_service(index: int) -> str:
    return "held_out" if index < 128 else "real_derived_shadow"


def _source_window_id(split: str, service_index: int, ordinal: int) -> str:
    return f"p105-fleet-queue-{split}-svc{service_index:03d}-sample{ordinal:03d}"


def _sample_offsets(sample_count: int) -> list[int]:
    return [index * CADENCE_SECONDS for index in range(sample_count)]


def _public_profile_hash(profile_id: str) -> str:
    return _sha256_text(_stable_json({"cadence_seconds": CADENCE_SECONDS, "profile": profile_id, "services": [_service_id(index) for index in range(SERVICE_COUNT)]}))


def _fleet_schedule() -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    for split, base in (("held_out", 0), ("real_derived_shadow", 128)):
        for group in range(8):
            start = 900 + 30 * group
            failure = 3300 + 30 * group
            service_indexes = [base + offset for offset in range(4 * group, 4 * group + 4)]
            start_ordinal = start // CADENCE_SECONDS
            end_ordinal = (start + 300) // CADENCE_SECONDS
            schedule.append(
                {
                    "affected_services": [_service_id(index) for index in service_indexes],
                    "bound_public_source_window_ids": [
                        _source_window_id(split, service_index, ordinal)
                        for service_index in service_indexes
                        for ordinal in range(start_ordinal, end_ordinal + 1)
                    ],
                    "group": f"g{group:02d}",
                    "incident_group_id": f"p105-fleet-queue-{split}-g{group:02d}",
                    "kind": QUEUE_KINDS[group % 4],
                    "kind_index": group % 4,
                    "lead_time_minutes": {"maximum": 40, "minimum": 35},
                    "positive_precursor_end_offset_seconds": start + 300,
                    "positive_precursor_start_offset_seconds": start,
                    "private_failure_offset_seconds": failure,
                    "split": split,
                }
            )
    return schedule


def _affected_incidents_by_service() -> dict[int, list[dict[str, Any]]]:
    incidents: dict[int, list[dict[str, Any]]] = {index: [] for index in range(SERVICE_COUNT)}
    for group in _fleet_schedule():
        for service_id in group["affected_services"]:
            index = int(str(service_id).rsplit(".", 1)[1])
            incidents[index].append(group)
    return incidents


def _message_count_for_service(service_index: int, offset_seconds: int, incidents_by_service: dict[int, list[dict[str, Any]]]) -> tuple[int, int]:
    if offset_seconds % HEARTBEAT_PERIOD_SECONDS != 0:
        return 0, 0
    valid_messages = 0
    invalid_messages = 0
    for incident in incidents_by_service[service_index]:
        start = int(incident["positive_precursor_start_offset_seconds"])
        if offset_seconds == start and incident["kind"] == "poison_dead_letter":
            invalid_messages += 1
        elif offset_seconds == start:
            valid_messages += 1
    return valid_messages, invalid_messages


def _public_config(profile_id: str, sample_count: int, project_name: str) -> dict[str, Any]:
    services = [_service_id(index) for index in range(SERVICE_COUNT)]
    return {
        "adapter_key": ADAPTER_KEY,
        "adapter_version": ADAPTER_VERSION,
        "authority": {
            "action_execution": False,
            "action_plan": False,
            "credentials_read": False,
            "external_broker_endpoint": False,
            "host_ports": [],
            "production_mutation": False,
            "release_counting_authority": False,
        },
        "cleanup": {
            "cleanup_scope": "isolated_run_container_and_volume_only",
            "container_removed": False,
            "isolated_docker_project": project_name,
            "volume_removed": False,
        },
        "management_plan": {
            "bulk_broker_state_observation_per_sample": True,
            "maximum_concurrent_management_operations": 8,
            "maximum_management_http_calls": MAX_MANAGEMENT_HTTP_CALLS,
        },
        "message_plan": {
            "heartbeat_period_seconds": HEARTBEAT_PERIOD_SECONDS,
            "maximum_consumed_or_rejected_messages": MAX_MESSAGES,
            "maximum_published_messages": MAX_MESSAGES,
            "normal_heartbeat_messages_per_service": 0,
            "poison_invalid_messages_per_affected_service": 1,
            "precursor_seed_messages_per_affected_service": 1,
            "publish_mode": "one_shot_at_private_precursor_start_then_observe_broker_state",
        },
        "partitions": {
            "assigned_before_private_schedule_loading": True,
            "held_out": services[:128],
            "real_derived_shadow": services[128:],
        },
        "profile": {
            "hash": _public_profile_hash(profile_id),
            "hash_phase": "before_private_schedule_loading",
            "id": profile_id,
        },
        "queues": {
            "dead_letter_queues": [_dlq_name(index) for index in range(DLQ_COUNT)],
            "queues": [_queue_name(index) for index in range(SERVICE_COUNT)],
        },
        "resource_maxima": {
            "broker_disk_mib": 512,
            "container_memory_mib": 1024,
            "maximum_total_queues": SERVICE_COUNT + DLQ_COUNT,
            "output_artifact_mib": MAX_OUTPUT_MIB,
        },
        "runtime": {
            "broker_health_observed": False,
            "in_memory_queue_simulation": False,
            "isolated_run_container": True,
            "rabbitmq_image": RABBITMQ_IMAGE,
            "kind": "actual_rabbitmq_docker",
        },
        "sample_plan": {
            "cadence_seconds": CADENCE_SECONDS,
            "offsets_seconds": _sample_offsets(sample_count),
            "requested_runtime_seconds": REQUESTED_RUNTIME_SECONDS if profile_id == PROFILE_ID else sample_count * CADENCE_SECONDS,
            "scheduled_samples_per_service": sample_count,
        },
        "schema_version": SCHEMA_VERSION,
        "services": services,
    }


def _compose_file(output_dir: Path, image: str) -> Path:
    compose = output_dir / "p105-queue-fleet-rabbitmq.compose.yml"
    compose.write_text(
        "\n".join(
            [
                "services:",
                "  rabbitmq:",
                f"    image: {image}",
                "    mem_limit: 1024m",
                "    healthcheck:",
                "      test: ['CMD', 'rabbitmq-diagnostics', '-q', 'ping']",
                "      interval: 5s",
                "      timeout: 5s",
                "      retries: 30",
                "    volumes:",
                "      - rabbitmq-data:/var/lib/rabbitmq",
                "volumes:",
                "  rabbitmq-data:",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return compose


def _compose_command(compose_file: Path, project_name: str, args: list[str]) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file), "-p", project_name, *args]


def _rabbitmqadmin_command(compose_file: Path, project_name: str, args: list[str]) -> list[str]:
    return _compose_command(
        compose_file,
        project_name,
        ["exec", "-T", "rabbitmq", "rabbitmqadmin", "--vhost=/", "--format=raw_json", *args],
    )


def _run_command(command: list[str], *, attestations: list[CommandAttestation], step: str, input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, input=input_text, text=True, capture_output=True, check=False, timeout=timeout)
    attestations.append(CommandAttestation(command=command, returncode=completed.returncode, stderr=completed.stderr, stdout=completed.stdout, step=step))
    if completed.returncode != 0:
        raise RuntimeError(
            _stable_json(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-2000:],
                    "step": step,
                    "stdout": completed.stdout[-2000:],
                }
            )
        )
    return completed


def _wait_for_broker(compose_file: Path, project_name: str, attestations: list[CommandAttestation]) -> None:
    last_error = ""
    for attempt in range(60):
        completed = subprocess.run(
            _compose_command(compose_file, project_name, ["exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"]),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        attestations.append(
            CommandAttestation(
                command=_compose_command(compose_file, project_name, ["exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"]),
                returncode=completed.returncode,
                stderr=completed.stderr,
                stdout=completed.stdout,
                step=f"rabbitmq.ping.{attempt:02d}",
            )
        )
        if completed.returncode == 0:
            return
        last_error = completed.stderr or completed.stdout
        time.sleep(1)
    raise RuntimeError(f"rabbitmq_not_ready:{last_error[-500:]}")


def _docker_runtime_evidence(compose_file: Path, project_name: str, attestations: list[CommandAttestation]) -> dict[str, Any]:
    container_id = _run_command(
        _compose_command(compose_file, project_name, ["ps", "-q", "rabbitmq"]),
        step="docker.compose.ps.rabbitmq",
        attestations=attestations,
    ).stdout.strip()
    if not container_id:
        raise RuntimeError("rabbitmq_container_id_missing")
    inspect = _run_command(
        ["docker", "inspect", container_id],
        step="docker.inspect.rabbitmq",
        attestations=attestations,
    )
    inspected = json.loads(inspect.stdout or "[]")
    if not isinstance(inspected, list) or not inspected or not isinstance(inspected[0], dict):
        raise RuntimeError("rabbitmq_container_inspect_missing")
    networks = inspected[0].get("NetworkSettings", {}).get("Networks", {})
    if not isinstance(networks, dict) or not networks:
        raise RuntimeError("rabbitmq_docker_network_missing")
    return {
        "container_id": container_id,
        "docker_network_name": sorted(str(name) for name in networks)[0],
    }


def _declare_broker_shape(compose_file: Path, project_name: str, attestations: list[CommandAttestation]) -> int:
    management_calls = 0
    _run_command(
        _rabbitmqadmin_command(compose_file, project_name, ["declare", "exchange", "name=p105.fleet.dlx", "type=direct", "durable=false"]),
        step="rabbitmq.declare.dlx",
        attestations=attestations,
    )
    management_calls += 1
    for index in range(SERVICE_COUNT):
        dlq = _dlq_name(index)
        queue = _queue_name(index)
        _run_command(_rabbitmqadmin_command(compose_file, project_name, ["declare", "queue", f"name={dlq}", "durable=false"]), step=f"rabbitmq.declare.{dlq}", attestations=attestations)
        _run_command(
            _rabbitmqadmin_command(compose_file, project_name, ["declare", "binding", "source=p105.fleet.dlx", "destination_type=queue", f"destination={dlq}", f"routing_key={dlq}"]),
            step=f"rabbitmq.bind.{dlq}",
            attestations=attestations,
        )
        _run_command(
            _rabbitmqadmin_command(
                compose_file,
                project_name,
                [
                    "declare",
                    "queue",
                    f"name={queue}",
                    "durable=false",
                    f"arguments={_stable_json({'x-dead-letter-exchange': 'p105.fleet.dlx', 'x-dead-letter-routing-key': dlq})}",
                ],
            ),
            step=f"rabbitmq.declare.{queue}",
            attestations=attestations,
        )
        management_calls += 3
    return management_calls


def _bulk_observe(compose_file: Path, project_name: str, attestations: list[CommandAttestation]) -> list[dict[str, Any]]:
    completed = _run_command(
        _rabbitmqadmin_command(compose_file, project_name, ["list", "queues", "name", "messages", "messages_ready", "messages_unacknowledged"]),
        step="rabbitmq.observe.bulk_queues",
        attestations=attestations,
        timeout=120,
    )
    rows = json.loads(completed.stdout or "[]")
    if not isinstance(rows, list):
        raise RuntimeError("rabbitmq_queue_observation_not_json_list")
    return [row for row in rows if isinstance(row, dict)]


def _bounded_broker_observation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    queue_rows = [row for row in rows if str(row.get("name", "")).startswith("p105-fleet-q-")]
    dlq_rows = [row for row in rows if str(row.get("name", "")).startswith("p105-fleet-dlq-")]
    sample = sorted(
        (
            {
                "messages": int(row.get("messages", 0)),
                "messages_ready": int(row.get("messages_ready", 0)),
                "messages_unacknowledged": int(row.get("messages_unacknowledged", 0)),
                "name": str(row.get("name", "")),
            }
            for row in rows
            if str(row.get("name", "")).startswith("p105-fleet-")
        ),
        key=lambda row: str(row["name"]),
    )[:8]
    return {
        "bounded": True,
        "dead_letter_queue_count": len(dlq_rows),
        "management_command": "rabbitmqadmin list queues name messages messages_ready messages_unacknowledged",
        "observed_queue_count": len(queue_rows),
        "sample_rows": sample,
        "truncated": len(queue_rows) + len(dlq_rows) > len(sample),
    }


def _rabbitmq_management_observed(attestations: list[CommandAttestation]) -> bool:
    return any(
        attestation.returncode == 0
        and len(attestation.command) >= 2
        and "rabbitmqadmin" in attestation.command
        and any(item in {"list", "declare", "--version"} for item in attestation.command)
        for attestation in attestations
    )


def _publish_rows(compose_file: Path, project_name: str, attestations: list[CommandAttestation], rows: list[tuple[str, dict[str, Any]]]) -> None:
    if not rows:
        return
    input_rows = "".join(f"{routing_key}\t{_stable_json(payload)}\n" for routing_key, payload in rows)
    script = (
        "while IFS='	' read -r routing_key payload; do "
        "rabbitmqadmin -q --vhost=/ publish exchange=amq.default routing_key=\"$routing_key\" payload=\"$payload\" >/dev/null; "
        "done"
    )
    _run_command(
        _compose_command(compose_file, project_name, ["exec", "-T", "rabbitmq", "sh", "-eu", "-c", script]),
        step="rabbitmq.publish.batch",
        attestations=attestations,
        input_text=input_rows,
        timeout=600,
    )


def _consume_rows(
    compose_file: Path,
    project_name: str,
    attestations: list[CommandAttestation],
    rows: list[tuple[str, int, str]],
) -> None:
    if not rows:
        return
    input_rows = "".join(f"{queue}\t{count}\t{ackmode}\n" for queue, count, ackmode in rows)
    script = (
        "while IFS='\t' read -r queue count ackmode; do "
        "rabbitmqadmin -q --vhost=/ get queue=\"$queue\" count=\"$count\" ackmode=\"$ackmode\" encoding=auto >/dev/null; "
        "done"
    )
    _run_command(
        _compose_command(compose_file, project_name, ["exec", "-T", "rabbitmq", "sh", "-eu", "-c", script]),
        step="rabbitmq.consume.batch",
        attestations=attestations,
        input_text=input_rows,
        timeout=120,
    )


def _telemetry_row(
    service_index: int,
    sample_ordinal: int,
    *,
    broker_observed: bool,
    messages_ready: int,
    dlq_messages_ready: int,
    published_count: int,
    rejected_count: int,
) -> dict[str, Any]:
    split = _split_for_service(service_index)
    row = {
        "adapter_key": ADAPTER_KEY,
        "authority_counters": {"credential_reads": 0, "host_ports": 0, "production_endpoint_attempts": 0, "production_mutations": 0},
        "broker_observed": broker_observed,
        "dlq_messages_ready": dlq_messages_ready,
        "family": "queue",
        "messages_ready": messages_ready,
        "partition_id": split,
        "profile_id": PROFILE_ID,
        "published_count": published_count,
        "queue_name": _queue_name(service_index),
        "rejected_count": rejected_count,
        "sample_offset_seconds": sample_ordinal * CADENCE_SECONDS,
        "sample_ordinal": sample_ordinal,
        "schema_version": "p105.queue.fleet_public_telemetry.v1",
        "service": _service_id(service_index),
        "source_system": "fleet",
        "source_window_id": _source_window_id(split, service_index, sample_ordinal),
    }
    row["row_sha256"] = _sha256_text(_stable_json({"p105_queue_fleet_public_telemetry": row}))
    return row


def _raw_observation(service_index: int, sample_ordinal: int, monotonic_ns: int, queue_counts: dict[str, Any]) -> dict[str, Any]:
    split = _split_for_service(service_index)
    return {
        "monotonic_ns": monotonic_ns,
        "queue_counts": queue_counts,
        "sample_ordinal": sample_ordinal,
        "service": _service_id(service_index),
        "source_window_id": _source_window_id(split, service_index, sample_ordinal),
    }


def _coverage_segments(raw_observations: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for service_index, rows in sorted(raw_observations.items()):
        if len(rows) < 2:
            continue
        current: list[dict[str, Any]] = [rows[0]]
        for previous, row in zip(rows, rows[1:], strict=False):
            delta_ns = int(row["monotonic_ns"]) - int(previous["monotonic_ns"])
            consecutive = int(row["sample_ordinal"]) == int(previous["sample_ordinal"]) + 1
            if consecutive and 4_000_000_000 <= delta_ns <= 7_500_000_000:
                current.append(row)
            else:
                segments.extend(_segment_rows(service_index, current))
                current = [row]
        segments.extend(_segment_rows(service_index, current))
    return segments


def _segment_rows(service_index: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) < 2:
        return []
    raw_elapsed_seconds = (int(rows[-1]["monotonic_ns"]) - int(rows[0]["monotonic_ns"])) / 1_000_000_000
    conservative_seconds = min((len(rows) - 1) * CADENCE_SECONDS, int(raw_elapsed_seconds // CADENCE_SECONDS) * CADENCE_SECONDS)
    if conservative_seconds <= 0:
        return []
    return [
        {
            "canonical_duration_seconds": conservative_seconds,
            "coverage_source": "receipt_bound_adjacent_monotonic_samples",
            "end_sample_ordinal": rows[-1]["sample_ordinal"],
            "end_source_window_id": rows[-1]["source_window_id"],
            "family": "queue",
            "sample_count": len(rows),
            "service": _service_id(service_index),
            "split": _split_for_service(service_index),
            "start_sample_ordinal": rows[0]["sample_ordinal"],
            "start_source_window_id": rows[0]["source_window_id"],
        }
    ]


def _materialize_fixture(sample_count: int, *, diagnostic_only: bool) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    telemetry = [
        _telemetry_row(
            service_index,
            sample_ordinal,
            broker_observed=False,
            messages_ready=0,
            dlq_messages_ready=0,
            published_count=0,
            rejected_count=0,
        )
        for sample_ordinal in range(sample_count)
        for service_index in range(SERVICE_COUNT)
    ]
    coverage = {
        "coverage_segments": [],
        "coverage_source": "not_counting_fixture_no_runtime",
        "counting_coverage_seconds": 0,
        "diagnostic_only": diagnostic_only,
        "legacy_created_at_tick_seconds_coverage": False,
        "schema_version": "p105.queue.fleet_coverage.v1",
    }
    raw_attestation = {
        "actual_runtime_executed": False,
        "authority": {"credential_reads": 0, "host_ports": [], "production_endpoint_attempts": 0, "production_mutations": 0},
        "capabilities": [],
        "commands": [],
        "fixture_only": True,
        "monotonic_finished_ns": None,
        "monotonic_started_ns": None,
        "raw_sample_observations": [],
        "schema_version": "p105.queue.fleet_raw_runtime_attestation.v1",
        "uses_in_memory_queue_simulation": False,
    }
    cleanup = {"container_removed": False, "volume_removed": False}
    return telemetry, coverage, raw_attestation, cleanup


def _materialize_actual(args: argparse.Namespace, sample_count: int, project_name: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if shutil.which("docker") is None:
        raise RuntimeError("docker_cli_not_found")
    compose_file = _compose_file(args.output_dir, args.rabbitmq_image)
    attestations: list[CommandAttestation] = []
    raw_by_service: dict[int, list[dict[str, Any]]] = {index: [] for index in range(SERVICE_COUNT)}
    telemetry: list[dict[str, Any]] = []
    incidents_by_service = _affected_incidents_by_service()
    published_by_service = {index: 0 for index in range(SERVICE_COUNT)}
    rejected_by_service = {index: 0 for index in range(SERVICE_COUNT)}
    management_calls = 0
    published_total = 0
    consumed_total = 0
    monotonic_started_ns: int | None = None
    monotonic_finished_ns: int | None = None
    docker_evidence: dict[str, Any] = {}
    broker_observation: dict[str, Any] | None = None
    cleanup = {"container_removed": False, "volume_removed": False}
    try:
        _run_command(["docker", "version", "--format", "{{json .}}"], step="docker.version", attestations=attestations)
        _run_command(_compose_command(compose_file, project_name, ["up", "-d", "--wait"]), step="compose.up", attestations=attestations, timeout=300)
        docker_evidence = _docker_runtime_evidence(compose_file, project_name, attestations)
        _wait_for_broker(compose_file, project_name, attestations)
        _run_command(_rabbitmqadmin_command(compose_file, project_name, ["--version"]), step="rabbitmqadmin.version", attestations=attestations)
        management_calls += _declare_broker_shape(compose_file, project_name, attestations)
        monotonic_started_ns = time.monotonic_ns()
        for sample_ordinal, offset_seconds in enumerate(_sample_offsets(sample_count)):
            tick_started = time.monotonic()
            publish_batch: list[tuple[str, dict[str, Any]]] = []
            consume_plan: list[tuple[str, int, str]] = []
            for service_index in range(SERVICE_COUNT):
                valid_count, invalid_count = _message_count_for_service(service_index, offset_seconds, incidents_by_service)
                if valid_count or invalid_count:
                    queue = _queue_name(service_index)
                    split = _split_for_service(service_index)
                    for message_index in range(valid_count):
                        publish_batch.append((queue, _message_payload(service_index, sample_ordinal, message_index, True)))
                    for message_index in range(invalid_count):
                        publish_batch.append((queue, _message_payload(service_index, sample_ordinal, message_index, False)))
                    published_by_service[service_index] += valid_count + invalid_count
                    rejected_by_service[service_index] += invalid_count
                    published_total += valid_count + invalid_count
                    if invalid_count:
                        consume_plan.append((_queue_name(service_index), invalid_count, "reject_requeue_false"))
                        consumed_total += invalid_count
                    if split not in {"held_out", "real_derived_shadow"}:
                        raise RuntimeError("invalid_split")
                for incident in incidents_by_service[service_index]:
                    cleanup_offset = int(incident["positive_precursor_end_offset_seconds"]) + CADENCE_SECONDS
                    if offset_seconds != cleanup_offset:
                        continue
                    if incident["kind"] == "poison_dead_letter":
                        consume_plan.append((_dlq_name(service_index), 1, "ack_requeue_false"))
                    else:
                        consume_plan.append((_queue_name(service_index), 1, "ack_requeue_false"))
                    consumed_total += 1
            if published_total > MAX_MESSAGES or consumed_total > MAX_MESSAGES:
                raise RuntimeError("queue_fleet_message_bound_breach")
            _publish_rows(compose_file, project_name, attestations, publish_batch)
            _consume_rows(compose_file, project_name, attestations, consume_plan)
            broker_rows = _bulk_observe(compose_file, project_name, attestations)
            management_calls += 1
            if management_calls > MAX_MANAGEMENT_HTTP_CALLS:
                raise RuntimeError("queue_fleet_management_http_call_bound_breach")
            broker_observation = _bounded_broker_observation(broker_rows)
            broker_counts = {str(row.get("name")): row for row in broker_rows}
            sample_monotonic_ns = time.monotonic_ns()
            for service_index in range(SERVICE_COUNT):
                counts = broker_counts.get(_queue_name(service_index), {})
                dlq_counts = broker_counts.get(_dlq_name(service_index), {})
                messages_ready = int(counts.get("messages_ready", 0)) if counts else 0
                telemetry.append(
                    _telemetry_row(
                        service_index,
                        sample_ordinal,
                        broker_observed=True,
                        messages_ready=messages_ready,
                        dlq_messages_ready=int(dlq_counts.get("messages_ready", 0)) if dlq_counts else 0,
                        published_count=published_by_service[service_index],
                        rejected_count=rejected_by_service[service_index],
                    )
                )
                raw_by_service[service_index].append(_raw_observation(service_index, sample_ordinal, sample_monotonic_ns, counts))
            if not args.no_sleep and sample_ordinal + 1 < sample_count:
                remaining = CADENCE_SECONDS - (time.monotonic() - tick_started)
                if remaining > 0:
                    time.sleep(remaining)
        monotonic_finished_ns = time.monotonic_ns()
    finally:
        down = subprocess.run(_compose_command(compose_file, project_name, ["down", "--volumes", "--remove-orphans"]), text=True, capture_output=True, check=False, timeout=180)
        attestations.append(
            CommandAttestation(
                command=_compose_command(compose_file, project_name, ["down", "--volumes", "--remove-orphans"]),
                returncode=down.returncode,
                stderr=down.stderr,
                stdout=down.stdout,
                step="compose.down",
            )
        )
        cleanup = {"container_removed": down.returncode == 0, "volume_removed": down.returncode == 0}
    raw_rows = [row for service_rows in raw_by_service.values() for row in service_rows]
    coverage_segments = _coverage_segments(raw_by_service)
    coverage = {
        "coverage_segments": coverage_segments,
        "coverage_source": "receipt_bound_adjacent_monotonic_samples",
        "counting_coverage_seconds": 0 if args.diagnostic else sum(int(segment["canonical_duration_seconds"]) for segment in coverage_segments),
        "diagnostic_only": args.diagnostic,
        "legacy_created_at_tick_seconds_coverage": False,
        "schema_version": "p105.queue.fleet_coverage.v1",
    }
    raw_attestation = {
        "actual_runtime_executed": True,
        "adjacent_deltas_seconds": _adjacent_deltas(raw_by_service),
        "authority": {"credential_reads": 0, "host_ports": [], "production_endpoint_attempts": 0, "production_mutations": 0},
        "broker_observation": broker_observation,
        "capabilities": ["actual_rabbitmq_docker"],
        "commands": [attestation.__dict__ for attestation in attestations],
        "container_id": docker_evidence.get("container_id"),
        "docker_network_name": docker_evidence.get("docker_network_name"),
        "fixture_only": False,
        "management_http_calls": management_calls,
        "messages_consumed_or_rejected": consumed_total,
        "messages_published": published_total,
        "monotonic_finished_ns": monotonic_finished_ns,
        "monotonic_started_ns": monotonic_started_ns,
        "raw_sample_observations": raw_rows,
        "rabbitmq_management_observed": _rabbitmq_management_observed(attestations),
        "schema_version": "p105.queue.fleet_raw_runtime_attestation.v1",
        "uses_in_memory_queue_simulation": False,
    }
    return telemetry, coverage, raw_attestation, cleanup


def _message_payload(service_index: int, sample_ordinal: int, message_index: int, valid_schema: bool) -> dict[str, Any]:
    payload_seed = {"message_index": message_index, "sample_ordinal": sample_ordinal, "service": _service_id(service_index), "valid_schema": valid_schema}
    return {
        "message_id": f"p105-fleet-queue-svc{service_index:03d}-sample{sample_ordinal:03d}-{'valid' if valid_schema else 'poison'}-{message_index:02d}",
        "payload_hash": _sha256_text(_stable_json(payload_seed)),
        "sample_ordinal": sample_ordinal,
        "service": _service_id(service_index),
        "valid_schema": valid_schema,
    }


def _adjacent_deltas(raw_by_service: dict[int, list[dict[str, Any]]]) -> list[float]:
    deltas: list[float] = []
    for rows in raw_by_service.values():
        for previous, row in zip(rows, rows[1:], strict=False):
            deltas.append((int(row["monotonic_ns"]) - int(previous["monotonic_ns"])) / 1_000_000_000)
    return deltas


def _artifact_hashes(output_dir: Path) -> dict[str, str]:
    excluded = {"p105-queue-fleet-provenance-hashes.json", "p105-queue-fleet-runtime-attestation.raw.json", "p105-queue-fleet-rabbitmq.compose.yml"}
    return {path.name: _sha256_path(path) for path in sorted(output_dir.iterdir()) if path.is_file() and path.name not in excluded}


def _validate_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if args.rabbitmq_image != RABBITMQ_IMAGE:
        errors.append("rabbitmq_image_not_fixed_3_13_management_alpine")
    if args.full_runtime and args.diagnostic:
        errors.append("full_runtime_and_diagnostic_are_mutually_exclusive")
    if not args.expect_no_host_ports:
        errors.append("host_port_guard_missing")
    if not args.expect_no_production_authority:
        errors.append("production_authority_guard_missing")
    if not args.full_runtime and not args.diagnostic and not args.fixture_only:
        errors.append("must_select_full_runtime_diagnostic_or_fixture_only")
    if args.diagnostic_samples < 1 or args.diagnostic_samples > SCHEDULED_SAMPLES_PER_SERVICE:
        errors.append("diagnostic_samples_out_of_range")
    return errors


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize P105 queue fleet canonical artifacts using an isolated RabbitMQ Docker runtime.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rabbitmq-image", default=RABBITMQ_IMAGE)
    parser.add_argument("--seed", default=105032, type=int)
    parser.add_argument("--diagnostic", action="store_true", help="Run actual RabbitMQ plumbing with a shortened non-counting sample plan.")
    parser.add_argument("--diagnostic-samples", default=2, type=int)
    parser.add_argument("--fixture-only", action="store_true", help="Emit deterministic static artifacts without claiming actual RabbitMQ runtime evidence.")
    parser.add_argument("--full-runtime", action="store_true", help="Run the frozen 256x1h profile. This is the only counting-capable source mode.")
    parser.add_argument("--no-sleep", action="store_true", help="Skip cadence sleeps for local smoke diagnostics; intervals remain non-counting unless verifier accepts raw deltas.")
    parser.add_argument("--expect-no-host-ports", action="store_true")
    parser.add_argument("--expect-no-production-authority", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    errors = _validate_args(args)
    if errors:
        sys.stderr.write(json.dumps({"error": "p105_queue_fleet_harness_fail_closed", "validation_error_codes": errors}, sort_keys=True) + "\n")
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    profile_id = PROFILE_ID if args.full_runtime else DIAGNOSTIC_PROFILE_ID
    sample_count = SCHEDULED_SAMPLES_PER_SERVICE if args.full_runtime else args.diagnostic_samples
    project_name = "p105-queue-fleet-run-001"
    public_config = _public_config(profile_id, sample_count, project_name)
    try:
        if args.fixture_only:
            telemetry, coverage, raw_attestation, cleanup = _materialize_fixture(sample_count, diagnostic_only=args.diagnostic)
        else:
            telemetry, coverage, raw_attestation, cleanup = _materialize_actual(args, sample_count, project_name)
    except Exception as exc:
        sys.stderr.write(json.dumps({"error": "p105_queue_fleet_harness_runtime_failed", "message": str(exc)}, sort_keys=True) + "\n")
        return 3
    public_config["runtime"]["broker_health_observed"] = bool(raw_attestation["actual_runtime_executed"])
    public_config["cleanup"].update(cleanup)
    private_ledger = {
        "label_join_phase": "after_sampling_and_partition",
        "loaded_after_public_config_hash": _sha256_text(_stable_json(public_config)),
        "public_artifact": False,
        "schedule": _fleet_schedule(),
        "schema_version": "p105.queue.fleet_private_injection_ledger.v1",
    }
    partitions = {
        "assigned_before_private_schedule_loading": True,
        "held_out": [_service_id(index) for index in range(128)],
        "real_derived_shadow": [_service_id(index) for index in range(128, 256)],
        "schema_version": "p105.queue.fleet_pre_label_partitions.v1",
    }
    _write_jsonl(args.output_dir / "p105-queue-fleet-public-telemetry.jsonl", telemetry)
    _write_json(args.output_dir / "p105-queue-fleet-private-injection-ledger.json", private_ledger)
    _write_json(args.output_dir / "p105-queue-fleet-pre-label-partitions.json", partitions)
    _write_json(args.output_dir / "p105-queue-fleet-coverage.json", coverage)
    _write_json(args.output_dir / "p105-queue-fleet-runtime-attestation.raw.json", raw_attestation)
    canonical_argv = _canonical_argv(sys.argv if argv is None else [sys.argv[0], *argv])
    manifest = {
        "artifact_paths": {
            "coverage": "p105-queue-fleet-coverage.json",
            "partitions": "p105-queue-fleet-pre-label-partitions.json",
            "private_injection_ledger": "p105-queue-fleet-private-injection-ledger.json",
            "provenance_hashes": "p105-queue-fleet-provenance-hashes.json",
            "public_telemetry": "p105-queue-fleet-public-telemetry.jsonl",
        },
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": _sha256_text(_stable_json(canonical_argv)),
        "diagnostic_only": not args.full_runtime,
        "private_injection_ledger": private_ledger,
        "public_config": public_config,
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "runtime_attestation": {"kind": "actual_rabbitmq_docker" if raw_attestation["actual_runtime_executed"] else "not_executed"},
        "schema_version": SCHEMA_VERSION,
        "source_harness_issues_verifier_qualification_receipt": False,
    }
    _write_json(args.output_dir / "p105-queue-fleet-harness-manifest.json", manifest)
    provenance = {
        "artifact_hashes": _artifact_hashes(args.output_dir),
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": manifest["command_argv_sha256"],
        "profile_hash": public_config["profile"]["hash"],
        "schema_version": "p105.queue.fleet_provenance_hashes.v1",
    }
    _write_json(args.output_dir / "p105-queue-fleet-provenance-hashes.json", provenance)
    print(json.dumps({"fixture_only": args.fixture_only, "manifest_path": str(args.output_dir / "p105-queue-fleet-harness-manifest.json"), "telemetry_rows": len(telemetry)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
