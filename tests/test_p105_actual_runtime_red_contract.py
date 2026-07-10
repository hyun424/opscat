from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

DB_POOL_SCRIPT = Path("scripts/run_p105_db_pool_harness.py")
QUEUE_SCRIPT = Path("scripts/run_p105_queue_harness.py")
DEPLOY_SCRIPT = Path("scripts/run_p105_deploy_canary_harness.py")
VERIFY_SCRIPT = Path("scripts/verify_p105_source_expansion_artifacts.py")
MATERIALIZER_SCRIPT = Path("scripts/materialize_p105_release_evidence.py")

FORBIDDEN_CANONICAL_RUNTIME_KEYS = {
    "container_id",
    "container_name",
    "docker_network_name",
    "host_port",
    "loopback_port",
    "monotonic_finished_ns",
    "monotonic_started_ns",
    "process_id",
    "raw_attestation_hash",
    "raw_attestation_path",
    "sqlite_connection_object_id",
    "thread_id",
    "thread_name",
    "verified_release_counting",
    "release_counting_allowed",
}


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key))
            keys.update(_flatten_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.update(_flatten_keys(nested))
    return keys


def _assert_canonical_excludes_raw_runtime_fields(payload: dict[str, Any]) -> None:
    assert _flatten_keys(payload).isdisjoint(FORBIDDEN_CANONICAL_RUNTIME_KEYS)


def test_simulated_in_memory_accelerated_and_schedule_only_artifacts_never_count_with_forged_fields(tmp_path: Path) -> None:
    registry_sources = []
    eligibility_entries = []
    for kind in ("simulated", "in_memory", "accelerated_clock", "schedule_only"):
        source_key = f"{kind}-forged-source"
        registry_sources.append({"source_key": source_key, "reviewed": True})
        eligibility_entries.append(
            {
                "source_key": source_key,
                "source_window_id": f"{source_key}-window",
                "family_candidate": "queue",
                "family_authority_source": "reviewed_source_registry",
                "eligible_for_release_floor": True,
                "coverage_interval_ids": [f"{source_key}-interval"],
                "coverage_seconds": 123,
                "coverage_source": "actual",
                "runtime_attestation": {"kind": kind},
                "verified_release_counting": True,
                "release_counting_allowed": True,
                "counting_rows": 999,
                "counting_coverage_seconds": 999,
            }
        )
    registry = _write_json(tmp_path / "registry.json", {"schema_version": "p105.source-registry.v1", "sources": registry_sources})
    eligibility = _write_json(tmp_path / "eligibility.json", {"schema_version": "p105.source-eligibility.v1", "entries": eligibility_entries})

    result = _api().validate_p105_source_expansion_release_inputs(source_registry=registry, source_eligibility=eligibility)

    assert result["counting_coverage_seconds"] == 0
    assert {
        "runtime_attestation_not_actual",
        "source_forged_release_counting_authority",
    } <= set(result["validation_error_codes"])
    assert result["release_gate"] == {"release_qualified": False, "p106_unlocked": False}


def test_db_pool_harness_requires_actual_sqlite_pool_sql_evidence_raw_attestation_and_canonical_split(tmp_path: Path) -> None:
    if not DB_POOL_SCRIPT.exists():
        pytest.fail("P105-024 RED: missing scripts/run_p105_db_pool_harness.py actual SQLite pool harness.", pytrace=False)
    output = tmp_path / "db-pool"
    completed = subprocess.run(
        [
            sys.executable,
            str(DB_POOL_SCRIPT),
            "--sqlite-db",
            str(output / "p105-database-pool.sqlite3"),
            "--seed",
            "105028",
            "--services",
            "dbpool-svc-00,dbpool-svc-04",
            "--heldout-services",
            "dbpool-svc-00",
            "--shadow-services",
            "dbpool-svc-04",
            "--pool-size",
            "3",
            "--workers-per-service",
            "2",
            "--acquisitions-per-worker-per-second",
            "1",
            "--acquire-timeout-ms",
            "75",
            "--normal-hold-ms",
            "1",
            "--saturation-hold-ms",
            "2",
            "--ticks",
            "3",
            "--tick-seconds",
            "0.001",
            "--output-dir",
            str(output),
            "--mode",
            "isolated-local",
            "--created-at",
            "2024-03-09T16:13:20Z",
            "--expect-runtime-attestation-kind",
            "actual_sqlite_pool",
            "--test-fast-runtime",
            "--expect-no-production-authority",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-db-pool-harness-manifest.json")
    raw_attestation = _read_json(output / "p105-db-pool-runtime-attestation.raw.json")
    assert manifest["runtime_attestation"]["kind"] == "actual_sqlite_pool"
    assert manifest["runtime_attestation"]["capability"] == "sqlite3_connection_pool"
    assert manifest["sql_operation_evidence"] == {"insert": True, "select_count": True, "update": True}
    assert raw_attestation["monotonic_finished_ns"] > raw_attestation["monotonic_started_ns"]
    assert raw_attestation["sqlite_connection_observations"]
    _assert_canonical_excludes_raw_runtime_fields(manifest)


def test_queue_harness_requires_actual_rabbitmq_docker_attestation_and_not_in_memory_deque_simulation(tmp_path: Path) -> None:
    output = tmp_path / "queue"
    completed = subprocess.run(
        [
            sys.executable,
            str(QUEUE_SCRIPT),
            "--compose-file",
            "tools/p105/queue/docker-compose.yml",
            "--rabbitmq-image",
            "rabbitmq:3.13-management-alpine",
            "--seed",
            "105026",
            "--ticks",
            "3",
            "--tick-seconds",
            "0",
            "--output-dir",
            str(output),
            "--mode",
            "isolated-local",
            "--created-at",
            "2024-03-09T16:06:40Z",
            "--expect-no-host-ports",
            "--test-fast-runtime",
            "--expect-no-production-authority",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-queue-harness-manifest.json")
    assert manifest["runtime_attestation"]["kind"] == "actual_rabbitmq_docker"
    assert manifest["runtime_attestation"]["capability"] == "docker_compose_rabbitmq_broker"
    assert manifest["broker_observation_attestation"]["docker_compose_ps_observed"] is True
    assert manifest["broker_observation_attestation"]["rabbitmq_management_observed"] is True
    assert manifest["implementation_guard"]["uses_in_memory_deque_simulation"] is False
    _assert_canonical_excludes_raw_runtime_fields(manifest)


def test_deploy_harness_requires_threading_http_server_loopback_observations_and_measured_latency(tmp_path: Path) -> None:
    output = tmp_path / "deploy"
    completed = subprocess.run(
        [
            sys.executable,
            str(DEPLOY_SCRIPT),
            "--host",
            "127.0.0.1",
            "--seed",
            "105027",
            "--ticks",
            "12",
            "--tick-seconds",
            "0",
            "--requests-per-tick",
            "10",
            "--fault-tick",
            "3",
            "--output-dir",
            str(output),
            "--mode",
            "isolated-local",
            "--created-at",
            "2024-03-09T16:23:20Z",
            "--expect-rollback-trigger-tick",
            "72",
            "--expect-rollback-observed-tick",
            "73",
            "--test-fast-runtime",
            "--expect-no-production-authority",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    first_row = json.loads((output / "p105-deploy-public-telemetry.jsonl").read_text(encoding="utf-8").splitlines()[0])
    manifest = _read_json(output / "p105-deploy-harness-manifest.json")
    assert manifest["runtime_attestation"]["kind"] == "actual_threading_http_server"
    assert manifest["runtime_attestation"]["capability"] == "loopback_threading_http_server"
    assert first_row["client_target_host"] == "127.0.0.1"
    assert first_row["handler_observation_sha256"]
    assert first_row["response_body_sha256"]
    assert first_row["measured_latency_bucket_ms"]
    assert manifest["implementation_guard"]["materialized_without_http_serving"] is False
    _assert_canonical_excludes_raw_runtime_fields(manifest)


def test_verifier_runtime_phase_creates_envelopes_and_release_phase_consumes_receipt_and_release_dir(tmp_path: Path) -> None:
    envelopes = tmp_path / "envelopes"
    receipt = tmp_path / "p105-source-runtime-qualification.json"
    runtime = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--phase",
            "runtime",
            "--registry",
            str(tmp_path / "registry.json"),
            "--eligibility",
            str(tmp_path / "eligibility.json"),
            "--db-pool-manifest",
            str(tmp_path / "db" / "p105-db-pool-harness-manifest.json"),
            "--db-pool-rerun-manifest",
            str(tmp_path / "db-rerun" / "p105-db-pool-harness-manifest.json"),
            "--db-pool-raw-attestation",
            str(tmp_path / "db" / "p105-db-pool-runtime-attestation.raw.json"),
            "--db-pool-rerun-raw-attestation",
            str(tmp_path / "db-rerun" / "p105-db-pool-runtime-attestation.raw.json"),
            "--queue-manifest",
            str(tmp_path / "queue" / "p105-queue-harness-manifest.json"),
            "--queue-rerun-manifest",
            str(tmp_path / "queue-rerun" / "p105-queue-harness-manifest.json"),
            "--queue-raw-attestation",
            str(tmp_path / "queue" / "p105-queue-runtime-attestation.raw.json"),
            "--queue-rerun-raw-attestation",
            str(tmp_path / "queue-rerun" / "p105-queue-runtime-attestation.raw.json"),
            "--deploy-manifest",
            str(tmp_path / "deploy" / "p105-deploy-harness-manifest.json"),
            "--deploy-rerun-manifest",
            str(tmp_path / "deploy-rerun" / "p105-deploy-harness-manifest.json"),
            "--deploy-raw-attestation",
            str(tmp_path / "deploy" / "p105-deploy-runtime-attestation.raw.json"),
            "--deploy-rerun-raw-attestation",
            str(tmp_path / "deploy-rerun" / "p105-deploy-runtime-attestation.raw.json"),
            "--write-run-envelopes-dir",
            str(envelopes),
            "--output-json",
            str(receipt),
            "--expect-byte-identical-canonical-reruns",
            "--expect-tamper-fixtures-fail-closed",
            "--expect-runtime-kinds",
            "actual_sqlite_pool,actual_rabbitmq_docker,actual_threading_http_server",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert runtime.returncode != 2, runtime.stderr
    assert "unrecognized arguments" not in runtime.stderr
    assert envelopes.exists()
    assert receipt.exists()

    release = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--phase",
            "release",
            "--registry",
            str(tmp_path / "registry.json"),
            "--eligibility",
            str(tmp_path / "eligibility.json"),
            "--source-runtime-qualification-receipt",
            str(receipt),
            "--release-dir",
            str(tmp_path / "release"),
            "--expect-verified-release-counting-receipt",
            "--expect-db-pool-command-args",
            "--output-json",
            str(tmp_path / "release-verification.json"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert release.returncode != 2, release.stderr
    assert "unrecognized arguments" not in release.stderr


def test_central_materializer_accepts_approved_runtime_flags_and_rejects_forged_or_synthetic_inputs(tmp_path: Path) -> None:
    forged_receipt = _write_json(
        tmp_path / "forged-receipt.json",
        {
            "schema_version": "p105.source-runtime-qualification.v1",
            "verified_release_counting": True,
            "created_by": "harness-not-verifier",
            "run_envelopes": [],
        },
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER_SCRIPT),
            "--p32-replay",
            "evals/telemetry/replay/p32_replay_pack.json",
            "--p41-sources",
            "evals/real_datasets/raw/p41_sources.json",
            "--p44-reviewed-local-manifest",
            str(tmp_path / "p44.json"),
            "--p44-mode",
            "reviewed-local",
            "--dejavu-a1-reviewed-local-manifest",
            str(tmp_path / "dejavu.json"),
            "--db-pool-harness-manifest",
            str(tmp_path / "db.json"),
            "--queue-harness-manifest",
            str(tmp_path / "queue.json"),
            "--deploy-harness-manifest",
            str(tmp_path / "deploy.json"),
            "--schema-adapter",
            "p32=p105.adapter.p32-replay.v1",
            "--schema-adapter",
            "p41=p105.adapter.p41-sources.v1",
            "--schema-adapter",
            "p44=p105.adapter.p44-reviewed-local.v1",
            "--schema-adapter",
            "dejavu_a1=p105.adapter.dejavu-a1-reviewed-local.v1",
            "--schema-adapter",
            "db_pool=p105.adapter.database-pool-harness.v1",
            "--schema-adapter",
            "queue=p105.adapter.rabbitmq-harness.v1",
            "--schema-adapter",
            "deploy=p105.adapter.threading-http-deploy-harness.v1",
            "--source-registry",
            str(tmp_path / "registry.json"),
            "--source-eligibility",
            str(tmp_path / "eligibility.json"),
            "--output-dir",
            str(tmp_path / "release"),
            "--mode",
            "release_qualified",
            "--reject-synthetic-four-day-coverage",
            "--require-actual-runtime-attestation",
            "--fail-on-unknown-source-schema",
            "--source-runtime-qualification-receipt",
            str(forged_receipt),
            "--count-only-verified-release-receipts",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 2, completed.stderr
    assert "unrecognized arguments" not in completed.stderr
    assert completed.returncode != 0
    assert any(
        code in completed.stderr
        for code in ("forged_source_runtime_receipt", "unknown_source_schema", "synthetic_four_day_coverage")
    )


def test_central_coverage_uses_actual_intervals_without_fixed_four_day_fallback(tmp_path: Path) -> None:
    result = _api().materialize_p105_release_qualified_evidence(
        p32_replay="evals/telemetry/replay/p32_replay_pack.json",
        p41_sources="evals/real_datasets/raw/p41_sources.json",
        p44_mode="disabled",
        output_dir=tmp_path / "release",
        mode="release_qualified",
        expect_locked=True,
    )

    coverage = result["coverage_manifest"]
    assert coverage["false_alert_denominator_method"] == "actual_observed_interval_union"
    assert "fixed_four_day_constant" in coverage["rejects"]
    assert all(
        interval.get("timestamp_source") != "raw_source_record_plus_fixed_4_days"
        and interval.get("duration_seconds") != 4 * 24 * 60 * 60
        for family in coverage["service_day_coverage"].values()
        for interval in family["coverage_intervals"]
    )


def test_runtime_contract_preserves_no_auth_or_production_mutation_authority(tmp_path: Path) -> None:
    output = tmp_path / "queue"
    completed = subprocess.run(
        [
            sys.executable,
            str(QUEUE_SCRIPT),
            "--compose-file",
            "tools/p105/queue/docker-compose.yml",
            "--rabbitmq-image",
            "rabbitmq:3.13-management-alpine",
            "--seed",
            "105026",
            "--ticks",
            "3",
            "--tick-seconds",
            "0",
            "--output-dir",
            str(output),
            "--mode",
            "isolated-local",
            "--created-at",
            "2024-03-09T16:06:40Z",
            "--expect-no-host-ports",
            "--test-fast-runtime",
            "--expect-no-production-authority",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-queue-harness-manifest.json")
    assert manifest["authority"] == {
        "auth_enabled": False,
        "credentials_read": False,
        "external_broker_endpoint": False,
        "host_ports": [],
        "production_endpoint": False,
        "production_mutation": False,
        "release_counting_authority": False,
    }
