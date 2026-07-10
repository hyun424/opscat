from __future__ import annotations

import copy
import hashlib
import importlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

RELEASE_BENCHMARK = Path("evals/proactive/forecast/p105_release_benchmark_rows.json")
DIAGNOSTIC_CORPUS = Path("evals/proactive/forecast/p105_curated_synthetic_rows.json")
P32_REPLAY_PACK = Path("evals/telemetry/replay/p32_replay_pack.json")
P41_SOURCE_CARDS = Path("evals/real_datasets/raw/p41_sources.json")
P44_MATRIX_MANIFEST = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
P105_MODEL_CARD = Path("docs/operations/p105-model-card.md")
P105_FINAL_SUMMARY = Path("docs/operations/p105-final-summary.md")
VERIFY_SCRIPT = Path("scripts/verify.sh")

RELEASE_FAMILIES = {"database", "queue", "deploy"}
CANONICAL_SOURCE_TUPLE_KEYS = {
    "source_system",
    "source_dataset",
    "source_manifest_key",
    "source_content_hash",
    "materialized_record_hash",
    "materialization_version",
}
SCORER_ONLY_PREFIXES = ("label_", "lead_time_label_minutes", "incident_group_id")
HASH_SAFE_DIAGNOSTIC_KEYS = {
    "row_id_hash",
    "diagnostic_reason_code",
    "expected_disposition",
    "actual_disposition",
    "counted_in_release_gate",
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.failure_forecast_engine")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P105 implementation missing: app.services.failure_forecast_engine must expose run_p105_benchmark ({exc}).", pytrace=False)


def _payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows() -> list[dict[str, Any]]:
    return list(_payload(RELEASE_BENCHMARK)["rows"])


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["row_id"]): row for row in payload["rows"]}


