from __future__ import annotations

import importlib
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REGISTRY_SCRIPT = Path("scripts/build_p105_source_registry.py")

FLEET_PROFILE = "p105.actual-fleet-soak.256x1h.v1"
FLEET_ADAPTERS = {
    "database_fleet": "p105.adapter.sqlite-pool-fleet-harness.v1",
    "queue_fleet": "p105.adapter.rabbitmq-fleet-harness.v1",
    "deploy_fleet": "p105.adapter.threading-http-deploy-fleet-harness.v1",
}
FLEET_ROOT_SCHEMAS = {
    "database_fleet": "p105.database.fleet_harness.v1",
    "queue_fleet": "p105.queue.fleet_harness.v1",
    "deploy_fleet": "p105.deploy.fleet_harness.v1",
}
ALL_SCHEMA_ADAPTERS = {
    "p32": "p105.adapter.p32-replay.v1",
    "p41": "p105.adapter.p41-sources.v1",
    "p44": "p105.adapter.p44-reviewed-local.v1",
    "dejavu_a1": "p105.adapter.dejavu-a1-reviewed-local.v1",
    "db_pool": "p105.adapter.database-pool-harness.v1",
    "queue": "p105.adapter.rabbitmq-harness.v1",
    "deploy": "p105.adapter.threading-http-deploy-harness.v1",
    **FLEET_ADAPTERS,
}


def _forecast_api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _registry_api() -> Any:
    return importlib.import_module("scripts.build_p105_source_registry")


def _verifier_api() -> Any:
    return importlib.import_module("scripts.verify_p105_source_expansion_artifacts")


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _fleet_coverage_fn() -> Any:
    fn = getattr(_forecast_api(), "compute_p105_fleet_coverage_segments", None)
    if fn is None:
        pytest.fail("P105-031 RED: expose compute_p105_fleet_coverage_segments for receipt-bound fleet coverage.", pytrace=False)
    return fn


def _floor_credit_fn() -> Any:
    fn = getattr(_forecast_api(), "compute_p105_fleet_floor_credit", None)
    if fn is None:
        pytest.fail("P105-031 RED: expose compute_p105_fleet_floor_credit so reruns add zero floor credit.", pytrace=False)
    return fn


def test_closed_registry_declares_database_queue_and_deploy_fleet_adapters() -> None:
    registry = _registry_api()

    for key, adapter in FLEET_ADAPTERS.items():
        assert registry.REQUIRED_SCHEMA_ADAPTERS[key] == adapter
        assert FLEET_ROOT_SCHEMAS[key] in registry.KNOWN_ROOT_SCHEMAS


