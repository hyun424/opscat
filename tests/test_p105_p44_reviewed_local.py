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