def _write_payload(tmp_path: Path, name: str, payload: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _release_floor_fixture() -> dict[str, Any]:
    payload = copy.deepcopy(_payload(RELEASE_BENCHMARK))
    payload["mode"] = "release_qualified"
    payload["release_qualification"] = {
        "mode": "release_qualified",
        "floor_contract_version": "p105-012",
        "held_out_min_positive_per_family": 2,
        "held_out_min_negative_per_family": 2,
        "real_derived_min_positive_per_family": 2,
        "real_derived_min_negative_per_family": 2,
        "minimum_union_service_days": 7,
        "minimum_source_record_sets": 3,
        "maximum_single_source_fraction": 0.6,
    }
    new_rows: list[dict[str, Any]] = []
    for family in sorted(RELEASE_FAMILIES):
        for partition in ("held_out", "real_derived_shadow"):
            base_rows = [row for row in payload["rows"] if row["partition"] == partition and row["family"] == family]
            for index, base in enumerate(base_rows, start=1):
                duplicate = copy.deepcopy(base)
                duplicate["row_id"] = f"{base['row_id']}-floor-extra-{index}"
                duplicate["source_window_id"] = f"{base['source_window_id']}-floor-extra-{index}"
                duplicate["forecast_timestamp"] = "2026-01-20T10:00:00Z"
                duplicate["window_start_timestamp"] = "2026-01-20T09:45:00Z"
                duplicate["window_end_timestamp"] = "2026-01-20T10:00:00Z"
                duplicate["scorer_labels"]["incident_group_id"] = f"{duplicate['row_id']}-group"
                if duplicate["scorer_labels"]["label_positive"] is True:
                    duplicate["scorer_labels"]["label_incident_id"] = f"{duplicate['row_id']}-incident"
                    duplicate["scorer_labels"]["label_incident_start_timestamp"] = "2026-01-20T11:00:00Z"
                    duplicate["scorer_labels"]["lead_time_label_minutes"] = 60
                if partition == "real_derived_shadow" and index == 2:
                    duplicate["source_id"] = "p44:loghub:hdfs:public-matrix"
                    duplicate["derivation"] = {
                        "type": "p44_public_matrix_adaptation",
                        "source_path": str(P44_MATRIX_MANIFEST),
                        "source_event_id": "p44:loghub:hdfs:public-matrix",
                        "derivation_id": f"derive-{duplicate['row_id']}",
                        "source_record_hash": hashlib.sha256(duplicate["row_id"].encode()).hexdigest(),
                        "byte_offset": index * 100,
                    }
                else:
                    duplicate["derivation"]["derivation_id"] = f"derive-{duplicate['row_id']}"
                    duplicate["derivation"]["source_event_id"] = duplicate["source_id"]
                new_rows.append(duplicate)
                payload["partitions"][partition]["row_ids"].append(duplicate["row_id"])
    payload["rows"].extend(new_rows)
    payload["service_day_coverage"] = {
        family: {
            "coverage_intervals": [
                {"service": f"{family}-primary", "start": "2026-01-01T00:00:00Z", "end": "2026-01-04T12:00:00Z"},
                {"service": f"{family}-primary", "start": "2026-01-04T12:00:00Z", "end": "2026-01-08T00:00:00Z"},
            ],
            "covered_service_seconds": 604800,
            "service_days": 7.0,
        }
        for family in sorted(RELEASE_FAMILIES)
    }
    return payload


def _public_key_paths(value: Any, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        paths: set[str] = set()
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(path)
            paths.update(_public_key_paths(child, path))
        return paths
    if isinstance(value, list):
        paths = set()
        for index, child in enumerate(value):
            paths.update(_public_key_paths(child, f"{prefix}[{index}]"))
        return paths
    return set()


def _labels(row: dict[str, Any]) -> dict[str, Any]:
    labels = row.get("scorer_labels")
    assert isinstance(labels, dict), f"{row['row_id']} must keep labels in scorer_labels"
    return labels


def test_release_benchmark_fixture_declares_explicit_partitions_and_scorer_only_labels() -> None:
    payload = _payload(RELEASE_BENCHMARK)
    by_id = _row_by_id(payload)

    assert payload["schema_version"] == "p105.forecast.release_benchmark.v1"
    assert set(payload["release_supported_families"]) == RELEASE_FAMILIES
    assert payload["diagnostic_families"] == ["observability_zero_positive"]
    assert payload["release_gate_eligible_partitions"] == ["held_out", "real_derived_shadow"]

    for partition, spec in payload["partitions"].items():
        assert "split_id" in spec
        assert isinstance(spec["eligible_for_release_gate"], bool)
        assert set(spec["row_ids"]) <= set(by_id)
        for row_id in spec["row_ids"]:
            row = by_id[row_id]
            assert row["partition"] == partition
            assert row["split_id"] == spec["split_id"]

    for row in payload["rows"]:
        root_leaks = {key for key in row if key.startswith("label_") or key in {"lead_time_label_minutes", "incident_group_id"}}
        public_leaks = {
            path for path in _public_key_paths(row["public_features"])
            if path.rsplit(".", 1)[-1].startswith("label_") or path.rsplit(".", 1)[-1] in SCORER_ONLY_PREFIXES
        }
        assert root_leaks == set(), f"{row['row_id']} leaked scorer labels at row root"
        assert public_leaks == set(), f"{row['row_id']} leaked scorer labels in public_features"
        assert set(_labels(row)) == {
            "label_incident_id",
            "label_incident_start_timestamp",
            "label_family",
            "label_failure_mode",
            "label_positive",
            "lead_time_label_minutes",
            "incident_group_id",
        }


def test_release_benchmark_has_temporal_positive_and_negative_denominators_per_release_family() -> None:
    rows = _rows()

    for partition in ("held_out", "real_derived_shadow"):
        partition_rows = [row for row in rows if row["partition"] == partition]
        assert {row["family"] for row in partition_rows} == RELEASE_FAMILIES
        for family in RELEASE_FAMILIES:
            family_rows = [row for row in partition_rows if row["family"] == family]
            positives = [row for row in family_rows if _labels(row)["label_positive"] is True]
            negatives = [row for row in family_rows if _labels(row)["label_positive"] is False]
            assert len(positives) >= 1, f"{partition}/{family} must have temporal positives"
            assert len(negatives) >= 1, f"{partition}/{family} must have temporal negatives"
            for positive in positives:
                assert _parse_ts(positive["forecast_timestamp"]) < _parse_ts(_labels(positive)["label_incident_start_timestamp"])
            for negative in negatives:
                assert _labels(negative)["label_incident_start_timestamp"] is None


def test_release_benchmark_provenance_points_back_to_p32_replay_pack_and_p41_source_cards() -> None:
    p32_source_ids = {source["id"] for source in _payload(P32_REPLAY_PACK)["sources"]}
    p41_source_ids = {source["id"] for source in _payload(P41_SOURCE_CARDS)["sources"]}
    real_rows = [row for row in _rows() if row["partition"] == "real_derived_shadow"]

    assert any(row["derivation"]["type"] == "p32_real_telemetry_replay_adaptation" for row in real_rows)
    assert any(row["derivation"]["type"] == "p41_raw_source_card_adaptation" for row in real_rows)
    for row in real_rows:
        derivation = row["derivation"]
        assert derivation["source_path"] in {
            "evals/telemetry/replay/p32_replay_pack.json",
            "evals/real_datasets/raw/p41_sources.json",
        }
        if derivation["type"] == "p32_real_telemetry_replay_adaptation":
            assert row["source_id"] in p32_source_ids
            assert derivation["source_event_id"] in p32_source_ids
        if derivation["type"] == "p41_raw_source_card_adaptation":
            assert row["source_id"] in p41_source_ids
            assert derivation["source_event_id"] in p41_source_ids


def test_release_benchmark_exclusion_rules_are_deterministic_and_not_outcome_based() -> None:
    payload = _payload(RELEASE_BENCHMARK)

    rules = payload["exclusion_rules"]
    assert {rule["id"] for rule in rules} == {
        "exclude-diagnostic-family",
        "exclude-training-calibration",
        "exclude-unqualified-evidence",
    }
    assert all(rule["deterministic"] is True for rule in rules)
    assert all(rule["outcome_based"] is False for rule in rules)
    assert all("label" not in rule["condition"] and "score" not in rule["condition"] for rule in rules)


def test_release_benchmark_has_no_duplicate_clones_masquerading_as_independent_events() -> None:
    rows = _rows()
    source_windows = [row["source_window_id"] for row in rows]
    derivations = [row["derivation"]["derivation_id"] for row in rows]
    independent_event_keys = [
        (
            row["partition"],
            row["family"],
            row["source_id"],
            row["derivation"]["source_event_id"],
            row["forecast_timestamp"],
        )
        for row in rows
    ]

    assert len(source_windows) == len(set(source_windows))
    assert len(derivations) == len(set(derivations))
    assert len(independent_event_keys) == len(set(independent_event_keys))


def test_run_p105_benchmark_reports_release_and_diagnostic_partitions_separately() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)

    assert report["schema_version"] == "p105.release_benchmark.report.v1"
    assert set(report["release_partitions"]) == {"held_out", "real_derived_shadow"}
    assert report["diagnostic_partition"]["source_path"] == str(DIAGNOSTIC_CORPUS)
    assert report["diagnostic_partition"]["row_count"] >= 3
    assert report["release_gate"]["eligible_partitions"] == ["held_out", "real_derived_shadow"]
    assert report["release_gate"]["excluded_partitions"] == ["train", "calibration", "diagnostic"]
    assert report["release_gate"]["diagnostic_denominator_count"] == 0


def test_run_p105_benchmark_keeps_p106_locked_when_only_unchanged_thresholds_pass_on_tiny_fixture() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)
    gate = report["release_gate"]

    assert gate["p106_unlocked"] is False
    assert gate["release_qualified"] is False
    assert gate["unchanged_metrics"]["pass"] is True
    assert gate["thresholds"] == {
        "minimum_useful_lead_time_rate": 0.8,
        "maximum_family_false_alerts_per_service_day": 0.5,
        "maximum_global_false_alerts_per_service_day": 0.25,
        "maximum_family_abstention_rate": 0.3,
        "maximum_global_abstention_rate": 0.2,
        "maximum_real_derived_useful_lead_time_drop": 0.1,
        "maximum_real_derived_false_alert_increase": 0.1,
    }
    assert set(gate["families"]) == RELEASE_FAMILIES
    assert "observability_zero_positive" not in gate["families"]
    assert all(row["pass"] is True for row in gate["families"].values())
    assert gate["global"]["pass"] is True


