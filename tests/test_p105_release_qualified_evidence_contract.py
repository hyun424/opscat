from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

RELEASE_BENCHMARK = Path("evals/proactive/forecast/p105_release_benchmark_rows.json")

RELEASE_FAMILIES = {"database", "deploy", "queue"}
DOCUMENTED_FLOORS = {
    "held_out": {
        "evaluated_count": 30,
        "non_abstained_count": 24,
        "positive_count": 6,
        "incident_group_count": 4,
        "service_day_count": 2.0,
    },
    "real_derived_shadow": {
        "evaluated_count": 20,
        "non_abstained_count": 16,
        "positive_count": 4,
        "incident_group_count": 3,
        "service_day_count": 1.0,
    },
}


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _payload() -> dict[str, Any]:
    return json.loads(RELEASE_BENCHMARK.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any], name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _release_qualified_fixture() -> dict[str, Any]:
    payload = copy.deepcopy(_payload())
    payload["mode"] = "release_qualified"
    payload["release_qualification"] = {
        "mode": "release_qualified",
        "floor_contract_version": "p105-g006",
        "held_out_min_evaluated_per_family": 30,
        "held_out_min_non_abstained_per_family": 24,
        "held_out_min_positive_per_family": 6,
        "held_out_min_incident_groups_per_family": 4,
        "held_out_min_service_days_per_family": 2.0,
        "real_derived_min_evaluated_per_family": 20,
        "real_derived_min_non_abstained_per_family": 16,
        "real_derived_min_positive_per_family": 4,
        "real_derived_min_incident_groups_per_family": 3,
        "real_derived_min_service_days_per_family": 1.0,
        "minimum_source_record_sets": 3,
        "maximum_single_source_fraction": 0.6,
        "minimum_union_service_days": 7.0,
    }
    return payload


def test_locked_smoke_preserves_existing_p106_lock_and_receives_no_floor_credit() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)
    gate = report["release_gate"]

    assert gate["qualification_mode"] == "smoke_only_missing_mode"
    assert gate["release_qualified"] is False
    assert gate["p106_unlocked"] is False
    assert gate["qualification_floors"]["pass"] is False
    assert gate["smoke_only_reason"] == "tiny_release_fixture_missing_release_qualification_floors"


def test_release_qualified_contract_requires_exact_documented_floors_per_family(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, _release_qualified_fixture(), "candidate.json")

    gate = _api().run_p105_benchmark(path)["release_gate"]

    assert gate["qualification_mode"] == "release_qualified"
    assert set(gate["qualification_floors"]["families"]) == RELEASE_FAMILIES
    for family in RELEASE_FAMILIES:
        for partition, expected in DOCUMENTED_FLOORS.items():
            floor_row = gate["qualification_floors"]["families"][family][partition]
            for metric, minimum in expected.items():
                assert floor_row[metric]["minimum"] == minimum
    assert gate["release_qualified"] is False
    assert gate["p106_unlocked"] is False


def test_source_availability_preflight_is_required_before_scoring_release_qualified_candidate(tmp_path: Path) -> None:
    payload = _release_qualified_fixture()
    payload.pop("source_availability_preflight", None)
    path = _write_payload(tmp_path, payload, "missing-preflight.json")

    report = _api().run_p105_benchmark(path)

    assert "source_availability_preflight_missing" in report["release_gate"]["validation_error_codes"]
    assert report["release_gate"]["source_availability_preflight"]["checked_before_scoring"] is False
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_preflight_floor_failure_keeps_release_qualified_candidate_locked_before_metrics(tmp_path: Path) -> None:
    payload = _release_qualified_fixture()
    payload["source_availability_preflight"] = {
        "checked_before_scoring": True,
        "families": {
            family: {
                "available_source_rows": 2,
                "positive_labels": 1,
                "incidents": 1,
                "incident_groups": 1,
                "distinct_canonical_source_tuples": 1,
                "review_redaction_status": "reviewed",
                "local_source_hashes": ["source-hash"],
                "materialized_record_hashes": ["materialized-hash"],
            }
            for family in RELEASE_FAMILIES
        },
    }
    path = _write_payload(tmp_path, payload, "insufficient-preflight.json")

    gate = _api().run_p105_benchmark(path)["release_gate"]

    assert gate["source_availability_preflight"]["pass"] is False
    assert gate["source_availability_preflight"]["failure_scope"] == "pre_scoring"
    assert gate["release_qualified"] is False
    assert gate["p106_unlocked"] is False


def test_missing_required_denominators_family_ids_split_ids_or_coverage_fail_closed(tmp_path: Path) -> None:
    payload = _release_qualified_fixture()
    row = next(item for item in payload["rows"] if item["partition"] == "held_out")
    row.pop("family", None)
    row.pop("split_id", None)
    payload["service_day_coverage"].pop("database", None)
    path = _write_payload(tmp_path, payload, "missing-required-fields.json")

    gate = _api().run_p105_benchmark(path)["release_gate"]

    assert "family_id_missing" in gate["validation_error_codes"]
    assert "partition_split_mismatch" in gate["validation_error_codes"]
    assert "service_day_coverage_missing" in gate["validation_error_codes"]
    assert gate["release_qualified"] is False
    assert gate["p106_unlocked"] is False


def test_smoke_cannot_be_promoted_by_mode_filename_or_manifest_metadata_only(tmp_path: Path) -> None:
    payload = copy.deepcopy(_payload())
    payload["mode"] = "release_qualified"
    payload["artifact_manifest"] = {
        "artifact_kind": "qualified",
        "source_rows_artifact": "p105-release-qualified-rows.json",
        "previous_smoke_artifact_hash": "renamed-smoke-hash",
    }
    path = _write_payload(tmp_path, payload, "p105-release-qualified-rows.json")

    gate = _api().run_p105_benchmark(path)["release_gate"]

    assert "smoke_artifact_metadata_promotion" in gate["validation_error_codes"]
    assert gate["qualification_floors"]["pass"] is False
    assert gate["release_qualified"] is False
    assert gate["p106_unlocked"] is False
