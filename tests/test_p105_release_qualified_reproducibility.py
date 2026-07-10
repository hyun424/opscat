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

RELEASE_BENCHMARK = Path("evals/proactive/forecast/p105_release_benchmark_rows.json")
P32_REPLAY = Path("evals/telemetry/replay/p32_replay_pack.json")
P41_SOURCES = Path("evals/real_datasets/raw/p41_sources.json")
MATERIALIZER_SCRIPT = Path("scripts/materialize_p105_release_evidence.py")
BENCHMARK_SCRIPT = Path("scripts/run_failure_forecast_benchmark.py")
REQUIRED_MANIFEST_FILES = {
    "source": "p105-source-manifest.json",
    "preflight": "p105-source-availability-preflight.json",
    "private_label": "p105-private-scorer-label-ledger.json",
    "partition": "p105-partitions.json",
    "coverage": "p105-coverage.json",
    "p24": "p105-p24-parity.json",
    "benchmark": "p105-release-qualified-benchmark.json",
    "review": "p105-review.json",
}
REQUIRED_PRIVACY_PROVENANCE_FILES = {
    "privacy": "p105-privacy-redaction-manifest.json",
    "license": "p105-license-manifest.json",
    "citation": "p105-citation-manifest.json",
    "provenance": "p105-provenance-hash-manifest.json",
}


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _payload() -> dict[str, Any]:
    return json.loads(RELEASE_BENCHMARK.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any], name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _materialize(output_dir: Path) -> dict[str, Any]:
    materializer = getattr(_api(), "materialize_p105_release_qualified_evidence", None)
    if materializer is None:
        pytest.fail("G006 materializer missing: expose materialize_p105_release_qualified_evidence.", pytrace=False)
    return materializer(
        p32_replay=P32_REPLAY,
        p41_sources=P41_SOURCES,
        p44_mode="disabled",
        output_dir=output_dir,
        mode="release_qualified",
        expect_locked=True,
    )


def _tamper_check(path: Path) -> dict[str, Any]:
    checker = getattr(_api(), "validate_p105_release_qualified_tamper", None)
    if checker is None:
        pytest.fail("G006 tamper validator missing: expose validate_p105_release_qualified_tamper.", pytrace=False)
    return checker(path)


