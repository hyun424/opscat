from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEPLOY_FLEET_SCRIPT = Path("scripts/run_p105_deploy_fleet_harness.py")
REGISTRY_SCRIPT = Path("scripts/build_p105_source_registry.py")
MATERIALIZER_SCRIPT = Path("scripts/materialize_p105_release_evidence.py")

PROFILE = "p105.actual-fleet-soak.256x1h.v1"
DIAGNOSTIC_PROFILE = "p105.deploy-fleet.diagnostic.fast.v1"
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


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _harness() -> Any:
    spec = importlib.util.spec_from_file_location("run_p105_deploy_fleet_harness", DEPLOY_FLEET_SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _deploy_contract() -> dict[str, Any]:
    builder = getattr(_api(), "build_p105_deploy_fleet_profile_contract", None)
    assert callable(builder), "P105-031 RED: missing deploy fleet profile contract builder"
    return dict(builder())


def _flatten_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value} | set().union(*(_flatten_keys(child) for child in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_flatten_keys(child) for child in value), set())
    return set()


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
            DIAGNOSTIC_PROFILE,
            "--services",
            "256",
            "--heldout-services",
            "128",
            "--shadow-services",
            "128",
            "--requested-seconds",
            "30",
            "--sample-cadence-seconds",
            "5",
            "--samples-per-service",
            "6",
            "--max-requests",
            "1536",
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


def _full_profile_args(output_dir: Path) -> list[str]:
    return [
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
        "--expect-no-production-authority",
    ]


def test_deploy_fleet_full_profile_contract_is_exact_without_executing_an_accelerated_soak() -> None:
    contract = _deploy_contract()

    assert contract["profile"] == PROFILE
    assert contract["requested_seconds"] == 3600
    assert contract["sample_cadence_seconds"] == 5
    assert contract["samples_per_service"] == 720
    assert contract["sample_offsets_seconds"] == list(range(0, 3600, 5))
    assert contract["request_cap"] == 184_320
    assert len(contract["profile_config_hash"]) == 64
    assert contract["profile_config_hash_phase"] == "before_private_schedule_loading"
    assert contract["private_schedule_loaded_after_profile_hash"] is True
    assert contract["service_paths"] == [f"/p105/fleet/deploy/{index:03d}" for index in range(256)]
    assert contract["partitions"]["held_out"] == [f"p105.fleet.deploy.{index:03d}" for index in range(128)]
    assert contract["partitions"]["real_derived_shadow"] == [f"p105.fleet.deploy.{index:03d}" for index in range(128, 256)]


def test_deploy_fleet_harness_accepts_full_profile_contract_without_diagnostic_escape_hatch(tmp_path: Path) -> None:
    harness = _harness()
    parser = harness._parser()
    args = parser.parse_args(_full_profile_args(tmp_path / "full"))

    harness._validate_args(args)

    assert harness._is_full_profile(args) is True
    assert args.test_fast_diagnostic is False
    assert harness._sample_offsets(args) == list(range(0, 3600, 5))
    assert harness._command_argv(args).count("--test-fast-diagnostic") == 0
    assert args.max_requests == args.services * args.samples_per_service == 184_320


def test_deploy_fleet_harness_rejects_full_profile_with_diagnostic_flag_or_wrong_request_cap(tmp_path: Path) -> None:
    harness = _harness()
    parser = harness._parser()

    with_test_flag = parser.parse_args([*_full_profile_args(tmp_path / "full"), "--test-fast-diagnostic"])
    try:
        harness._validate_args(with_test_flag)
    except ValueError as exc:
        assert "--test-fast-diagnostic is only valid" in str(exc)
    else:
        raise AssertionError("full profile must reject diagnostic escape hatch")

    wrong_cap_args = _full_profile_args(tmp_path / "wrong-cap")
    wrong_cap_args[wrong_cap_args.index("--max-requests") + 1] = "1536"
    wrong_cap = parser.parse_args(wrong_cap_args)
    try:
        harness._validate_args(wrong_cap)
    except ValueError as exc:
        assert "max-requests must be 184320" in str(exc)
    else:
        raise AssertionError("full profile must enforce 184320 request cap")


def test_deploy_fleet_fast_diagnostic_is_short_actual_and_non_counting(tmp_path: Path) -> None:
    output = tmp_path / "deploy-fleet"
    completed = _run_deploy_fleet(output)

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-deploy-fleet-harness-manifest.json")
    telemetry = _read_jsonl(output / "p105-deploy-fleet-public-telemetry.jsonl")

    assert manifest["schema_version"] == DEPLOY_FLEET_SCHEMA
    assert manifest["adapter_key"] == "deploy_fleet"
    assert manifest["adapter_version"] == DEPLOY_FLEET_ADAPTER
    assert manifest["profile"] == DIAGNOSTIC_PROFILE
    assert manifest["diagnostic_profile"] == {"enabled": True, "runtime_qualification_eligible": False}
    assert "release_counting_allowed" not in json.dumps(manifest, sort_keys=True)
    assert manifest["requested_seconds"] == 30
    assert manifest["sample_cadence_seconds"] == 5
    assert manifest["samples_per_service"] == 6
    assert manifest["sample_offsets_seconds"] == [0, 5, 10, 15, 20, 25]
    assert manifest["request_cap"] == 1_536

    service_paths = manifest["service_paths"]
    assert service_paths == [f"/p105/fleet/deploy/{index:03d}" for index in range(256)]
    partitions = manifest["partitions"]
    assert partitions["held_out"] == [f"p105.fleet.deploy.{index:03d}" for index in range(128)]
    assert partitions["real_derived_shadow"] == [f"p105.fleet.deploy.{index:03d}" for index in range(128, 256)]

    public_keys = _flatten_keys(telemetry)
    assert public_keys.isdisjoint(
        {
            "label",
            "labels",
            "incident_answer_key",
            "incident_group_id",
            "private_failure_second",
            "scorer_threshold",
            "scorer_thresholds",
            "floor_deficit",
            "floor_deficits",
            "release_qualified",
            "p106_unlocked",
        }
    )


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


