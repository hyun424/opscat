from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

PROFILE_ID = "p105.actual-fleet-soak.256x1h.v1"
DIAGNOSTIC_PROFILE_ID = "p105.queue-fleet.diagnostic.fast.v1"
QUEUE_SCHEMA = "p105.queue.fleet_harness.v1"
QUEUE_ADAPTER_KEY = "queue_fleet"
QUEUE_ADAPTER_VERSION = "p105.adapter.rabbitmq-fleet-harness.v1"


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _validator() -> Any:
    validator = getattr(_api(), "validate_p105_queue_fleet_contract", None)
    if validator is None:
        pytest.fail(
            "P105-031 RED: expose validate_p105_queue_fleet_contract before queue_fleet can receive release credit.",
            pytrace=False,
        )
    return validator


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _service_id(index: int) -> str:
    return f"p105.fleet.queue.{index:03d}"


def _source_window_id(split: str, service_index: int, ordinal: int) -> str:
    return f"p105-fleet-queue-{split}-svc{service_index:03d}-sample{ordinal:03d}"


def _fleet_schedule() -> list[dict[str, Any]]:
    schedule = []
    for split, base in (("held_out", 0), ("real_derived_shadow", 128)):
        for group in range(8):
            start = 900 + 30 * group
            failure = 3300 + 30 * group
            services = [base + offset for offset in range(4 * group, 4 * group + 4)]
            start_ordinal = start // 5
            end_ordinal = (start + 300) // 5
            schedule.append(
                {
                    "incident_group_id": f"p105-fleet-queue-{split}-g{group:02d}",
                    "group": f"g{group:02d}",
                    "split": split,
                    "kind_index": group % 4,
                    "kind": [
                        "consumer_slowdown",
                        "consumer_pause",
                        "poison_dead_letter",
                        "bounded_producer_burst",
                    ][group % 4],
                    "affected_services": [_service_id(index) for index in services],
                    "private_failure_offset_seconds": failure,
                    "positive_precursor_start_offset_seconds": start,
                    "positive_precursor_end_offset_seconds": start + 300,
                    "lead_time_minutes": {"minimum": 35, "maximum": 40},
                    "bound_public_source_window_ids": [_source_window_id(split, service_index, ordinal) for service_index in services for ordinal in range(start_ordinal, end_ordinal + 1)],
                }
            )
    return schedule


def _queue_fleet_manifest() -> dict[str, Any]:
    services = [_service_id(index) for index in range(256)]
    public_config = {
        "schema_version": QUEUE_SCHEMA,
        "adapter_key": QUEUE_ADAPTER_KEY,
        "adapter_version": QUEUE_ADAPTER_VERSION,
        "profile": {
            "id": PROFILE_ID,
            "hash": _json_sha256({"profile": PROFILE_ID, "services": services, "cadence_seconds": 5}),
            "hash_phase": "before_private_schedule_loading",
        },
        "runtime": {
            "kind": "actual_rabbitmq_docker",
            "rabbitmq_image": "rabbitmq:3.13-management-alpine",
            "isolated_run_container": True,
            "in_memory_queue_simulation": False,
            "broker_health_observed": True,
        },
        "services": services,
        "partitions": {
            "assigned_before_private_schedule_loading": True,
            "held_out": services[:128],
            "real_derived_shadow": services[128:],
        },
        "sample_plan": {
            "requested_runtime_seconds": 3600,
            "cadence_seconds": 5,
            "scheduled_samples_per_service": 720,
            "offsets_seconds": list(range(0, 3600, 5)),
        },
        "queues": {
            "queues": [f"p105-fleet-q-{index:03d}" for index in range(256)],
            "dead_letter_queues": [f"p105-fleet-dlq-{index:03d}" for index in range(256)],
        },
        "message_plan": {
            "heartbeat_period_seconds": 30,
            "heartbeat_messages_per_service": 1,
            "producer_burst_messages_per_affected_service": 5,
            "poison_invalid_messages_per_affected_service": 2,
            "maximum_published_messages": 35872,
            "maximum_consumed_or_rejected_messages": 35872,
        },
        "management_plan": {
            "bulk_broker_state_observation_per_sample": True,
            "maximum_concurrent_management_operations": 8,
            "maximum_management_http_calls": 80000,
        },
        "resource_maxima": {
            "maximum_total_queues": 512,
            "container_memory_mib": 1024,
            "broker_disk_mib": 512,
            "output_artifact_mib": 256,
        },
        "cleanup": {
            "isolated_docker_project": "p105-queue-fleet-run-001",
            "container_removed": True,
            "volume_removed": True,
            "cleanup_scope": "isolated_run_container_and_volume_only",
        },
        "authority": {
            "credentials_read": False,
            "external_broker_endpoint": False,
            "host_ports": [],
            "production_mutation": False,
            "action_plan": False,
            "action_execution": False,
            "release_counting_authority": False,
        },
    }
    return {
        "public_config": public_config,
        "private_injection_ledger": {
            "loaded_after_public_config_hash": _json_sha256(public_config),
            "label_join_phase": "after_sampling_and_partition",
            "schedule": _fleet_schedule(),
        },
    }


