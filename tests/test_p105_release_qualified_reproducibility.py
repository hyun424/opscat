from __future__ import annotations

import copy
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
