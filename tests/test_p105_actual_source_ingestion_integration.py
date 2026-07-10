from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.failure_forecast_engine import (
    P105_REQUIRED_SCHEMA_ADAPTERS,
    materialize_p105_release_qualified_evidence,
)
from tests.test_p105_dejavu_a1_materializer import _run_dejavu

P32_REPLAY = Path("evals/telemetry/replay/p32_replay_pack.json")
P41_SOURCES = Path("evals/real_datasets/raw/p41_sources.json")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(_stable_json(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _runtime_row(source: str, family: str, partition: str, index: int) -> dict[str, Any]:
    source_window_id = f"{source}-{partition}-{index:04d}"
    common = {
        "event_time": f"2024-03-09T16:{index:02d}:00Z",
        "partition_id": partition,
        "schema_version": f"p105.{source}.public_telemetry.v1",
        "service": f"{source}-service",
        "source_window_id": source_window_id,
        "tick": index,
    }
    if family == "database":
        return {
            **common,
            "acquisition_latency_p95_bucket_ms": 100,
            "checked_out_count": 3,
            "failed_acquisition_count": 1,
            "sqlite_pool_size": 3,
            "timeout_count": 1,
            "wait_queue_length": 1,
        }
    if family == "queue":
        return {
            **common,
            "ack_lag_p95_ticks": 3,
            "dlq_messages_ready": 1,
            "messages_ready": 12,
            "messages_total": 20,
            "queue_name": f"{source}-service",
        }
    return {
        **common,
        "cohort": "canary",
        "measured_latency_bucket_ms": "100-250",
        "rollback_state": "triggered",
        "rolling_error_rate": 0.5,
        "status_code": 503,
    }


def _write_runtime_bundle(root: Path, *, source: str, family: str, runtime_kind: str, test_fast: bool = False) -> Path:
    bundle = root / source
    public_name = f"p105-{source}-public-telemetry.jsonl"
    ledger_name = f"p105-{source}-private-ledger.json"
    coverage_name = f"p105-{source}-coverage.json"
    partitions_name = f"p105-{source}-partitions.json"
    provenance_name = f"p105-{source}-provenance-hashes.json"
    manifest_name = f"p105-{source}-harness-manifest.json"
    rows = [
        _runtime_row(source, family, "held_out_test", 1),
        _runtime_row(source, family, "real_derived_shadow", 2),
    ]
    _write_jsonl(bundle / public_name, rows)
    _write_json(
        bundle / ledger_name,
        {
            "public_artifact": False,
            "records": [
                {
                    "incident_group_id": f"incident-{source}",
                    "label_incident_id": f"incident-{source}",
                    "label_positive": True,
                    "partition_id": row["partition_id"],
                    "public_source_window_ids": [row["source_window_id"]],
                }
                for row in rows
            ],
        },
    )
    _write_json(
        bundle / coverage_name,
        {
            "clock_source": "time.monotonic_ns",
            "coverage_method": "actual_observation_tick_union",
            "observed_intervals": {f"{source}-service": [{"start_tick": 0, "end_tick": 60}]},
        },
    )
    _write_json(
        bundle / partitions_name,
        {
            "label_blind": True,
            "records": [
                {"source_window_id": row["source_window_id"], "partition_id": row["partition_id"]}
                for row in rows
            ],
        },
    )
    artifact_hashes = {
        name: _sha256_path(bundle / name)
        for name in (public_name, ledger_name, coverage_name, partitions_name)
    }
    manifest = {
        "artifact_paths": {
            "coverage": coverage_name,
            "partitions": partitions_name,
            "private_injection_ledger": ledger_name,
            "provenance_hashes": provenance_name,
            "public_telemetry": public_name,
        },
        "authority": {
            "auth_enabled": False,
            "credentials_read": False,
            "production_endpoint": False,
            "production_mutation": False,
            "release_counting_authority": False,
        },
        "created_at": "2024-03-09T16:00:00Z",
        "diagnostic_profile": {"non_qualifying": test_fast},
        "program_version": f"p105-{source}-test-contract-v1",
        "runtime_attestation": {"kind": runtime_kind, "capability": f"{source}_actual_runtime"},
        "schema_version": f"p105.{source}.harness_manifest.v1",
        "source_family": family,
        "test_fast_runtime": test_fast,
        "tick_seconds": 1,
        "ticks": 61,
    }
    manifest_path = _write_json(bundle / manifest_name, manifest)
    _write_json(
        bundle / provenance_name,
        {
            "artifact_hashes": {**artifact_hashes, manifest_name: _sha256_path(manifest_path)},
            "program_version": manifest["program_version"],
            "schema_version": f"p105.{source}.provenance_hashes.v1",
        },
    )
    return manifest_path


def _canonical_root(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    provenance = json.loads((manifest_path.parent / manifest["artifact_paths"]["provenance_hashes"]).read_text(encoding="utf-8"))
    return hashlib.sha256(_stable_json({"artifact_hashes": provenance["artifact_hashes"]}).encode()).hexdigest()


def _write_receipt(path: Path, manifests: dict[str, Path]) -> Path:
    envelopes = [
        {
            "schema_version": "p105.source-runtime-run-envelope.v1",
            "created_by": "scripts/verify_p105_source_expansion_artifacts.py",
            "source": source,
            "run_label": "run_1",
            "manifest_path": str(manifest),
            "manifest_sha256": _sha256_path(manifest),
            "canonical_artifact_root_sha256": _canonical_root(manifest),
            "runtime_attestation": json.loads(manifest.read_text(encoding="utf-8"))["runtime_attestation"],
            "validation_error_codes": [],
            "verified": True,
        }
        for source, manifest in manifests.items()
    ]
    return _write_json(
        path,
        {
            "schema_version": "p105.source-runtime-qualification.v1",
            "created_by": "scripts/verify_p105_source_expansion_artifacts.py",
            "verified_release_counting": True,
            "run_envelopes": envelopes,
            "canonical_roots": {source: _canonical_root(manifest) for source, manifest in manifests.items()},
            "validation_error_codes": [],
        },
    )


def _materialize(tmp_path: Path, *, test_fast: bool = False, tamper_receipt: bool = False) -> dict[str, Any]:
    completed, dejavu_dir = _run_dejavu(tmp_path / "dejavu")
    assert completed.returncode == 0, completed.stderr
    manifests = {
        "db_pool": _write_runtime_bundle(
            tmp_path / "runtime", source="db-pool", family="database", runtime_kind="actual_sqlite_pool", test_fast=test_fast
        ),
        "queue": _write_runtime_bundle(
            tmp_path / "runtime", source="queue", family="queue", runtime_kind="actual_rabbitmq_docker", test_fast=test_fast
        ),
        "deploy": _write_runtime_bundle(
            tmp_path / "runtime", source="deploy", family="deploy", runtime_kind="actual_threading_http_server", test_fast=test_fast
        ),
    }
    receipt = _write_receipt(tmp_path / "receipt.json", manifests)
    if tamper_receipt:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["run_envelopes"][0]["manifest_sha256"] = "0" * 64
        _write_json(receipt, payload)
    registry = _write_json(tmp_path / "registry.json", {"schema_version": "p105.source-registry.v1", "sources": []})
    eligibility = _write_json(tmp_path / "eligibility.json", {"schema_version": "p105.source-eligibility.v1", "entries": []})
    return materialize_p105_release_qualified_evidence(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_mode="disabled",
        dejavu_a1_reviewed_local_manifest=dejavu_dir / "p105-dejavu-a1-reviewed-local-manifest.json",
        db_pool_harness_manifest=manifests["db_pool"],
        queue_harness_manifest=manifests["queue"],
        deploy_harness_manifest=manifests["deploy"],
        source_registry=registry,
        source_eligibility=eligibility,
        schema_adapters=P105_REQUIRED_SCHEMA_ADAPTERS,
        reject_synthetic_four_day_coverage=True,
        require_actual_runtime_attestation=True,
        fail_on_unknown_source_schema=True,
        source_runtime_qualification_receipt=receipt,
        count_only_verified_release_receipts=True,
        output_dir=tmp_path / "release",
        expect_locked=True,
    )


def test_verified_actual_sources_become_central_rows_coverage_and_preflight(tmp_path: Path) -> None:
    result = _materialize(tmp_path)

    source_systems = {
        row["source_record_provenance"]["canonical_source_tuple"]["source_system"]
        for row in result["rows"]
    }
    assert {"dejavu_a1", "db_pool", "queue", "deploy"} <= source_systems
    for source in ("dejavu_a1", "db_pool", "queue", "deploy"):
        preflight = result["source_availability_preflight"]["sources"][source]
        assert preflight["available_source_rows"] > 0
        assert preflight["local_source_hashes"]
        assert preflight["materialized_record_hashes"]
    actual_rows = [
        row
        for row in result["rows"]
        if row["source_record_provenance"]["canonical_source_tuple"]["source_system"] in {"db_pool", "queue", "deploy"}
    ]
    assert actual_rows
    assert all(row["source_record_provenance"]["coverage_interval"] for row in actual_rows)
    assert result["coverage_manifest"]["false_alert_denominator_method"] == "actual_observed_interval_union"
    assert result["source_runtime_qualification"]["receipt_sha256"]
    assert result["release_gate"]["p106_unlocked"] is False


def test_receipt_must_hash_bind_every_ingested_runtime_manifest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_runtime_receipt_manifest_mismatch"):
        _materialize(tmp_path, tamper_receipt=True)


def test_test_fast_runtime_sources_cannot_enter_release_counting_materialization(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="test_fast_runtime_noncounting"):
        _materialize(tmp_path, test_fast=True)
