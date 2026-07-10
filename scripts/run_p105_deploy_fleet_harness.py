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

PROFILE = "p105.actual-fleet-soak.256x1h.v1"
DIAGNOSTIC_PROFILE = "p105.deploy-fleet.diagnostic.fast.v1"
SCHEMA_VERSION = "p105.deploy.fleet_harness.v1"
ADAPTER_VERSION = "p105.adapter.threading-http-deploy-fleet-harness.v1"

PUBLIC_TELEMETRY = "p105-deploy-fleet-public-telemetry.jsonl"
PRIVATE_LEDGER = "p105-deploy-fleet-private-injection-ledger.json"
COVERAGE = "p105-deploy-fleet-coverage.json"
PARTITIONS = "p105-deploy-fleet-pre-label-partitions.json"
RAW_ATTESTATION = "p105-deploy-fleet-runtime-attestation.raw.json"
MANIFEST = "p105-deploy-fleet-harness-manifest.json"
PROVENANCE_HASHES = "p105-deploy-fleet-provenance-hashes.json"

PROGRAM_VERSION = "p105.deploy.fleet.diagnostic.v1"
CONFIG_VERSION = "deploy-fleet-diagnostic-config-v1"
FAULTED_CONFIG_VERSION = "deploy-fleet-diagnostic-config-fault-v1"
SERVICE_COUNT = 256
HELD_OUT_COUNT = 128
SHADOW_COUNT = 128
FULL_REQUESTED_SECONDS = 3600
CADENCE_SECONDS = 5
FULL_SAMPLES_PER_SERVICE = 720
FULL_REQUESTS = 184_320
DIAGNOSTIC_REQUESTED_SECONDS = 30
DIAGNOSTIC_SAMPLES_PER_SERVICE = 6
DIAGNOSTIC_REQUESTS = 1_536
KINDS = [
    "canary_error_regression",
    "latency_regression",
    "configuration_mismatch",
    "bounded_rollback_delay",
]


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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _service_id(index: int) -> str:
    return f"p105.fleet.deploy.{index:03d}"


def _service_path(index: int) -> str:
    return f"/p105/fleet/deploy/{index:03d}"


def _split_for_service(index: int) -> str:
    return "held_out" if index < 128 else "real_derived_shadow"


def _source_window_id(split: str, service_index: int, sample_ordinal: int) -> str:
    return f"p105-fleet-deploy-{split}-svc{service_index:03d}-sample{sample_ordinal:03d}"


def _is_diagnostic(args: argparse.Namespace) -> bool:
    return args.profile == DIAGNOSTIC_PROFILE


def _is_full_profile(args: argparse.Namespace) -> bool:
    return args.profile == PROFILE


def _sample_offsets(args: argparse.Namespace) -> list[int]:
    return [index * args.sample_cadence_seconds for index in range(args.samples_per_service)]


def _profile_config_hash(args: argparse.Namespace) -> str:
    return _sha256_text(
        _stable_json(
            {
                "adapter_key": "deploy_fleet",
                "adapter_version": ADAPTER_VERSION,
                "cadence_seconds": args.sample_cadence_seconds,
                "max_requests": args.max_requests,
                "profile": args.profile,
                "requested_seconds": args.requested_seconds,
                "schema_version": SCHEMA_VERSION,
                "services": [_service_id(index) for index in range(args.services)],
            }
        )
    )


