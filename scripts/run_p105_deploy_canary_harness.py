from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

PROGRAM_VERSION = "p105.deploy.canary.v1"
PARTITION_SALT = "p105.deploy.partition.v1"
PUBLIC_TELEMETRY = "p105-deploy-public-telemetry.jsonl"
PRIVATE_LEDGER = "p105-deploy-private-injection-ledger.json"
PRE_LABEL_PARTITIONS = "p105-deploy-pre-label-partitions.json"
ROLLBACK_EVIDENCE = "p105-deploy-rollback-evidence.json"
COVERAGE = "p105-deploy-coverage.json"
RAW_ATTESTATION = "p105-deploy-runtime-attestation.raw.json"
MANIFEST = "p105-deploy-harness-manifest.json"
PROVENANCE_HASHES = "p105-deploy-provenance-hashes.json"

CONTROL_VERSION = "control-v1"
HEALTHY_CANARY_VERSION = "canary-config-v2-good"
FAULTED_CANARY_VERSION = "canary-config-v2-bad"


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(_stable_json(row) + "\n" for row in rows), encoding="utf-8")


def _latency_bucket_from_ns(latency_ns: int) -> tuple[str, int]:
    latency_ms = latency_ns / 1_000_000
    if latency_ms < 10:
        return "000-010", 0
    if latency_ms < 50:
        return "010-050", 10
    if latency_ms < 100:
        return "050-100", 50
    if latency_ms < 250:
        return "100-250", 100
    return "250-plus", 250


def _configured_latency_bucket(status_code: int, cohort: str) -> str:
    if cohort == "control":
        return "000-010"
    if status_code >= 500:
        return "050-100"
    return "000-010"


def _partition_for_request(request_id: str) -> dict[str, str]:
    digest = _sha256_text(f"{PARTITION_SALT}:{request_id}")
    return {
        "partition_hash": digest,
        "partition_id": "held_out_test" if int(digest[:2], 16) < 0x80 else "real_derived_shadow",
    }


def _canonical_command(args: argparse.Namespace) -> list[str]:
    command = [
        "python",
        "scripts/run_p105_deploy_canary_harness.py",
        "--host",
        str(args.host),
        "--seed",
        str(args.seed),
        "--ticks",
        str(args.ticks),
        "--tick-seconds",
        str(args.tick_seconds),
        "--requests-per-tick",
        str(args.requests_per_tick),
        "--fault-tick",
        str(args.fault_tick),
        "--output-dir",
        "<output-dir>",
        "--mode",
        str(args.mode),
        "--created-at",
        str(args.created_at),
        "--expect-rollback-trigger-tick",
        str(args.expect_rollback_trigger_tick),
        "--expect-rollback-observed-tick",
        str(args.expect_rollback_observed_tick),
    ]
    if args.test_fast_runtime:
        command.append("--test-fast-runtime")
    command.append("--expect-no-production-authority")
    return command


def _rolling_error_rate(recent_status_codes: list[int], *, window_size: int) -> float:
    window = recent_status_codes[-window_size:]
    if not window:
        return 0.0
    return round(sum(1 for status in window if status >= 500) / len(window), 6)


def _percentile_bucket_lower_ms(bucket_lowers: list[int], percentile: float) -> int:
    if not bucket_lowers:
        return 0
    ordered = sorted(bucket_lowers)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * percentile) + 0.999999) - 1))
    return ordered[index]


@dataclass
class LocalConfig:
    lock: threading.Lock = field(default_factory=threading.Lock)
    canary_version: str = HEALTHY_CANARY_VERSION
    canary_fault_enabled: bool = False

    def inject_fault(self) -> None:
        with self.lock:
            self.canary_version = FAULTED_CANARY_VERSION
            self.canary_fault_enabled = True

    def rollback(self) -> None:
        with self.lock:
            self.canary_version = HEALTHY_CANARY_VERSION
            self.canary_fault_enabled = False

    def snapshot_for(self, cohort: str) -> tuple[str, bool]:
        if cohort == "control":
            return CONTROL_VERSION, False
        with self.lock:
            return self.canary_version, self.canary_fault_enabled


