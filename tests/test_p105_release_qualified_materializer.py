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
