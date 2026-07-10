from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROGRAM_VERSION = "p105.deploy.canary.v1"
PARTITION_SALT = "p105.deploy.partition.v1"
PUBLIC_TELEMETRY = "p105-deploy-public-telemetry.jsonl"
PRIVATE_LEDGER = "p105-deploy-private-injection-ledger.json"
PRE_LABEL_PARTITIONS = "p105-deploy-pre-label-partitions.json"
ROLLBACK_EVIDENCE = "p105-deploy-rollback-evidence.json"
COVERAGE = "p105-deploy-coverage.json"
MANIFEST = "p105-deploy-harness-manifest.json"
PROVENANCE_HASHES = "p105-deploy-provenance-hashes.json"


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


def _bucket_latency(latency_ms: int) -> str:
    if latency_ms <= 50:
        return "000-050"
    if latency_ms <= 100:
        return "051-100"
    return "101-plus"


def _partition_for_request(request_id: str) -> dict[str, str]:
    digest = _sha256_text(f"{PARTITION_SALT}:{request_id}")
    return {
        "partition_hash": digest,
        "partition_id": "held_out_test" if int(digest[:2], 16) < 0x80 else "real_derived_shadow",
    }


def _canonical_command(args: argparse.Namespace) -> list[str]:
    return [
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
        "--expect-no-production-authority",
    ]


def _status_for_request(
    *,
    tick: int,
    slot: int,
    canary_sequence: int,
    fault_tick: int,
    rollback_observed_tick: int,
) -> tuple[str, str, int, int]:
    cohort = "canary" if slot in (8, 9) else "control"
    if cohort == "control":
        return cohort, "control-v1", 200, 42 + (slot % 3)
    if tick < fault_tick or tick >= rollback_observed_tick:
        return cohort, "canary-config-v2-good", 200, 45 + (slot - 8)
    status_code = 503 if canary_sequence % 4 == 0 else 200
    latency_ms = 80 if status_code == 503 else 64 + (slot - 8)
    return cohort, "canary-config-v2-bad", status_code, latency_ms


def _rolling_error_rate(
    recent_status_codes: list[int],
    *,
    window_size: int,
) -> float:
    window = recent_status_codes[-window_size:]
    if not window:
        return 0.0
    return round(sum(1 for status in window if status >= 500) / len(window), 6)