def test_deploy_fleet_private_schedule_contract_has_exact_g00_to_g07_25_to_30m_leads_and_window_ids() -> None:
    incidents = _deploy_contract()["private_schedule"]
    assert [(item["split"], item["group_id"]) for item in incidents] == [(split, f"g{group:02d}") for split in ("held_out", "real_derived_shadow") for group in range(8)]
    for incident in incidents:
        group = int(incident["group_id"][1:])
        base = 0 if incident["split"] == "held_out" else 128
        start = 1500 + (30 * group)
        affected = [f"p105.fleet.deploy.{base + (4 * group) + offset:03d}" for offset in range(4)]

        assert incident["incident_group_id"] == f"p105-fleet-deploy-{incident['split']}-g{group:02d}"
        assert (
            incident["kind"]
            == [
                "canary_error_regression",
                "latency_regression",
                "configuration_mismatch",
                "bounded_rollback_delay",
            ][group % 4]
        )
        assert incident["affected_services"] == affected
        assert incident["precursor_start_offset_seconds"] == start
        assert incident["precursor_end_offset_seconds"] == start + 300
        assert incident["private_failure_offset_seconds"] == 3300 + (30 * group)
        assert incident["lead_range_minutes"] == [25, 30]
        expected_windows = [
            f"p105-fleet-deploy-{incident['split']}-svc{service_index:03d}-sample{ordinal:03d}"
            for service_index in range(base + (4 * group), base + (4 * group) + 4)
            for ordinal in range(start // 5, (start + 300) // 5 + 1)
        ]
        assert incident["expected_bound_public_source_window_ids"] == expected_windows


def test_deploy_fleet_full_schedule_binding_and_observed_monotonic_coverage_are_canonical() -> None:
    harness = _harness()
    observed_windows = {
        "p105-fleet-deploy-held_out-svc000-sample300",
        "p105-fleet-deploy-held_out-svc000-sample301",
        "p105-fleet-deploy-held_out-svc000-sample302",
        "p105-fleet-deploy-held_out-svc001-sample300",
    }

    incidents = harness._private_schedule_with_binding(observed_windows, bind_observed=True)
    first = incidents[0]

    assert first["incident_group_id"] == "p105-fleet-deploy-held_out-g00"
    assert first["bound_public_source_window_ids"] == [
        "p105-fleet-deploy-held_out-svc000-sample300",
        "p105-fleet-deploy-held_out-svc000-sample301",
        "p105-fleet-deploy-held_out-svc000-sample302",
        "p105-fleet-deploy-held_out-svc001-sample300",
    ]

    telemetry = [
        {
            "sample_ordinal": 300,
            "service_id": "p105.fleet.deploy.000",
            "source_window_id": "p105-fleet-deploy-held_out-svc000-sample300",
            "split": "held_out",
            "telemetry_monotonic_ns": 10_000_000_000,
        },
        {
            "sample_ordinal": 301,
            "service_id": "p105.fleet.deploy.000",
            "source_window_id": "p105-fleet-deploy-held_out-svc000-sample301",
            "split": "held_out",
            "telemetry_monotonic_ns": 15_100_000_000,
        },
        {
            "sample_ordinal": 303,
            "service_id": "p105.fleet.deploy.000",
            "source_window_id": "p105-fleet-deploy-held_out-svc000-sample303",
            "split": "held_out",
            "telemetry_monotonic_ns": 25_100_000_000,
        },
    ]
    segments, total_ns = harness._observed_coverage_segments(telemetry)

    assert total_ns == 5_000_000_000
    assert segments == [
        {
            "conservative_duration_seconds": 5,
            "coverage_source": "receipt_bound_adjacent_monotonic_samples",
            "end_sample_ordinal": 301,
            "end_source_window_id": "p105-fleet-deploy-held_out-svc000-sample301",
            "sample_count": 2,
            "service_id": "p105.fleet.deploy.000",
            "split": "held_out",
            "start_sample_ordinal": 300,
            "start_source_window_id": "p105-fleet-deploy-held_out-svc000-sample300",
        }
    ]


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
    assert coverage["family_seconds"]["deploy"] == 0
    assert coverage["canonical_segments"] == []
    assert raw_attestation["observation_count"] > 0
    assert raw_attestation["diagnostic_not_receipt_eligible"] is True


def test_deploy_fleet_telemetry_loss_or_shutdown_failure_locks_receipt_and_fast_diagnostic_never_counts(tmp_path: Path) -> None:
    output = tmp_path / "deploy-fleet-loss"
    completed = _run_deploy_fleet(output, "--inject-telemetry-loss-at-sample", "1", "--inject-server-shutdown-failure")

    assert completed.returncode == 0, completed.stderr
    manifest = _read_json(output / "p105-deploy-fleet-harness-manifest.json")

    status = manifest["runtime_candidate_status"]
    assert status["runtime_qualification_eligible"] is False
    assert status["harness_issues_receipts"] is False
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
