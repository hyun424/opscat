from __future__ import annotations

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
    """Create enough distinct reviewed-local P44 records to satisfy G006 floors."""

    dataset_dir = tmp_path / "reviewed-p44"
    dataset_dir.mkdir()
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


def test_reviewed_local_p44_positive_path_counts_only_reviewed_redacted_local_records(tmp_path: Path) -> None:
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
    assert preflight["available_source_rows"] > 0
    assert preflight["available_source_rows"] <= 2000
    assert preflight["local_source_hashes"]
    assert preflight["materialized_record_hashes"]


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


def test_materializer_cli_reviewed_local_p44_positive_contract(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER_SCRIPT),
            "--p32-replay",
            str(P32_REPLAY),
            "--p41-sources",
            str(P41_SOURCES),
            "--p44-reviewed-local-manifest",
            str(_reviewed_p44_manifest(tmp_path)),
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


def test_reviewed_local_p44_end_to_end_materializes_and_unlocks_release_gate(tmp_path: Path) -> None:
    reviewed_manifest = _write_floor_scale_p44_dataset(tmp_path)
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


def test_reviewed_local_p44_manifest_uses_parsed_records_hashes_and_private_labels(tmp_path: Path) -> None:
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
    assert p44["available_source_rows"] == len(parsed_records)
    assert p44["record_count_verified_from_parsed_records"] is True
    assert p44["positive_labels"] == sum(1 for record in parsed_records if record["private_label"]["label_positive"] is True)
    assert p44["incidents"] == sum(1 for record in parsed_records if record["private_label"]["label_incident_id"])
    assert p44["incident_groups"] == len({record["private_label"]["incident_group_id"] for record in parsed_records})


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
