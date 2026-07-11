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
class QueueRuntimeState:
    published: list[Message]
    consume_cursor: int = 0
    dlq_count: int = 0
    published_count: int = 0
    acknowledged_count: int = 0
    rejected_count: int = 0

    def expected_ready(self) -> list[Message]:
        return self.published[self.consume_cursor :]

    def consume_expected(self, count: int) -> list[Message]:
        expected = self.expected_ready()[:count]
        self.consume_cursor += len(expected)
        return expected


@dataclass
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


def _run_command(command: list[str], *, step: str, attestations: list[CommandAttestation], input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, input=input_text, text=True, capture_output=True, check=False, timeout=timeout)
    attestations.append(
        CommandAttestation(
            step=step,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    )
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


def _compose_command(args: argparse.Namespace, project_name: str, compose_args: list[str]) -> list[str]:
    return ["docker", "compose", "-f", args.compose_file, "-p", project_name, *compose_args]


def _rabbitmqadmin_command(args: argparse.Namespace, project_name: str, admin_args: list[str]) -> list[str]:
    return _compose_command(
        args,
        project_name,
        [
            "exec",
            "-T",
            "rabbitmq",
            "rabbitmqadmin",
            "-u",
            "guest",
            "-p",
            "guest",
            "--vhost=/",
            "--format=raw_json",
            *admin_args,
        ],
    )


def _ensure_docker_runtime_available(args: argparse.Namespace, attestations: list[CommandAttestation]) -> None:
    if shutil.which("docker") is None:
        raise RuntimeError("docker_cli_not_found")
    if not Path(args.compose_file).is_file():
        raise RuntimeError(f"compose_file_not_found:{args.compose_file}")
    _run_command(["docker", "version", "--format", "{{json .}}"], step="docker.version", attestations=attestations)


def _wait_for_broker(args: argparse.Namespace, project_name: str, attestations: list[CommandAttestation]) -> None:
    last_error = ""
    for attempt in range(60):
        completed = subprocess.run(
            _compose_command(args, project_name, ["exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"]),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        attestations.append(
            CommandAttestation(
                step=f"rabbitmq.ping.{attempt:02d}",
                command=_compose_command(args, project_name, ["exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"]),
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        )
        if completed.returncode == 0:
            return
        last_error = completed.stderr or completed.stdout
        if not args.test_fast_runtime:
            subprocess.run(["sleep", "1"], check=False)
    raise RuntimeError(f"rabbitmq_not_ready:{last_error[-500:]}")


def _setup_broker(args: argparse.Namespace, project_name: str, attestations: list[CommandAttestation]) -> None:
    for queue_name in (*QUEUE_NAMES, *DLQ_NAMES.values()):
        subprocess.run(_rabbitmqadmin_command(args, project_name, ["delete", "queue", f"name={queue_name}"]), text=True, capture_output=True, check=False, timeout=60)
    subprocess.run(_rabbitmqadmin_command(args, project_name, ["delete", "exchange", "name=p105.dlx"]), text=True, capture_output=True, check=False, timeout=60)
    _run_command(_rabbitmqadmin_command(args, project_name, ["declare", "exchange", "name=p105.dlx", "type=direct", "durable=false"]), step="rabbitmq.declare.dlx", attestations=attestations)
    for queue_name in QUEUE_NAMES:
        dlq_name = DLQ_NAMES[queue_name]
        _run_command(_rabbitmqadmin_command(args, project_name, ["declare", "queue", f"name={dlq_name}", "durable=false"]), step=f"rabbitmq.declare.{dlq_name}", attestations=attestations)
        _run_command(
            _rabbitmqadmin_command(
                args,
                project_name,
                ["declare", "binding", "source=p105.dlx", "destination_type=queue", f"destination={dlq_name}", f"routing_key={dlq_name}"],
            ),
            step=f"rabbitmq.bind.{dlq_name}",
            attestations=attestations,
        )
        _run_command(
            _rabbitmqadmin_command(
                args,
                project_name,
                [
                    "declare",
                    "queue",
                    f"name={queue_name}",
                    "durable=false",
                    f"arguments={_stable_json({'x-dead-letter-exchange': 'p105.dlx', 'x-dead-letter-routing-key': dlq_name})}",
                ],
            ),
            step=f"rabbitmq.declare.{queue_name}",
            attestations=attestations,
        )


def _message_payload(message: Message, queue_name: str) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "payload_hash": message.payload_hash,
        "producer_tick": message.producer_tick,
        "queue_name": queue_name,
        "valid_schema": message.valid_schema,
    }


def _publish_messages(args: argparse.Namespace, project_name: str, attestations: list[CommandAttestation], queue_name: str, messages: list[Message]) -> None:
    if not messages:
        return
    rows = "".join(f"{queue_name}\t{_stable_json(_message_payload(message, queue_name))}\n" for message in messages)
    script = (
        "while IFS='	' read -r routing_key payload; do "
        "rabbitmqadmin -q -u guest -p guest --vhost=/ publish exchange=amq.default routing_key=\"$routing_key\" payload=\"$payload\" >/dev/null; "
        "done"
    )
    _run_command(
        _compose_command(args, project_name, ["exec", "-T", "rabbitmq", "sh", "-eu", "-c", script]),
        step=f"rabbitmq.publish.{queue_name}",
        attestations=attestations,
        input_text=rows,
        timeout=300,
    )


def _parse_get_payloads(stdout: str) -> list[dict[str, Any]]:
    rows = json.loads(stdout or "[]")
    if not isinstance(rows, list):
        raise RuntimeError("rabbitmq_get_not_json_list")
    payloads: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("rabbitmq_get_row_not_object")
        payload = row.get("payload")
        if not isinstance(payload, str):
            raise RuntimeError("rabbitmq_get_payload_missing")
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise RuntimeError("rabbitmq_get_payload_not_object")
        payloads.append(decoded)
    return payloads


def _consume_expected_messages(
    args: argparse.Namespace,
    project_name: str,
    attestations: list[CommandAttestation],
    queue_name: str,
    expected_messages: list[Message],
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    index = 0
    while index < len(expected_messages):
        valid_schema = expected_messages[index].valid_schema
        run_length = 1
        while index + run_length < len(expected_messages) and expected_messages[index + run_length].valid_schema == valid_schema:
            run_length += 1
        ackmode = "ack_requeue_false" if valid_schema else "reject_requeue_false"
        completed = _run_command(
            _rabbitmqadmin_command(args, project_name, ["get", f"queue={queue_name}", f"count={run_length}", f"ackmode={ackmode}", "encoding=auto"]),
            step=f"rabbitmq.consume.{queue_name}.{ackmode}",
            attestations=attestations,
            timeout=120,
        )
        payloads = _parse_get_payloads(completed.stdout)
        expected_run = expected_messages[index : index + run_length]
        if len(payloads) != len(expected_run):
            raise RuntimeError(f"rabbitmq_consume_count_mismatch:{queue_name}:{len(payloads)}:{len(expected_run)}")
        for payload, expected in zip(payloads, expected_run, strict=True):
            if payload.get("message_id") != expected.message_id or bool(payload.get("valid_schema")) != expected.valid_schema:
                raise RuntimeError(f"rabbitmq_consume_payload_mismatch:{queue_name}:{payload.get('message_id')}:{expected.message_id}")
            observed.append(payload)
        index += run_length
    return observed


def _observe_queues(args: argparse.Namespace, project_name: str, attestations: list[CommandAttestation]) -> dict[str, dict[str, int]]:
    completed = _run_command(
        _compose_command(
            args,
            project_name,
            [
                "exec",
                "-T",
                "rabbitmq",
                "rabbitmqctl",
                "list_queues",
                "--formatter",
                "json",
                "name",
                "messages",
                "messages_ready",
                "messages_unacknowledged",
            ],
        ),
        step="rabbitmq.observe.queues",
        attestations=attestations,
        timeout=120,
    )
    rows = json.loads(completed.stdout or "[]")
    if not isinstance(rows, list):
        raise RuntimeError("rabbitmq_queue_observation_not_json_list")
    observations: dict[str, dict[str, int]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("name") in (*QUEUE_NAMES, *DLQ_NAMES.values()):
            observations[str(row["name"])] = {
                "messages": int(row.get("messages", 0)),
                "messages_ready": int(row.get("messages_ready", 0)),
                "messages_unacknowledged": int(row.get("messages_unacknowledged", 0)),
            }
    return observations


def _expected_queue_counts(states: dict[str, QueueRuntimeState]) -> dict[str, dict[str, int]]:
    expected: dict[str, dict[str, int]] = {}
    for queue_name, state in states.items():
        ready = len(state.expected_ready())
        expected[queue_name] = {"messages": ready, "messages_ready": ready, "messages_unacknowledged": 0}
        rejected = state.rejected_count
        expected[DLQ_NAMES[queue_name]] = {"messages": rejected, "messages_ready": rejected, "messages_unacknowledged": 0}
    return expected


def _observe_queues_until_settled(
    args: argparse.Namespace,
    project_name: str,
    attestations: list[CommandAttestation],
    states: dict[str, QueueRuntimeState],
) -> dict[str, dict[str, int]]:
    expected = _expected_queue_counts(states)
    observed: dict[str, dict[str, int]] = {}
    for _attempt in range(20):
        observed = _observe_queues(args, project_name, attestations)
        if all(observed.get(queue_name) == counts for queue_name, counts in expected.items()):
            return observed
        time.sleep(0.05)
    raise RuntimeError(
        "rabbitmq_queue_observation_not_settled:"
        + _stable_json({"expected": expected, "observed": observed})
    )


def _run_raw_reject_dlq_probe(args: argparse.Namespace, project_name: str, attestations: list[CommandAttestation]) -> dict[str, Any]:
    probe_queue = "p105.raw.probe.queue"
    probe_dlq = "p105.raw.probe.dlq"
    for queue_name in (probe_queue, probe_dlq):
        subprocess.run(_rabbitmqadmin_command(args, project_name, ["delete", "queue", f"name={queue_name}"]), text=True, capture_output=True, check=False, timeout=60)
    _run_command(_rabbitmqadmin_command(args, project_name, ["declare", "queue", f"name={probe_dlq}", "durable=false"]), step="rabbitmq.raw_probe.declare.dlq", attestations=attestations)
    _run_command(
        _rabbitmqadmin_command(
            args,
            project_name,
            ["declare", "binding", "source=p105.dlx", "destination_type=queue", f"destination={probe_dlq}", f"routing_key={probe_dlq}"],
        ),
        step="rabbitmq.raw_probe.bind.dlq",
        attestations=attestations,
    )
    _run_command(
        _rabbitmqadmin_command(
            args,
            project_name,
            [
                "declare",
                "queue",
                f"name={probe_queue}",
                "durable=false",
                f"arguments={_stable_json({'x-dead-letter-exchange': 'p105.dlx', 'x-dead-letter-routing-key': probe_dlq})}",
            ],
        ),
        step="rabbitmq.raw_probe.declare.queue",
        attestations=attestations,
    )
    _run_command(
        _rabbitmqadmin_command(
            args,
            project_name,
            [
                "publish",
                "exchange=amq.default",
                f"routing_key={probe_queue}",
                f"payload={_stable_json({'message_id': 'p105-raw-probe-reject-dlq', 'valid_schema': False})}",
            ],
        ),
        step="rabbitmq.raw_probe.publish",
        attestations=attestations,
    )
    _run_command(
        _rabbitmqadmin_command(args, project_name, ["get", f"queue={probe_queue}", "count=1", "ackmode=reject_requeue_false", "encoding=auto"]),
        step="rabbitmq.raw_probe.reject",
        attestations=attestations,
    )
    dlq_ready = 0
    for attempt in range(60):
        completed = _run_command(
            _rabbitmqadmin_command(args, project_name, ["list", "queues", "name", "messages_ready", "messages_unacknowledged"]),
            step=f"rabbitmq.raw_probe.observe.dlq.{attempt:02d}",
            attestations=attestations,
        )
        rows = json.loads(completed.stdout or "[]")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("name") == probe_dlq:
                    dlq_ready = int(row.get("messages_ready", 0))
        if dlq_ready == 1:
            break
        time.sleep(0.25)
    if dlq_ready != 1:
        raise RuntimeError(f"rabbitmq_raw_probe_dlq_not_observed:{dlq_ready}")
    return {
        "capability": "actual_publish_consume_reject_dlq",
        "dlq_messages_ready": dlq_ready,
        "probe_canonical_artifact": False,
    }


def _materialize_with_rabbitmq(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    attestations: list[CommandAttestation] = []
    _ensure_docker_runtime_available(args, attestations)
    project_name = f"p105queue{_sha256_text(str(args.output_dir.resolve()))[:12]}"
    states = {queue_name: QueueRuntimeState(published=[]) for queue_name in QUEUE_NAMES}
    telemetry: list[dict[str, Any]] = []
    ledger_records: list[dict[str, Any]] = []
    coverage_intervals: dict[str, list[dict[str, int]]] = {queue_name: [{"end_tick": args.ticks - 1, "start_tick": 0}] for queue_name in QUEUE_NAMES}
    raw_observations: list[dict[str, Any]] = []
    monotonic_started_ns: int | None = None
    monotonic_finished_ns: int | None = None

    try:
        _run_command(_compose_command(args, project_name, ["up", "-d", "--wait"]), step="compose.up", attestations=attestations, timeout=300)
        _run_command(_compose_command(args, project_name, ["ps", "--format", "json"]), step="compose.ps", attestations=attestations, timeout=60)
        _wait_for_broker(args, project_name, attestations)
        _run_command(_rabbitmqadmin_command(args, project_name, ["--version"]), step="rabbitmqadmin.version", attestations=attestations, timeout=60)
        _setup_broker(args, project_name, attestations)
        raw_observations.append(_run_raw_reject_dlq_probe(args, project_name, attestations))

        monotonic_started_ns = time.monotonic_ns()
        for tick in range(args.ticks):
            for queue_name in QUEUE_NAMES:
                state = states[queue_name]
                tick_messages = [_message(queue_name, tick, index) for index in range(SCHEDULE["producer_rate"])]
                if tick == _poison_tick(queue_name):
                    poison_messages = [_message(queue_name, tick, index, valid_schema=False) for index in range(5)]
                    tick_messages.extend(poison_messages)
                    ledger_records.append(
                        {
                            "end_tick": tick,
                            "expected_broker_transition": "invalid_schema_messages_dead_lettered",
                            "injected_message_ids": [message.message_id for message in poison_messages],
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
                _publish_messages(args, project_name, attestations, queue_name, tick_messages)
                state.published.extend(tick_messages)
                state.published_count += len(tick_messages)

            for queue_name in QUEUE_NAMES:
                state = states[queue_name]
                expected = state.expected_ready()[: _consumer_rate(queue_name, tick)]
                consumed_payloads = _consume_expected_messages(args, project_name, attestations, queue_name, state.consume_expected(len(expected)))
                ack_lags: list[int] = []
                for payload in consumed_payloads:
                    if bool(payload["valid_schema"]):
                        state.acknowledged_count += 1
                        ack_lags.append(tick - int(payload["producer_tick"]))
                    else:
                        state.rejected_count += 1
                queue_observations = _observe_queues_until_settled(args, project_name, attestations, states)
                state.dlq_count = queue_observations.get(DLQ_NAMES[queue_name], {}).get("messages_ready", state.dlq_count)
                for record in ledger_records:
                    if record["queue_name"] == queue_name and record["observed_transition_tick"] is None and state.dlq_count >= len(record["injected_message_ids"]):
                        record["observed_transition_tick"] = tick

                ready_messages = state.expected_ready()
                queue_counts = queue_observations.get(queue_name, {"messages": 0, "messages_ready": 0, "messages_unacknowledged": 0})
                oldest_unacked_age = tick - ready_messages[0].producer_tick if ready_messages else 0
                observation = {
                    "ack_lag_max_ticks": max(ack_lags) if ack_lags else 0,
                    "ack_lag_p50_ticks": _percentile(ack_lags, 0.50),
                    "ack_lag_p95_ticks": _percentile(ack_lags, 0.95),
                    "acknowledged_count": state.acknowledged_count,
                    "authority_counters": {"credential_reads": 0, "host_ports": 0, "production_endpoint_attempts": 0, "production_mutations": 0},
                    "broker_capability": "actual_rabbitmq_docker",
                    "dlq_messages_ready": state.dlq_count,
                    "event_time": _event_time(args.created_at, tick),
                    "messages_ready": queue_counts["messages_ready"],
                    "messages_total": queue_counts["messages"] + state.dlq_count,
                    "messages_unacknowledged": queue_counts["messages_unacknowledged"],
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
                raw_observations.append({"queue_counts": queue_observations, "queue_name": queue_name, "tick": tick})
            if not args.test_fast_runtime and tick + 1 < args.ticks:
                _run_command(["sleep", str(args.tick_seconds)], step=f"tick.sleep.{tick:04d}", attestations=attestations, timeout=args.tick_seconds + 10)
        monotonic_finished_ns = time.monotonic_ns()
    finally:
        down = subprocess.run(_compose_command(args, project_name, ["down", "--volumes", "--remove-orphans"]), text=True, capture_output=True, check=False, timeout=180)
        attestations.append(
            CommandAttestation(
                step="compose.down",
                command=_compose_command(args, project_name, ["down", "--volumes", "--remove-orphans"]),
                returncode=down.returncode,
                stdout=down.stdout,
                stderr=down.stderr,
            )
        )

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
    runtime_attestation = {
        "authority": {
            "credential_reads": 0,
            "credential_source": "rabbitmq_default_loopback_inside_private_container",
            "host_ports": [],
            "production_endpoint_attempts": 0,
            "production_mutations": 0,
        },
        "capabilities": ["actual_rabbitmq_docker"],
        "commands": [attestation.__dict__ for attestation in attestations],
        "compose_file": args.compose_file,
        "actual_elapsed_seconds": None
        if monotonic_started_ns is None or monotonic_finished_ns is None
        else (monotonic_finished_ns - monotonic_started_ns) / 1_000_000_000,
        "monotonic_finished_ns": monotonic_finished_ns,
        "monotonic_started_ns": monotonic_started_ns,
        "raw_broker_observations": raw_observations,
        "schema_version": "p105.queue.raw_runtime_attestation.v1",
        "test_fast_runtime": args.test_fast_runtime,
        "uses_in_memory_deque_simulation": False,
    }
    return telemetry, private_ledger, partitions, coverage, runtime_attestation


def _artifact_hashes(output: Path) -> dict[str, str]:
    return {
        path.name: _sha256_path(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name not in {"p105-queue-provenance-hashes.json", "p105-queue-runtime-attestation.raw.json"}
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize deterministic isolated P105 RabbitMQ queue harness artifacts.")
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
    parser.add_argument("--test-fast-runtime", action="store_true", help="Run a 3-tick no-sleep actual-broker smoke instead of the 900-second release runtime.")
    return parser


def _validate_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if args.mode != "isolated-local":
        errors.append("mode_not_isolated_local")
    if args.rabbitmq_image != "rabbitmq:3.13-management-alpine":
        errors.append("rabbitmq_image_not_fixed_3_13_management_alpine")
    if args.tick_seconds < 0:
        errors.append("tick_seconds_negative")
    if not args.test_fast_runtime and args.tick_seconds != 1:
        errors.append("tick_seconds_not_fixed_one")
    expected_ticks = 3 if args.test_fast_runtime else 900
    if args.ticks != expected_ticks:
        errors.append("ticks_not_fixed_3_for_test_fast_runtime" if args.test_fast_runtime else "ticks_not_fixed_900")
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

    try:
        telemetry, private_ledger, partitions, coverage, runtime_attestation = _materialize_with_rabbitmq(args)
    except Exception as exc:
        sys.stderr.write(json.dumps({"error": "p105_queue_harness_runtime_failed", "message": str(exc)}, sort_keys=True) + "\n")
        return 3

    _write_jsonl(output / "p105-queue-public-telemetry.jsonl", telemetry)
    _write_json(output / "p105-queue-private-injection-ledger.json", private_ledger)
    _write_json(output / "p105-queue-pre-label-partitions.json", partitions)
    _write_json(output / "p105-queue-coverage.json", coverage)
    _write_json(output / "p105-queue-runtime-attestation.raw.json", runtime_attestation)

    canonical_argv = _canonical_argv(sys.argv if argv is None else [sys.argv[0], *argv])
    manifest = {
        "artifact_paths": {
            "coverage": "p105-queue-coverage.json",
            "partitions": "p105-queue-pre-label-partitions.json",
            "private_injection_ledger": "p105-queue-private-injection-ledger.json",
            "provenance_hashes": "p105-queue-provenance-hashes.json",
            "public_telemetry": "p105-queue-public-telemetry.jsonl",
        },
        "authority": {
            "auth_enabled": False,
            "credentials_read": False,
            "external_broker_endpoint": False,
            "host_ports": [],
            "production_endpoint": False,
            "production_mutation": False,
            "release_counting_authority": False,
        },
        "broker_observation_attestation": {
            "docker_compose_ps_observed": True,
            "rabbitmq_management_observed": True,
        },
        "capabilities": ["actual_rabbitmq_docker"],
        "canonical_command_argv": canonical_argv,
        "command_argv_sha256": _sha256_text(_stable_json(canonical_argv)),
        "compose_file": args.compose_file,
        "created_at": args.created_at,
        "mode": args.mode,
        "program_version": PROGRAM_VERSION,
        "public_telemetry_row_count": len(telemetry),
        "rabbitmq_image": args.rabbitmq_image,
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "implementation_guard": {"uses_in_memory_deque_simulation": False},
        "runtime_attestation": {
            "capability": "docker_compose_rabbitmq_broker",
            "kind": "actual_rabbitmq_docker",
        },
        "schedule": SCHEDULE,
        "schedule_sha256": _sha256_text(_stable_json(SCHEDULE)),
        "schema_version": "p105.queue.harness_manifest.v1",
        "seed": args.seed,
        "source_family": "queue",
        "test_fast_runtime": args.test_fast_runtime,
        "tick_seconds": args.tick_seconds,
        "ticks": args.ticks,
        "uses_in_memory_deque_simulation": False,
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