def _queue_fleet_receipt() -> dict[str, Any]:
    return {
        "schema_version": "p105.source-runtime-qualification.v1",
        "created_by": "scripts/verify_p105_source_expansion_artifacts.py",
        "verified_release_counting": True,
        "locked": False,
        "release_counting": True,
        "coverage_source": "receipt_bound_monotonic_segments",
        "legacy_created_at_tick_seconds_coverage": False,
        "telemetry_complete": True,
        "failure_codes": [],
    }


def test_queue_fleet_profile_requires_exact_public_capacity_shape_and_resource_bounds(tmp_path: Path) -> None:
    manifest = _write_json(tmp_path / "queue-fleet.json", _queue_fleet_manifest())

    result = _validator()(manifest, verifier_receipt=_queue_fleet_receipt())

    assert result["accepted"] is True
    assert result["profile_id"] == PROFILE_ID
    assert result["adapter_key"] == QUEUE_ADAPTER_KEY
    assert result["runtime_kind"] == "actual_rabbitmq_docker"
    assert result["queue_count"] == 256
    assert result["dead_letter_queue_count"] == 256
    assert result["partition_counts"] == {"held_out": 128, "real_derived_shadow": 128}
    assert result["scheduled_samples_per_service"] == 720
    assert result["sample_offsets_seconds"] == {"first": 0, "last": 3595, "step": 5}
    assert result["message_maxima"] == {"published": 35872, "consumed_or_rejected": 35872}
    assert result["management_maxima"] == {"concurrent_operations": 8, "http_calls": 80000}
    assert result["resource_maxima"] == {"queues": 512, "memory_mib": 1024, "disk_mib": 512, "output_mib": 256}


def test_queue_fleet_private_schedule_is_exact_g00_through_g07_with_35_to_40_minute_lead(tmp_path: Path) -> None:
    manifest = _write_json(tmp_path / "queue-fleet.json", _queue_fleet_manifest())

    result = _validator()(manifest, verifier_receipt=_queue_fleet_receipt())

    assert result["schedule"]["groups_by_split"] == {
        "held_out": [f"g{index:02d}" for index in range(8)],
        "real_derived_shadow": [f"g{index:02d}" for index in range(8)],
    }
    assert result["schedule"]["queue_group_rows"] == [
        {
            "split": split,
            "group": f"g{index:02d}",
            "kind_index": index % 4,
            "kind": ["consumer_slowdown", "consumer_pause", "poison_dead_letter", "bounded_producer_burst"][index % 4],
            "affected_services": [_service_id(base + 4 * index + offset) for offset in range(4)],
            "precursor_start_seconds": 900 + 30 * index,
            "private_failure_seconds": 3300 + 30 * index,
            "lead_minutes": {"minimum": 35, "maximum": 40},
        }
        for split, base in (("held_out", 0), ("real_derived_shadow", 128))
        for index in range(8)
    ]
    assert result["schedule"]["controls_per_split"] == {"held_out": 96, "real_derived_shadow": 96}