def _build_artifacts(args: argparse.Namespace) -> dict[str, Any]:
    baseline_slots = list(range(0, 8))
    canary_slots = [8, 9]
    rollback_trigger_tick = args.fault_tick + 69
    rollback_observed_tick = rollback_trigger_tick + 1
    if args.expect_rollback_trigger_tick is not None and args.expect_rollback_trigger_tick != rollback_trigger_tick:
        raise ValueError(f"expected rollback trigger tick {args.expect_rollback_trigger_tick}, computed {rollback_trigger_tick}")
    if args.expect_rollback_observed_tick is not None and args.expect_rollback_observed_tick != rollback_observed_tick:
        raise ValueError(f"expected rollback observed tick {args.expect_rollback_observed_tick}, computed {rollback_observed_tick}")

    telemetry: list[dict[str, Any]] = []
    partitions: list[dict[str, Any]] = []
    canary_statuses: list[int] = []
    control_statuses: list[int] = []
    injection_request_ids: list[str] = []
    rollback_trigger_request_ids: list[str] = []
    canary_sequence = 0
    rolling_window = 140

    for tick in range(args.ticks):
        for slot in range(args.requests_per_tick):
            request_id = f"p105-deploy-{args.seed}-{tick:04d}-{slot:02d}"
            if slot in canary_slots:
                canary_sequence += 1
            cohort, version, status_code, latency_ms = _status_for_request(
                tick=tick,
                slot=slot,
                canary_sequence=canary_sequence,
                fault_tick=args.fault_tick,
                rollback_observed_tick=rollback_observed_tick,
            )
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
            if cohort == "canary":
                canary_statuses.append(status_code)
                rolling_error_rate = _rolling_error_rate(canary_statuses, window_size=rolling_window)
                if args.fault_tick <= tick < rollback_observed_tick:
                    injection_request_ids.append(request_id)
                if tick == rollback_trigger_tick:
                    rollback_trigger_request_ids.append(request_id)
            else:
                control_statuses.append(status_code)
                rolling_error_rate = _rolling_error_rate(control_statuses, window_size=rolling_window * 4)
            rollback_state = "not_triggered"
            if tick == rollback_trigger_tick:
                rollback_state = "triggered"
            elif tick >= rollback_observed_tick:
                rollback_state = "rolled_back"
            public_features = {
                "cohort": cohort,
                "latency_bucket_ms": _bucket_latency(latency_ms),
                "public_version_hash": _sha256_text(f"{PROGRAM_VERSION}:{version}")[:16],
                "request_id": request_id,
                "rolling_error_rate": rolling_error_rate,
                "rollback_state": rollback_state,
                "slot": slot,
                "status_code": status_code,
                "tick": tick,
            }
            telemetry.append(
                {
                    **public_features,
                    "materialized_record_hash": _sha256_text(_stable_json({"public_deploy_request": public_features})),
                    "pre_label_partition": partition["partition_id"],
                    "source_key": "p105-isolated-local-deploy-canary",
                    "source_window_id": _sha256_text(f"{request_id}:{cohort}:{version}")[:24],
                }
            )

    canary_fault_statuses = [
        row["status_code"]
        for row in telemetry
        if row["cohort"] == "canary" and args.fault_tick <= int(row["tick"]) < rollback_observed_tick
    ]
    canary_fault_latencies = [
        80 if row["status_code"] == 503 else 64 + (int(row["slot"]) - 8)
        for row in telemetry
        if row["cohort"] == "canary" and args.fault_tick <= int(row["tick"]) < rollback_observed_tick
    ]
    observed_error_rate = round(sum(1 for status in canary_fault_statuses if status >= 500) / len(canary_fault_statuses), 6)
    observed_latency_ms_p50 = sorted(canary_fault_latencies)[len(canary_fault_latencies) // 2]
    injected_config = {
        "canary_status_rule": "every_fourth_canary_request_returns_503",
        "latency_ms_on_error": 80,
        "version": "canary-config-v2-bad",
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
    ledger = {
        "config_hash": _sha256_bytes(injected_config_bytes),
        "fault_tick": args.fault_tick,
        "injected_config_bytes": injected_config_bytes.decode("utf-8"),
        "injected_request_count": len(injection_request_ids),
        "injection_request_ids_hash": _sha256_text(_stable_json(injection_request_ids)),
        "label_join_phase": "after_sampling_and_partition",
        "private_fields": ["injected_config_bytes", "injection_request_ids_hash", "fault_tick"],
        "program_version": PROGRAM_VERSION,
        "version_fault": "canary-config-v2-bad",
    }
    rollback = {
        "authority_counters": authority_counters,
        "error_rate_threshold": 0.2,
        "grants_p106_or_p107_authority": False,
        "local_oracle": {
            "canary_fault_error_rate": observed_error_rate,
            "canary_fault_latency_ms_p50": observed_latency_ms_p50,
            "control_error_rate": 0.0,
            "decision": "rollback_required_for_local_evidence_only",
        },
        "rollback_observed_tick": rollback_observed_tick,
        "rollback_state_transition": ["not_triggered", "triggered", "rolled_back"],
        "rollback_trigger_request_ids_hash": _sha256_text(_stable_json(rollback_trigger_request_ids)),
        "trigger_tick": rollback_trigger_tick,
    }
    coverage = {
        "actual_coverage": True,
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
        "coverage_intervals": [{"end_tick": args.ticks - 1, "start_tick": 0, "tick_seconds": args.tick_seconds}],
        "fault_window": {"end_tick": rollback_observed_tick - 1, "start_tick": args.fault_tick},
        "sampling": "full_census_completed_requests",
    }
    return {
        "authority": authority,
        "authority_counters": authority_counters,
        "baseline_slots": baseline_slots,
        "canary_slots": canary_slots,
        "coverage": coverage,
        "ledger": ledger,
        "partitions": partitions,
        "rollback": rollback,
        "telemetry": telemetry,
    }


def _hash_written_artifacts(output_dir: Path, names: list[str]) -> dict[str, str]:
    return {name: _sha256_bytes((output_dir / name).read_bytes()) for name in names}


def _write_artifacts(args: argparse.Namespace) -> None:
    if args.expect_no_production_authority is not True:
        raise ValueError("--expect-no-production-authority is required")
    artifacts = _build_artifacts(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(output_dir / PUBLIC_TELEMETRY, artifacts["telemetry"])
    _write_json(output_dir / PRIVATE_LEDGER, artifacts["ledger"])
    _write_json(output_dir / PRE_LABEL_PARTITIONS, {"partition_salt": PARTITION_SALT, "partitions": artifacts["partitions"]})
    _write_json(output_dir / ROLLBACK_EVIDENCE, artifacts["rollback"])
    _write_json(output_dir / COVERAGE, artifacts["coverage"])

    base_names = [PUBLIC_TELEMETRY, PRIVATE_LEDGER, PRE_LABEL_PARTITIONS, ROLLBACK_EVIDENCE, COVERAGE]
    base_hashes = _hash_written_artifacts(output_dir, base_names)
    manifest = {
        "artifact_hashes": base_hashes,
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
        "command_argv": _canonical_command(args),
        "created_at": args.created_at,
        "host": args.host,
        "mode": args.mode,
        "program_version": PROGRAM_VERSION,
        "rollback_evidence_hash": base_hashes[ROLLBACK_EVIDENCE],
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
        },
    }
    _write_json(output_dir / MANIFEST, manifest)

    provenance_names = [*base_names, MANIFEST]
    provenance = {
        "artifact_hashes": _hash_written_artifacts(output_dir, provenance_names),
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