def test_legacy_registry_adapter_rejects_fleet_root_schema_cross_profile(tmp_path: Path) -> None:
    manifest = _write_json(
        tmp_path / "queue-fleet-manifest.json",
        {
            "schema_version": FLEET_ROOT_SCHEMAS["queue_fleet"],
            "profile": FLEET_PROFILE,
            "source_key": "p105-fleet-queue",
            "source_family": "queue",
            "source_family_candidate": "queue",
            "runtime_attestation": {"kind": "actual_rabbitmq_docker", "capability": "actual_rabbitmq_docker"},
            "adapter_key": "queue",
        },
    )
    ledger = _write_json(tmp_path / "ledger.json", {"schema_version": "p105.source-review-ledger.v1", "decisions": []})

    completed = subprocess.run(
        [
            sys.executable,
            str(REGISTRY_SCRIPT),
            "--candidate-manifest",
            str(manifest),
            "--review-ledger",
            str(ledger),
            "--output-registry",
            str(tmp_path / "registry.json"),
            "--output-eligibility",
            str(tmp_path / "eligibility.json"),
            "--created-at",
            "2024-03-09T16:33:20Z",
            "--schema-version",
            "p105.source-registry.v1",
            "--fail-on-unknown-source-schema",
            *[item for key, adapter in ALL_SCHEMA_ADAPTERS.items() for item in ("--schema-adapter", f"{key}={adapter}")],
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "cross_profile_schema_adapter_mismatch" in completed.stderr


def test_materializer_cli_accepts_fleet_manifest_args_and_receipt_root() -> None:
    parser = _forecast_api().build_p105_materializer_cli_parser()

    args = parser.parse_args(
        [
            "--p32-replay",
            "p32.json",
            "--p41-sources",
            "p41.json",
            "--p44-mode",
            "disabled",
            "--database-fleet-manifest",
            "database-fleet.json",
            "--queue-fleet-manifest",
            "queue-fleet.json",
            "--deploy-fleet-manifest",
            "deploy-fleet.json",
            "--fleet-runtime-qualification-receipt",
            "fleet-receipt.json",
            "--output-dir",
            "out",
        ]
    )

    assert args.database_fleet_manifest == "database-fleet.json"
    assert args.queue_fleet_manifest == "queue-fleet.json"
    assert args.deploy_fleet_manifest == "deploy-fleet.json"
    assert args.fleet_runtime_qualification_receipt == "fleet-receipt.json"


def test_verifier_runtime_cli_accepts_fleet_run_envelope_roots() -> None:
    parser = _verifier_api()._build_arg_parser()

    args = parser.parse_args(
        [
            "--phase",
            "runtime",
            "--database-fleet-manifest",
            "database-fleet.json",
            "--database-fleet-raw-attestation",
            "database-fleet.raw.json",
            "--queue-fleet-manifest",
            "queue-fleet.json",
            "--queue-fleet-raw-attestation",
            "queue-fleet.raw.json",
            "--deploy-fleet-manifest",
            "deploy-fleet.json",
            "--deploy-fleet-raw-attestation",
            "deploy-fleet.raw.json",
            "--write-run-envelopes-dir",
            "envelopes",
        ]
    )

    assert args.database_fleet_manifest == Path("database-fleet.json")
    assert args.queue_fleet_manifest == Path("queue-fleet.json")
    assert args.deploy_fleet_manifest == Path("deploy-fleet.json")


def test_raw_monotonic_adjacency_accepts_only_4_0_through_7_5_second_deltas() -> None:
    segments = _fleet_coverage_fn()(
        [
            {"source_window_id": "w0", "sample_ordinal": 0, "monotonic_ns": 0},
            {"source_window_id": "w1", "sample_ordinal": 1, "monotonic_ns": 4_000_000_000},
            {"source_window_id": "w2", "sample_ordinal": 2, "monotonic_ns": 11_500_000_000},
            {"source_window_id": "w3", "sample_ordinal": 3, "monotonic_ns": 19_100_000_000},
        ],
        source="queue_fleet",
        family="queue",
        split_id="held_out",
        service="p105.fleet.queue.000",
        run_id="run-1",
        receipt_bound_source_window_ids={"w0", "w1", "w2", "w3"},
    )

    assert [segment["sample_count"] for segment in segments] == [3, 1]
    assert [segment["conservative_duration_seconds"] for segment in segments] == [10, 0]


def test_conservative_segment_duration_uses_min_scheduled_adjacency_and_raw_elapsed_bucket() -> None:
    segments = _fleet_coverage_fn()(
        [
            {"source_window_id": "w0", "sample_ordinal": 0, "monotonic_ns": 0},
            {"source_window_id": "w1", "sample_ordinal": 1, "monotonic_ns": 4_900_000_000},
            {"source_window_id": "w2", "sample_ordinal": 2, "monotonic_ns": 9_800_000_000},
            {"source_window_id": "w3", "sample_ordinal": 3, "monotonic_ns": 14_900_000_000},
        ],
        source="database_fleet",
        family="database",
        split_id="held_out",
        service="p105.fleet.database.000",
        run_id="run-1",
        receipt_bound_source_window_ids={"w0", "w1", "w2", "w3"},
    )

    assert segments == [
        {
            "source": "database_fleet",
            "family": "database",
            "split_id": "held_out",
            "service": "p105.fleet.database.000",
            "run_id": "run-1",
            "start_source_window_id": "w0",
            "end_source_window_id": "w3",
            "sample_count": 4,
            "conservative_duration_seconds": 10,
        }
    ]


def test_missing_duplicate_or_unbound_adjacency_reduces_measured_coverage() -> None:
    segments = _fleet_coverage_fn()(
        [
            {"source_window_id": "w0", "sample_ordinal": 0, "monotonic_ns": 0},
            {"source_window_id": "w1", "sample_ordinal": 1, "monotonic_ns": 5_000_000_000},
            {"source_window_id": "w1-duplicate", "sample_ordinal": 1, "monotonic_ns": 5_100_000_000},
            {"source_window_id": "w3", "sample_ordinal": 3, "monotonic_ns": 15_000_000_000},
            {"source_window_id": "w4-unbound", "sample_ordinal": 4, "monotonic_ns": 20_000_000_000},
        ],
        source="deploy_fleet",
        family="deploy",
        split_id="real_derived_shadow",
        service="p105.fleet.deploy.128",
        run_id="run-1",
        receipt_bound_source_window_ids={"w0", "w1", "w1-duplicate", "w3"},
    )

    assert sum(segment["conservative_duration_seconds"] for segment in segments) == 5
    assert all(segment["end_source_window_id"] != "w4-unbound" for segment in segments)


def test_central_materializer_has_fleet_manifest_parameters_and_no_created_at_tick_fleet_credit_path() -> None:
    signature = inspect.signature(_forecast_api().materialize_p105_release_qualified_evidence)

    for parameter in (
        "database_fleet_manifest",
        "queue_fleet_manifest",
        "deploy_fleet_manifest",
        "fleet_runtime_qualification_receipt",
    ):
        assert parameter in signature.parameters
    assert "created_at_tick_seconds_fleet_coverage_allowed" not in signature.parameters


def test_fleet_rerun_receipts_add_zero_release_floor_credit() -> None:
    credit = _floor_credit_fn()(
        primary_run={
            "run_id": "run-1",
            "segments": [{"coverage_segment_id": "seg-1", "duration_seconds": 3595}],
            "positive_source_window_ids": ["positive-1"],
            "incident_group_ids": ["group-1"],
        },
        reruns=[
            {
                "run_id": "run-2",
                "segments": [{"coverage_segment_id": "seg-1-rerun", "duration_seconds": 3595}],
                "positive_source_window_ids": ["positive-1-rerun"],
                "incident_group_ids": ["group-1-rerun"],
            }
        ],
    )

    assert credit["counted_run_ids"] == ["run-1"]
    assert credit["rerun_floor_credit"] == {"rows": 0, "positives": 0, "incident_groups": 0, "coverage_seconds": 0}


def test_existing_per_family_seven_day_union_gate_and_p106_lock_remain_unchanged(tmp_path: Path) -> None:
    api = _forecast_api()
    payload = {
        "schema_version": "p105.forecast.release_benchmark.v1",
        "mode": "release_qualified",
        "release_supported_families": ["database", "deploy", "queue"],
        "release_qualification": {
            "mode": "release_qualified",
            "floor_contract_version": "p105-g006",
            "minimum_union_service_days": 7.0,
        },
        "rows": [],
        "service_day_coverage": {
            family: {
                "service_days": 6.999_988,
                "coverage_intervals": [
                    {
                        "split_id": "g006-held_out",
                        "family": family,
                        "service": f"{family}-svc",
                        "source_system": "fleet",
                        "start": "2026-01-01T00:00:00Z",
                        "end": "2026-01-07T23:59:59Z",
                    }
                ],
            }
            for family in ("database", "deploy", "queue")
        },
        "source_availability_preflight": {"checked_before_scoring": True, "families": {}},
    }
    path = _write_json(tmp_path / "candidate.json", payload)

    report = api.run_p105_benchmark(path)
    coverage = report["release_gate"]["qualification_floors"]["service_day_coverage"]

    assert coverage["union_service_days"]["minimum"] == 7.0
    assert coverage["pass"] is False
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False