def test_queue_fleet_public_config_is_label_blind_and_private_ledger_binds_exact_sampled_windows(tmp_path: Path) -> None:
    manifest = _write_json(tmp_path / "queue-fleet.json", _queue_fleet_manifest())

    result = _validator()(manifest, verifier_receipt=_queue_fleet_receipt())

    assert result["public_config_forbidden_keys_present"] == []
    assert result["private_ledger_loaded_after_public_profile_hash"] is True
    assert result["private_source_window_binding"] == {
        "uses_exact_already_sampled_source_window_ids": True,
        "uses_arithmetic_ranges": False,
        "bound_window_count": 16 * 4 * 61,
    }


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing_broker_health", "queue_fleet_broker_health_missing"),
        ("telemetry_loss", "queue_fleet_telemetry_loss"),
        ("cleanup_scope_escape", "queue_fleet_cleanup_scope_escape"),
        ("partial_cleanup", "queue_fleet_partial_cleanup"),
        ("message_bound_breach", "queue_fleet_message_bound_breach"),
    ],
)
def test_queue_fleet_failures_lock_receipt_and_make_all_fleet_evidence_non_counting(tmp_path: Path, mutation: str, expected_code: str) -> None:
    payload = _queue_fleet_manifest()
    receipt = _queue_fleet_receipt()
    if mutation == "missing_broker_health":
        payload["public_config"]["runtime"]["broker_health_observed"] = False
    elif mutation == "telemetry_loss":
        receipt["telemetry_complete"] = False
    elif mutation == "cleanup_scope_escape":
        payload["public_config"]["cleanup"]["cleanup_scope"] = "all_docker_volumes"
    elif mutation == "partial_cleanup":
        payload["public_config"]["cleanup"]["volume_removed"] = False
    elif mutation == "message_bound_breach":
        payload["public_config"]["message_plan"]["maximum_published_messages"] = 35873
    manifest = _write_json(tmp_path / f"{mutation}.json", payload)

    result = _validator()(manifest, verifier_receipt=receipt)

    assert result["accepted"] is False
    assert result["receipt"] == {"locked": True, "release_counting": False}
    assert result["counting_coverage_seconds"] == 0
    assert expected_code in result["validation_error_codes"]


@pytest.mark.parametrize(
    ("schema_version", "adapter_key", "profile_id", "expected_code"),
    [
        ("p105.queue.rabbitmq.v1", "queue_fleet", PROFILE_ID, "queue_fleet_rejects_legacy_root_schema"),
        (QUEUE_SCHEMA, "queue", PROFILE_ID, "queue_fleet_requires_closed_adapter_key"),
        (QUEUE_SCHEMA, QUEUE_ADAPTER_KEY, "p105.queue.rabbitmq.v1", "queue_fleet_rejects_legacy_profile"),
    ],
)
def test_queue_fleet_rejects_legacy_or_cross_profile_substitution(tmp_path: Path, schema_version: str, adapter_key: str, profile_id: str, expected_code: str) -> None:
    payload = _queue_fleet_manifest()
    payload["public_config"]["schema_version"] = schema_version
    payload["public_config"]["adapter_key"] = adapter_key
    payload["public_config"]["profile"]["id"] = profile_id
    manifest = _write_json(tmp_path / "cross-profile.json", payload)

    result = _validator()(manifest, verifier_receipt=_queue_fleet_receipt())

    assert result["accepted"] is False
    assert result["receipt"] == {"locked": True, "release_counting": False}
    assert expected_code in result["validation_error_codes"]


def test_queue_fleet_fast_diagnostic_profile_exercises_actual_rabbitmq_but_never_counts_for_release(tmp_path: Path) -> None:
    payload = _queue_fleet_manifest()
    payload["public_config"]["profile"]["id"] = DIAGNOSTIC_PROFILE_ID
    payload["public_config"]["sample_plan"] = {
        "requested_runtime_seconds": 30,
        "cadence_seconds": 5,
        "scheduled_samples_per_service": 6,
        "offsets_seconds": [0, 5, 10, 15, 20, 25],
    }
    payload["public_config"]["authority"]["release_counting_authority"] = False
    payload["public_config"]["profile"]["hash"] = _json_sha256(
        {
            "profile": DIAGNOSTIC_PROFILE_ID,
            "services": payload["public_config"]["services"],
            "cadence_seconds": 5,
        }
    )
    payload["private_injection_ledger"]["loaded_after_public_config_hash"] = _json_sha256(payload["public_config"])
    manifest = _write_json(tmp_path / "queue-fleet-diagnostic.json", payload)

    result = _validator()(manifest, verifier_receipt=None)

    assert result["accepted"] is True
    assert result["profile_id"] == DIAGNOSTIC_PROFILE_ID
    assert result["runtime_kind"] == "actual_rabbitmq_docker"
    assert result["diagnostic_only"] is True
    assert result["receipt"] == {"locked": False, "release_counting": False}
    assert result["counting_coverage_seconds"] == 0
    assert result["release_floor_credit"] == {"rows": 0, "positives": 0, "groups": 0, "coverage_seconds": 0}