def _reviewed_p44_v3_manifest(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    records_path = tmp_path / "reviewed-p44-v3-public-records.jsonl"
    ledger_path = tmp_path / "reviewed-p44-v3-private-ledger.json"
    rows = []
    labels = []
    for family in ("database", "deploy", "queue"):
        for partition, count, positives in (("held_out", 30, 6), ("real_derived_shadow", 20, 4)):
            for index in range(count):
                positive = index < positives
                window_id = f"p44-v3-window-{family}-{partition}-{index:03d}"
                label_source = "official_nab_window" if family in {"database", "queue"} else "reviewed_loghub_burst"
                rows.append(
                    {
                        "record_id": f"p44-v3-{family}-{partition}-{index:03d}",
                        "source_dataset": "p44-reviewed-local-v3",
                        "family": family,
                        "pre_label_partition": partition,
                        "source_timestamp": f"2026-05-{(index % 20) + 1:02d}T10:00:00Z",
                        "source_window_id": window_id,
                        "public_features": {"metric": f"{family}.saturation", "value": index, "trend": "rising" if positive else "flat"},
                        "p24_input": {
                            "id": window_id,
                            "window_id": window_id,
                            "service": f"{family}-service",
                            "metric": f"{family}.saturation",
                            "risk_type": family,
                            "values": [1.0, 2.0, 4.0, 7.0, 9.0] if positive else [1.0, 1.1, 1.3, 1.5, 1.7],
                        },
                        "coverage_interval": {"timestamp_source": "raw_source_record", "split_id": f"g006-{partition}", "family": family, "service": f"{family}-service", "source_system": "p44"},
                        "reviewed_label_join": {
                            "sampled_before_label_join": True,
                            "label_source": label_source,
                            "official_window_id": window_id if label_source == "official_nab_window" else None,
                            "loghub_burst_id": f"burst-{window_id}" if label_source == "reviewed_loghub_burst" else None,
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
                        "lead_time_label_minutes": 60 if positive else None,
                        "label_source": label_source,
                    }
                )
    records_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    ledger_path.write_text(json.dumps({"schema_version": "p105.reviewed_p44_private_label_ledger.v1", "records": labels}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()
    ledger_hash = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    for filename, payload in {
        "p105-privacy-redaction-manifest.json": {"schema_version": "p105.privacy_redaction.v1", "raw_private_labels_embedded": False},
        "p105-license-manifest.json": {"schema_version": "p105.license.v1", "license_id": "fixture-only-reviewed-local"},
        "p105-citation-manifest.json": {"schema_version": "p105.citation.v1", "citation_id": "fixture:p44:v3"},
        "p105-provenance-hash-manifest.json": {"schema_version": "p105.provenance_hash.v1", "public_records_sha256": source_hash, "private_ledger_sha256": ledger_hash},
    }.items():
        (tmp_path / filename).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "p44-reviewed-local-manifest-v3.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "p105.reviewed_p44_local_manifest.v3",
                "review_redaction_status": "reviewed_redacted",
                "private_label_ledger_path": str(ledger_path),
                "privacy_manifest_path": str(tmp_path / "p105-privacy-redaction-manifest.json"),
                "license_manifest_path": str(tmp_path / "p105-license-manifest.json"),
                "citation_manifest_path": str(tmp_path / "p105-citation-manifest.json"),
                "provenance_hash_manifest_path": str(tmp_path / "p105-provenance-hash-manifest.json"),
                "sources": [
                    {
                        "source_id": "p44:v3:reviewed-local",
                        "family": "multi",
                        "local_materialized_path": str(records_path),
                        "local_source_hash": source_hash,
                        "record_count": len(rows),
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


def _materialize_reviewed_local(output_dir: Path, manifest_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER_SCRIPT),
            "--p32-replay",
            str(P32_REPLAY),
            "--p41-sources",
            str(P41_SOURCES),
            "--p44-reviewed-local-manifest",
            str(manifest_path),
            "--p44-mode",
            "reviewed-local",
            "--output-dir",
            str(output_dir),
            "--mode",
            "release_qualified",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_materializer_runs_are_byte_identical_for_rows_manifests_partitions_coverage_and_benchmark(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    _materialize(first_dir)
    _materialize(second_dir)

    for name in [
        "p105-release-qualified-rows.json",
        "p105-source-availability-preflight.json",
        "p105-partitions.json",
        "p105-coverage.json",
        "p105-release-qualified-benchmark.json",
    ]:
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes(), name


def test_source_record_edit_changes_expected_source_and_materialized_hashes(tmp_path: Path) -> None:
    result = _materialize(tmp_path)
    rows_path = tmp_path / "p105-release-qualified-rows.json"
    payload = json.loads(rows_path.read_text(encoding="utf-8"))
    payload["rows"][0]["public_features"]["pre_outcome_metric"] = "tampered"
    rows_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    tamper = _tamper_check(rows_path)

    assert "source_content_hash_mismatch" in tamper["validation_error_codes"]
    assert "materialized_record_hash_mismatch" in tamper["validation_error_codes"]
    assert tamper["release_gate"]["release_qualified"] is False
    assert tamper["release_gate"]["p106_unlocked"] is False
    assert result["artifact_hashes"] != tamper["artifact_hashes"]


@pytest.mark.parametrize(
    ("name", "mutator", "expected_code"),
    [
        (
            "row-deletion",
            lambda payload: payload["rows"].pop(),
            "row_manifest_tamper",
        ),
        (
            "row-duplication",
            lambda payload: payload["rows"].append(copy.deepcopy(payload["rows"][0])),
            "duplicate_release_row",
        ),
        (
            "mode-edit",
            lambda payload: payload.__setitem__("mode", "release_qualified"),
            "mode_metadata_tamper",
        ),
        (
            "partition-edit",
            lambda payload: payload["rows"][0].__setitem__("partition", "real_derived_shadow"),
            "partition_manifest_tamper",
        ),
        (
            "floor-weakening",
            lambda payload: payload.setdefault("release_qualification", {}).__setitem__("held_out_min_evaluated_per_family", 1),
            "floor_contract_tamper",
        ),
        (
            "coverage-edit",
            lambda payload: payload["service_day_coverage"]["database"].__setitem__("service_days", 999),
            "coverage_manifest_tamper",
        ),
    ],
)
def test_artifact_tamper_attempts_fail_closed(tmp_path: Path, name: str, mutator: Any, expected_code: str) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    mutator(payload)
    path = _write_payload(tmp_path, payload, f"{name}.json")

    tamper = _tamper_check(path)

    assert expected_code in tamper["validation_error_codes"]
    assert tamper["release_gate"]["release_qualified"] is False
    assert tamper["release_gate"]["p106_unlocked"] is False


def test_label_tamper_fails_when_public_hashes_are_unchanged_or_recomputed(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    payload["private_scorer_label_ledger"] = {
        "records": [
            {
                "row_id": payload["rows"][0]["row_id"],
                "incident_group_id": "tampered-group",
                "label_positive": not payload["rows"][0]["scorer_labels"]["label_positive"],
                "label_hash": "recomputed-public-hash-does-not-matter",
            }
        ]
    }
    payload["artifact_hashes"] = {"rows_sha256": "recomputed-public-rows-hash"}
    path = _write_payload(tmp_path, payload, "label-recomputed-public-hash.json")

    tamper = _tamper_check(path)

    assert "private_label_hash_mismatch" in tamper["validation_error_codes"]
    assert "public_hash_recompute_cannot_mask_private_label_tamper" in tamper["validation_error_codes"]
    assert tamper["release_gate"]["release_qualified"] is False
    assert tamper["release_gate"]["p106_unlocked"] is False


def test_clone_inflation_fails_before_scoring(tmp_path: Path) -> None:
    payload = _payload()
    payload["mode"] = "release_qualified"
    clone = copy.deepcopy(payload["rows"][0])
    clone["row_id"] = "clone-row"
    clone["source_window_id"] = payload["rows"][0]["source_window_id"]
    clone["derivation"] = copy.deepcopy(payload["rows"][0]["derivation"])
    clone["source_record_provenance"] = {
        "canonical_source_tuple": {
            "source_system": "p32",
            "source_dataset": "clone",
            "source_manifest_key": "clone",
            "source_content_hash": "same-source",
            "materialized_record_hash": "same-materialized-record",
            "materialization_version": "v1",
        },
        "record_offset": 0,
    }
    payload["rows"][0]["source_record_provenance"] = copy.deepcopy(clone["source_record_provenance"])
    payload["rows"].append(clone)
    path = _write_payload(tmp_path, payload, "clone.json")

    tamper = _tamper_check(path)

    assert tamper["failure_stage"] == "pre_scoring"
    assert "duplicate_materialized_record_hash" in tamper["validation_error_codes"]
    assert "duplicate_source_window_incident_derivation_key" in tamper["validation_error_codes"]
    assert tamper["release_gate"]["release_qualified"] is False
    assert tamper["release_gate"]["p106_unlocked"] is False


def test_benchmark_cli_writes_output_and_returns_locked_for_smoke_artifact(tmp_path: Path) -> None:
    output = tmp_path / "p105-release-benchmark-smoke.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(BENCHMARK_SCRIPT),
            "--release-benchmark",
            str(RELEASE_BENCHMARK),
            "--output-json",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_materializer_cli_reproducibility_contract_is_byte_identical(tmp_path: Path) -> None:
    first_dir = tmp_path / "first-cli"
    second_dir = tmp_path / "second-cli"
    command = [
        sys.executable,
        str(MATERIALIZER_SCRIPT),
        "--p32-replay",
        str(P32_REPLAY),
        "--p41-sources",
        str(P41_SOURCES),
        "--p44-mode",
        "disabled",
        "--mode",
        "release_qualified",
        "--expect-locked",
    ]

    first = subprocess.run(command + ["--output-dir", str(first_dir)], text=True, capture_output=True, check=False)
    second = subprocess.run(command + ["--output-dir", str(second_dir)], text=True, capture_output=True, check=False)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (first_dir / "p105-release-qualified-rows.json").read_bytes() == (
        second_dir / "p105-release-qualified-rows.json"
    ).read_bytes()


def test_required_manifest_files_exist_and_hashes_are_verified(tmp_path: Path) -> None:
    output_dir = tmp_path / "qualified"
    _materialize_reviewed_local(output_dir, _reviewed_p44_v3_manifest(tmp_path))
    rows_payload = json.loads((output_dir / "p105-release-qualified-rows.json").read_text(encoding="utf-8"))

    assert set(rows_payload["artifact_manifests"]) == set(REQUIRED_MANIFEST_FILES)
    for key, filename in REQUIRED_MANIFEST_FILES.items():
        path = output_dir / filename
        assert path.exists(), key
        assert rows_payload["artifact_manifests"][key]["path"] == filename
        assert rows_payload["artifact_manifests"][key]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("manifest_key", "expected_code"),
    [
        ("source", "source_manifest_tamper"),
        ("preflight", "source_availability_preflight_tamper"),
        ("private_label", "private_label_ledger_tamper"),
        ("partition", "partition_manifest_tamper"),
        ("coverage", "coverage_manifest_tamper"),
        ("p24", "p24_parity_manifest_tamper"),
        ("benchmark", "benchmark_manifest_tamper"),
        ("review", "review_manifest_tamper"),
    ],
)
def test_deleting_required_manifest_fails_closed(tmp_path: Path, manifest_key: str, expected_code: str) -> None:
    output_dir = tmp_path / f"delete-{manifest_key}"
    _materialize_reviewed_local(output_dir, _reviewed_p44_v3_manifest(tmp_path / f"fixture-{manifest_key}"))
    target = output_dir / REQUIRED_MANIFEST_FILES[manifest_key]
    assert target.exists(), f"materializer must write required {manifest_key} manifest before deletion tamper can be tested"
    target.unlink()

    tamper = _tamper_check(output_dir / "p105-release-qualified-rows.json")

    assert expected_code in tamper["validation_error_codes"]
    assert tamper["release_gate"]["release_qualified"] is False
    assert tamper["release_gate"]["p106_unlocked"] is False


@pytest.mark.parametrize(
    ("manifest_key", "expected_code"),
    [
        ("source", "source_manifest_tamper"),
        ("preflight", "source_availability_preflight_tamper"),
        ("private_label", "private_label_ledger_tamper"),
        ("partition", "partition_manifest_tamper"),
        ("coverage", "coverage_manifest_tamper"),
        ("p24", "p24_parity_manifest_tamper"),
        ("benchmark", "benchmark_manifest_tamper"),
        ("review", "review_manifest_tamper"),
    ],
)
def test_tampering_required_manifest_fails_closed(tmp_path: Path, manifest_key: str, expected_code: str) -> None:
    output_dir = tmp_path / f"tamper-{manifest_key}"
    _materialize_reviewed_local(output_dir, _reviewed_p44_v3_manifest(tmp_path / f"fixture-tamper-{manifest_key}"))
    target = output_dir / REQUIRED_MANIFEST_FILES[manifest_key]
    assert target.exists(), f"materializer must write required {manifest_key} manifest before content tamper can be tested"
    target.write_text(target.read_text(encoding="utf-8") + "\n{\"tampered\": true}\n", encoding="utf-8")

    tamper = _tamper_check(output_dir / "p105-release-qualified-rows.json")

    assert expected_code in tamper["validation_error_codes"]
    assert tamper["release_gate"]["release_qualified"] is False
    assert tamper["release_gate"]["p106_unlocked"] is False


@pytest.mark.parametrize(
    ("manifest_key", "expected_code"),
    [
        ("privacy", "privacy_manifest_tamper"),
        ("license", "license_manifest_tamper"),
        ("citation", "citation_manifest_tamper"),
        ("provenance", "provenance_hash_manifest_tamper"),
    ],
)
def test_privacy_license_citation_and_provenance_manifest_tamper_fails_closed(
    tmp_path: Path,
    manifest_key: str,
    expected_code: str,
) -> None:
    output_dir = tmp_path / f"tamper-{manifest_key}"
    _materialize_reviewed_local(output_dir, _reviewed_p44_v3_manifest(tmp_path / f"fixture-{manifest_key}"))
    rows_path = output_dir / "p105-release-qualified-rows.json"
    rows_payload = json.loads(rows_path.read_text(encoding="utf-8"))
    target = output_dir / REQUIRED_PRIVACY_PROVENANCE_FILES[manifest_key]

    assert target.exists(), f"materializer must write required {manifest_key} manifest before tamper can be tested"
    assert rows_payload["artifact_manifests"][manifest_key]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    target.write_text(target.read_text(encoding="utf-8") + "\n{\"tampered\": true}\n", encoding="utf-8")

    tamper = _tamper_check(rows_path)

    assert expected_code in tamper["validation_error_codes"]
    assert tamper["release_gate"]["release_qualified"] is False
    assert tamper["release_gate"]["p106_unlocked"] is False