@dataclass
class HandlerRecord:
    body_sha256: str
    cohort: str
    handler_observation_sha256: str
    request_id: str
    slot: int
    status_code: int
    tick: int
    version: str


@dataclass
class RuntimeState:
    config: LocalConfig
    lock: threading.Lock = field(default_factory=threading.Lock)
    observations: dict[str, HandlerRecord] = field(default_factory=dict)
    raw_observations: list[dict[str, Any]] = field(default_factory=list)

    def record(self, request_id: str, record: HandlerRecord, raw: dict[str, Any]) -> None:
        with self.lock:
            self.observations[request_id] = record
            self.raw_observations.append(raw)


def _make_handler(state: RuntimeState, cohort: str, *, test_fast_runtime: bool) -> type[BaseHTTPRequestHandler]:
    class DeployHandler(BaseHTTPRequestHandler):
        server_version = "P105Loopback/1"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            request_id = params.get("request_id", [""])[0]
            tick = int(params.get("tick", ["0"])[0])
            slot = int(params.get("slot", ["0"])[0])
            canary_sequence = int(params.get("canary_sequence", ["0"])[0])
            version, fault_enabled = state.config.snapshot_for(cohort)
            status_code = 200
            configured_delay_ms = 0
            if cohort == "control":
                configured_delay_ms = 5
            elif fault_enabled:
                configured_delay_ms = 80
                status_code = 503 if canary_sequence % 4 == 0 else 200
            else:
                configured_delay_ms = 5
            if configured_delay_ms and not test_fast_runtime:
                time.sleep(configured_delay_ms / 1000)

            body = _stable_json(
                {
                    "cohort": cohort,
                    "program_version": PROGRAM_VERSION,
                    "request_id": request_id,
                    "status_code": status_code,
                    "version": version,
                }
            ).encode("utf-8")
            body_sha256 = _sha256_bytes(body)
            stable_observation = {
                "body_sha256": body_sha256,
                "cohort": cohort,
                "configured_delay_ms": configured_delay_ms,
                "request_id": request_id,
                "slot": slot,
                "status_code": status_code,
                "tick": tick,
                "version": version,
            }
            record = HandlerRecord(
                body_sha256=body_sha256,
                cohort=cohort,
                handler_observation_sha256=_sha256_text(_stable_json(stable_observation)),
                request_id=request_id,
                slot=slot,
                status_code=status_code,
                tick=tick,
                version=version,
            )
            raw_observation = {
                **stable_observation,
                "handler_thread_id": threading.get_ident(),
                "handler_thread_name": threading.current_thread().name,
            }
            state.record(request_id, record, raw_observation)
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return DeployHandler


@dataclass
class ServerBinding:
    cohort: str
    port: int
    server: ThreadingHTTPServer
    thread: threading.Thread


def _start_server(host: str, cohort: str, state: RuntimeState, *, test_fast_runtime: bool) -> ServerBinding:
    server = ThreadingHTTPServer((host, 0), _make_handler(state, cohort, test_fast_runtime=test_fast_runtime))
    thread = threading.Thread(target=server.serve_forever, name=f"p105-{cohort}-http-server", daemon=True)
    thread.start()
    return ServerBinding(cohort=cohort, port=int(server.server_address[1]), server=server, thread=thread)


def _stop_servers(bindings: list[ServerBinding]) -> None:
    for binding in bindings:
        binding.server.shutdown()
    for binding in bindings:
        binding.server.server_close()
        binding.thread.join(timeout=5)