def _private_schedule() -> list[dict[str, Any]]:
    incidents: list[dict[str, Any]] = []
    for split, base in (("held_out", 0), ("real_derived_shadow", 128)):
        for group in range(8):
            start = 1500 + (30 * group)
            affected_indexes = [base + (4 * group) + offset for offset in range(4)]
            incidents.append(
                {
                    "affected_services": [_service_id(index) for index in affected_indexes],
                    "bound_public_source_window_ids": [],
                    "expected_bound_public_source_window_ids": [
                        _source_window_id(split, service_index, ordinal) for service_index in affected_indexes for ordinal in range(start // 5, (start + 300) // 5 + 1)
                    ],
                    "group_id": f"g{group:02d}",
                    "incident_group_id": f"p105-fleet-deploy-{split}-g{group:02d}",
                    "kind": KINDS[group % len(KINDS)],
                    "lead_range_minutes": [25, 30],
                    "precursor_end_offset_seconds": start + 300,
                    "precursor_start_offset_seconds": start,
                    "private_failure_offset_seconds": 3300 + (30 * group),
                    "split": split,
                }
            )
    return incidents


def _private_schedule_with_binding(observed_source_window_ids: set[str], *, bind_observed: bool) -> list[dict[str, Any]]:
    incidents = _private_schedule()
    for incident in incidents:
        expected = incident["expected_bound_public_source_window_ids"]
        incident["bound_public_source_window_ids"] = [window_id for window_id in expected if window_id in observed_source_window_ids] if bind_observed else []
    return incidents


def _incident_indexes_by_sample() -> set[tuple[int, int]]:
    faulted: set[tuple[int, int]] = set()
    for incident in _private_schedule():
        start_ordinal = int(incident["precursor_start_offset_seconds"]) // CADENCE_SECONDS
        end_ordinal = int(incident["precursor_end_offset_seconds"]) // CADENCE_SECONDS
        for service_id in incident["affected_services"]:
            service_index = int(str(service_id).rsplit(".", 1)[1])
            for ordinal in range(start_ordinal, end_ordinal + 1):
                faulted.add((service_index, ordinal))
    return faulted


def _status_code_for_fault(faulted: bool) -> int:
    return 503 if faulted else 200


@dataclass
class RuntimeState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    active_operations: int = 0
    live_sockets: int = 0
    peak_operations: int = 0
    peak_live_sockets: int = 0
    observations: list[dict[str, Any]] = field(default_factory=list)
    observed_remote_hosts: set[str] = field(default_factory=set)

    def begin_operation(self) -> None:
        with self.lock:
            self.active_operations += 1
            self.live_sockets += 1
            self.peak_operations = max(self.peak_operations, self.active_operations)
            self.peak_live_sockets = max(self.peak_live_sockets, self.live_sockets)

    def end_operation(self) -> None:
        with self.lock:
            self.active_operations -= 1
            self.live_sockets -= 1

    def record(self, row: dict[str, Any], remote_host: str) -> None:
        with self.lock:
            self.observations.append(row)
            self.observed_remote_hosts.add(remote_host)


def _make_handler(state: RuntimeState, *, max_response_body_bytes: int) -> type[BaseHTTPRequestHandler]:
    class DeployFleetHandler(BaseHTTPRequestHandler):
        server_version = "P105DeployFleetLoopback/1"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            service_index = int(params.get("service_index", ["0"])[0])
            sample_ordinal = int(params.get("sample_ordinal", ["0"])[0])
            split = _split_for_service(service_index)
            faulted = params.get("faulted", ["0"])[0] == "1"
            status_code = _status_code_for_fault(faulted)
            version = FAULTED_CONFIG_VERSION if faulted else CONFIG_VERSION
            body = _stable_json(
                {
                    "configuration_fingerprint": _sha256_text(version)[:16],
                    "rollback_state": "diagnostic_noop",
                    "service_id": _service_id(service_index),
                    "status_code": status_code,
                    "version": version,
                }
            ).encode("utf-8")
            if len(body) > max_response_body_bytes:
                status_code = 500
                body = b"{}"
            now_ns = time.monotonic_ns()
            row = {
                "body_sha256": _sha256_bytes(body),
                "canary_cohort": "diagnostic",
                "configuration_fingerprint": _sha256_text(version)[:16],
                "monotonic_ns": now_ns,
                "rollback_state": "diagnostic_noop",
                "sample_ordinal": sample_ordinal,
                "service_id": _service_id(service_index),
                "service_path": _service_path(service_index),
                "source_window_id": _source_window_id(split, service_index, sample_ordinal),
                "split": split,
                "status_code": status_code,
                "version": version,
            }
            state.record(row, self.client_address[0])
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return DeployFleetHandler


@dataclass
class ServerBinding:
    server: ThreadingHTTPServer
    thread: threading.Thread
    port: int


def _start_server(args: argparse.Namespace, state: RuntimeState) -> ServerBinding:
    server = ThreadingHTTPServer(
        (args.host, 0),
        _make_handler(state, max_response_body_bytes=args.max_response_body_bytes),
    )
    thread = threading.Thread(target=server.serve_forever, name="p105-deploy-fleet-http-server", daemon=True)
    thread.start()
    return ServerBinding(server=server, thread=thread, port=int(server.server_address[1]))


def _stop_server(binding: ServerBinding) -> None:
    binding.server.shutdown()
    binding.server.server_close()
    binding.thread.join(timeout=5)


def _client_get(args: argparse.Namespace, port: int, path: str, state: RuntimeState) -> tuple[int, bytes, int]:
    state.begin_operation()
    started_ns = time.monotonic_ns()
    connection = http.client.HTTPConnection(args.host, port, timeout=args.request_timeout_seconds)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read(args.max_response_body_bytes + 1)
        latency_ns = time.monotonic_ns() - started_ns
        if len(body) > args.max_response_body_bytes:
            raise ValueError("response body exceeded configured maximum")
        return int(response.status), body, latency_ns
    finally:
        connection.close()
        state.end_operation()


def _validate_args(args: argparse.Namespace) -> None:
    if not args.expect_no_production_authority:
        raise ValueError("--expect-no-production-authority is required")
    if args.host != "127.0.0.1":
        raise ValueError("deploy fleet harness is restricted to 127.0.0.1 loopback")
    if args.mode != "isolated-local":
        raise ValueError("deploy fleet harness supports only isolated-local mode")
    if args.test_fast_diagnostic and not _is_diagnostic(args):
        raise ValueError("--test-fast-diagnostic is only valid with the diagnostic profile")
    if not args.test_fast_diagnostic and _is_diagnostic(args):
        raise ValueError("diagnostic profile requires --test-fast-diagnostic")
    if not (_is_diagnostic(args) or _is_full_profile(args)):
        raise ValueError(f"profile must be {PROFILE!r} or {DIAGNOSTIC_PROFILE!r}")
    expected = {
        "heldout_services": HELD_OUT_COUNT,
        "max_concurrency": 64,
        "max_live_sockets": 64,
        "max_memory_mib": 512,
        "max_output_mib": 256,
        "max_response_body_bytes": 1024,
        "request_timeout_seconds": 2,
        "sample_cadence_seconds": CADENCE_SECONDS,
        "services": SERVICE_COUNT,
        "shadow_services": SHADOW_COUNT,
    }
    if _is_diagnostic(args):
        expected.update(
            {
                "max_requests": DIAGNOSTIC_REQUESTS,
                "requested_seconds": DIAGNOSTIC_REQUESTED_SECONDS,
                "samples_per_service": DIAGNOSTIC_SAMPLES_PER_SERVICE,
            }
        )
    else:
        expected.update(
            {
                "max_requests": FULL_REQUESTS,
                "requested_seconds": FULL_REQUESTED_SECONDS,
                "samples_per_service": FULL_SAMPLES_PER_SERVICE,
            }
        )
    for key, expected_value in expected.items():
        if getattr(args, key) != expected_value:
            raise ValueError(f"{key.replace('_', '-')} must be {expected_value!r} for {args.profile}")
    if args.heldout_services + args.shadow_services != args.services:
        raise ValueError("heldout and shadow services must exactly cover the declared services")
    if args.max_requests != args.services * args.samples_per_service:
        raise ValueError("max requests must equal services * samples per service")
    if args.inject_telemetry_loss_at_sample is not None and not 0 <= args.inject_telemetry_loss_at_sample < args.samples_per_service:
        raise ValueError("--inject-telemetry-loss-at-sample is outside the sampled diagnostic range")


def _build_telemetry(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state = RuntimeState()
    started_ns = time.monotonic_ns()
    binding = _start_server(args, state)
    telemetry: list[dict[str, Any]] = []
    client_latency_observations: list[dict[str, Any]] = []
    telemetry_loss = args.inject_telemetry_loss_at_sample is not None
    faulted_indexes = _incident_indexes_by_sample()
    shutdown_complete = not args.inject_server_shutdown_failure
    stop_error: str | None = None

    try:
        for sample_ordinal, sample_offset in enumerate(_sample_offsets(args)):
            if _is_full_profile(args):
                target_ns = started_ns + (sample_offset * 1_000_000_000)
                remaining_seconds = (target_ns - time.monotonic_ns()) / 1_000_000_000
                if remaining_seconds > 0:
                    time.sleep(remaining_seconds)
            for service_index in range(args.services):
                split = _split_for_service(service_index)
                faulted = sample_ordinal == 1 if _is_diagnostic(args) else (service_index, sample_ordinal) in faulted_indexes
                path = f"{_service_path(service_index)}?service_index={service_index}&sample_ordinal={sample_ordinal}&faulted={int(faulted)}"
                status_code, body, latency_ns = _client_get(args, binding.port, path, state)
                source_window_id = _source_window_id(split, service_index, sample_ordinal)
                client_latency_observations.append(
                    {
                        "latency_ns": latency_ns,
                        "source_window_id": source_window_id,
                    }
                )
                if args.inject_telemetry_loss_at_sample == sample_ordinal:
                    continue
                version = FAULTED_CONFIG_VERSION if faulted else CONFIG_VERSION
                telemetry_basis = {
                    "canary_cohort": "diagnostic" if _is_diagnostic(args) else ("held_out" if split == "held_out" else "shadow"),
                    "configuration_fingerprint": _sha256_text(version)[:16],
                    "latency_bucket_ms": "observed",
                    "request_host": args.host,
                    "rollback_state": "diagnostic_noop",
                    "sample_offset_seconds": sample_offset,
                    "sample_ordinal": sample_ordinal,
                    "schema_version": "p105.deploy.fleet.public_telemetry.v1",
                    "service_id": _service_id(service_index),
                    "service_path": _service_path(service_index),
                    "source_key": "p105-deploy-fleet-diagnostic" if _is_diagnostic(args) else "p105-deploy-fleet-actual-soak",
                    "source_window_id": source_window_id,
                    "split": split,
                    "status_code": status_code,
                    "version_hash": _sha256_text(version)[:16],
                    "response_body_sha256": _sha256_bytes(body),
                }
                telemetry.append(
                    {
                        **telemetry_basis,
                        "materialized_record_hash": _sha256_text(_stable_json(telemetry_basis)),
                    }
                )
    finally:
        finished_ns = time.monotonic_ns()
        try:
            _stop_server(binding)
        except OSError as exc:
            shutdown_complete = False
            stop_error = str(exc)

    raw_attestation = {
        "bind_host": args.host,
        "diagnostic_not_receipt_eligible": _is_diagnostic(args),
        "client_latency_observations": client_latency_observations,
        "handler_observations": state.observations,
        "monotonic_finished_ns": finished_ns,
        "monotonic_started_ns": started_ns,
        "observation_count": len(state.observations),
        "observed_remote_hosts": sorted(state.observed_remote_hosts),
        "process_id": os.getpid(),
        "server_class": "http.server.ThreadingHTTPServer",
        "server_thread_id": binding.thread.ident,
        "server_thread_name": binding.thread.name,
    }
    cleanup: dict[str, Any] = {
        "external_resources_mutated": False,
        "server_shutdown_complete": shutdown_complete,
    }
    if args.inject_server_shutdown_failure:
        cleanup["injected_shutdown_failure"] = True
    if stop_error is not None:
        cleanup["server_shutdown_error"] = stop_error
    runtime = {
        "cleanup": cleanup,
        "raw_attestation": raw_attestation,
        "resource_observations": {
            "peak_concurrent_client_handler_operations": state.peak_operations,
            "peak_live_sockets": state.peak_live_sockets,
        },
        "telemetry_loss": telemetry_loss,
    }
    return telemetry, runtime


def _observed_coverage_segments(telemetry: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_service: dict[str, list[dict[str, Any]]] = {}
    for row in telemetry:
        by_service.setdefault(str(row["service_id"]), []).append(row)

    segments: list[dict[str, Any]] = []
    total_ns = 0
    for service_id in sorted(by_service):
        rows = sorted(by_service[service_id], key=lambda row: int(row["sample_ordinal"]))
        current_segment: list[dict[str, Any]] = []
        for row in rows:
            if not current_segment:
                current_segment = [row]
                continue
            previous = current_segment[-1]
            ordinal_delta = int(row["sample_ordinal"]) - int(previous["sample_ordinal"])
            monotonic_delta_ns = int(row["telemetry_monotonic_ns"]) - int(previous["telemetry_monotonic_ns"])
            if ordinal_delta == 1 and 4_000_000_000 <= monotonic_delta_ns <= 7_500_000_000:
                current_segment.append(row)
                continue
            segment = _deploy_coverage_segment(service_id, current_segment)
            if segment is not None:
                segments.append(segment)
                total_ns += int(segment["conservative_duration_seconds"]) * 1_000_000_000
            current_segment = [row]
        segment = _deploy_coverage_segment(service_id, current_segment)
        if segment is not None:
            segments.append(segment)
            total_ns += int(segment["conservative_duration_seconds"]) * 1_000_000_000
    return segments, total_ns


def _deploy_coverage_segment(service_id: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(rows) < 2:
        return None
    observed_ns = max(0, int(rows[-1]["telemetry_monotonic_ns"]) - int(rows[0]["telemetry_monotonic_ns"]))
    conservative_seconds = min((len(rows) - 1) * CADENCE_SECONDS, int((observed_ns / 1_000_000_000) // CADENCE_SECONDS) * CADENCE_SECONDS)
    if conservative_seconds <= 0:
        return None
    return {
        "conservative_duration_seconds": conservative_seconds,
        "coverage_source": "receipt_bound_adjacent_monotonic_samples",
        "end_sample_ordinal": int(rows[-1]["sample_ordinal"]),
        "end_source_window_id": rows[-1]["source_window_id"],
        "sample_count": len(rows),
        "service_id": service_id,
        "split": rows[0]["split"],
        "start_sample_ordinal": int(rows[0]["sample_ordinal"]),
        "start_source_window_id": rows[0]["source_window_id"],
    }


def _coverage(args: argparse.Namespace, telemetry: list[dict[str, Any]]) -> dict[str, Any]:
    if _is_diagnostic(args):
        segments: list[dict[str, Any]] = []
        total_ns = 0
    else:
        segments, total_ns = _observed_coverage_segments(telemetry)
    coverage_seconds = total_ns / 1_000_000_000
    return {
        "canonical_segments": segments,
        "coverage_source": "receipt_bound_adjacent_monotonic_samples",
        "diagnostic_only": _is_diagnostic(args),
        "family_observed_duration_ns": {"deploy": total_ns},
        "family_seconds": {"deploy": coverage_seconds},
        "full_profile_theoretical_bounds": {
            "adjacent_intervals_per_service": FULL_SAMPLES_PER_SERVICE - 1,
            "max_seconds_per_family": 920_320,
            "max_seconds_per_service": 3595,
            "max_seconds_per_split": 460_160,
            "samples_per_service": FULL_SAMPLES_PER_SERVICE,
        },
        "rejects_legacy_created_at_tick_seconds_path": True,
        "release_floor_credit_seconds": coverage_seconds,
        "requested_duration_substitutes_for_observed_duration": False,
    }


def _hash_written_artifacts(output_dir: Path, names: list[str]) -> dict[str, str]:
    return {name: _sha256_bytes((output_dir / name).read_bytes()) for name in names}


def finalize_existing_output(output_dir: Path) -> dict[str, Any]:
    """Bind an already completed deploy fleet run to the closed artifact contract."""

    manifest_path = output_dir / MANIFEST
    required_names = [PUBLIC_TELEMETRY, PRIVATE_LEDGER, COVERAGE, RAW_ATTESTATION, MANIFEST]
    missing = [name for name in required_names if not (output_dir / name).is_file()]
    if missing:
        raise ValueError(f"deploy fleet output is incomplete: {','.join(missing)}")

    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("deploy fleet finalizer requires the closed fleet schema")
    if manifest.get("adapter_key") != "deploy_fleet" or manifest.get("adapter_version") != ADAPTER_VERSION:
        raise ValueError("deploy fleet finalizer requires the closed fleet adapter")
    partitions = manifest.get("partitions")
    if not isinstance(partitions, dict):
        raise ValueError("deploy fleet finalizer requires embedded pre-label partitions")
    held_out = partitions.get("held_out")
    shadow = partitions.get("real_derived_shadow")
    if not isinstance(held_out, list) or not isinstance(shadow, list) or not held_out or not shadow:
        raise ValueError("deploy fleet finalizer requires both pre-label partitions")

    _write_json(
        output_dir / PARTITIONS,
        {
            "assigned_before_private_schedule_loading": True,
            "held_out": held_out,
            "real_derived_shadow": shadow,
            "schema_version": "p105.deploy.fleet.pre_label_partition.v1",
        },
    )
    provenance_path = output_dir / PROVENANCE_HASHES
    existing_provenance = _read_json(provenance_path) if provenance_path.is_file() else {}
    manifest["program_version"] = str(existing_provenance.get("program_version") or PROGRAM_VERSION)
    manifest["artifact_paths"] = {
        "coverage": COVERAGE,
        "partitions": PARTITIONS,
        "private_injection_ledger": PRIVATE_LEDGER,
        "provenance_hashes": PROVENANCE_HASHES,
        "public_telemetry": PUBLIC_TELEMETRY,
        "raw_attestation": RAW_ATTESTATION,
    }
    canonical_payload_names = [PUBLIC_TELEMETRY, PRIVATE_LEDGER, COVERAGE, PARTITIONS]
    manifest["artifact_hashes"] = _hash_written_artifacts(output_dir, canonical_payload_names)
    _write_json(manifest_path, manifest)

    all_payload_names = [*canonical_payload_names, RAW_ATTESTATION]
    provenance = {
        "artifact_hashes": _hash_written_artifacts(output_dir, [*all_payload_names, MANIFEST]),
        "hash_algorithm": "sha256",
        "program_version": str(existing_provenance.get("program_version") or PROGRAM_VERSION),
        "script_hash": str(existing_provenance.get("script_hash") or _sha256_bytes(Path(__file__).read_bytes())),
    }
    _write_json(provenance_path, provenance)
    return manifest


def _command_argv(args: argparse.Namespace) -> list[str]:
    command = [
        "python",
        "scripts/run_p105_deploy_fleet_harness.py",
        "--host",
        args.host,
        "--seed",
        str(args.seed),
        "--profile",
        args.profile,
        "--services",
        str(args.services),
        "--heldout-services",
        str(args.heldout_services),
        "--shadow-services",
        str(args.shadow_services),
        "--requested-seconds",
        str(args.requested_seconds),
        "--sample-cadence-seconds",
        str(args.sample_cadence_seconds),
        "--samples-per-service",
        str(args.samples_per_service),
        "--max-requests",
        str(args.max_requests),
        "--max-concurrency",
        str(args.max_concurrency),
        "--max-live-sockets",
        str(args.max_live_sockets),
        "--request-timeout-seconds",
        str(args.request_timeout_seconds),
        "--max-response-body-bytes",
        str(args.max_response_body_bytes),
        "--max-memory-mib",
        str(args.max_memory_mib),
        "--max-output-mib",
        str(args.max_output_mib),
        "--output-dir",
        "<output-dir>",
        "--mode",
        args.mode,
        "--created-at",
        args.created_at,
    ]
    if args.test_fast_diagnostic:
        command.append("--test-fast-diagnostic")
    command.append("--expect-no-production-authority")
    if args.inject_telemetry_loss_at_sample is not None:
        command.extend(["--inject-telemetry-loss-at-sample", str(args.inject_telemetry_loss_at_sample)])
    if args.inject_server_shutdown_failure:
        command.append("--inject-server-shutdown-failure")
    return command


def _write_artifacts(args: argparse.Namespace) -> None:
    _validate_args(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    telemetry, runtime = _build_telemetry(args)
    observations_by_window = {observation["source_window_id"]: observation for observation in runtime["raw_attestation"]["handler_observations"]}
    for row in telemetry:
        matching = observations_by_window[row["source_window_id"]]
        row["telemetry_monotonic_ns"] = matching["monotonic_ns"]
    coverage = _coverage(args, telemetry)
    for row in telemetry:
        row.pop("telemetry_monotonic_ns", None)
        row.pop("observed_latency_ns", None)
    profile_hash = _profile_config_hash(args)
    observed_source_window_ids = {str(row["source_window_id"]) for row in telemetry}
    incidents = _private_schedule_with_binding(observed_source_window_ids, bind_observed=_is_full_profile(args))
    ledger = {
        "incidents": incidents,
        "label_join_phase": "after_sampling_and_partition",
        "private_schedule_loaded_after_profile_hash": True,
        "profile_config_hash": profile_hash,
    }

    _write_jsonl(output_dir / PUBLIC_TELEMETRY, telemetry)
    _write_json(output_dir / PRIVATE_LEDGER, ledger)
    _write_json(output_dir / COVERAGE, coverage)
    _write_json(output_dir / RAW_ATTESTATION, runtime["raw_attestation"])

    expected_coverage_seconds = args.services * max(args.samples_per_service - 1, 0) * args.sample_cadence_seconds
    canonical_segments = coverage["canonical_segments"]
    coverage_complete = (
        len(canonical_segments) == args.services
        and coverage["family_seconds"]["deploy"] == expected_coverage_seconds
        and all(
            int(segment["sample_count"]) == args.samples_per_service
            and int(segment["start_sample_ordinal"]) == 0
            and int(segment["end_sample_ordinal"]) == args.samples_per_service - 1
            and int(segment["conservative_duration_seconds"]) == max(args.samples_per_service - 1, 0) * args.sample_cadence_seconds
            for segment in canonical_segments
        )
    )
    schedule_binding_complete = all(incident["bound_public_source_window_ids"] == incident["expected_bound_public_source_window_ids"] for incident in incidents)
    complete = (
        len(telemetry) == args.max_requests
        and runtime["raw_attestation"]["observation_count"] == args.max_requests
        and coverage_complete
        and schedule_binding_complete
        and runtime["cleanup"]["server_shutdown_complete"]
        and not runtime["telemetry_loss"]
        and runtime["resource_observations"]["peak_concurrent_client_handler_operations"] <= args.max_concurrency
        and runtime["resource_observations"]["peak_live_sockets"] <= args.max_live_sockets
    )
    validation_error_codes = []
    if _is_diagnostic(args):
        validation_error_codes.append("fast_diagnostic_non_counting")
    if runtime["telemetry_loss"]:
        validation_error_codes.append("telemetry_loss")
    if not runtime["cleanup"]["server_shutdown_complete"]:
        validation_error_codes.append("server_shutdown_incomplete")
    if _is_full_profile(args) and not complete:
        validation_error_codes.append("full_profile_incomplete")

    service_ids = [_service_id(index) for index in range(args.services)]
    release_floor_credit = {
        "coverage_observed_duration_ns": coverage["family_observed_duration_ns"]["deploy"],
        "coverage_seconds": coverage["family_seconds"]["deploy"],
        "groups": 16 if complete and _is_full_profile(args) else 0,
        "positives": 64 if complete and _is_full_profile(args) else 0,
        "rows": len(telemetry) if complete and _is_full_profile(args) else 0,
    }
    manifest = {
        "adapter_key": "deploy_fleet",
        "adapter_version": ADAPTER_VERSION,
        "authority": {
            "action_executed": False,
            "action_plan_created": False,
            "auth_enabled": False,
            "credentials_read": False,
            "deployment_api": False,
            "external_host": False,
            "production_endpoint": False,
            "production_mutation": False,
        },
        "cleanup": runtime["cleanup"],
        "command_argv": _command_argv(args),
        "created_at": args.created_at,
        "diagnostic_profile": {"enabled": _is_diagnostic(args), "runtime_qualification_eligible": False},
        "mode": args.mode,
        "partitions": {
            "held_out": service_ids[: args.heldout_services],
            "real_derived_shadow": service_ids[args.heldout_services :],
        },
        "profile": args.profile,
        "profile_config_hash": profile_hash,
        "request_cap": args.max_requests,
        "requested_seconds": args.requested_seconds,
        "resource_limits": {
            "max_concurrent_client_handler_operations": args.max_concurrency,
            "max_live_sockets": args.max_live_sockets,
            "max_memory_mib": args.max_memory_mib,
            "max_output_mib": args.max_output_mib,
            "max_response_body_bytes": args.max_response_body_bytes,
            "request_timeout_seconds": args.request_timeout_seconds,
        },
        "resource_observations": runtime["resource_observations"],
        "runtime_attestation": {
            "capability": "loopback_threading_http_server",
            "kind": "actual_threading_http_server",
        },
        "runtime_candidate_status": {
            "complete_profile_observed": complete,
            "harness_issues_receipts": False,
            "release_floor_credit": release_floor_credit,
            "runtime_qualification_eligible": complete and _is_full_profile(args),
            "validation_error_codes": validation_error_codes,
        },
        "sample_cadence_seconds": args.sample_cadence_seconds,
        "sample_offsets_seconds": _sample_offsets(args),
        "samples_per_service": args.samples_per_service,
        "schema_version": SCHEMA_VERSION,
        "seed": args.seed,
        "service_paths": [_service_path(index) for index in range(args.services)],
        "source_key": "p105-deploy-fleet-diagnostic" if _is_diagnostic(args) else "p105-deploy-fleet-actual-soak",
    }
    _write_json(output_dir / MANIFEST, manifest)

    names = [PUBLIC_TELEMETRY, PRIVATE_LEDGER, COVERAGE, RAW_ATTESTATION, MANIFEST]
    provenance = {
        "artifact_hashes": _hash_written_artifacts(output_dir, names),
        "hash_algorithm": "sha256",
        "program_version": PROGRAM_VERSION,
        "script_hash": _sha256_bytes(Path(__file__).read_bytes()),
    }
    _write_json(output_dir / PROVENANCE_HASHES, provenance)
    finalize_existing_output(output_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run non-counting P105 deploy fleet diagnostic evidence.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--services", required=True, type=int)
    parser.add_argument("--heldout-services", required=True, type=int)
    parser.add_argument("--shadow-services", required=True, type=int)
    parser.add_argument("--requested-seconds", required=True, type=int)
    parser.add_argument("--sample-cadence-seconds", required=True, type=int)
    parser.add_argument("--samples-per-service", required=True, type=int)
    parser.add_argument("--max-requests", required=True, type=int)
    parser.add_argument("--max-concurrency", required=True, type=int)
    parser.add_argument("--max-live-sockets", required=True, type=int)
    parser.add_argument("--request-timeout-seconds", required=True, type=int)
    parser.add_argument("--max-response-body-bytes", required=True, type=int)
    parser.add_argument("--max-memory-mib", required=True, type=int)
    parser.add_argument("--max-output-mib", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--test-fast-diagnostic", action="store_true")
    parser.add_argument("--expect-no-production-authority", action="store_true")
    parser.add_argument("--inject-telemetry-loss-at-sample", type=int)
    parser.add_argument("--inject-server-shutdown-failure", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _write_artifacts(args)
    except ValueError as exc:
        print(f"p105 deploy fleet harness failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
