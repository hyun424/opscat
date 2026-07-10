from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

P32_REPLAY = Path("evals/telemetry/replay/p32_replay_pack.json")
P41_SOURCES = Path("evals/real_datasets/raw/p41_sources.json")
P44_MATRIX = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
MATERIALIZER_SCRIPT = Path("scripts/materialize_p105_release_evidence.py")
BENCHMARK_SCRIPT = Path("scripts/run_failure_forecast_benchmark.py")

CANONICAL_KEYS = {
    "source_system",
    "source_dataset",
    "source_manifest_key",
    "source_content_hash",
    "materialized_record_hash",
    "materialization_version",
}
ZERO_AUTHORITY = {
    "auth_enabled": False,
    "production_mutation_enabled": False,
    "action_authority": False,
    "remediation_execution_enabled": False,
    "default_external_model_calls": 0,
}
REQUIRED_OUTPUTS = {
    "rows": "p105-release-qualified-rows.json",
    "source_availability_preflight": "p105-source-availability-preflight.json",
    "private_label_ledger": "p105-private-scorer-label-ledger.json",
    "partitions": "p105-partitions.json",
    "coverage": "p105-coverage.json",
    "p24_parity": "p105-p24-parity.json",
    "benchmark": "p105-release-qualified-benchmark.json",
    "review": "p105-review.json",
}


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _materialize(**kwargs: Any) -> dict[str, Any]:
    materializer = getattr(_api(), "materialize_p105_release_qualified_evidence", None)
    if materializer is None:
        pytest.fail("G006 materializer missing: expose materialize_p105_release_qualified_evidence.", pytrace=False)
    return materializer(**kwargs)


