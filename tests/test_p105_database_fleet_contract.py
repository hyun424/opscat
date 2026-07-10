from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

PROFILE = "p105.actual-fleet-soak.256x1h.v1"
DATABASE_FLEET_SCHEMA = "p105.database.fleet_harness.v1"
DATABASE_FLEET_ADAPTER = "p105.adapter.sqlite-pool-fleet-harness.v1"

FORBIDDEN_PUBLIC_KEYS = {
    "label",
    "labels",
    "label_positive",
    "incident_answer_key",
    "incident_group_id",
    "private_failure_second",
    "private_failure_timestamp",
    "scorer_threshold",
    "scorer_thresholds",
    "floor_deficit",
    "floor_deficits",
    "release_qualified",
    "p106_unlocked",
}


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _database_fleet_contract() -> Mapping[str, Any]:
    api = _api()
    builder = getattr(api, "build_p105_database_fleet_profile_contract", None)
    assert callable(builder), "P105 capacity RED: missing build_p105_database_fleet_profile_contract() for database_fleet profile p105.actual-fleet-soak.256x1h.v1"
    contract = builder()
    assert isinstance(contract, Mapping)
    return contract


def _flatten_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        keys: set[str] = set()
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_flatten_keys(child))
        return keys
    if isinstance(value, list):
        keys = set()
        for child in value:
            keys.update(_flatten_keys(child))
        return keys
    return set()


def test_registry_declares_database_fleet_as_closed_adapter_without_reusing_legacy_db_pool() -> None:
    adapters = dict(_api().P105_REQUIRED_SCHEMA_ADAPTERS)

    assert adapters.get("database_fleet") == DATABASE_FLEET_ADAPTER
    assert adapters.get("db_pool") == "p105.adapter.database-pool-harness.v1"
    assert adapters.get("db_pool") != DATABASE_FLEET_ADAPTER


def test_materializer_cli_accepts_dedicated_database_fleet_manifest_argument() -> None:
    parser = _api().build_p105_materializer_cli_parser()

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
            "--output-dir",
            "out",
        ]
    )

    assert args.database_fleet_manifest == "database-fleet.json"
    assert not hasattr(args, "db_pool_fleet_manifest")


def test_database_fleet_profile_shape_is_exact_256_services_128_128_partition_and_sample_grid() -> None:
    contract = _database_fleet_contract()

    assert contract["profile"] == PROFILE
    assert contract["schema_version"] == DATABASE_FLEET_SCHEMA
    assert contract["adapter_key"] == "database_fleet"
    assert contract["adapter_version"] == DATABASE_FLEET_ADAPTER
    assert contract["runtime_attestation_kind"] == "actual_sqlite_pool"
    assert contract["requested_wall_clock_seconds"] == 3600
    assert contract["observation_cadence_seconds"] == 5
    assert contract["scheduled_samples_per_service"] == 720
    assert contract["sample_offsets_seconds"] == list(range(0, 3600, 5))

    services = list(contract["services"])
    held_out = list(contract["partitions"]["held_out"])
    real_derived = list(contract["partitions"]["real_derived_shadow"])
    assert len(services) == 256
    assert len(set(services)) == 256
    assert held_out == [f"p105.fleet.database.{index:03d}" for index in range(128)]
    assert real_derived == [f"p105.fleet.database.{index:03d}" for index in range(128, 256)]


def test_database_fleet_runtime_resource_envelope_requires_64_sqlite_shards_and_real_sql_cycles() -> None:
    resources = _database_fleet_contract()["resource_limits"]

    assert resources["sqlite_shard_files"] == 64
    assert resources["bounded_pools"] == 64
    assert resources["services_per_shard"] == 4
    assert resources["pool_size"] == 3
    assert resources["max_live_sqlite_connections"] == 192
    assert resources["heartbeat_sql_transaction_interval_seconds"] == 30
    assert resources["max_sql_transaction_cycles"] == 40_000
    assert resources["worker_threads"] == 64
    assert resources["process_memory_bytes"] == 1024 * 1024 * 1024
    assert resources["sqlite_files_and_wal_bytes"] == 512 * 1024 * 1024
    assert resources["output_artifacts_bytes"] == 256 * 1024 * 1024
    assert resources["required_sql_operations"] == ["insert", "select", "update"]


