from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
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


def _harness() -> Any:
    return importlib.import_module("scripts.run_p105_queue_fleet_harness")


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
            "normal_heartbeat_messages_per_service": 0,
            "precursor_seed_messages_per_affected_service": 1,
            "poison_invalid_messages_per_affected_service": 1,
            "publish_mode": "one_shot_at_private_precursor_start_then_observe_broker_state",
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
        "canonical_roots": {"queue_fleet": "a" * 64},
        "run_envelopes": [
            {
                "source": "queue_fleet",
                "run_label": "run_1",
                "verified": True,
                "validation_error_codes": [],
            }
        ],
        "verified_fleet_coverage_segments": {
            "queue_fleet": [
                {
                    "service": "p105.fleet.queue.000",
                    "split": "held_out",
                    "conservative_duration_seconds": 3595,
                }
            ]
        },
        "validation_error_codes": [],
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
        receipt["run_envelopes"][0]["verified"] = False
        receipt["run_envelopes"][0]["validation_error_codes"] = ["telemetry_loss"]
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


def test_queue_fleet_harness_compose_and_management_commands_do_not_request_host_ports_or_credentials(tmp_path: Path) -> None:
    harness = _harness()
    compose_path = harness._compose_file(tmp_path, "rabbitmq:3.13-management-alpine")
    compose_text = compose_path.read_text(encoding="utf-8")

    assert "ports:" not in compose_text
    assert "RABBITMQ_DEFAULT_USER" not in compose_text
    assert "RABBITMQ_DEFAULT_PASS" not in compose_text

    command = harness._rabbitmqadmin_command(compose_path, "p105-queue-fleet-test", ["list", "queues"])
    rabbitmqadmin_args = command[command.index("rabbitmqadmin") :]

    assert "-u" not in rabbitmqadmin_args
    assert "-p" not in rabbitmqadmin_args
    assert "guest" not in rabbitmqadmin_args
    assert "--vhost=/" in rabbitmqadmin_args