def test_run_p105_benchmark_keeps_diagnostic_safety_cases_fail_closed_out_of_denominators() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)
    diagnostics = report["diagnostic_partition"]

    assert diagnostics["families"]["observability_zero_positive"]["release_supported"] is False
    assert diagnostics["families"]["observability_zero_positive"]["counted_in_release_gate"] is False
    for row in diagnostics["rows"]:
        assert row["counted_in_release_gate"] is False
        assert row["expected_disposition"] == "abstain_fail_closed"
        assert row["actual_disposition"] in {"abstain", "fail_closed"}
    assert report["release_gate"]["diagnostic_denominator_count"] == 0


def test_run_p105_benchmark_locks_p106_when_any_release_family_or_evidence_denominator_is_missing(tmp_path: Path) -> None:
    payload = _payload(RELEASE_BENCHMARK)
    missing_queue_negative = copy.deepcopy(payload)
    missing_queue_negative["rows"] = [
        row for row in missing_queue_negative["rows"]
        if row["row_id"] != "p105-release-shadow-p41-queue-neg-001"
    ]
    missing_queue_negative["partitions"]["real_derived_shadow"]["row_ids"] = [
        row_id for row_id in missing_queue_negative["partitions"]["real_derived_shadow"]["row_ids"]
        if row_id != "p105-release-shadow-p41-queue-neg-001"
    ]
    path = tmp_path / "p105-release-missing-denominator.json"
    path.write_text(json.dumps(missing_queue_negative, indent=2), encoding="utf-8")

    report = _api().run_p105_benchmark(path)

    assert report["release_gate"]["p106_unlocked"] is False
    assert report["release_gate"]["missing_denominators"] == [
        {
            "partition": "real_derived_shadow",
            "family": "queue",
            "missing": "negative_evidence_denominator",
        }
    ]