def test_database_fleet_schedule_is_exact_g00_to_g07_for_both_splits_with_database_leads() -> None:
    groups = list(_database_fleet_contract()["private_schedule"])

    assert [group["group_id"] for group in groups] == [f"p105-fleet-database-{split}-g{group:02d}" for split in ("held_out", "real_derived_shadow") for group in range(8)]
    for group in groups:
        g = int(str(group["group_id"]).rsplit("g", 1)[1])
        split_base = 0 if group["split"] == "held_out" else 128
        assert group["affected_services"] == [f"p105.fleet.database.{split_base + 4 * g + offset:03d}" for offset in range(4)]
        assert group["group_start_second"] == 300 + 30 * g
        assert group["private_failure_second"] == 3300 + 30 * g
        assert group["positive_precursor_range_seconds"] == [300 + 30 * g, 600 + 30 * g]
        assert group["lead_range_minutes"] == [45, 50]
        assert group["kind"] == ["pool_saturation", "slow_transaction", "lock_contention", "checkout_timeout"][g % 4]
        expected_windows = [
            f"p105-fleet-database-{group['split']}-svc{service_index:03d}-sample{ordinal:03d}"
            for service_index in range(split_base + 4 * g, split_base + 4 * g + 4)
            for ordinal in range((300 + 30 * g) // 5, (600 + 30 * g) // 5 + 1)
        ]
        assert group["expected_bound_public_source_window_ids"] == expected_windows


def test_database_fleet_public_config_excludes_private_labels_and_scorer_answers() -> None:
    contract = _database_fleet_contract()
    public_config = contract["public_config"]

    assert _flatten_keys(public_config).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
    assert public_config["profile"] == PROFILE
    assert public_config["adapter_key"] == "database_fleet"
    assert public_config["runtime_attestation_kind"] == "actual_sqlite_pool"
    assert public_config["partitioned_before_private_schedule_loading"] is True
    assert len(public_config["profile_config_hash"]) == 64
    assert public_config["profile_config_hash_phase"] == "before_private_schedule_loading"
    assert contract["private_schedule_loaded_after_profile_hash"] is True


def test_database_fleet_rejects_legacy_schema_or_wrong_profile_before_counting() -> None:
    api = _api()
    validator = getattr(api, "validate_p105_database_fleet_manifest_contract", None)
    assert callable(validator), "P105 capacity RED: missing database_fleet manifest/profile validator"

    legacy_schema = validator({"schema_version": "p105.database.pool.harness_manifest.v1", "profile": PROFILE, "adapter_key": "database_fleet"})
    wrong_profile = validator({"schema_version": DATABASE_FLEET_SCHEMA, "profile": "p105.database.pool.v1", "adapter_key": "database_fleet"})
    legacy_adapter = validator({"schema_version": DATABASE_FLEET_SCHEMA, "profile": PROFILE, "adapter_key": "db_pool"})

    assert "database_fleet_schema_required" in legacy_schema["validation_error_codes"]
    assert "database_fleet_profile_required" in wrong_profile["validation_error_codes"]
    assert "database_fleet_adapter_required" in legacy_adapter["validation_error_codes"]
    assert legacy_schema["release_counting_allowed"] is False
    assert wrong_profile["release_counting_allowed"] is False
    assert legacy_adapter["release_counting_allowed"] is False


def test_database_fleet_fast_diagnostic_uses_actual_sqlite_pool_but_is_non_counting() -> None:
    contract = _database_fleet_contract()
    diagnostic = contract["diagnostic_profile"]

    assert diagnostic["non_qualifying"] is True
    assert diagnostic["runtime_qualification_eligible"] is False
    assert diagnostic["runtime_attestation_kind"] == "actual_sqlite_pool"
    assert diagnostic["requested_wall_clock_seconds"] < contract["requested_wall_clock_seconds"]
    assert diagnostic["service_count"] < 256
    assert diagnostic["forbidden_release_credit"] == ["rows", "positives", "incident_groups", "coverage"]
    assert "release_counting_allowed" not in diagnostic
