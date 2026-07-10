from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEPLOY_FLEET_SCRIPT = Path("scripts/run_p105_deploy_fleet_harness.py")
REGISTRY_SCRIPT = Path("scripts/build_p105_source_registry.py")
MATERIALIZER_SCRIPT = Path("scripts/materialize_p105_release_evidence.py")

PROFILE = "p105.actual-fleet-soak.256x1h.v1"
DEPLOY_FLEET_SCHEMA = "p105.deploy.fleet_harness.v1"
DEPLOY_FLEET_ADAPTER = "p105.adapter.threading-http-deploy-fleet-harness.v1"
LEGACY_DEPLOY_SCHEMA = "p105.deploy.harness.manifest.v1"
LEGACY_DEPLOY_ADAPTER = "p105.adapter.threading-http-deploy-harness.v1"
ALL_SCHEMA_ADAPTERS = {
    "p32": "p105.adapter.p32-replay.v1",
    "p41": "p105.adapter.p41-sources.v1",
    "p44": "p105.adapter.p44-reviewed-local.v1",
    "dejavu_a1": "p105.adapter.dejavu-a1-reviewed-local.v1",
    "db_pool": "p105.adapter.database-pool-harness.v1",
    "queue": "p105.adapter.rabbitmq-harness.v1",
    "deploy": LEGACY_DEPLOY_ADAPTER,
    "database_fleet": "p105.adapter.sqlite-pool-fleet-harness.v1",
    "queue_fleet": "p105.adapter.rabbitmq-fleet-harness.v1",
    "deploy_fleet": DEPLOY_FLEET_ADAPTER,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run_deploy_fleet(output_dir: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(DEPLOY_FLEET_SCRIPT),
            "--host",
            "127.0.0.1",
            "--seed",
            "105031",
            "--profile",
            PROFILE,
            "--services",
            "256",
            "--heldout-services",
            "128",
            "--shadow-services",
            "128",
            "--requested-seconds",
            "3600",
            "--sample-cadence-seconds",
            "5",
            "--samples-per-service",
            "720",
            "--max-requests",
            "184320",
            "--max-concurrency",
            "64",
            "--max-live-sockets",
            "64",
            "--request-timeout-seconds",
            "2",
            "--max-response-body-bytes",
            "1024",
            "--max-memory-mib",
            "512",
            "--max-output-mib",
            "256",
            "--output-dir",
            str(output_dir),
            "--mode",
            "isolated-local",
            "--created-at",
            "2024-03-09T16:25:00Z",
            "--test-fast-diagnostic",
            "--expect-no-production-authority",
            *extra_args,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_deploy_fleet_fast_diagnostic_emits_exact_256_path_profile_and_is_non_counting(tmp_path: Path) -> None:
    output = tmp_path / "deploy-fleet"
    completed = _run_deploy_fleet(output)

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-deploy-fleet-harness-manifest.json")
    telemetry = _read_jsonl(output / "p105-deploy-fleet-public-telemetry.jsonl")

    assert manifest["schema_version"] == DEPLOY_FLEET_SCHEMA
    assert manifest["adapter_key"] == "deploy_fleet"
    assert manifest["adapter_version"] == DEPLOY_FLEET_ADAPTER
    assert manifest["profile"] == PROFILE
    assert manifest["diagnostic_profile"] == {"enabled": True, "runtime_qualification_eligible": False}
    assert "release_counting_allowed" not in json.dumps(manifest, sort_keys=True)
    assert manifest["requested_seconds"] == 3600
    assert manifest["sample_cadence_seconds"] == 5
    assert manifest["samples_per_service"] == 720
    assert manifest["sample_offsets_seconds"] == list(range(0, 3600, 5))
    assert manifest["request_cap"] == 184_320

    service_paths = manifest["service_paths"]
    assert service_paths == [f"/p105/fleet/deploy/{index:03d}" for index in range(256)]
    partitions = manifest["partitions"]
    assert partitions["held_out"] == [f"p105.fleet.deploy.{index:03d}" for index in range(128)]
    assert partitions["real_derived_shadow"] == [f"p105.fleet.deploy.{index:03d}" for index in range(128, 256)]

    public_keys = {key for row in telemetry for key in row}
    assert public_keys.isdisjoint({"label", "incident_answer_key", "scorer_threshold", "floor_deficit", "release_qualified", "p106_unlocked"})


def test_deploy_fleet_uses_actual_threading_http_server_loopback_caps_timeouts_body_memory_output_and_no_mutation(tmp_path: Path) -> None:
    output = tmp_path / "deploy-fleet"
    completed = _run_deploy_fleet(output)

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-deploy-fleet-harness-manifest.json")
    raw_attestation = _read_json(output / "p105-deploy-fleet-runtime-attestation.raw.json")

    assert manifest["runtime_attestation"] == {
        "kind": "actual_threading_http_server",
        "capability": "loopback_threading_http_server",
    }
    assert raw_attestation["server_class"] == "http.server.ThreadingHTTPServer"
    assert raw_attestation["bind_host"] == "127.0.0.1"
    assert raw_attestation["observed_remote_hosts"] == ["127.0.0.1"]
    assert manifest["resource_limits"] == {
        "max_concurrent_client_handler_operations": 64,
        "max_live_sockets": 64,
        "request_timeout_seconds": 2,
        "max_response_body_bytes": 1024,
        "max_memory_mib": 512,
        "max_output_mib": 256,
    }
    assert manifest["resource_observations"]["peak_concurrent_client_handler_operations"] <= 64
    assert manifest["resource_observations"]["peak_live_sockets"] <= 64
    assert manifest["authority"] == {
        "auth_enabled": False,
        "credentials_read": False,
        "external_host": False,
        "production_endpoint": False,
        "deployment_api": False,
        "production_mutation": False,
        "action_plan_created": False,
        "action_executed": False,
    }


def test_deploy_fleet_private_schedule_has_exact_g00_to_g07_25_to_30m_leads_and_source_window_binding(tmp_path: Path) -> None:
    output = tmp_path / "deploy-fleet"
    completed = _run_deploy_fleet(output)

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-deploy-fleet-harness-manifest.json")
    ledger = _read_json(output / "p105-deploy-fleet-private-injection-ledger.json")
    telemetry = _read_jsonl(output / "p105-deploy-fleet-public-telemetry.jsonl")

    assert ledger["label_join_phase"] == "after_sampling_and_partition"
    assert ledger["profile_config_hash"] == manifest["profile_config_hash"]
    assert ledger["private_schedule_loaded_after_profile_hash"] is True
    public_windows = {row["source_window_id"]: row for row in telemetry}

    incidents = ledger["incidents"]
    assert [(item["split"], item["group_id"]) for item in incidents] == [(split, f"g{group:02d}") for split in ("held_out", "real_derived_shadow") for group in range(8)]
    for incident in incidents:
        group = int(incident["group_id"][1:])
        base = 0 if incident["split"] == "held_out" else 128
        start = 1500 + (30 * group)
        affected = [f"p105.fleet.deploy.{base + (4 * group) + offset:03d}" for offset in range(4)]

        assert incident["incident_group_id"] == f"p105-fleet-deploy-{incident['split']}-g{group:02d}"
        assert incident["kind"] in {"canary_error_regression", "latency_regression", "configuration_mismatch", "bounded_rollback_delay"}
        assert incident["affected_services"] == affected
        assert incident["precursor_start_offset_seconds"] == start
        assert incident["precursor_end_offset_seconds"] == start + 300
        assert incident["private_failure_offset_seconds"] == 3300 + (30 * group)
        assert incident["lead_range_minutes"] == [25, 30]
        assert incident["bound_public_source_window_ids"]
        assert set(incident["bound_public_source_window_ids"]) <= set(public_windows)
        for window_id in incident["bound_public_source_window_ids"]:
            window = public_windows[window_id]
            assert window["service_id"] in affected
            assert start <= window["sample_offset_seconds"] <= start + 300


def test_deploy_fleet_coverage_reconstructs_from_adjacent_monotonic_samples_and_caps_requested_credit(tmp_path: Path) -> None:
    output = tmp_path / "deploy-fleet"
    completed = _run_deploy_fleet(output)

    assert completed.returncode == 0, completed.stderr
    coverage = _read_json(output / "p105-deploy-fleet-coverage.json")
    raw_attestation = _read_json(output / "p105-deploy-fleet-runtime-attestation.raw.json")

    assert coverage["coverage_source"] == "receipt_bound_adjacent_monotonic_samples"
    assert coverage["rejects_legacy_created_at_tick_seconds_path"] is True
    assert coverage["requested_duration_substitutes_for_observed_duration"] is False
    assert coverage["full_profile_theoretical_bounds"] == {
        "samples_per_service": 720,
        "adjacent_intervals_per_service": 719,
        "max_seconds_per_service": 3595,
        "max_seconds_per_split": 460_160,
        "max_seconds_per_family": 920_320,
    }
    assert coverage["diagnostic_only"] is True
    assert coverage["release_floor_credit_seconds"] == 0
    assert coverage["family_seconds"]["deploy"] < 920_320
    for segment in coverage["canonical_segments"]:
        assert segment["endpoint_source_window_ids"]
        assert segment["sample_count"] >= 2
        assert "raw_elapsed_seconds" not in segment
        assert "raw_adjacent_deltas_seconds" not in segment
    assert all(4.0 <= delta <= 7.5 for delta in raw_attestation["adjacent_deltas_seconds"])


def test_deploy_fleet_telemetry_loss_or_shutdown_failure_locks_receipt_and_fast_diagnostic_never_counts(tmp_path: Path) -> None:
    output = tmp_path / "deploy-fleet-loss"
    completed = _run_deploy_fleet(output, "--inject-telemetry-loss-at-sample", "17", "--inject-server-shutdown-failure")

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-deploy-fleet-harness-manifest.json")

    status = manifest["runtime_candidate_status"]
    assert status["runtime_qualification_eligible"] is False
    assert {"telemetry_loss", "server_shutdown_incomplete", "fast_diagnostic_non_counting"} <= set(status["validation_error_codes"])
    assert not (output / "p105-deploy-fleet-runtime-qualification-receipt.json").exists()
    assert manifest["cleanup"]["server_shutdown_complete"] is False
    assert manifest["cleanup"]["external_resources_mutated"] is False


def test_deploy_fleet_closed_adapter_rejects_legacy_manifest_and_materializer_rejects_cross_profile_substitution(tmp_path: Path) -> None:
    legacy_manifest = tmp_path / "legacy-deploy-manifest.json"
    legacy_manifest.write_text(
        json.dumps(
            {
                "schema_version": LEGACY_DEPLOY_SCHEMA,
                "program_version": "p105.deploy.canary.v1",
                "adapter_key": "deploy",
                "adapter_version": LEGACY_DEPLOY_ADAPTER,
                "profile": "p105.deploy.canary.v1",
                "source_key": "legacy-deploy-canary",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    review_ledger = tmp_path / "review-ledger.json"
    review_ledger.write_text(
        json.dumps({"schema_version": "p105.source-review-ledger.v1", "decisions": []}) + "\n",
        encoding="utf-8",
    )

    registry = subprocess.run(
        [
            sys.executable,
            str(REGISTRY_SCRIPT),
            "--candidate-manifest",
            str(legacy_manifest),
            "--review-ledger",
            str(review_ledger),
            "--output-registry",
            str(tmp_path / "registry.json"),
            "--output-eligibility",
            str(tmp_path / "eligibility.json"),
            "--created-at",
            "2024-03-09T16:25:00Z",
            "--schema-version",
            "p105.source-registry.v1",
            *[item for key, adapter in ALL_SCHEMA_ADAPTERS.items() for item in ("--schema-adapter", f"{key}={adapter}")],
            "--fail-on-unknown-source-schema",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert registry.returncode != 2, registry.stderr
    assert "unrecognized arguments" not in registry.stderr
    assert registry.returncode != 0
    assert "fleet_adapter_rejects_legacy_deploy_root" in registry.stderr

    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "p105.source-runtime-qualification.v1",
                "verified_release_counting": True,
                "canonical_root_schema": LEGACY_DEPLOY_SCHEMA,
                "profile": "p105.deploy.canary.v1",
                "created_by": "p105-source-runtime-verifier",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    materializer = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER_SCRIPT),
            "--p32-replay",
            "evals/telemetry/replay/p32_replay_pack.json",
            "--p41-sources",
            "evals/real_datasets/raw/p41_sources.json",
            "--p44-mode",
            "disabled",
            "--deploy-fleet-manifest",
            str(legacy_manifest),
            "--schema-adapter",
            f"deploy_fleet={DEPLOY_FLEET_ADAPTER}",
            "--output-dir",
            str(tmp_path / "release"),
            "--mode",
            "release_qualified",
            "--source-runtime-qualification-receipt",
            str(receipt),
            "--count-only-verified-release-receipts",
            "--fail-on-unknown-source-schema",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert materializer.returncode != 2, materializer.stderr
    assert "unrecognized arguments" not in materializer.stderr
    assert materializer.returncode != 0
    assert "deploy_fleet_cross_profile_rejected" in materializer.stderr