def test_run_p105_benchmark_normalizes_missing_mode_to_smoke_only_missing_mode() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)

    assert report["release_gate"]["qualification_mode"] == "smoke_only_missing_mode"
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_run_p105_benchmark_normalizes_unknown_mode_to_smoke_only_missing_mode(tmp_path: Path) -> None:
    payload = _payload(RELEASE_BENCHMARK)
    payload["mode"] = "release-ready-but-not-predeclared"
    path = _write_payload(tmp_path, "p105-unknown-mode.json", payload)

    report = _api().run_p105_benchmark(path)

    assert report["release_gate"]["qualification_mode"] == "smoke_only_missing_mode"
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_current_committed_release_fixture_is_smoke_only_until_floor_metadata_exists() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)

    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["smoke_only_reason"] == "tiny_release_fixture_missing_release_qualification_floors"
    assert report["release_gate"]["p106_unlocked"] is False


def test_release_qualification_requires_anti_tiny_n_source_diversity_and_union_service_day_floors(tmp_path: Path) -> None:
    payload = _release_floor_fixture()
    payload["rows"] = [
        row
        for row in payload["rows"]
        if not (row["partition"] == "real_derived_shadow" and row["family"] == "deploy" and row["scorer_labels"]["label_positive"] is False)
    ]
    path = _write_payload(tmp_path, "p105-floor-missing-deploy-real-negative.json", payload)

    report = _api().run_p105_benchmark(path)

    floors = report["release_gate"]["qualification_floors"]
    assert floors["families"]["deploy"]["real_derived_shadow"]["negative_count"]["pass"] is False
    assert floors["source_diversity"]["distinct_source_record_sets"]["minimum"] == 3
    assert floors["source_diversity"]["maximum_single_source_fraction"]["maximum"] == 0.6
    assert floors["service_day_coverage"]["union_service_days"]["minimum"] == 7
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_coverage_interval_union_prevents_overlapping_service_day_dilution(tmp_path: Path) -> None:
    payload = _release_floor_fixture()
    payload["service_day_coverage"]["database"] = {
        "coverage_intervals": [
            {"service": "checkout-api", "start": "2026-01-01T00:00:00Z", "end": "2026-01-06T00:00:00Z"},
            {"service": "checkout-api", "start": "2026-01-03T00:00:00Z", "end": "2026-01-08T00:00:00Z"},
        ],
        "covered_service_seconds": 864000,
        "service_days": 10.0,
    }
    path = _write_payload(tmp_path, "p105-overlapping-coverage.json", payload)

    report = _api().run_p105_benchmark(path)

    database_coverage = report["release_gate"]["qualification_floors"]["service_day_coverage"]["families"]["database"]
    assert database_coverage["raw_service_days"] == 10.0
    assert database_coverage["union_service_days"] == 7.0
    assert database_coverage["pass"] is True