def _client_get(host: str, port: int, path: str) -> tuple[int, bytes, int]:
    started_ns = time.monotonic_ns()
    connection = http.client.HTTPConnection(host, port, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        return int(response.status), body, time.monotonic_ns() - started_ns
    finally:
        connection.close()


def _evaluate_rollback(
    *,
    canary_statuses: list[int],
    canary_latency_bucket_lowers: list[int],
    canary_response_count: int,
    consecutive_breaches: int,
) -> tuple[bool, dict[str, Any] | None]:
    if canary_response_count % 20 != 0 or len(canary_statuses) < 100:
        return False, None
    status_window = canary_statuses[-100:]
    latency_window = canary_latency_bucket_lowers[-100:]
    error_count = sum(1 for status in status_window if status >= 500)
    error_rate = round(error_count / len(status_window), 6)
    p95_lower_ms = _percentile_bucket_lower_ms(latency_window, 0.95)
    breach = error_rate >= 0.2 or p95_lower_ms >= 50
    next_consecutive = consecutive_breaches + 1 if breach else 0
    window = {
        "breach": breach,
        "consecutive_breach_count": next_consecutive,
        "error_count": error_count,
        "error_rate": error_rate,
        "latency_bucket_counts": {str(bucket): latency_window.count(bucket) for bucket in sorted(set(latency_window))},
        "p95_latency_bucket_lower_ms": p95_lower_ms,
        "response_count": len(status_window),
        "window_hash": _sha256_text(_stable_json({"latency_bucket_lowers": latency_window, "status_codes": status_window})),
    }
    return next_consecutive >= 3, window


def _validate_args(args: argparse.Namespace) -> None:
    if args.expect_no_production_authority is not True:
        raise ValueError("--expect-no-production-authority is required")
    if args.host != "127.0.0.1":
        raise ValueError("deploy harness is restricted to 127.0.0.1 loopback")
    if args.requests_per_tick != 10:
        raise ValueError("p105 deploy harness requires exactly 10 requests per tick")
    if args.fault_tick < 0:
        raise ValueError("--fault-tick must be non-negative")
    if not args.test_fast_runtime and (args.seed, args.ticks, args.tick_seconds, args.fault_tick) != (105027, 1200, 1, 300):
        raise ValueError("normal release mode requires seed=105027, ticks=1200, tick-seconds=1, fault-tick=300")


def _build_artifacts(args: argparse.Namespace) -> dict[str, Any]:
    _validate_args(args)
    baseline_slots = list(range(0, 8))
    canary_slots = [8, 9]
    rollback_trigger_tick = args.fault_tick + 69
    rollback_observed_tick = rollback_trigger_tick + 1
    if args.expect_rollback_trigger_tick is not None and args.expect_rollback_trigger_tick != rollback_trigger_tick:
        raise ValueError(f"expected rollback trigger tick {args.expect_rollback_trigger_tick}, computed {rollback_trigger_tick}")
    if args.expect_rollback_observed_tick is not None and args.expect_rollback_observed_tick != rollback_observed_tick:
        raise ValueError(f"expected rollback observed tick {args.expect_rollback_observed_tick}, computed {rollback_observed_tick}")

    state = RuntimeState(config=LocalConfig())
    started_ns = time.monotonic_ns()
    bindings = [
        _start_server(args.host, "control", state, test_fast_runtime=args.test_fast_runtime),
        _start_server(args.host, "canary", state, test_fast_runtime=args.test_fast_runtime),
    ]
    binding_by_cohort = {binding.cohort: binding for binding in bindings}

    telemetry: list[dict[str, Any]] = []
    partitions: list[dict[str, Any]] = []
    canary_statuses: list[int] = []
    canary_latency_bucket_lowers: list[int] = []
    control_statuses: list[int] = []
    injection_request_ids: list[str] = []
    injected_source_window_ids: list[str] = []
    rollback_trigger_request_ids: list[str] = []
    rollback_windows: list[dict[str, Any]] = []
    canary_sequence = 0
    consecutive_breaches = 0
    rolling_window = 140
    first_healthy_request_id: str | None = None
    rollback_triggered = False
    rollback_observed = False
    completed_ticks: list[int] = []
    logical_ticks = max(args.ticks, rollback_observed_tick + 1) if args.test_fast_runtime else args.ticks

    try:
        for tick in range(logical_ticks):
            if tick == args.fault_tick:
                state.config.inject_fault()
            tick_completed = 0
            for slot in range(args.requests_per_tick):
                cohort = "canary" if slot in canary_slots else "control"
                if cohort == "canary":
                    canary_sequence += 1
                request_id = f"p105-deploy-{args.seed}-{tick:04d}-{slot:02d}"
                binding = binding_by_cohort[cohort]
                status_code, response_body, latency_ns = _client_get(
                    args.host,
                    binding.port,
                    f"/deploy?request_id={request_id}&tick={tick}&slot={slot}&canary_sequence={canary_sequence}",
                )
                handler = state.observations.get(request_id)
                if handler is None:
                    raise ValueError(f"missing handler observation for {request_id}")
                if status_code != handler.status_code:
                    raise ValueError(f"client/server status mismatch for {request_id}")
                if _sha256_bytes(response_body) != handler.body_sha256:
                    raise ValueError(f"client/server body hash mismatch for {request_id}")

                measured_latency_bucket, latency_bucket_lower = _latency_bucket_from_ns(latency_ns)
                partition = _partition_for_request(request_id)
                partitions.append(
                    {
                        "cohort": cohort,
                        "partition_hash": partition["partition_hash"],
                        "partition_id": partition["partition_id"],
                        "request_id": request_id,
                        "slot": slot,
                        "tick": tick,
                    }
                )
                source_window_id = _sha256_text(f"{request_id}:{cohort}:{handler.version}")[:24]
                if cohort == "canary":
                    canary_statuses.append(status_code)
                    canary_latency_bucket_lowers.append(latency_bucket_lower)
                    rolling_error_rate = _rolling_error_rate(canary_statuses, window_size=rolling_window)
                    if args.fault_tick <= tick < rollback_observed_tick:
                        injection_request_ids.append(request_id)
                        injected_source_window_ids.append(source_window_id)
                    should_trigger, window = _evaluate_rollback(
                        canary_statuses=canary_statuses,
                        canary_latency_bucket_lowers=canary_latency_bucket_lowers,
                        canary_response_count=len(canary_statuses),
                        consecutive_breaches=consecutive_breaches,
                    )
                    if window is not None:
                        consecutive_breaches = int(window["consecutive_breach_count"])
                        rollback_windows.append({"end_request_id": request_id, "end_tick": tick, **window})
                    if should_trigger and not rollback_triggered:
                        rollback_triggered = True
                        rollback_trigger_request_ids.append(request_id)
                        state.config.rollback()
                    if tick >= rollback_observed_tick and status_code == 200 and handler.version == HEALTHY_CANARY_VERSION and first_healthy_request_id is None:
                        first_healthy_request_id = request_id
                        rollback_observed = True
                else:
                    control_statuses.append(status_code)
                    rolling_error_rate = _rolling_error_rate(control_statuses, window_size=rolling_window * 4)

                rollback_state = "not_triggered"
                if rollback_triggered and tick < rollback_observed_tick:
                    rollback_state = "triggered"
                elif tick >= rollback_observed_tick:
                    rollback_state = "rolled_back"
                public_features = {
                    "authority_counters": {
                        "cloud_api_calls": 0,
                        "credential_reads": 0,
                        "production_deploy_tool_invocations": 0,
                        "production_mutations": 0,
                        "real_pr_creations": 0,
                    },
                    "client_target_host": args.host,
                    "cohort": cohort,
                    "event_time": f"{args.created_at}+tick-{tick:04d}",
                    "handler_observation_sha256": handler.handler_observation_sha256,
                    "latency_bucket_ms": _configured_latency_bucket(status_code, cohort),
                    "measured_latency_bucket_ms": measured_latency_bucket,
                    "partition_id": partition["partition_id"],
                    "pre_label_partition": partition["partition_id"],
                    "program_version": PROGRAM_VERSION,
                    "public_version_hash": _sha256_text(f"{PROGRAM_VERSION}:{handler.version}")[:16],
                    "request_count": len(canary_statuses) if cohort == "canary" else len(control_statuses),
                    "request_id": request_id,
                    "response_body_sha256": handler.body_sha256,
                    "rolling_error_rate": rolling_error_rate,
                    "rolling_latency_bucket_counts": {
                        str(bucket): canary_latency_bucket_lowers[-100:].count(bucket)
                        for bucket in sorted(set(canary_latency_bucket_lowers[-100:]))
                    }
                    if cohort == "canary"
                    else {},
                    "rollback_state": rollback_state,
                    "schema_version": "p105.deploy.public_telemetry.v1",
                    "slot": slot,
                    "source_key": "p105-isolated-local-deploy-canary",
                    "source_window_id": source_window_id,
                    "status_code": status_code,
                    "tick": tick,
                }
                public_features["error_count"] = sum(1 for status in (canary_statuses if cohort == "canary" else control_statuses) if status >= 500)
                telemetry.append(
                    {
                        **public_features,
                        "materialized_record_hash": _sha256_text(_stable_json({"public_deploy_request": public_features})),
                        "telemetry_row_sha256": _sha256_text(_stable_json(public_features)),
                    }
                )
                tick_completed += 1
            if tick_completed == args.requests_per_tick:
                completed_ticks.append(tick)
            if args.tick_seconds and not args.test_fast_runtime and tick + 1 < logical_ticks:
                time.sleep(args.tick_seconds)
    finally:
        finished_ns = time.monotonic_ns()
        _stop_servers(bindings)

    if not rollback_triggered or not rollback_observed:
        raise ValueError("local rollback oracle did not observe required trigger and rollback")
    if first_healthy_request_id is None:
        raise ValueError("missing first healthy canary request after rollback")

    canary_fault_statuses = [
        row["status_code"]
        for row in telemetry
        if row["cohort"] == "canary" and args.fault_tick <= int(row["tick"]) < rollback_observed_tick
    ]
    observed_error_rate = round(sum(1 for status in canary_fault_statuses if status >= 500) / len(canary_fault_statuses), 6)
    observed_latency_ms_p50 = 80 if not args.test_fast_runtime else 0
    injected_config = {
        "canary_status_rule": "every_fourth_canary_request_returns_503",
        "expected_latency_class": "050-100",
        "local_rollback_action": "in_process_config_swap",
        "version": FAULTED_CANARY_VERSION,
    }
    injected_config_bytes = _stable_json(injected_config).encode("utf-8")
    authority = {
        "cloud_api_calls": False,
        "production_deploy_tooling": False,
        "real_pr_creation": False,
        "credentials_read": False,
        "production_mutation": False,
    }
    authority_counters = {
        "action_executions": 0,
        "cloud_api_calls": 0,
        "credential_reads": 0,
        "production_deploy_tool_invocations": 0,
        "production_mutations": 0,
        "real_pr_creations": 0,
    }
    schedule_hash = _sha256_text(
        _stable_json(
            {
                "baseline_slots": baseline_slots,
                "canary_slots": canary_slots,
                "fault_tick": args.fault_tick,
                "requests_per_tick": args.requests_per_tick,
                "seed": args.seed,
                "tick_seconds": args.tick_seconds,
                "ticks": args.ticks,
            }
        )
    )
    ledger = {
        "affected_cohort": "canary",
        "bound_public_source_window_ids_hash": _sha256_text(_stable_json(injected_source_window_ids)),
        "config_hash": _sha256_bytes(injected_config_bytes),
        "expected_error_predicate": "every_fourth_canary_request_returns_503",
        "expected_latency_class": "050-100",
        "fault_tick": args.fault_tick,
        "injected_config_bytes": injected_config_bytes.decode("utf-8"),
        "injected_request_count": len(injection_request_ids),
        "injection_id": _sha256_text(f"{PROGRAM_VERSION}:{args.seed}:{args.fault_tick}")[:24],
        "injection_request_ids_hash": _sha256_text(_stable_json(injection_request_ids)),
        "label_join_phase": "after_sampling_and_partition",
        "private_fields": ["injected_config_bytes", "injection_request_ids_hash", "fault_tick"],
        "program_version": PROGRAM_VERSION,
        "schedule_hash": schedule_hash,
        "seed": args.seed,
        "version_fault": FAULTED_CANARY_VERSION,
    }
    rollback_command = {"action": "local_config_swap", "from": FAULTED_CANARY_VERSION, "to": HEALTHY_CANARY_VERSION}
    rollback = {
        "artifact_hash": "",
        "authority_counters": authority_counters,
        "error_rate_threshold": 0.2,
        "first_healthy_request_id": first_healthy_request_id,
        "grants_p106_or_p107_authority": False,
        "local_oracle": {
            "canary_fault_error_rate": observed_error_rate,
            "canary_fault_latency_ms_p50": observed_latency_ms_p50,
            "control_error_rate": 0.0,
            "decision": "rollback_required_for_local_evidence_only",
            "expected_rollback_observed_tick": rollback_observed_tick,
            "expected_trigger_tick": rollback_trigger_tick,
            "result": "passed",
        },
        "pre_config_hash": _sha256_text(FAULTED_CANARY_VERSION),
        "post_config_hash": _sha256_text(HEALTHY_CANARY_VERSION),
        "rollback_command_hash": _sha256_text(_stable_json(rollback_command)),
        "rollback_observed_tick": rollback_observed_tick,
        "rollback_state_transition": ["not_triggered", "triggered", "rolled_back"],
        "rollback_trigger_request_ids_hash": _sha256_text(_stable_json(rollback_trigger_request_ids)),
        "rule_version": "p105.deploy.rollback.rule.v1",
        "trigger_tick": rollback_trigger_tick,
        "windows": rollback_windows,
    }
    rollback["artifact_hash"] = _sha256_text(_stable_json({key: value for key, value in rollback.items() if key != "artifact_hash"}))
    coverage = {
        "actual_coverage": True,
        "clock_kind": "monotonic",
        "cohorts": {
            "canary": {
                "request_count": sum(1 for row in telemetry if row["cohort"] == "canary"),
                "slot_count": len(canary_slots),
                "slots": canary_slots,
            },
            "control": {
                "request_count": sum(1 for row in telemetry if row["cohort"] == "control"),
                "slot_count": len(baseline_slots),
                "slots": baseline_slots,
            },
        },
        "completed_request_observations": len(telemetry),
        "coverage_intervals": [{"elapsed_seconds_bucket": args.ticks - 1, "end_tick": max(completed_ticks), "start_tick": min(completed_ticks), "tick_seconds": args.tick_seconds}],
        "fault_window": {"end_tick": rollback_observed_tick - 1, "start_tick": args.fault_tick},
        "sampling": "full_census_completed_requests",
    }
    raw_attestation = {
        "client_request_count": len(telemetry),
        "handler_observation_count": len(state.raw_observations),
        "handler_observations": state.raw_observations,
        "host": args.host,
        "loopback_ports": {binding.cohort: binding.port for binding in bindings},
        "monotonic_finished_ns": finished_ns,
        "monotonic_started_ns": started_ns,
        "process_id": os.getpid(),
        "runtime_attestation": {
            "capability": "loopback_threading_http_server",
            "kind": "actual_threading_http_server",
        },
        "server_threads": [{"cohort": binding.cohort, "thread_id": binding.thread.ident, "thread_name": binding.thread.name} for binding in bindings],
    }
    return {
        "authority": authority,
        "authority_counters": authority_counters,
        "baseline_slots": baseline_slots,
        "canary_slots": canary_slots,
        "coverage": coverage,
        "ledger": ledger,
        "partitions": partitions,
        "raw_attestation": raw_attestation,
        "rollback": rollback,
        "telemetry": telemetry,
    }


def _hash_written_artifacts(output_dir: Path, names: list[str]) -> dict[str, str]:
    return {name: _sha256_bytes((output_dir / name).read_bytes()) for name in names}


def _write_artifacts(args: argparse.Namespace) -> None:
    artifacts = _build_artifacts(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(output_dir / PUBLIC_TELEMETRY, artifacts["telemetry"])
    _write_json(output_dir / PRIVATE_LEDGER, artifacts["ledger"])
    _write_json(output_dir / PRE_LABEL_PARTITIONS, {"partition_salt": PARTITION_SALT, "partitions": artifacts["partitions"]})
    _write_json(output_dir / ROLLBACK_EVIDENCE, artifacts["rollback"])
    _write_json(output_dir / COVERAGE, artifacts["coverage"])
    _write_json(output_dir / RAW_ATTESTATION, artifacts["raw_attestation"])

    base_names = [PUBLIC_TELEMETRY, PRIVATE_LEDGER, PRE_LABEL_PARTITIONS, ROLLBACK_EVIDENCE, COVERAGE]
    base_hashes = _hash_written_artifacts(output_dir, base_names)
    command_argv = _canonical_command(args)
    manifest = {
        "artifact_hashes": base_hashes,
        "artifact_paths": {
            "actual_coverage": COVERAGE,
            "harness_manifest": MANIFEST,
            "pre_label_partitions": PRE_LABEL_PARTITIONS,
            "private_injection_ledger": PRIVATE_LEDGER,
            "provenance_hashes": PROVENANCE_HASHES,
            "public_telemetry": PUBLIC_TELEMETRY,
            "rollback_evidence": ROLLBACK_EVIDENCE,
        },
        "artifacts": {
            "actual_coverage": COVERAGE,
            "harness_manifest": MANIFEST,
            "pre_label_partitions": PRE_LABEL_PARTITIONS,
            "private_injection_ledger": PRIVATE_LEDGER,
            "provenance_hashes": PROVENANCE_HASHES,
            "public_telemetry": PUBLIC_TELEMETRY,
            "rollback_evidence": ROLLBACK_EVIDENCE,
        },
        "authority": artifacts["authority"],
        "authority_counters": artifacts["authority_counters"],
        "canonical_artifact_root_hash": _sha256_text(_stable_json(base_hashes)),
        "command_argv": command_argv,
        "command_argv_sha256": _sha256_text(_stable_json(command_argv)),
        "created_at": args.created_at,
        "host": args.host,
        "implementation_guard": {
            "materialized_without_http_serving": False,
            "uses_ops_cat_production_adapter": False,
        },
        "mode": args.mode,
        "program_version": PROGRAM_VERSION,
        "rollback_evidence_hash": base_hashes[ROLLBACK_EVIDENCE],
        "runtime_attestation": {
            "capability": "loopback_threading_http_server",
            "kind": "actual_threading_http_server",
        },
        "schedule": {
            "baseline_slots": [artifacts["baseline_slots"][0], artifacts["baseline_slots"][-1]],
            "canary_slots": artifacts["canary_slots"],
            "fault_tick": args.fault_tick,
            "requests_per_tick": args.requests_per_tick,
            "tick_seconds": args.tick_seconds,
            "ticks": args.ticks,
        },
        "seed": args.seed,
        "source_hashes": {
            "coverage": base_hashes[COVERAGE],
            "injection_ledger": base_hashes[PRIVATE_LEDGER],
            "pre_label_partitions": base_hashes[PRE_LABEL_PARTITIONS],
            "public_telemetry": base_hashes[PUBLIC_TELEMETRY],
            "rollback_evidence": base_hashes[ROLLBACK_EVIDENCE],
        },
        "source_key": "p105-isolated-local-deploy-canary",
        "verifier_compatibility": {
            "authority_counter_must_be_zero": True,
            "fail_closed_hash_fields": ["rollback_evidence_hash", "artifact_hashes", "source_hashes", "command_argv", "authority_counters"],
            "manifest_schema": "p105.deploy.harness.manifest.v1",
            "raw_attestation_separated": True,
        },
    }
    _write_json(output_dir / MANIFEST, manifest)

    provenance_names = [*base_names, MANIFEST]
    provenance = {
        "artifact_hashes": _hash_written_artifacts(output_dir, provenance_names),
        "command_argv_sha256": manifest["command_argv_sha256"],
        "hash_algorithm": "sha256",
        "program_version": PROGRAM_VERSION,
        "script_hash": _sha256_bytes(Path(__file__).read_bytes()),
    }
    _write_json(output_dir / PROVENANCE_HASHES, provenance)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize deterministic P105 isolated deploy canary evidence.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--ticks", required=True, type=int)
    parser.add_argument("--tick-seconds", required=True, type=int)
    parser.add_argument("--requests-per-tick", required=True, type=int)
    parser.add_argument("--fault-tick", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", required=True, choices=["isolated-local"])
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--expect-rollback-trigger-tick", type=int)
    parser.add_argument("--expect-rollback-observed-tick", type=int)
    parser.add_argument("--test-fast-runtime", action="store_true")
    parser.add_argument("--expect-no-production-authority", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _write_artifacts(args)
    except ValueError as exc:
        print(f"p105 deploy harness failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