def test_queue_fleet_harness_derives_container_and_network_from_docker_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    harness = _harness()
    compose_path = tmp_path / "compose.yml"
    attestations: list[Any] = []
    commands: list[list[str]] = []

    def fake_run(command: list[str], *, attestations: list[Any], step: str, input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        del input_text, timeout
        commands.append(command)
        if step == "docker.compose.ps.rabbitmq":
            stdout = "8f4a1c2b3d4e\n"
        elif step == "docker.inspect.rabbitmq":
            stdout = json.dumps([{"NetworkSettings": {"Networks": {"p105-queue-fleet-test_default": {}}}}])
        else:
            raise AssertionError(f"unexpected step {step}")
        completed = subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
        attestations.append(harness.CommandAttestation(step=step, command=command, returncode=0, stdout=stdout, stderr=""))
        return completed

    monkeypatch.setattr(harness, "_run_command", fake_run)

    evidence = harness._docker_runtime_evidence(compose_path, "p105-queue-fleet-test", attestations)

    assert evidence == {
        "container_id": "8f4a1c2b3d4e",
        "docker_network_name": "p105-queue-fleet-test_default",
    }
    assert commands == [
        ["docker", "compose", "-f", str(compose_path), "-p", "p105-queue-fleet-test", "ps", "-q", "rabbitmq"],
        ["docker", "inspect", "8f4a1c2b3d4e"],
    ]


def test_queue_fleet_harness_broker_observation_is_bounded_and_verifier_keyed() -> None:
    harness = _harness()
    rows = [
        {"name": f"p105-fleet-q-{index:03d}", "messages": index, "messages_ready": index % 2, "messages_unacknowledged": 0}
        for index in range(10)
    ] + [
        {"name": f"p105-fleet-dlq-{index:03d}", "messages": 0, "messages_ready": 0, "messages_unacknowledged": 0}
        for index in range(3)
    ]

    observation = harness._bounded_broker_observation(rows)

    assert observation["bounded"] is True
    assert observation["observed_queue_count"] == 10
    assert observation["dead_letter_queue_count"] == 3
    assert observation["truncated"] is True
    assert len(observation["sample_rows"]) == 8
    assert set(observation["sample_rows"][0]) == {"messages", "messages_ready", "messages_unacknowledged", "name"}


def test_queue_fleet_harness_management_observed_requires_successful_rabbitmqadmin_command() -> None:
    harness = _harness()
    observed = [
        harness.CommandAttestation(
            step="rabbitmq.observe.bulk_queues",
            command=["docker", "compose", "exec", "-T", "rabbitmq", "rabbitmqadmin", "--vhost=/", "--format=raw_json", "list", "queues"],
            returncode=0,
            stdout="[]",
            stderr="",
        )
    ]
    failed = [
        harness.CommandAttestation(
            step="rabbitmq.observe.bulk_queues",
            command=["docker", "compose", "exec", "-T", "rabbitmq", "rabbitmqadmin", "--vhost=/", "--format=raw_json", "list", "queues"],
            returncode=1,
            stdout="",
            stderr="failed",
        )
    ]

    assert harness._rabbitmq_management_observed(observed) is True
    assert harness._rabbitmq_management_observed(failed) is False


def test_queue_fleet_incident_messages_are_one_shot_and_normal_services_do_not_create_command_fanout() -> None:
    harness = _harness()
    incidents = harness._affected_incidents_by_service()

    assert harness._message_count_for_service(64, 0, incidents) == (0, 0)
    assert harness._message_count_for_service(0, 900, incidents) == (1, 0)
    assert harness._message_count_for_service(0, 930, incidents) == (0, 0)
    assert harness._message_count_for_service(8, 960, incidents) == (0, 1)
    assert harness._message_count_for_service(8, 990, incidents) == (0, 0)

    active_service_ticks = sum(
        bool(harness._message_count_for_service(service_index, offset, incidents) != (0, 0))
        for offset in harness._sample_offsets(harness.SCHEDULED_SAMPLES_PER_SERVICE)
        for service_index in range(harness.SERVICE_COUNT)
    )
    assert active_service_ticks == 64


def test_queue_fleet_consumption_is_one_compose_exec_batch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    harness = _harness()
    calls: list[tuple[list[str], str | None, str]] = []

    def fake_run(command: list[str], *, attestations: list[Any], step: str, input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        del attestations, timeout
        calls.append((command, input_text, step))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(harness, "_run_command", fake_run)
    harness._consume_rows(
        tmp_path / "compose.yml",
        "p105-queue-fleet-test",
        [],
        [
            ("p105-fleet-q-000", 1, "ack_requeue_false"),
            ("p105-fleet-dlq-008", 1, "ack_requeue_false"),
        ],
    )

    assert len(calls) == 1
    command, input_text, step = calls[0]
    assert command[:6] == ["docker", "compose", "-f", str(tmp_path / "compose.yml"), "-p", "p105-queue-fleet-test"]
    assert input_text == "p105-fleet-q-000\t1\tack_requeue_false\np105-fleet-dlq-008\t1\tack_requeue_false\n"
    assert step == "rabbitmq.consume.batch"


def test_queue_fleet_actual_path_emits_verifier_required_rabbitmq_evidence_without_docker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    harness = _harness()
    args = type(
        "Args",
        (),
        {
            "diagnostic": True,
            "no_sleep": True,
            "output_dir": tmp_path,
            "rabbitmq_image": "rabbitmq:3.13-management-alpine",
        },
    )()

    def fake_run_command(command: list[str], *, attestations: list[Any], step: str, input_text: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        del input_text, timeout
        if step == "docker.compose.ps.rabbitmq":
            stdout = "container-123\n"
        elif step == "docker.inspect.rabbitmq":
            stdout = json.dumps([{"NetworkSettings": {"Networks": {"p105-queue-fleet-test_default": {}}}}])
        else:
            stdout = "ok\n"
        attestations.append(harness.CommandAttestation(step=step, command=command, returncode=0, stdout=stdout, stderr=""))
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    def fake_bulk_observe(compose_file: Path, project_name: str, attestations: list[Any]) -> list[dict[str, Any]]:
        del compose_file, project_name
        attestations.append(
            harness.CommandAttestation(
                step="rabbitmq.observe.bulk_queues",
                command=["docker", "compose", "exec", "-T", "rabbitmq", "rabbitmqadmin", "--vhost=/", "--format=raw_json", "list", "queues"],
                returncode=0,
                stdout="[]",
                stderr="",
            )
        )
        return [
            {"name": f"p105-fleet-q-{index:03d}", "messages": 0, "messages_ready": 0, "messages_unacknowledged": 0}
            for index in range(256)
        ] + [
            {"name": f"p105-fleet-dlq-{index:03d}", "messages": 0, "messages_ready": 0, "messages_unacknowledged": 0}
            for index in range(256)
        ]

    monkeypatch.setattr(harness.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(harness, "_run_command", fake_run_command)
    monkeypatch.setattr(harness, "_wait_for_broker", lambda compose_file, project_name, attestations: None)
    monkeypatch.setattr(harness, "_declare_broker_shape", lambda compose_file, project_name, attestations: 1)
    monkeypatch.setattr(harness, "_publish_rows", lambda compose_file, project_name, attestations, rows: None)
    monkeypatch.setattr(harness, "_consume_rows", lambda compose_file, project_name, attestations, rows: None)
    monkeypatch.setattr(harness, "_bulk_observe", fake_bulk_observe)
    monkeypatch.setattr(harness.subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""))

    _telemetry, _coverage, raw_attestation, cleanup = harness._materialize_actual(args, 1, "p105-queue-fleet-test")

    assert cleanup == {"container_removed": True, "volume_removed": True}
    assert raw_attestation["actual_runtime_executed"] is True
    assert raw_attestation["container_id"] == "container-123"
    assert raw_attestation["docker_network_name"] == "p105-queue-fleet-test_default"
    assert raw_attestation["rabbitmq_management_observed"] is True
    assert raw_attestation["broker_observation"]["bounded"] is True
    assert raw_attestation["broker_observation"]["observed_queue_count"] == 256