def test_post_incident_public_features_fail_release_closed(tmp_path: Path) -> None:
    payload = _payload(RELEASE_BENCHMARK)
    payload["rows"][0]["public_features"]["post_incident"] = {"resolved_at": "2026-01-03T11:00:00Z"}
    path = _write_payload(tmp_path, "p105-post-incident-leak.json", payload)

    report = _api().run_p105_benchmark(path)

    assert "post_incident_leakage" in report["release_gate"]["validation_error_codes"]
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_predeclared_partitions_reject_time_order_and_incident_group_isolation_violations(tmp_path: Path) -> None:
    payload = _payload(RELEASE_BENCHMARK)
    held_out_row = next(row for row in payload["rows"] if row["partition"] == "held_out")
    shadow_row = next(row for row in payload["rows"] if row["partition"] == "real_derived_shadow")
    shadow_row["scorer_labels"]["incident_group_id"] = held_out_row["scorer_labels"]["incident_group_id"]
    shadow_row["forecast_timestamp"] = "2026-01-01T00:00:00Z"
    path = _write_payload(tmp_path, "p105-partition-isolation-break.json", payload)

    report = _api().run_p105_benchmark(path)

    assert "incident_group_partition_overlap" in report["release_gate"]["validation_error_codes"]
    assert "partition_time_order_violation" in report["release_gate"]["validation_error_codes"]
    assert report["release_gate"]["release_qualified"] is False


def test_supported_valid_rows_cannot_be_hidden_in_private_safety_diagnostics(tmp_path: Path) -> None:
    payload = _payload(RELEASE_BENCHMARK)
    hidden = copy.deepcopy(next(row for row in payload["rows"] if row["partition"] == "held_out" and row["family"] == "database"))
    hidden["row_id"] = "p105-hidden-supported-valid-diagnostic"
    hidden["partition"] = "diagnostic"
    hidden["split"] = "diagnostic"
    hidden["split_id"] = payload["partitions"]["diagnostic"]["split_id"]
    hidden["expected_diagnostic_disposition"] = "abstain_fail_closed"
    payload["rows"].append(hidden)
    payload["partitions"]["diagnostic"]["row_ids"].append(hidden["row_id"])
    path = _write_payload(tmp_path, "p105-hidden-valid-diagnostic.json", payload)

    report = _api().run_p105_benchmark(path)

    assert "supported_valid_row_hidden_in_diagnostic" in report["release_gate"]["validation_error_codes"]
    assert report["release_gate"]["release_qualified"] is False


def test_private_safety_diagnostics_publish_only_hash_safe_metadata() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)

    for row in report["diagnostic_partition"]["rows"]:
        assert set(row) <= HASH_SAFE_DIAGNOSTIC_KEYS
        assert "row_id" not in row
        assert len(row["row_id_hash"]) == 64