def test_queue_fleet_public_config_rejects_labels_scores_deficits_and_release_outcomes(tmp_path: Path) -> None:
    payload = _queue_fleet_manifest()
    payload["public_config"]["release_qualified"] = True
    payload["public_config"]["floor_deficits"] = {"queue": 0}
    payload["public_config"]["labels"] = {"p105-fleet-queue-held_out-g00": "positive"}
    payload["public_config"]["scorer_thresholds"] = {"minimum_union_service_days": 7.0}
    manifest = _write_json(tmp_path / "label-leak.json", payload)

    result = _validator()(manifest, verifier_receipt=_queue_fleet_receipt())

    assert result["accepted"] is False
    assert result["receipt"] == {"locked": True, "release_counting": False}
    assert {
        "queue_fleet_public_label_leak",
        "queue_fleet_public_floor_deficit_leak",
        "queue_fleet_public_release_outcome_leak",
        "queue_fleet_public_scorer_threshold_leak",
    } <= set(result["validation_error_codes"])


def test_queue_fleet_profile_hash_is_frozen_before_private_schedule_loading(tmp_path: Path) -> None:
    payload = _queue_fleet_manifest()
    payload["private_injection_ledger"]["schedule"][0]["affected_services"] = [_service_id(127)]
    manifest = _write_json(tmp_path / "private-schedule-tamper.json", payload)

    result = _validator()(manifest, verifier_receipt=_queue_fleet_receipt())

    assert result["accepted"] is False
    assert result["receipt"] == {"locked": True, "release_counting": False}
    assert "queue_fleet_private_schedule_changed_after_public_profile_hash" in result["validation_error_codes"]


def test_queue_fleet_rejects_duplicate_positive_group_or_service_interval_credit(tmp_path: Path) -> None:
    payload = _queue_fleet_manifest()
    receipt = _queue_fleet_receipt()
    duplicate_window = payload["private_injection_ledger"]["schedule"][0]["bound_public_source_window_ids"][0]
    payload["private_injection_ledger"]["schedule"][0]["bound_public_source_window_ids"].append(duplicate_window)
    receipt["duplicate_group_ids"] = ["p105-fleet-queue-held_out-g00"]
    receipt["duplicate_service_interval_ids"] = ["p105.fleet.queue.000:sample180-181"]
    manifest = _write_json(tmp_path / "duplicate-credit.json", payload)

    result = _validator()(manifest, verifier_receipt=receipt)

    assert result["accepted"] is False
    assert result["receipt"] == {"locked": True, "release_counting": False}
    assert {
        "queue_fleet_duplicate_source_window_credit",
        "queue_fleet_duplicate_group_credit",
        "queue_fleet_duplicate_service_interval_credit",
    } <= set(result["validation_error_codes"])


def test_queue_fleet_receipt_rejects_legacy_created_at_tick_seconds_coverage_path(tmp_path: Path) -> None:
    payload = _queue_fleet_manifest()
    receipt = _queue_fleet_receipt()
    receipt["coverage_source"] = "created_at_plus_tick_seconds"
    receipt["legacy_created_at_tick_seconds_coverage"] = True
    manifest = _write_json(tmp_path / "legacy-coverage.json", payload)

    result = _validator()(manifest, verifier_receipt=receipt)

    assert result["accepted"] is False
    assert result["receipt"] == {"locked": True, "release_counting": False}
    assert "queue_fleet_legacy_row_coverage_path" in result["validation_error_codes"]