def _reviewed_p44_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "p44-reviewed-local-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "p105.reviewed_p44_local_manifest.v1",
                "review_redaction_status": "reviewed_redacted",
                "source_cap": 2000,
                "sources": [
                    {
                        "source_id": "p44:loghub:hdfs:public-matrix",
                        "family": "deploy",
                        "local_materialized_path": str(P44_MATRIX),
                        "local_source_hash": hashlib.sha256(P44_MATRIX.read_bytes()).hexdigest(),
                        "record_count": 20,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_floor_scale_p44_dataset(tmp_path: Path) -> Path:
    """Legacy v2 synthetic fixture: floor-shaped, but not honest release evidence."""

    dataset_dir = tmp_path / "reviewed-p44"
    dataset_dir.mkdir(parents=True)
    records_path = dataset_dir / "p44-reviewed-local-records.jsonl"
    families = ("database", "deploy", "queue")
    lines: list[str] = []
    for family in families:
        for partition, count, positives in (("held_out", 30, 6), ("real_derived_shadow", 20, 4)):
            for index in range(count):
                positive = index < positives
                record = {
                    "record_id": f"p44-{family}-{partition}-{index:03d}",
                    "family": family,
                    "failure_mode": f"{family}_failure",
                    "partition": partition,
                    "service": f"{family}-service",
                    "source_system": "p44",
                    "source_dataset": "temporary-reviewed-local-p44",
                    "source_timestamp": f"2026-02-{(index % 20) + 1:02d}T10:00:00Z",
                    "source_window_id": f"p44-window-{family}-{partition}-{index:03d}",
                    "public_features": {
                        "metric_name": f"{family}.saturation",
                        "metric_value": 80 + index,
                        "trend": "rising" if positive else "flat",
                    },
                    "private_label": {
                        "label_positive": positive,
                        "label_incident_id": f"inc-{family}-{partition}-{index:03d}" if positive else None,
                        "incident_group_id": f"group-{family}-{partition}-{index % max(positives, 1):03d}",
                        "label_incident_start_timestamp": f"2026-02-{(index % 20) + 1:02d}T11:00:00Z" if positive else None,
                        "lead_time_label_minutes": 60 if positive else None,
                    },
                    "p24_input": {
                        "window_id": f"p44-window-{family}-{partition}-{index:03d}",
                        "risk_type": family,
                        "signals": [{"name": f"{family}.saturation", "value": 80 + index}],
                    },
                    "coverage_interval": {
                        "split_id": f"g006-{partition}",
                        "family": family,
                        "service": f"{family}-service",
                        "source_system": "p44",
                        "start": "2026-02-01T00:00:00Z",
                        "end": "2026-02-04T00:00:00Z" if partition == "held_out" else "2026-02-03T00:00:00Z",
                    },
                }
                lines.append(json.dumps(record, sort_keys=True))
    records_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = dataset_dir / "p44-reviewed-local-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "p105.reviewed_p44_local_manifest.v2",
                "review_redaction_status": "reviewed_redacted",
                "source_cap": 2000,
                "sources": [
                    {
                        "source_id": "p44:temporary:reviewed-local-floor-scale",
                        "family": "multi",
                        "local_materialized_path": str(records_path),
                        "local_source_hash": hashlib.sha256(records_path.read_bytes()).hexdigest(),
                        "record_count": len(lines),
                        "private_label_format": "embedded_private_label",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _write_honest_v3_p44_dataset(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "reviewed-p44-v3"
    dataset_dir.mkdir(parents=True)
    records_path = dataset_dir / "p44-reviewed-local-public-records.jsonl"
    ledger_path = dataset_dir / "p44-reviewed-local-private-ledger.json"
    records: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for family_index, family in enumerate(("database", "deploy", "queue"), start=1):
        label_source = "official_nab_window" if family in {"database", "queue"} else "reviewed_loghub_burst"
        for partition, count, positives in (("held_out", 30, 6), ("real_derived_shadow", 20, 4)):
            for index in range(count):
                positive = index < positives
                window_id = f"p44-v3-{family}-{partition}-{index:03d}"
                timestamp = f"2026-05-{family_index:02d}T{(index % 20):02d}:00:00Z"
                metric_value = 92.0 if positive else 11.0 + index
                records.append(
                    {
                        "record_id": f"p44-v3-{family}-{partition}-{index:03d}",
                        "source_dataset": "p44-reviewed-local-v3",
                        "family": family,
                        "pre_label_partition": partition,
                        "source_timestamp": timestamp,
                        "source_window_id": window_id,
                        "public_features": {
                            "metric_name": f"{family}.saturation",
                            "metric_value": metric_value,
                            "trend": "rising" if positive else "flat",
                        },
                        "p24_input": {
                            "id": window_id,
                            "window_id": window_id,
                            "service": f"{family}-service",
                            "metric": f"{family}.saturation",
                            "risk_type": family,
                            "window_minutes": 15,
                            "baseline": 1.0,
                            "threshold": 10.0,
                            "values": [1.0, 2.5, 4.5, 7.0, 9.5] if positive else [1.0, 1.1, 1.2, 1.4, 1.6],
                        },
                        "coverage_interval": {
                            "timestamp_source": "raw_source_record",
                            "split_id": f"g006-{partition}",
                            "family": family,
                            "service": f"{family}-service",
                            "source_system": "p44",
                            "start": f"2026-05-{family_index:02d}T00:00:00Z",
                            "end": f"2026-05-{family_index + 1:02d}T00:00:00Z",
                        },
                        "reviewed_label_join": {
                            "sampled_before_label_join": True,
                            "label_source": label_source,
                            "official_window_id": window_id if label_source == "official_nab_window" else None,
                            "loghub_burst_id": f"burst-{window_id}" if label_source == "reviewed_loghub_burst" else None,
                            "source_line_offset": index,
                            "source_hash": "filled-by-manifest",
                        },
                    }
                )
                labels.append(
                    {
                        "record_id": f"p44-v3-{family}-{partition}-{index:03d}",
                        "source_window_id": window_id,
                        "label_positive": positive,
                        "label_incident_id": f"inc-v3-{family}-{partition}-{index:03d}" if positive else None,
                        "incident_group_id": f"group-v3-{family}-{partition}-{index % max(positives, 1):03d}" if positive else None,
                        "label_incident_start_timestamp": f"2026-05-{family_index:02d}T{((index % 20) + 1):02d}:00:00Z" if positive else None,
                        "lead_time_label_minutes": 60 if positive else None,
                        "label_source": label_source,
                    }
                )
    records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    source_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()
    for record in records:
        record["reviewed_label_join"]["source_hash"] = source_hash
    records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    source_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": "p105.reviewed_p44_private_label_ledger.v1",
                "join_timing": "after_sampling_and_pre_label_partition",
                "public_artifact": False,
                "records": labels,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for filename, payload in {
        "p105-privacy-redaction-manifest.json": {"schema_version": "p105.privacy_redaction.v1", "review_status": "reviewed_redacted", "raw_private_labels_embedded": False},
        "p105-license-manifest.json": {"schema_version": "p105.license.v1", "sources": [{"source_id": "p44:v3:reviewed-local", "license_id": "fixture-only-reviewed-local"}]},
        "p105-citation-manifest.json": {"schema_version": "p105.citation.v1", "citations": [{"citation_id": "fixture:p44:v3", "source_id": "p44:v3:reviewed-local"}]},
        "p105-provenance-hash-manifest.json": {
            "schema_version": "p105.provenance_hash.v1",
            "public_records_sha256": source_hash,
            "private_ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        },
    }.items():
        (dataset_dir / filename).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = dataset_dir / "p44-reviewed-local-manifest-v3.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "p105.reviewed_p44_local_manifest.v3",
                "review_redaction_status": "reviewed_redacted",
                "source_cap": 2000,
                "private_label_ledger_path": str(ledger_path),
                "privacy_manifest_path": str(dataset_dir / "p105-privacy-redaction-manifest.json"),
                "license_manifest_path": str(dataset_dir / "p105-license-manifest.json"),
                "citation_manifest_path": str(dataset_dir / "p105-citation-manifest.json"),
                "provenance_hash_manifest_path": str(dataset_dir / "p105-provenance-hash-manifest.json"),
                "sources": [
                    {
                        "source_id": "p44:v3:reviewed-local",
                        "family": "multi",
                        "local_materialized_path": str(records_path),
                        "local_source_hash": source_hash,
                        "record_count": len(records),
                        "private_label_format": "separate_private_ledger",
                        "partition_format": "pre_label_partition",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _g006_row_for_regression(tmp_path: Path, record: dict[str, Any], *, sequence_index: int = 17) -> tuple[dict[str, Any], dict[str, Any]]:
    source_path = tmp_path / "public-source-record.json"
    public_record = copy.deepcopy(record)
    public_record.pop("private_label", None)
    source_path.write_text(json.dumps(public_record, sort_keys=True) + "\n", encoding="utf-8")
    return _api()._g006_row_from_record(
        source_system="p44",
        source_dataset="public-source-record",
        source_manifest_key="p44:reviewed:record-001",
        source_path=source_path,
        raw_record=json.dumps(record, sort_keys=True),
        record=record,
        record_offset=4,
        partition="held_out",
        family="deploy",
        sequence_index=sequence_index,
    )


def _shuffle_private_ledger_labels(output_dir: Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rows_path = output_dir / REQUIRED_OUTPUTS["rows"]
    payload = json.loads(rows_path.read_text(encoding="utf-8"))
    ledger_path = output_dir / REQUIRED_OUTPUTS["private_label_ledger"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    original_records = copy.deepcopy(ledger["records"])
    label_fields = [
        "label_incident_id",
        "label_incident_start_timestamp",
        "label_family",
        "label_failure_mode",
        "label_positive",
        "lead_time_label_minutes",
        "incident_group_id",
    ]
    shuffled_records = copy.deepcopy(original_records)
    shifted_labels = [copy.deepcopy(record) for record in original_records[1:] + original_records[:1]]
    for record, shifted in zip(shuffled_records, shifted_labels, strict=True):
        for field in label_fields:
            record[field] = shifted.get(field)
    ledger["records"] = shuffled_records
    payload["private_scorer_label_ledger"] = ledger
    payload.pop("release_gate", None)
    shuffled_path = output_dir / "p105-release-qualified-rows-shuffled-labels.json"
    shuffled_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return shuffled_path, payload, original_records, shuffled_records


def test_g006_public_materialization_is_invariant_when_only_private_labels_flip(tmp_path: Path) -> None:
    base_record = {
        "record_id": "p44-review-001",
        "family": "deploy",
        "failure_mode": "deploy_failure",
        "partition": "held_out",
        "service": "deploy-service",
        "source_timestamp": "2026-02-01T10:00:00Z",
        "source_window_id": "p44-window-review-001",
        "metric_name": "deploy.error_budget",
        "metric_value": 88,
        "private_label": {
            "label_positive": False,
            "label_incident_id": None,
            "incident_group_id": None,
            "label_incident_start_timestamp": None,
            "lead_time_label_minutes": None,
        },
    }
    flipped_record = copy.deepcopy(base_record)
    flipped_record["private_label"] = {
        "label_positive": True,
        "label_incident_id": "inc-review-001",
        "incident_group_id": "group-review-001",
        "label_incident_start_timestamp": "2026-02-01T11:00:00Z",
        "lead_time_label_minutes": 60,
    }

    base_row, base_label = _g006_row_for_regression(tmp_path, base_record)
    flipped_row, flipped_label = _g006_row_for_regression(tmp_path, flipped_record)

    assert flipped_row["public_features"] == base_row["public_features"]
    assert flipped_row["p24_input"] == base_row["p24_input"]
    assert flipped_row["p24_input_hash"] == base_row["p24_input_hash"]
    assert flipped_row["row_id"] == base_row["row_id"]
    assert flipped_row["source_window_id"] == base_row["source_window_id"]
    assert flipped_row["partition"] == base_row["partition"]
    assert (
        flipped_row["source_record_provenance"]["canonical_source_tuple"]["source_content_hash"]
        == base_row["source_record_provenance"]["canonical_source_tuple"]["source_content_hash"]
    )
    assert (
        flipped_row["source_record_provenance"]["canonical_source_tuple"]["materialized_record_hash"]
        == base_row["source_record_provenance"]["canonical_source_tuple"]["materialized_record_hash"]
    )
    assert flipped_label["label_hash"] != base_label["label_hash"]


def test_g006_metadata_words_do_not_create_positive_label_without_reviewed_private_label() -> None:
    labels = _api()._g006_labels_from_record(
        {
            "record_id": "metadata-only-001",
            "family": "deploy",
            "failure_mode": "deploy_anomaly_regression_failure",
            "incident_type": "anomaly",
            "root_cause": "deploy regression",
        },
        "deploy",
        "held_out",
        3,
    )

    assert labels["label_positive"] is False
    assert labels["label_incident_id"] is None
    assert labels["incident_group_id"] is None


def test_g006_reviewed_local_materialization_is_invariant_under_private_label_shuffle(tmp_path: Path) -> None:
    first_manifest = _write_floor_scale_p44_dataset(tmp_path / "first")
    second_manifest = _write_floor_scale_p44_dataset(tmp_path / "second")
    records_path = Path(json.loads(second_manifest.read_text(encoding="utf-8"))["sources"][0]["local_materialized_path"])
    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
    shifted_private_labels = [copy.deepcopy(record["private_label"]) for record in records[1:] + records[:1]]
    for record, private_label in zip(records, shifted_private_labels, strict=True):
        record["private_label"] = private_label
    records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    manifest = json.loads(second_manifest.read_text(encoding="utf-8"))
    manifest["sources"][0]["local_source_hash"] = hashlib.sha256(records_path.read_bytes()).hexdigest()
    second_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    first = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=first_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "first-output",
        mode="release_qualified",
    )
    second = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=second_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "second-output",
        mode="release_qualified",
    )

    fields = [
        "row_id",
        "source_id",
        "source_window_id",
        "partition",
        "public_features",
        "p24_input",
        "p24_input_hash",
    ]
    first_rows = sorted(first["rows"], key=lambda row: row["row_id"])
    second_rows = sorted(second["rows"], key=lambda row: row["row_id"])
    assert [{field: row[field] for field in fields} for row in second_rows] == [{field: row[field] for field in fields} for row in first_rows]
    assert [
        row["source_record_provenance"]["canonical_source_tuple"]["source_content_hash"] for row in second_rows
    ] == [row["source_record_provenance"]["canonical_source_tuple"]["source_content_hash"] for row in first_rows]
    assert [
        row["source_record_provenance"]["canonical_source_tuple"]["materialized_record_hash"] for row in second_rows
    ] == [row["source_record_provenance"]["canonical_source_tuple"]["materialized_record_hash"] for row in first_rows]
    assert [row["private_label_ref"]["label_hash"] for row in second_rows] != [row["private_label_ref"]["label_hash"] for row in first_rows]


def test_g006_shuffled_private_label_ledger_changes_metrics_or_fails_release_closed(tmp_path: Path) -> None:
    output_dir = tmp_path / "qualified-output"
    reviewed_manifest = _write_floor_scale_p44_dataset(tmp_path / "reviewed")
    _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=output_dir,
        mode="release_qualified",
    )
    rows_path = output_dir / REQUIRED_OUTPUTS["rows"]
    original_public_rows = json.dumps(json.loads(rows_path.read_text(encoding="utf-8"))["rows"], sort_keys=True)
    original_report = _api().run_p105_benchmark(rows_path)

    shuffled_path, shuffled_payload, _original_records, _shuffled_records = _shuffle_private_ledger_labels(output_dir)
    shuffled_public_rows = json.dumps(shuffled_payload["rows"], sort_keys=True)
    shuffled_report = _api().run_p105_benchmark(shuffled_path)

    assert shuffled_public_rows == original_public_rows
    assert shuffled_report["release_gate"]["release_qualified"] is False or shuffled_report["release_metrics"] != original_report["release_metrics"]


def test_g006_shuffled_private_label_hashes_change_and_tamper_validation_fails_closed(tmp_path: Path) -> None:
    output_dir = tmp_path / "qualified-output"
    reviewed_manifest = _write_floor_scale_p44_dataset(tmp_path / "reviewed")
    _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=output_dir,
        mode="release_qualified",
    )

    shuffled_path, _payload, original_records, shuffled_records = _shuffle_private_ledger_labels(output_dir)
    assert [record["label_hash"] for record in shuffled_records] == [record["label_hash"] for record in original_records]
    assert any(
        {key: record.get(key) for key in ("label_positive", "label_incident_id", "incident_group_id")}
        != {key: original.get(key) for key in ("label_positive", "label_incident_id", "incident_group_id")}
        for record, original in zip(shuffled_records, original_records, strict=True)
    )

    result = _api().validate_p105_release_qualified_tamper(shuffled_path)

    assert "private_label_hash_mismatch" in result["validation_error_codes"]
    assert "private_label_ledger_tamper" in result["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_g006_label_shuffled_release_fixture_cannot_qualify_from_label_engineered_public_features(tmp_path: Path) -> None:
    output_dir = tmp_path / "qualified-output"
    reviewed_manifest = _write_floor_scale_p44_dataset(tmp_path / "reviewed")
    _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=output_dir,
        mode="release_qualified",
    )

    shuffled_path, shuffled_payload, _original_records, _shuffled_records = _shuffle_private_ledger_labels(output_dir)
    assert json.dumps(shuffled_payload["rows"], sort_keys=True) == json.dumps(json.loads((output_dir / REQUIRED_OUTPUTS["rows"]).read_text(encoding="utf-8"))["rows"], sort_keys=True)

    report = _api().run_p105_benchmark(shuffled_path)

    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_disabled_p44_negative_path_contributes_zero_p44_denominators_and_stays_locked(tmp_path: Path) -> None:
    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_mode="disabled",
        output_dir=tmp_path,
        mode="release_qualified",
        expect_locked=True,
    )

    preflight = result["source_availability_preflight"]["sources"]["p44"]
    assert preflight == {
        "mode": "disabled",
        "available_source_rows": 0,
        "positive_labels": 0,
        "incidents": 0,
        "incident_groups": 0,
        "distinct_canonical_source_tuples": 0,
        "local_source_hashes": [],
        "materialized_record_hashes": [],
        "review_redaction_status": "disabled",
    }
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_legacy_v1_reviewed_local_p44_manifest_cannot_supply_positive_release_rows(tmp_path: Path) -> None:
    reviewed_manifest = _reviewed_p44_manifest(tmp_path)

    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path,
        mode="release_qualified",
    )

    preflight = result["source_availability_preflight"]["sources"]["p44"]
    assert preflight["mode"] == "reviewed-local"
    assert preflight["review_redaction_status"] == "reviewed_redacted"
    assert preflight["available_source_rows"] == 0
    assert preflight["positive_labels"] == 0
    assert "legacy_reviewed_manifest_version" in preflight["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_materialized_rows_publish_exact_canonical_provenance_and_independent_record_keys(tmp_path: Path) -> None:
    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_mode="disabled",
        output_dir=tmp_path,
        mode="release_qualified",
        expect_locked=True,
    )

    independent_keys: set[tuple[Any, ...]] = set()
    materialized_hashes: set[str] = set()
    for row in result["rows"]:
        provenance = row["source_record_provenance"]
        canonical = provenance["canonical_source_tuple"]
        labels = row["private_label_ref"]
        assert set(canonical) == CANONICAL_KEYS
        assert provenance["record_offset"] is not None
        assert provenance["source_timestamp"] is not None
        assert row["partition"] == "real_derived_shadow"
        materialized_hash = canonical["materialized_record_hash"]
        assert materialized_hash not in materialized_hashes
        materialized_hashes.add(materialized_hash)
        key = (
            tuple(canonical[key] for key in sorted(CANONICAL_KEYS)),
            provenance["record_offset"],
            row["source_window_id"],
            labels["incident_key"],
            row["derivation"]["derivation_id"],
        )
        assert key not in independent_keys
        independent_keys.add(key)


def test_private_scorer_label_ledger_is_separate_hash_bound_and_not_public(tmp_path: Path) -> None:
    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_mode="disabled",
        output_dir=tmp_path,
        mode="release_qualified",
        expect_locked=True,
    )

    ledger = result["private_scorer_label_ledger"]
    assert ledger["public_artifact"] is False
    assert "scorer_labels" not in json.dumps(result["rows"], sort_keys=True)
    for record in ledger["records"]:
        assert record["label_hash"]
        assert record["label_hash_bindings"] == [
            "canonical_source_tuple",
            "record_offset",
            "incident_group_id",
            "derivation_id",
        ]
        assert record["row_id"] in {row["row_id"] for row in result["rows"]}


def test_materializer_outputs_zero_authority_for_every_source_path(tmp_path: Path) -> None:
    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=_reviewed_p44_manifest(tmp_path),
        p44_mode="reviewed-local",
        output_dir=tmp_path,
        mode="release_qualified",
    )

    assert result["authority"] == ZERO_AUTHORITY


def test_materializer_cli_disabled_p44_expect_locked_contract(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER_SCRIPT),
            "--p32-replay",
            str(P32_REPLAY),
            "--p41-sources",
            str(P41_SOURCES),
            "--p44-mode",
            "disabled",
            "--output-dir",
            str(tmp_path),
            "--mode",
            "release_qualified",
            "--expect-locked",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "p105-release-qualified-rows.json").exists()
    assert (tmp_path / "p105-source-availability-preflight.json").exists()


def test_materializer_cli_reviewed_local_p44_v3_positive_contract(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER_SCRIPT),
            "--p32-replay",
            str(P32_REPLAY),
            "--p41-sources",
            str(P41_SOURCES),
            "--p44-reviewed-local-manifest",
            str(_write_honest_v3_p44_dataset(tmp_path)),
            "--p44-mode",
            "reviewed-local",
            "--output-dir",
            str(tmp_path),
            "--mode",
            "release_qualified",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "p105-release-qualified-rows.json").exists()
    assert (tmp_path / "p105-private-scorer-label-ledger.json").exists()