def test_source_record_row_generator_is_deterministic_and_emits_canonical_provenance(tmp_path: Path) -> None:
    api = _api()

    first = api.generate_p105_source_record_rows(max_rows=2000, output_path=tmp_path / "first.json")
    api.generate_p105_source_record_rows(max_rows=2000, output_path=tmp_path / "second.json")

    assert first["row_count"] <= 2000
    assert (tmp_path / "first.json").read_bytes() == (tmp_path / "second.json").read_bytes()
    for row in first["rows"]:
        provenance = row["source_record_provenance"]
        assert {
            "canonical_source_tuple",
            "source_content_hash",
            "materialized_record_hash",
            "materialization_version",
            "byte_offset",
            "record_offset",
            "source_timestamp",
            "derivation_id",
            "derivation_type",
        } <= set(provenance)
        assert set(provenance["canonical_source_tuple"]) == CANONICAL_SOURCE_TUPLE_KEYS
        for key in CANONICAL_SOURCE_TUPLE_KEYS:
            assert provenance["canonical_source_tuple"][key]


def test_source_id_only_provenance_fails_closed_for_release(tmp_path: Path) -> None:
    payload = _payload(RELEASE_BENCHMARK)
    real_row = next(row for row in payload["rows"] if row["partition"] == "real_derived_shadow")
    real_row["derivation"] = {"source_path": "evals/telemetry/replay/p32_replay_pack.json"}
    path = _write_payload(tmp_path, "p105-source-id-only-provenance.json", payload)

    report = _api().run_p105_benchmark(path)

    assert "source_record_provenance_missing" in report["release_gate"]["validation_error_codes"]
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_p105_012_source_id_only_payload_can_never_release_qualify_or_unlock_p106(tmp_path: Path) -> None:
    payload = _release_floor_fixture()
    assert payload["release_qualification"]["floor_contract_version"] == "p105-012"
    for row in payload["rows"]:
        row.pop("source_record_provenance", None)
        if row["partition"] == "real_derived_shadow":
            row["source_id"] = f"legacy-source-id-only:{row['family']}:{row['row_id']}"
            row["derivation"]["source_event_id"] = row["source_id"]
    path = _write_payload(tmp_path, "p105-012-legacy-source-id-only.json", payload)

    report = _api().run_p105_benchmark(path)

    diversity = report["release_gate"]["qualification_floors"]["source_diversity"]
    assert diversity["canonical_tuple_keys"] == sorted(CANONICAL_SOURCE_TUPLE_KEYS)
    assert diversity["pass"] is False
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_release_qualified_real_derived_rows_require_exact_six_field_canonical_tuple(tmp_path: Path) -> None:
    payload = _release_floor_fixture()
    real_row = next(row for row in payload["rows"] if row["partition"] == "real_derived_shadow")
    real_row["source_record_provenance"] = {
        "canonical_source_tuple": {
            "source_system": "p32",
            "source_dataset": "replay",
            "source_manifest_key": "manifest-001",
            "source_content_hash": "source-content-001",
            "materialized_record_hash": "materialized-001",
            "materialization_version": "v1",
            "source_id": "legacy-extra-field",
        }
    }
    path = _write_payload(tmp_path, "p105-extra-canonical-field.json", payload)

    report = _api().run_p105_benchmark(path)

    assert "source_record_provenance_noncanonical" in report["release_gate"]["validation_error_codes"]
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_source_diversity_max_fraction_is_computed_per_family_over_real_derived_rows_only(tmp_path: Path) -> None:
    payload = _release_floor_fixture()
    real_family_seen: dict[str, int] = {}
    for row in payload["rows"]:
        if row["partition"] == "held_out":
            row["source_record_provenance"] = {
                "canonical_source_tuple": {
                    key: f"heldout-{row['family']}-{row['row_id']}-{key}" for key in CANONICAL_SOURCE_TUPLE_KEYS
                }
            }
            continue
        if row["partition"] != "real_derived_shadow":
            continue
        family = row["family"]
        real_family_seen[family] = real_family_seen.get(family, 0) + 1
        source_number = "dominant" if family == "database" and real_family_seen[family] <= 3 else row["row_id"]
        row["source_record_provenance"] = {
            "canonical_source_tuple": {
                "source_system": "p32",
                "source_dataset": f"{family}-dataset",
                "source_manifest_key": f"{family}-{source_number}",
                "source_content_hash": f"{family}-{source_number}-source",
                "materialized_record_hash": f"{family}-{source_number}-materialized",
                "materialization_version": "v1",
            }
        }
    path = _write_payload(tmp_path, "p105-per-family-source-diversity.json", payload)

    diversity = _api().run_p105_benchmark(path)["release_gate"]["qualification_floors"]["source_diversity"]

    assert diversity["source_scope"] == "real_derived_shadow"
    assert diversity["family_scope"] == "per_supported_family"
    assert set(diversity["families"]) == RELEASE_FAMILIES
    assert diversity["families"]["database"]["maximum_single_source_fraction"] == {
        "value": 0.666667,
        "maximum": 0.6,
        "pass": False,
    }
    assert all(
        family == "database" or row["maximum_single_source_fraction"]["pass"] is True
        for family, row in diversity["families"].items()
    )
    assert diversity["pass"] is False


