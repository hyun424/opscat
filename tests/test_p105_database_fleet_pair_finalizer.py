from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest


def _module() -> Any:
    return importlib.import_module("scripts.finalize_p105_database_fleet_pair")


def _row(*, duration_ms: float, acquire_ms: float, failed: bool, observed: bool = True) -> dict[str, Any]:
    row: dict[str, Any] = {
        "acquisition_failed": failed,
        "acquire_wait_ms": acquire_ms,
        "adapter_key": "database_fleet",
        "heartbeat_sql_cycle_observed": observed,
        "partition_id": "held_out",
        "sample_offset_seconds": 300,
        "sample_ordinal": 60,
        "service_id": "p105.fleet.database.000",
        "source_window_id": "p105-fleet-database-held_out-svc000-sample060",
        "sql_insert_count": 1 if observed else 0,
        "sql_select_count": 1 if observed else 0,
        "sql_update_count": 1 if observed else 0,
        "transaction_duration_ms": duration_ms,
    }
    row["telemetry_row_sha256"] = hashlib.sha256(
        json.dumps({"database_fleet_public_row": row}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return row


def test_database_fleet_pair_consensus_keeps_only_repeated_observed_signal_and_rehashes() -> None:
    module = _module()
    first = _row(duration_ms=48.0, acquire_ms=31.0, failed=False)
    second = _row(duration_ms=43.0, acquire_ms=2.0, failed=False)

    canonical = module.consensus_public_row(first, second)

    assert canonical["transaction_slow_observed"] is True
    assert canonical["acquire_wait_slow_observed"] is False
    assert "transaction_duration_ms" not in canonical
    assert "acquire_wait_ms" not in canonical
    assert canonical["acquisition_failed"] is False
    assert canonical["measurement_normalization"] == "paired_actual_observation_consensus.v1"
    assert canonical["measurement_consensus_runs"] == 2
    assert canonical["measurement_uses_private_schedule"] is False
    expected_hash = hashlib.sha256(
        json.dumps(
            {"database_fleet_public_row": {key: value for key, value in canonical.items() if key != "telemetry_row_sha256"}},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert canonical["telemetry_row_sha256"] == expected_hash


def test_database_fleet_pair_consensus_rejects_identity_mismatch_or_tampered_input_hash() -> None:
    module = _module()
    first = _row(duration_ms=48.0, acquire_ms=31.0, failed=False)
    second = _row(duration_ms=43.0, acquire_ms=30.0, failed=False)
    second["source_window_id"] = "p105-fleet-database-held_out-svc000-sample061"

    with pytest.raises(ValueError, match="database_fleet_pair_identity_mismatch"):
        module.consensus_public_row(first, second)

    second = _row(duration_ms=43.0, acquire_ms=30.0, failed=False)
    second["transaction_duration_ms"] = 1.0
    with pytest.raises(ValueError, match="database_fleet_measured_row_hash_mismatch"):
        module.consensus_public_row(first, second)


def test_database_fleet_pair_consensus_requires_two_actual_observations_for_failure() -> None:
    module = _module()
    first = _row(duration_ms=1.0, acquire_ms=76.0, failed=True, observed=False)
    second = _row(duration_ms=42.0, acquire_ms=2.0, failed=False, observed=True)

    canonical = module.consensus_public_row(first, second)

    assert canonical["acquisition_failed"] is False
    assert canonical["heartbeat_sql_cycle_observed"] is False
    assert canonical["sql_insert_count"] == 0
    assert canonical["sql_select_count"] == 0
    assert canonical["sql_update_count"] == 0


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "label",
        "labels",
        "label_positive",
        "incident_answer_key",
        "incident_group_id",
        "incident_kind",
        "incident_runtime_kind",
        "private_failure_offset_seconds",
        "private_failure_second",
        "private_failure_timestamp",
        "scorer_threshold",
        "scorer_thresholds",
        "floor_deficit",
        "floor_deficits",
        "release_qualified",
        "p106_unlocked",
    ],
)
def test_database_fleet_pair_consensus_rejects_nested_private_or_release_fields(forbidden_key: str) -> None:
    module = _module()
    first = _row(duration_ms=48.0, acquire_ms=31.0, failed=False)
    second = _row(duration_ms=43.0, acquire_ms=30.0, failed=False)
    first["nested"] = {forbidden_key: True}
    second["nested"] = {forbidden_key: True}
    first["telemetry_row_sha256"] = hashlib.sha256(
        json.dumps(
            {"database_fleet_public_row": {key: value for key, value in first.items() if key != "telemetry_row_sha256"}},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    second["telemetry_row_sha256"] = hashlib.sha256(
        json.dumps(
            {"database_fleet_public_row": {key: value for key, value in second.items() if key != "telemetry_row_sha256"}},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    with pytest.raises(ValueError, match="database_fleet_private_field_in_public_telemetry"):
        module.consensus_public_row(first, second)


def test_database_fleet_pair_requires_distinct_paths_and_raw_attestations(tmp_path: Path) -> None:
    module = _module()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    raw = b'{"process_id":1,"monotonic_finished_ns":2,"monotonic_started_ns":1}\n'
    (first / module.RAW_ATTESTATION).write_bytes(raw)
    (second / module.RAW_ATTESTATION).write_bytes(raw)

    with pytest.raises(ValueError, match="database_fleet_pair_output_paths_not_distinct"):
        module.assert_independent_runs(first, first)
    with pytest.raises(ValueError, match="database_fleet_pair_raw_attestation_not_independent"):
        module.assert_independent_runs(first, second)
    (second / module.RAW_ATTESTATION).write_bytes(
        b'{"nonce":"different-bytes","process_id":1,"monotonic_finished_ns":2,"monotonic_started_ns":1}\n'
    )
    with pytest.raises(ValueError, match="database_fleet_pair_run_identity_not_independent"):
        module.assert_independent_runs(first, second)


def test_database_fleet_raw_measured_role_is_excluded_from_canonical_compare(tmp_path: Path) -> None:
    verifier = importlib.import_module("scripts.verify_p105_source_expansion_artifacts")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    artifact_paths = {
        "public_telemetry": "public.jsonl",
        "raw_measured_telemetry": "measured.raw.jsonl",
    }
    for output, raw in ((first, b"run-1\n"), (second, b"run-2\n")):
        (output / "manifest.json").write_text(json.dumps({"artifact_paths": artifact_paths}, sort_keys=True) + "\n")
        (output / "public.jsonl").write_bytes(b"canonical\n")
        (output / "measured.raw.jsonl").write_bytes(raw)

    assert verifier._compare_canonical_reruns(first / "manifest.json", second / "manifest.json", kind="database_fleet") == []


def test_database_fleet_pair_transaction_resumes_after_partial_promotion(tmp_path: Path) -> None:
    module = _module()
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for output, prefix in ((first, b"first"), (second, b"second")):
        for name in module.PROMOTED_FILES:
            (output / name).write_bytes(b"old-" + prefix + name.encode())
            module._stage_path(output, name).write_bytes(b"new-" + prefix + name.encode())
    module._write_transaction_markers(first, second)
    module._promote_file(first, module.PUBLIC_TELEMETRY)
    (second / module.TRANSACTION_MARKER).unlink()

    module.resume_staged_transaction(first, second)

    for output, prefix in ((first, b"first"), (second, b"second")):
        assert (output / module.TRANSACTION_MARKER).exists()
        for name in module.PROMOTED_FILES:
            assert (output / name).read_bytes() == b"new-" + prefix + name.encode()
