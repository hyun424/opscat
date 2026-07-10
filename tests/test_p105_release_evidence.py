from __future__ import annotations

import copy
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

RELEASE_FAMILIES = {"database", "queue", "deploy"}
SCORER_ONLY_PREFIXES = ("label_", "lead_time_label_minutes", "incident_group_id")


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


def test_run_p105_benchmark_passes_unchanged_release_thresholds_on_credible_fixture() -> None:
    report = _api().run_p105_benchmark(RELEASE_BENCHMARK)
    gate = report["release_gate"]

    assert gate["p106_unlocked"] is True
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