def test_reviewed_local_p44_v3_end_to_end_materializes_and_unlocks_release_gate(tmp_path: Path) -> None:
    reviewed_manifest = _write_honest_v3_p44_dataset(tmp_path)
    output_dir = tmp_path / "qualified-output"

    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=output_dir,
        mode="release_qualified",
    )

    p44_rows = [
        row
        for row in result["rows"]
        if row["source_record_provenance"]["canonical_source_tuple"]["source_system"] == "p44"
        and row["partition"] == "real_derived_shadow"
    ]
    assert len(p44_rows) > 0
    assert result["source_input_manifest"]["forbidden_inputs"] == []
    assert str(Path("evals/proactive/forecast/p105_release_benchmark_rows.json")) not in json.dumps(
        result["source_input_manifest"],
        sort_keys=True,
    )
    assert result["release_gate"] == {"release_qualified": True, "p106_unlocked": True}

    rows_path = output_dir / REQUIRED_OUTPUTS["rows"]
    benchmark_path = output_dir / REQUIRED_OUTPUTS["benchmark"]
    report = _api().run_p105_benchmark(rows_path)
    assert report["release_gate"]["release_qualified"] is True
    assert report["release_gate"]["p106_unlocked"] is True
    assert json.loads(benchmark_path.read_text(encoding="utf-8"))["release_gate"] == report["release_gate"]

    cli_output = output_dir / "cli-benchmark.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--release-benchmark",
            str(rows_path),
            "--output-json",
            str(cli_output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    cli_report = json.loads(cli_output.read_text(encoding="utf-8"))
    assert cli_report["release_gate"]["release_qualified"] is True
    assert cli_report["release_gate"]["p106_unlocked"] is True


def test_legacy_floor_scale_p44_synthetic_fixture_remains_locked_and_cannot_unlock_p106(tmp_path: Path) -> None:
    reviewed_manifest = _write_floor_scale_p44_dataset(tmp_path)

    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "synthetic-output",
        mode="release_qualified",
    )

    assert result["source_availability_preflight"]["sources"]["p44"]["mode"] == "reviewed-local"
    assert "legacy_synthetic_floor_fixture" in set(result["release_gate"].get("validation_error_codes", ()))
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_p44_public_sampling_partition_features_and_p24_input_ignore_official_label_changes(tmp_path: Path) -> None:
    base_manifest = _write_honest_v3_p44_dataset(tmp_path / "base")
    edited_manifest = _write_honest_v3_p44_dataset(tmp_path / "edited")
    edited_payload = json.loads(edited_manifest.read_text(encoding="utf-8"))
    edited_ledger_path = Path(edited_payload["private_label_ledger_path"])
    edited_ledger = json.loads(edited_ledger_path.read_text(encoding="utf-8"))
    for label in edited_ledger["records"]:
        label["label_positive"] = not label["label_positive"]
        label["label_incident_id"] = f"changed-{label['record_id']}"
        label["incident_group_id"] = f"changed-group-{label['record_id']}"
        label["label_incident_start_timestamp"] = "2026-04-01T11:00:00Z"
        label["lead_time_label_minutes"] = 120
    edited_ledger_path.write_text(json.dumps(edited_ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    base = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=base_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "base-output",
        mode="release_qualified",
    )
    edited = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=edited_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "edited-output",
        mode="release_qualified",
    )

    public_fields = ["row_id", "source_window_id", "partition", "family", "public_features", "p24_input", "p24_input_hash"]
    base_rows = sorted(base["rows"], key=lambda row: row["row_id"])
    edited_rows = sorted(edited["rows"], key=lambda row: row["row_id"])
    assert [{field: row[field] for field in public_fields} for row in edited_rows] == [
        {field: row[field] for field in public_fields} for row in base_rows
    ]


