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


def _run_registry_for_manifest(tmp_path: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
    ledger = _write_json(tmp_path / "ledger.json", {"schema_version": "p105.source-review-ledger.v1", "decisions": []})
    return subprocess.run(
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


def _wrapped_queue_fleet_manifest() -> dict[str, Any]:
    return {
        "public_config": {
            "schema_version": FLEET_ROOT_SCHEMAS["queue_fleet"],
            "adapter_key": "queue_fleet",
            "adapter_version": FLEET_ADAPTERS["queue_fleet"],
            "profile": {"id": FLEET_PROFILE},
        },
        "source_key": "p105-fleet-queue",
        "source_family": "queue",
        "source_family_candidate": "queue",
        "runtime_attestation": {"kind": "actual_rabbitmq_docker", "capability": "actual_rabbitmq_docker"},
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    return path


def _minimal_nested_fleet_runtime_manifest(tmp_path: Path, adapter_key: str) -> Path:
    family = {"database_fleet": "database", "queue_fleet": "queue", "deploy_fleet": "deploy"}[adapter_key]
    root = tmp_path / adapter_key
    source_key = f"p105-fleet-{family}"
    public = _write_jsonl(
        root / "public.jsonl",
        [
            {
                "source_key": source_key,
                "source_window_id": f"{source_key}-window-001",
                "partition_id": "held_out_test",
                "coverage_bucket_seconds": 60,
                "service": f"p105.fleet.{family}.000",
            }
        ],
    )
    coverage = _write_json(root / "coverage.json", {"observed_intervals": {f"p105.fleet.{family}.000": [{"start_tick": 0, "end_tick": 60}]}})
    partitions = _write_json(root / "partitions.json", {"records": [{"source_window_id": f"{source_key}-window-001", "partition_id": "held_out_test"}]})
    private_ledger = _write_json(root / "private-ledger.json", {"public_artifact": False, "records": []})
    return _write_json(
        root / "manifest.json",
        {
            "public_config": {
                "schema_version": FLEET_ROOT_SCHEMAS[adapter_key],
                "adapter_key": adapter_key,
                "adapter_version": FLEET_ADAPTERS[adapter_key],
                "profile": {"id": FLEET_PROFILE},
            },
            "source_key": source_key,
            "artifact_paths": {
                "public_telemetry": public.name,
                "coverage": coverage.name,
                "partitions": partitions.name,
                "private_injection_ledger": private_ledger.name,
            },
            "runtime_attestation": {"kind": f"actual_{family}_fleet", "capability": f"actual_{family}_fleet"},
        },
    )


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("adapter_key", "queue"),
        ("adapter_version", "p105.adapter.rabbitmq-harness.v1"),
        ("profile", {"id": "p105.queue.rabbitmq.v1"}),
        ("adapter_key", None),
        ("adapter_version", None),
        ("profile", None),
    ],
)
def test_registry_resolves_nested_public_config_fleet_declarations_and_fails_closed(tmp_path: Path, field: str, value: Any) -> None:
    payload = _wrapped_queue_fleet_manifest()
    if value is None:
        payload["public_config"].pop(field)
    else:
        payload["public_config"][field] = value
    manifest = _write_json(tmp_path / "queue-fleet-manifest.json", payload)

    completed = _run_registry_for_manifest(tmp_path, manifest)

    assert completed.returncode != 0
    assert "cross_profile_schema_adapter_mismatch" in completed.stderr


def test_registry_accepts_exact_nested_queue_fleet_declarations_before_later_validation(tmp_path: Path) -> None:
    manifest = _write_json(tmp_path / "queue-fleet-manifest.json", _wrapped_queue_fleet_manifest())

    completed = _run_registry_for_manifest(tmp_path, manifest)

    assert completed.returncode != 0
    assert "cross_profile_schema_adapter_mismatch" not in completed.stderr
    assert "unknown_source_schema" not in completed.stderr
    assert "runtime source queue_fleet is missing required artifacts" in completed.stderr


def test_registry_accepts_complete_legacy_deploy_manifest_alongside_closed_fleet_adapter() -> None:
    registry = _registry_api()
    manifest = {
        "verifier_compatibility": {"manifest_schema": "p105.deploy.harness.manifest.v1"},
        "artifact_paths": {
            "actual_coverage": "coverage.json",
            "harness_manifest": "manifest.json",
            "pre_label_partitions": "partitions.json",
            "private_injection_ledger": "private.json",
            "provenance_hashes": "provenance.json",
            "public_telemetry": "telemetry.jsonl",
            "raw_attestation": "attestation.json",
            "rollback_evidence": "rollback.json",
        },
    }

    registry._validate_closed_adapter_profile(
        Path("legacy-deploy-manifest.json"),
        manifest,
        ALL_SCHEMA_ADAPTERS,
        fail_on_unknown_source_schema=True,
    )


def test_registry_infers_exact_fleet_families_from_nested_public_config_without_top_level_family(tmp_path: Path) -> None:
    manifests = [_minimal_nested_fleet_runtime_manifest(tmp_path, adapter_key) for adapter_key in ("database_fleet", "queue_fleet", "deploy_fleet")]
    ledger = _write_json(tmp_path / "ledger.json", {"schema_version": "p105.source-review-ledger.v1", "decisions": []})
    completed = subprocess.run(
        [
            sys.executable,
            str(REGISTRY_SCRIPT),
            *[item for manifest in manifests for item in ("--candidate-manifest", str(manifest))],
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

    assert completed.returncode == 0, completed.stderr
    registry = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    families = {source["source_system"]: (source["source_family"], source["source_family_candidate"]) for source in registry["sources"]}
    assert families == {
        "database_fleet": ("database", "database"),
        "queue_fleet": ("queue", "queue"),
        "deploy_fleet": ("deploy", "deploy"),
    }


def test_fleet_registry_uses_one_receipt_bound_source_entry_instead_of_copying_every_sample(tmp_path: Path) -> None:
    manifest = _minimal_nested_fleet_runtime_manifest(tmp_path, "queue_fleet")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    public_path = manifest.parent / payload["artifact_paths"]["public_telemetry"]
    _write_jsonl(
        public_path,
        [
            {
                "source_key": "p105-fleet-queue",
                "source_window_id": f"p105-fleet-queue-window-{index:03d}",
                "partition_id": "held_out_test",
                "coverage_bucket_seconds": 60,
            }
            for index in range(100)
        ],
    )
    ledger = _write_json(tmp_path / "ledger.json", {"schema_version": "p105.source-review-ledger.v1", "decisions": []})
    registry_path = tmp_path / "registry.json"
    eligibility_path = tmp_path / "eligibility.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(REGISTRY_SCRIPT),
            "--candidate-manifest",
            str(manifest),
            "--review-ledger",
            str(ledger),
            "--output-registry",
            str(registry_path),
            "--output-eligibility",
            str(eligibility_path),
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

    assert completed.returncode == 0, completed.stderr
    entries = json.loads(eligibility_path.read_text(encoding="utf-8"))["entries"]
    assert len(entries) == 1
    assert entries[0]["source_window_id"] == "p105-fleet-queue"
    assert entries[0]["coverage_interval_ids"]


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


def test_fleet_only_canonical_rerun_selection_does_not_require_legacy_manifests() -> None:
    verifier = _verifier_api()
    args = verifier._build_arg_parser().parse_args(
        [
            "--phase",
            "runtime",
            "--database-fleet-manifest",
            "database-fleet.json",
            "--database-fleet-rerun-manifest",
            "database-fleet-rerun.json",
            "--queue-fleet-manifest",
            "queue-fleet.json",
            "--queue-fleet-rerun-manifest",
            "queue-fleet-rerun.json",
            "--deploy-fleet-manifest",
            "deploy-fleet.json",
            "--deploy-fleet-rerun-manifest",
            "deploy-fleet-rerun.json",
        ]
    )

    specs = verifier._canonical_rerun_specs(args, legacy_args_present=False, fleet_args_present=True)

    assert [source for source, _, _ in specs] == ["database_fleet", "queue_fleet", "deploy_fleet"]


def test_runtime_materializer_selects_bounded_public_evidence_per_service_partition() -> None:
    selector = _forecast_api()._g006_select_runtime_records
    records = [
        (
            index,
            json.dumps({"source_window_id": f"window-{index}"}),
                {
                    "adapter_key": "queue_fleet",
                    "source_window_id": f"window-{index}",
                "service": "queue-svc-001",
                "partition_id": "held_out",
                "messages_ready": 1 if index == 500 else 0,
                "private_label": {"label_positive": index % 2 == 0},
            },
        )
        for index in range(1000)
    ]

    selected = selector(records, source_system="queue_fleet")
    selected_without_private_labels = selector(
        [(offset, raw, {key: value for key, value in record.items() if key != "private_label"}) for offset, raw, record in records],
        source_system="queue_fleet",
    )

    assert [offset for offset, _, _ in selected] == [0, 500, 999]
    assert [offset for offset, _, _ in selected_without_private_labels] == [0, 500, 999]


def test_runtime_partition_falls_back_to_fleet_window_identity() -> None:
    partition = _forecast_api()._g006_runtime_partition(
        {"source_window_id": "p105-fleet-deploy-real_derived_shadow-svc007-sample123"}
    )

    assert partition == "real_derived_shadow"


def test_runtime_selector_deduplicates_same_fleet_signal_across_services() -> None:
    selector = _forecast_api()._g006_select_runtime_records
    records = []
    offset = 0
    for service_index in range(10):
        for sample_ordinal, messages_ready in ((0, 0), (181, 1), (719, 0)):
            record = {
                "adapter_key": "queue_fleet",
                "source_window_id": f"queue-held_out-svc{service_index:03d}-sample{sample_ordinal:03d}",
                "service": f"queue-svc-{service_index:03d}",
                "partition_id": "held_out",
                "sample_ordinal": sample_ordinal,
                "messages_ready": messages_ready,
                "dlq_messages_ready": 0,
            }
            records.append((offset, json.dumps(record), record))
            offset += 1

    selected = selector(records, source_system="queue_fleet")

    assert sum(record["messages_ready"] > 0 for _, _, record in selected) == 1


def test_runtime_selector_collapses_contiguous_fleet_signal_episode() -> None:
    selector = _forecast_api()._g006_select_runtime_records
    records = []
    for offset, (sample_ordinal, messages_ready) in enumerate(
        ((0, 0), (181, 1), (182, 1), (183, 1), (400, 0), (500, 1), (501, 1), (719, 0))
    ):
        record = {
            "adapter_key": "queue_fleet",
            "source_window_id": f"queue-held_out-svc000-sample{sample_ordinal:03d}",
            "service": "queue-svc-000",
            "partition_id": "held_out",
            "sample_ordinal": sample_ordinal,
            "messages_ready": messages_ready,
            "dlq_messages_ready": 0,
        }
        records.append((offset, json.dumps(record), record))

    selected = selector(records, source_system="queue_fleet")

    selected_signal_ordinals = [
        record["sample_ordinal"]
        for _, _, record in selected
        if record["messages_ready"] > 0
    ]
    assert selected_signal_ordinals == [181, 500]


def test_runtime_selector_requires_correlated_database_fleet_precursors() -> None:
    selector = _forecast_api()._g006_select_runtime_records
    records = []
    offset = 0
    for service_index, onset in ((0, 60), (1, 61), (2, 62), (4, 66), (5, 66), (6, 67)):
        for sample_ordinal in (0, onset, onset + 4, 719):
            signal = sample_ordinal in (onset, onset + 4)
            record = {
                "adapter_key": "database_fleet",
                "source_window_id": f"database-held_out-svc{service_index:03d}-sample{sample_ordinal:03d}",
                "service_id": f"database-svc-{service_index:03d}",
                "partition_id": "held_out",
                "sample_ordinal": sample_ordinal,
                "acquisition_failed": False,
                "acquire_wait_slow_observed": False,
                "transaction_slow_observed": signal,
                "sql_error_count": 0,
            }
            records.append((offset, json.dumps(record), record))
            offset += 1
    for sample_ordinal in (0, 300, 719):
        isolated = {
            "adapter_key": "database_fleet",
            "source_window_id": f"database-held_out-svc100-sample{sample_ordinal:03d}",
            "service_id": "database-svc-100",
            "partition_id": "held_out",
            "sample_ordinal": sample_ordinal,
            "acquisition_failed": False,
            "acquire_wait_slow_observed": False,
            "transaction_slow_observed": sample_ordinal == 300,
            "sql_error_count": 0,
        }
        records.append((offset, json.dumps(isolated), isolated))
        offset += 1

    selected = selector(records, source_system="database_fleet")

    selected_signal_ordinals = [
        record["sample_ordinal"]
        for _, _, record in selected
        if record["transaction_slow_observed"]
    ]
    assert selected_signal_ordinals == [60, 66]


def test_runtime_selector_does_not_bypass_database_correlation_at_boundaries() -> None:
    selector = _forecast_api()._g006_select_runtime_records
    records = []
    for offset, (sample_ordinal, signal) in enumerate(
        ((0, True), (10, False), (20, True))
    ):
        record = {
            "adapter_key": "database_fleet",
            "source_window_id": f"database-held_out-svc100-sample{sample_ordinal:03d}",
            "service_id": "database-svc-100",
            "partition_id": "held_out",
            "sample_ordinal": sample_ordinal,
            "acquisition_failed": False,
            "acquire_wait_slow_observed": False,
            "transaction_slow_observed": signal,
            "sql_error_count": 0,
        }
        records.append((offset, json.dumps(record), record))

    selected = selector(records, source_system="database_fleet")

    assert all(
        record["transaction_slow_observed"] is False
        for _, _, record in selected
    )


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


def test_fleet_materializer_rejects_even_valid_profile_shape_without_verifier_owned_receipt(tmp_path: Path) -> None:
    manifest = _write_json(
        tmp_path / "database-fleet-manifest.json",
        {
            "schema_version": FLEET_ROOT_SCHEMAS["database_fleet"],
            "adapter_key": "database_fleet",
            "adapter_version": FLEET_ADAPTERS["database_fleet"],
            "profile": FLEET_PROFILE,
        },
    )

    with pytest.raises(ValueError, match="fleet_verified_runtime_receipt_required"):
        _forecast_api().materialize_p105_release_qualified_evidence(
            p32_replay="evals/telemetry/replay/p32_replay_pack.json",
            p41_sources="evals/real_datasets/raw/p41_sources.json",
            p44_mode="disabled",
            database_fleet_manifest=manifest,
            schema_adapters=ALL_SCHEMA_ADAPTERS,
            output_dir=tmp_path / "release",
        )


def test_fleet_private_ledger_expands_exact_window_bindings_without_public_label_inference(tmp_path: Path) -> None:
    ledger = _write_json(
        tmp_path / "private-ledger.json",
        {
            "schedule": [
                {
                    "incident_group_id": "p105-fleet-queue-held_out-g00",
                    "kind": "consumer_slowdown",
                    "private_failure_offset_seconds": 3300,
                    "bound_public_source_window_ids": [
                        "p105-fleet-queue-held_out-svc000-sample180",
                        "p105-fleet-queue-held_out-svc000-sample181",
                    ],
                }
            ]
        },
    )

    labels = _forecast_api()._g006_private_labels_by_window(ledger)

    assert set(labels) == {
        "p105-fleet-queue-held_out-svc000-sample180",
        "p105-fleet-queue-held_out-svc000-sample181",
    }
    assert labels["p105-fleet-queue-held_out-svc000-sample180"] == {
        "incident_group_id": "p105-fleet-queue-held_out-g00",
        "label_failure_mode": "consumer_slowdown",
        "label_incident_id": "p105-fleet-queue-held_out-g00",
        "label_incident_start_timestamp": None,
        "label_positive": True,
        "lead_time_label_minutes": 40.0,
    }


def test_fleet_coverage_artifact_is_materialized_from_segments_not_row_ticks(tmp_path: Path) -> None:
    coverage = _write_json(
        tmp_path / "coverage.json",
        {
            "canonical_segments": [
                {
                    "family": "database",
                    "split": "held_out",
                    "service_id": "p105.fleet.database.000",
                    "start_sample_ordinal": 0,
                    "end_sample_ordinal": 719,
                    "conservative_duration_seconds": 3595,
                }
            ]
        },
    )
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        {"created_at": "2024-03-09T16:25:00Z", "artifact_paths": {"coverage": coverage.name}},
    )

    intervals = _forecast_api()._g006_fleet_coverage_by_service(
        manifest_path,
        json.loads(manifest_path.read_text(encoding="utf-8")),
        "database_fleet",
        "database",
    )

    interval = intervals[("p105.fleet.database.000", "held_out")]
    assert interval["timestamp_source"] == "receipt_bound_monotonic_segment"
    assert interval["start"] == "2024-03-09T16:25:00Z"
    assert interval["end"] == "2024-03-09T17:24:55Z"


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


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"adapter_key": "database_fleet", "acquisition_failed": True, "source_window_id": "sample999"}, 0.86),
        ({"adapter_key": "database_fleet", "transaction_duration_ms": 40.5, "source_window_id": "sample999"}, 0.86),
        ({"adapter_key": "database_fleet", "transaction_slow_observed": True, "source_window_id": "sample999"}, 0.86),
        ({"adapter_key": "database_fleet", "acquire_wait_slow_observed": True, "source_window_id": "sample999"}, 0.86),
        ({"adapter_key": "queue_fleet", "messages_ready": 1, "dlq_messages_ready": 0, "source_window_id": "sample999"}, 0.86),
        ({"adapter_key": "deploy_fleet", "status_code": 503, "source_window_id": "sample999"}, 0.86),
        ({"adapter_key": "queue_fleet", "messages_ready": 0, "dlq_messages_ready": 0, "source_window_id": "sample000"}, 0.01),
    ],
)
def test_fleet_signal_strength_is_derived_from_observed_telemetry_not_row_order(record: dict[str, Any], expected: float) -> None:
    assert _forecast_api()._g006_public_signal_strength(record, "held_out", 0) == expected