def test_coverage_union_scope_keys_include_split_family_service_and_source_system(tmp_path: Path) -> None:
    payload = _release_floor_fixture()
    for row in payload["rows"]:
        if row["partition"] == "real_derived_shadow":
            row["source_record_provenance"] = {
                "canonical_source_tuple": {
                    "source_system": "p32" if row["family"] != "queue" else "p41",
                    "source_dataset": f"{row['family']}-dataset",
                    "source_manifest_key": row["row_id"],
                    "source_content_hash": f"{row['row_id']}-source",
                    "materialized_record_hash": f"{row['row_id']}-materialized",
                    "materialization_version": "v1",
                }
            }
    for family, coverage in payload["service_day_coverage"].items():
        coverage["coverage_intervals"] = [
            {
                "split_id": "p105-release-real-derived-shadow-v1",
                "family": family,
                "service": f"{family}-primary",
                "source_system": "p32",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-08T00:00:00Z",
            }
        ]
    path = _write_payload(tmp_path, "p105-coverage-scope-keys.json", payload)

    coverage = _api().run_p105_benchmark(path)["release_gate"]["qualification_floors"]["service_day_coverage"]

    assert coverage["union_scope_keys"] == ["split_id", "family", "service", "source_system"]
    for family, row in coverage["families"].items():
        assert row["union_scope"] == {
            "split_id": "p105-release-real-derived-shadow-v1",
            "family": family,
            "service": f"{family}-primary",
            "source_system": "p32",
        }


def test_release_benchmark_uses_actual_p24_risk_signal_baseline_authority() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)

    assert report["held_out_calibration"]["p24_baseline"]["authority"] == "app.services.proactive_risk_sentinel.RiskSignal"
    assert report["held_out_calibration"]["p24_baseline"]["uses_actual_risk_signal_from_window"] is True


def test_release_docs_verify_model_card_and_final_summary_are_wired() -> None:
    model_card = P105_MODEL_CARD.read_text(encoding="utf-8")
    final_summary = P105_FINAL_SUMMARY.read_text(encoding="utf-8")
    verify = VERIFY_SCRIPT.read_text(encoding="utf-8")

    assert "P105 model card" in model_card
    assert "smoke_only_missing_mode" in model_card
    assert "release_qualified" in model_card
    assert "P106 remains locked" in final_summary
    assert "p105_release_benchmark_smoke" in verify
    assert "tests/test_p105_release_evidence.py" in verify


def test_floor_scale_generated_evidence_stays_locked_until_full_canonical_hardening_evidence_exists(tmp_path: Path) -> None:
    payload = _release_floor_fixture()
    path = _write_payload(tmp_path, "p105-floor-scale-release-qualified.json", payload)

    report = _api().run_p105_benchmark(path)

    assert report["release_gate"]["qualification_mode"] == "release_qualified"
    assert report["release_gate"]["qualification_floors"]["floor_contract_version"] == "p105-012"
    assert report["release_gate"]["qualification_floors"]["pass"] is False
    assert report["release_gate"]["unchanged_metrics"]["pass"] is True
    assert report["release_gate"]["safety_boundary"]["pass"] is True
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False