def test_p44_coverage_comes_only_from_real_source_timestamps(tmp_path: Path) -> None:
    reviewed_manifest = _write_honest_v3_p44_dataset(tmp_path)

    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "coverage-output",
        mode="release_qualified",
    )

    for family_coverage in result["coverage_manifest"]["service_day_coverage"].values():
        for interval in family_coverage["coverage_intervals"]:
            assert interval.get("timestamp_source") == "raw_source_record"
            assert interval.get("source_record_provenance_hash")


def test_legacy_v2_reviewed_local_p44_manifest_with_embedded_private_labels_stays_locked(tmp_path: Path) -> None:
    reviewed_manifest = _write_floor_scale_p44_dataset(tmp_path)
    records_path = Path(json.loads(reviewed_manifest.read_text(encoding="utf-8"))["sources"][0]["local_materialized_path"])
    parsed_records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]

    result = _materialize(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=reviewed_manifest,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "qualified",
        mode="release_qualified",
    )

    p44 = result["source_availability_preflight"]["sources"]["p44"]
    assert p44["local_source_hashes"] == [hashlib.sha256(records_path.read_bytes()).hexdigest()]
    assert p44.get("legacy_embedded_private_label_row_count") == len(parsed_records)
    assert p44["available_source_rows"] == 0
    assert p44["positive_labels"] == 0
    assert "embedded_private_label_not_reviewed_truth" in p44["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (
            lambda manifest, _records_path: manifest["sources"][0].__setitem__("local_source_hash", "0" * 64),
            "p44_local_materialized_hash_mismatch",
        ),
        (
            lambda manifest, _records_path: manifest["sources"][0].__setitem__("record_count", 999),
            "p44_record_count_mismatch",
        ),
        (
            lambda manifest, _records_path: manifest["sources"][0].__setitem__("family", "wrong-family"),
            "p44_family_mismatch",
        ),
        (
            lambda manifest, records_path: records_path.unlink(),
            "p44_local_materialized_file_missing",
        ),
        (
            lambda manifest, _records_path: manifest.__setitem__("review_redaction_status", "unreviewed"),
            "p44_review_redaction_missing",
        ),
    ],
)
def test_reviewed_local_p44_manifest_tamper_fails_before_scoring(
    tmp_path: Path,
    mutator: Any,
    expected_code: str,
) -> None:
    reviewed_manifest = _write_floor_scale_p44_dataset(tmp_path)
    manifest = json.loads(reviewed_manifest.read_text(encoding="utf-8"))
    records_path = Path(manifest["sources"][0]["local_materialized_path"])
    mutator(manifest, records_path)
    reviewed_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validator = getattr(_api(), "validate_p105_reviewed_local_p44_manifest", None)
    if validator is None:
        pytest.fail("G006 reviewed-local P44 validator missing: expose validate_p105_reviewed_local_p44_manifest.", pytrace=False)
    result = validator(reviewed_manifest)

    assert result["failure_stage"] == "pre_scoring"
    assert expected_code in result["validation_error_codes"]
    assert result["release_gate"] == {"release_qualified": False, "p106_unlocked": False}
