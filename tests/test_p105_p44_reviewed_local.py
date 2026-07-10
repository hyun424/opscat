from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

P44_REVIEWED_LOCAL_SCRIPT = Path("scripts/materialize_p44_reviewed_local.py")
P32_REPLAY = Path("evals/telemetry/replay/p32_replay_pack.json")
P41_SOURCES = Path("evals/real_datasets/raw/p41_sources.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _write_records_manifest(tmp_path: Path, records: list[dict[str, Any]], *, source_id: str) -> Path:
    records_path = tmp_path / "p44-raw-records.jsonl"
    records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "p44-reviewed-local-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "p105.reviewed_p44_local_manifest.v2",
                "review_redaction_status": "reviewed_redacted",
                "source_cap": 2000,
                "sources": [
                    {
                        "source_id": source_id,
                        "family": "multi",
                        "local_materialized_path": str(records_path),
                        "local_source_hash": hashlib.sha256(records_path.read_bytes()).hexdigest(),
                        "record_count": len(records),
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


def _write_raw_intake_fixture(tmp_path: Path, *, labels_variant: str = "positive", include_required: set[str] | None = None) -> Path:
    include_required = include_required or {"timestamp", "labels", "license", "privacy", "hash"}
    raw_dir = tmp_path / f"raw-{labels_variant}"
    raw_dir.mkdir(parents=True)

    machine_csv = raw_dir / "machine_temperature_system_failure.csv"
    if "timestamp" in include_required:
        machine_csv.write_text(
            "\n".join(
                [
                    "timestamp,value",
                    "2013-12-10 06:20:00,67.5",
                    "2013-12-10 06:25:00,88.0",
                    "2013-12-10 06:30:00,91.0",
                    "2013-12-10 06:35:00,70.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        timestamp_field: str | None = "timestamp"
    else:
        machine_csv.write_text(
            "\n".join(["value", "67.5", "88.0", "91.0", "70.0"]) + "\n",
            encoding="utf-8",
        )
        timestamp_field = None

    labels_json = raw_dir / "combined_windows.json"
    label_windows = [["2013-12-10 06:24:00.000000", "2013-12-10 06:31:00.000000"]] if labels_variant == "positive" else [["2013-12-11 00:00:00.000000", "2013-12-11 00:05:00.000000"]]
    if "labels" in include_required:
        labels_json.write_text(
            json.dumps(
                {
                    "realKnownCause/machine_temperature_system_failure.csv": label_windows,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    hdfs_log = raw_dir / "HDFS_2k.log"
    hdfs_log.write_text(
        "\n".join(
            [
                "081109 203615 148 INFO dfs.DataNode$DataXceiver: Receiving block blk_100 src: /10.0.0.1:50010 dest: /10.0.0.2:50010",
                "081109 203616 149 WARN dfs.FSNamesystem: BLOCK* NameSystem.addStoredBlock: blockMap updated blk_100",
                "081109 203617 150 ERROR dfs.DataNode: IOException in receiveBlock for blk_100 on /rack-a/node-1",
                "081109 203618 151 ERROR dfs.DataNode: PacketResponder exception for blk_100 on /rack-a/node-1",
                "081109 203619 152 INFO dfs.DataNode: Verification succeeded for blk_100",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    raw_sources: list[dict[str, Any]] = [
        {
            "source_key": "nab:realKnownCause:machine_temperature_system_failure",
            "source_type": "nab_csv",
            "source_system": "p44",
            "source_dataset": "nab",
            "source_manifest_key": "realKnownCause/machine_temperature_system_failure.csv",
            "path": str(machine_csv),
            "timestamp_field": timestamp_field,
            "expected_record_count": 4,
            "expected_timestamp_min": "2013-12-10T06:20:00Z" if timestamp_field else None,
            "expected_timestamp_max": "2013-12-10T06:35:00Z" if timestamp_field else None,
            "family_proxy_mapping": {"family": "database", "mapping_review_status": "reviewed_supported", "evidence": "machine temperature metric maps to database thermal saturation proxy"},
            "license_name": "NAB Apache-2.0" if "license" in include_required else None,
            "license_url": "https://github.com/numenta/NAB/blob/master/LICENSE.txt" if "license" in include_required else None,
            "citation_text": "Numenta Anomaly Benchmark" if "license" in include_required else None,
            "redistribution_status": "local_reviewed_fixture",
            "privacy_review_status": "reviewed_no_pii" if "privacy" in include_required else None,
            "redaction_decisions": ["metric timestamps and values only"] if "privacy" in include_required else None,
            "reviewer_id": "g006-local-test-reviewer",
            "reviewed_at": "2026-07-10T00:00:00Z",
        },
        {
            "source_key": "loghub:hdfs:raw",
            "source_type": "loghub_raw",
            "source_system": "p44",
            "source_dataset": "loghub-hdfs",
            "source_manifest_key": "HDFS/HDFS_2k.log",
            "path": str(hdfs_log),
            "parser_version": "loghub-hdfs-parser-v1",
            "burst_predicate_version": "reviewed-error-burst-v1",
            "expected_record_count": 5,
            "family_proxy_mapping": {"family": "deploy", "mapping_review_status": "reviewed_supported", "evidence": "reviewed ERROR burst predicate maps to deploy/config regression proxy"},
            "license_name": "LogHub CC-BY-4.0" if "license" in include_required else None,
            "license_url": "https://github.com/logpai/loghub" if "license" in include_required else None,
            "citation_text": "LogHub public log dataset" if "license" in include_required else None,
            "redistribution_status": "local_reviewed_fixture",
            "privacy_review_status": "reviewed_redacted" if "privacy" in include_required else None,
            "redaction_decisions": ["private IPs ignored in public features"] if "privacy" in include_required else None,
            "reviewer_id": "g006-local-test-reviewer",
            "reviewed_at": "2026-07-10T00:00:00Z",
        },
        {
            "source_key": "nab:unknown:unsupported_metric",
            "source_type": "nab_csv",
            "source_system": "p44",
            "source_dataset": "nab",
            "source_manifest_key": "artificialNoAnomaly/unsupported_metric.csv",
            "path": str(machine_csv),
            "timestamp_field": timestamp_field,
            "expected_record_count": 4,
            "family_proxy_mapping": {"family": "unsupported_family", "mapping_review_status": "unsupported", "evidence": "no reviewed P105 family mapping"},
            "license_name": "NAB Apache-2.0" if "license" in include_required else None,
            "license_url": "https://github.com/numenta/NAB/blob/master/LICENSE.txt" if "license" in include_required else None,
            "citation_text": "Numenta Anomaly Benchmark" if "license" in include_required else None,
            "redistribution_status": "local_reviewed_fixture",
            "privacy_review_status": "reviewed_no_pii" if "privacy" in include_required else None,
            "redaction_decisions": ["metric timestamps and values only"] if "privacy" in include_required else None,
            "reviewer_id": "g006-local-test-reviewer",
            "reviewed_at": "2026-07-10T00:00:00Z",
        },
    ]
    if "hash" in include_required:
        for source in raw_sources:
            source["expected_sha256"] = _sha256(Path(source["path"]))
        if "labels" in include_required:
            labels_hash: str | None = _sha256(labels_json)
        else:
            labels_hash = None
    else:
        labels_hash = None

    if "labels" in include_required:
        raw_sources[0]["labels_json_path"] = str(labels_json)
        raw_sources[0]["labels_json_hash"] = labels_hash
        raw_sources[2]["labels_json_path"] = str(labels_json)
        raw_sources[2]["labels_json_hash"] = labels_hash

    manifest_path = raw_dir / "reviewed-p44-raw-source-manifest.json"
    manifest = {
        "schema_version": "p105.p44_raw_source_manifest.v1",
        "review_status": "reviewed-local",
        "materialization_version": "p44-reviewed-local-raw-intake-v1",
        "reviewer_id": "g006-local-test-reviewer",
        "raw_sources": raw_sources,
        "sources": raw_sources,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def _run_raw_manifest_materializer(raw_manifest: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(P44_REVIEWED_LOCAL_SCRIPT),
            "--raw-manifest",
            str(raw_manifest),
            "--output-dir",
            str(output_dir),
            "--reviewed-by",
            "g006-local-test-reviewer",
            "--license-id",
            "manifest-supplied",
            "--citation-id",
            "manifest-supplied",
            "--source-cap",
            "16",
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def _materialize_raw_fixture(tmp_path: Path, *, labels_variant: str = "positive") -> Path:
    raw_manifest = _write_raw_intake_fixture(tmp_path, labels_variant=labels_variant)
    output_dir = tmp_path / f"reviewed-{labels_variant}"
    completed = _run_raw_manifest_materializer(raw_manifest, output_dir)
    assert completed.returncode == 0, completed.stderr
    return output_dir


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_temp_raw_p44_fixture_is_materialized_by_planned_reviewed_local_script_contract(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw-p44.jsonl"
    raw_path.write_text(
        json.dumps(
            {
                "record_id": "nab-window-001",
                "source_dataset": "nab",
                "timestamp": "2026-02-01T10:00:00Z",
                "source_window_id": "official-window-001",
                "public_features": {"metric": "temperature", "value": 82.0},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reviewed-local"

    completed = subprocess.run(
        [
            sys.executable,
            str(P44_REVIEWED_LOCAL_SCRIPT),
            "--raw-p44",
            str(raw_path),
            "--output-dir",
            str(output_dir),
            "--reviewed-by",
            "local-test-reviewer",
            "--license-id",
            "fixture-only",
            "--citation-id",
            "fixture:p44:nab:window-001",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((output_dir / "p44-reviewed-local-manifest.json").read_text(encoding="utf-8"))
    assert manifest["review_redaction_status"] == "reviewed_redacted"
    assert manifest["privacy_manifest_path"] == "p105-privacy-redaction-manifest.json"
    assert manifest["license_manifest_path"] == "p105-license-manifest.json"
    assert manifest["citation_manifest_path"] == "p105-citation-manifest.json"


def test_raw_manifest_mode_parses_nab_csv_and_loghub_raw_log_with_source_hash_counts_and_timestamp_bounds(tmp_path: Path) -> None:
    output_dir = _materialize_raw_fixture(tmp_path)

    manifest = _read_json(output_dir / "p44-reviewed-local-manifest.json")
    raw_sources = {source["source_key"]: source for source in manifest["raw_sources"]}
    nab_source = raw_sources["nab:realKnownCause:machine_temperature_system_failure"]
    loghub_source = raw_sources["loghub:hdfs:raw"]

    assert manifest["schema_version"] == "p105.reviewed_p44_local_manifest.v3"
    assert nab_source["source_content_hash"] == _sha256(tmp_path / "raw-positive" / "machine_temperature_system_failure.csv")
    assert loghub_source["source_content_hash"] == _sha256(tmp_path / "raw-positive" / "HDFS_2k.log")
    assert nab_source["record_count"] == 4
    assert loghub_source["record_count"] == 5
    assert nab_source["timestamp_min"] == "2013-12-10T06:20:00Z"
    assert nab_source["timestamp_max"] == "2013-12-10T06:35:00Z"


def test_raw_manifest_sampling_and_pre_label_partitions_are_invariant_under_labels_json_changes(tmp_path: Path) -> None:
    positive_output = _materialize_raw_fixture(tmp_path / "positive", labels_variant="positive")
    negative_output = _materialize_raw_fixture(tmp_path / "negative", labels_variant="negative")

    positive_records = _read_jsonl(positive_output / "p44-reviewed-local-public-records.jsonl")
    negative_records = _read_jsonl(negative_output / "p44-reviewed-local-public-records.jsonl")
    positive_partitions = _read_json(positive_output / "p44-reviewed-local-pre-label-partitions.json")
    negative_partitions = _read_json(negative_output / "p44-reviewed-local-pre-label-partitions.json")

    public_fields = ["reviewed_record_id", "source_key", "source_window_id", "source_timestamp", "public_features", "p24_input"]
    assert [{field: row[field] for field in public_fields} for row in positive_records] == [{field: row[field] for field in public_fields} for row in negative_records]
    assert positive_partitions["pre_label_partitions"] == negative_partitions["pre_label_partitions"]
    assert positive_partitions["assignment_inputs"] == [
        "canonical_raw_bytes",
        "record_offset_or_row_index",
        "source_manifest_key",
        "source_timestamp",
        "versioned_salt",
    ]


def test_nab_combined_windows_join_happens_after_sampling_only_in_private_ledger_without_max_fallback(tmp_path: Path) -> None:
    output_dir = _materialize_raw_fixture(tmp_path)

    manifest = _read_json(output_dir / "p44-reviewed-local-manifest.json")
    ledger = _read_json(output_dir / manifest["private_ledger_ref"]["path"])
    public_records = _read_jsonl(output_dir / "p44-reviewed-local-public-records.jsonl")
    nab_labels = [record for record in ledger["records"] if record["label_join_source"] == "official_nab_windows"]

    assert ledger["label_join_completed_after_sampling"] is True
    assert ledger["max_value_fallback_allowed"] is False
    assert any(record["label_positive"] is True for record in nab_labels)
    assert all("max_value" not in json.dumps(record, sort_keys=True) for record in nab_labels)
    assert all("label_positive" not in record and "incident_group_id" not in record for record in public_records)


def test_loghub_reviewed_burst_ledger_records_parser_versions_offsets_windows_and_source_hash(tmp_path: Path) -> None:
    output_dir = _materialize_raw_fixture(tmp_path)

    manifest = _read_json(output_dir / "p44-reviewed-local-manifest.json")
    ledger = _read_json(output_dir / manifest["private_ledger_ref"]["path"])
    loghub_records = [record for record in ledger["records"] if record["label_join_source"] == "deterministic_loghub_error_burst_ledger"]

    assert loghub_records
    for record in loghub_records:
        assert record["parser_version"] == "loghub-hdfs-parser-v1"
        assert record["burst_predicate_version"] == "reviewed-error-burst-v1"
        assert record["line_start_offset"] <= record["line_end_offset"]
        assert record["window_start_timestamp"] <= record["window_end_timestamp"]
        assert record["source_hash"] == _sha256(tmp_path / "raw-positive" / "HDFS_2k.log")
        assert record["incident_group_id"].startswith("loghub-hdfs-burst-")


def test_public_records_exclude_private_ledger_data_and_p24_inputs_derive_from_same_raw_window(tmp_path: Path) -> None:
    output_dir = _materialize_raw_fixture(tmp_path)

    public_records = _read_jsonl(output_dir / "p44-reviewed-local-public-records.jsonl")

    for record in public_records:
        serialized = json.dumps(record, sort_keys=True)
        assert "private_label" not in record
        assert "label_positive" not in serialized
        assert "incident_group_id" not in serialized
        assert record["public_features"]["source_window_id"] == record["source_window_id"]
        assert record["p24_input"]["window_id"] == record["source_window_id"]
        assert record["p24_input"]["window_start_timestamp"] == record["window_start_timestamp"]
        assert record["p24_input"]["window_end_timestamp"] == record["window_end_timestamp"]


def test_raw_manifest_materializer_writes_complete_v3_manifest_and_sidecars(tmp_path: Path) -> None:
    output_dir = _materialize_raw_fixture(tmp_path)

    manifest = _read_json(output_dir / "p44-reviewed-local-manifest.json")

    assert manifest["schema_version"] == "p105.reviewed_p44_local_manifest.v3"
    assert manifest["materialization_version"] == "p44-reviewed-local-raw-intake-v1"
    assert manifest["review_status"] == "reviewed-local"
    assert manifest["sampling_policy"]["sampled_before_label_join"] is True
    for key in [
        "privacy_manifest_path",
        "license_manifest_path",
        "citation_manifest_path",
        "provenance_hash_manifest_path",
        "private_ledger_ref",
        "pre_label_partitions_path",
    ]:
        value = manifest[key]["path"] if isinstance(manifest[key], dict) else manifest[key]
        assert (output_dir / value).is_file()
    provenance = _read_json(output_dir / manifest["provenance_hash_manifest_path"])
    assert provenance["raw_source_hashes"]
    assert provenance["private_ledger_hash"] == _sha256(output_dir / manifest["private_ledger_ref"]["path"])
    assert provenance["public_records_hash"] == _sha256(output_dir / "p44-reviewed-local-public-records.jsonl")


def test_mapping_review_status_and_evidence_are_required_and_unsupported_mappings_cannot_count(tmp_path: Path) -> None:
    output_dir = _materialize_raw_fixture(tmp_path)

    manifest = _read_json(output_dir / "p44-reviewed-local-manifest.json")
    raw_sources = {source["source_key"]: source for source in manifest["raw_sources"]}
    public_records = _read_jsonl(output_dir / "p44-reviewed-local-public-records.jsonl")
    unsupported_records = [record for record in public_records if record["family_proxy_mapping"]["family"] == "unsupported_family"]

    for source in raw_sources.values():
        mapping = source["family_proxy_mapping"]
        assert mapping["mapping_review_status"] in {"reviewed_supported", "unsupported"}
        assert mapping["evidence"]
    assert unsupported_records
    assert all(record["countable_for_release_floors"] is False for record in unsupported_records)
    assert manifest["family_mapping_review_status"]["unsupported_family_count"] == len(unsupported_records)


def test_raw_manifest_mode_fails_closed_when_required_review_metadata_is_missing(tmp_path: Path) -> None:
    required_fields = {
        "timestamp": "source_timestamp_missing",
        "labels": "nab_labels_json_missing",
        "license": "source_license_missing",
        "privacy": "privacy_review_missing",
        "hash": "source_hash_missing",
    }

    for missing_field, expected_code in required_fields.items():
        raw_manifest = _write_raw_intake_fixture(
            tmp_path / missing_field,
            include_required={"timestamp", "labels", "license", "privacy", "hash"} - {missing_field},
        )
        output_dir = tmp_path / f"missing-{missing_field}"

        completed = _run_raw_manifest_materializer(raw_manifest, output_dir)

        assert completed.returncode != 0
        assert expected_code in completed.stderr


def test_nab_labels_join_only_after_sampling_from_official_windows_without_max_value_fallback(tmp_path: Path) -> None:
    manifest_path = _write_records_manifest(
        tmp_path,
        [
            {
                "record_id": "nab-max-value-without-official-window",
                "source_dataset": "nab-machine-temperature",
                "family": "database",
                "partition": "held_out",
                "timestamp": "2026-02-01T10:00:00Z",
                "source_window_id": "sampled-window-not-in-official-labels",
                "public_features": {"metric": "temperature", "value": 999.0, "trend": "spiking"},
                "private_label": {"label_positive": True, "label_incident_id": "forged-from-max-value", "incident_group_id": "forged"},
            }
        ],
        source_id="p44:nab:machine-temperature",
    )

    result = _api().validate_p105_reviewed_local_p44_manifest(manifest_path)

    assert result["failure_stage"] == "pre_scoring"
    assert "nab_official_window_join_missing" in result["validation_error_codes"]
    assert "nab_max_value_label_fallback_forbidden" in result["validation_error_codes"]
    assert result["release_gate"] == {"release_qualified": False, "p106_unlocked": False}


def test_loghub_positive_incidents_require_deterministic_reviewed_burst_metadata(tmp_path: Path) -> None:
    manifest_path = _write_records_manifest(
        tmp_path,
        [
            {
                "record_id": "loghub-error-without-reviewed-burst",
                "source_dataset": "loghub-hdfs",
                "family": "deploy",
                "partition": "held_out",
                "timestamp": "2026-02-01T10:00:00Z",
                "source_window_id": "loghub-window-001",
                "message": "ERROR namenode failed",
                "private_label": {"label_positive": True, "label_incident_id": "forged-loghub", "incident_group_id": "forged-loghub"},
            }
        ],
        source_id="p44:loghub:hdfs",
    )

    result = _api().validate_p105_reviewed_local_p44_manifest(manifest_path)

    assert result["failure_stage"] == "pre_scoring"
    assert "loghub_reviewed_burst_metadata_missing" in result["validation_error_codes"]
    assert "loghub_burst_source_hash_missing" in result["validation_error_codes"]
    assert result["release_gate"] == {"release_qualified": False, "p106_unlocked": False}


def test_embedded_private_label_family_or_partition_claims_do_not_count_as_reviewed_source_truth(tmp_path: Path) -> None:
    manifest_path = _write_records_manifest(
        tmp_path,
        [
            {
                "record_id": "embedded-claims-only",
                "family": "queue",
                "partition": "held_out",
                "timestamp": "2026-02-01T10:00:00Z",
                "source_window_id": "embedded-window-001",
                "public_features": {"metric": "queue.depth", "value": 100.0, "trend": "spiking"},
                "private_label": {"label_positive": True, "label_incident_id": "embedded-positive", "incident_group_id": "embedded-group"},
            }
        ],
        source_id="p44:embedded:claims-only",
    )

    result = _api().materialize_p105_release_qualified_evidence(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=manifest_path,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "qualified",
        mode="release_qualified",
    )

    p44_preflight = result["source_availability_preflight"]["sources"]["p44"]
    assert p44_preflight["available_source_rows"] == 0
    assert p44_preflight["positive_labels"] == 0
    assert "embedded_private_label_not_reviewed_truth" in p44_preflight["validation_error_codes"]
    assert "embedded_family_partition_not_sampling_authority" in p44_preflight["validation_error_codes"]
    assert result["release_gate"]["release_qualified"] is False
    assert result["release_gate"]["p106_unlocked"] is False


def test_missing_timestamp_or_duplicate_p24_window_makes_rows_unevaluable(tmp_path: Path) -> None:
    manifest_path = _write_records_manifest(
        tmp_path,
        [
            {
                "record_id": "missing-timestamp",
                "family": "database",
                "partition": "held_out",
                "source_window_id": "same-window",
                "p24_input": {"window_id": "same-window", "risk_type": "database"},
                "private_label": {"label_positive": False},
            },
            {
                "record_id": "duplicate-p24-window",
                "family": "database",
                "partition": "held_out",
                "timestamp": "2026-02-01T10:00:00Z",
                "source_window_id": "same-window",
                "p24_input": {"window_id": "same-window", "risk_type": "database"},
                "private_label": {"label_positive": False},
            },
        ],
        source_id="p44:duplicate:p24-window",
    )

    result = _api().materialize_p105_release_qualified_evidence(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_reviewed_local_manifest=manifest_path,
        p44_mode="reviewed-local",
        output_dir=tmp_path / "unevaluable",
        mode="release_qualified",
    )

    p44_preflight = result["source_availability_preflight"]["sources"]["p44"]
    assert p44_preflight["available_source_rows"] == 0
    assert p44_preflight["unevaluable_row_count"] == 2
    assert "source_timestamp_missing" in p44_preflight["validation_error_codes"]
    assert "duplicate_p24_source_window" in p44_preflight["validation_error_codes"]
