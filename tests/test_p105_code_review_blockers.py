from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.proactive_risk_sentinel import ProactiveRiskSentinel, RiskSignal, load_proactive_fixtures

RELEASE_BENCHMARK = Path("evals/proactive/forecast/p105_release_benchmark_rows.json")
P24_WINDOWS = Path("evals/proactive/seed/risk_windows.json")

DOCUMENTED_FLOORS = {
    "held_out": {
        "evaluated": 30,
        "non_abstained": 24,
        "actual_positive": 6,
        "incident_groups": 4,
        "service_days": 2.0,
    },
    "real_derived_shadow": {
        "evaluated": 20,
        "non_abstained": 16,
        "actual_positive": 4,
        "incident_groups": 3,
        "service_days": 1.0,
    },
}
CANONICAL_SOURCE_TUPLE_KEYS = {
    "source_system",
    "source_dataset",
    "source_manifest_key",
    "source_content_hash",
    "materialized_record_hash",
    "materialization_version",
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.failure_forecast_engine")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P105 implementation missing: app.services.failure_forecast_engine ({exc}).", pytrace=False)


def _payload(path: Path = RELEASE_BENCHMARK) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any], name: str = "p105-blocker.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _release_qualified_payload() -> dict[str, Any]:
    payload = copy.deepcopy(_payload())
    payload["mode"] = "release_qualified"
    payload["release_qualification"] = {
        "mode": "release_qualified",
        "floor_contract_version": "p105-code-review-final",
        "held_out_min_evaluated_per_family": DOCUMENTED_FLOORS["held_out"]["evaluated"],
        "held_out_min_non_abstained_per_family": DOCUMENTED_FLOORS["held_out"]["non_abstained"],
        "held_out_min_positive_per_family": DOCUMENTED_FLOORS["held_out"]["actual_positive"],
        "held_out_min_incident_groups_per_family": DOCUMENTED_FLOORS["held_out"]["incident_groups"],
        "held_out_min_service_days_per_family": DOCUMENTED_FLOORS["held_out"]["service_days"],
        "real_derived_min_evaluated_per_family": DOCUMENTED_FLOORS["real_derived_shadow"]["evaluated"],
        "real_derived_min_non_abstained_per_family": DOCUMENTED_FLOORS["real_derived_shadow"]["non_abstained"],
        "real_derived_min_positive_per_family": DOCUMENTED_FLOORS["real_derived_shadow"]["actual_positive"],
        "real_derived_min_incident_groups_per_family": DOCUMENTED_FLOORS["real_derived_shadow"]["incident_groups"],
        "real_derived_min_service_days_per_family": DOCUMENTED_FLOORS["real_derived_shadow"]["service_days"],
        "minimum_union_service_days": 7,
        "minimum_source_record_sets": 3,
        "maximum_single_source_fraction": 0.6,
    }
    payload["service_day_coverage"] = {
        family: {
            "coverage_intervals": [
                {"service": f"{family}-svc", "start": "2026-01-01T00:00:00Z", "end": "2026-01-08T00:00:00Z"}
            ],
            "covered_service_seconds": 604800,
            "service_days": 999.0,
        }
        for family in payload["release_supported_families"]
    }
    return payload


def test_underqualified_release_mode_uses_exact_documented_floor_rows_and_stays_locked(tmp_path: Path) -> None:
    payload = _release_qualified_payload()
    path = _write_payload(tmp_path, payload)

    report = _api().run_p105_benchmark(path)

    floors = report["release_gate"]["qualification_floors"]["families"]
    for family in payload["release_supported_families"]:
        for partition, expected in DOCUMENTED_FLOORS.items():
            row = floors[family][partition]
            assert row["evaluated_count"] == {"count": 2, "minimum": expected["evaluated"], "pass": False}
            assert row["non_abstained_count"]["minimum"] == expected["non_abstained"]
            assert row["positive_count"]["minimum"] == expected["actual_positive"]
            assert row["incident_group_count"]["minimum"] == expected["incident_groups"]
            assert row["service_day_count"]["minimum"] == expected["service_days"]
            assert row["pass"] is False
    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False


def test_source_diversity_counts_only_real_derived_canonical_materialized_tuples_and_rejects_heldout_inflation(tmp_path: Path) -> None:
    payload = _release_qualified_payload()
    for row in payload["rows"]:
        if row["partition"] == "held_out":
            row["source_id"] = f"synthetic-heldout-inflation:{row['row_id']}"
            row["derivation"]["source_event_id"] = row["source_id"]
            row["source_record_provenance"] = {
                "canonical_source_tuple": {
                    key: f"heldout-{row['row_id']}-{key}" for key in CANONICAL_SOURCE_TUPLE_KEYS
                }
            }
        if row["partition"] == "real_derived_shadow":
            row["source_record_provenance"] = {
                "canonical_source_tuple": {
                    "source_system": "p32",
                    "source_dataset": "single-real-derived-source",
                    "source_manifest_key": "shared-record",
                    "source_content_hash": "source-content-shared",
                    "materialized_record_hash": "materialized-record-shared",
                    "materialization_version": "v1",
                }
            }
    path = _write_payload(tmp_path, payload)

    diversity = _api().run_p105_benchmark(path)["release_gate"]["qualification_floors"]["source_diversity"]

    assert diversity["source_scope"] == "real_derived_shadow"
    assert diversity["canonical_tuple_keys"] == sorted(CANONICAL_SOURCE_TUPLE_KEYS)
    assert diversity["distinct_source_record_sets"] == {"count": 1, "minimum": 3, "pass": False}
    assert diversity["pass"] is False


def test_false_alerts_per_service_day_denominator_uses_merged_coverage_intervals_not_inflated_raw_service_days() -> None:
    report = _api().score_forecasts(
        [
            {
                "forecast_id": "raw-service-days-inflation-fp",
                "source_window_id": "coverage-row-001",
                "family": "database",
                "forecast_timestamp": "2026-03-01T10:00:00Z",
                "probability": 0.95,
                "lead_time_interval_minutes": [30, 60],
                "abstention_reason": None,
            }
        ],
        [],
        family_thresholds={"database": 0.7},
        family_min_response_minutes={"database": 30},
        service_day_coverage={
            "database": {
                "service_days": 999.0,
                "coverage_intervals": [
                    {"service": "checkout-api", "start": "2026-03-01T00:00:00Z", "end": "2026-03-02T12:00:00Z"},
                    {"service": "checkout-api", "start": "2026-03-02T00:00:00Z", "end": "2026-03-03T00:00:00Z"},
                ],
            }
        },
        split_id="p105-coverage-interval-denominator-red",
    )

    assert report["families"]["database"]["false_alerts_per_service_day"] == {
        "numerator": 1,
        "denominator_service_days": 2.0,
        "value": 0.5,
    }


def test_p24_baseline_parity_uses_real_risk_forecast_path_and_cannot_be_faked_by_metadata(tmp_path: Path) -> None:
    payload = _payload()
    payload["p24_baseline"] = {
        "authority": "metadata-only-forgery",
        "uses_actual_risk_signal_from_window": True,
        "uses_actual_risk_forecast_from_sentinel": True,
        "parity_rows": [{"source_window_id": "pre-db-pool-wait-rising", "route": "preventive_review", "eta_minutes": 0, "confidence": 1.0}],
    }
    path = _write_payload(tmp_path, payload)

    report = _api().run_p105_benchmark(path)
    baseline = report["held_out_calibration"]["p24_baseline"]
    window = next(item for item in load_proactive_fixtures(P24_WINDOWS) if item.id == "pre-db-pool-wait-rising")
    signal = RiskSignal.from_window(window)
    forecast = ProactiveRiskSentinel()._forecast(signal).to_dict()

    assert baseline["forecast_path"] == "app.services.proactive_risk_sentinel.ProactiveRiskSentinel._forecast"
    assert baseline["uses_actual_risk_forecast_from_sentinel"] is True
    assert baseline["metadata_source"] == "computed_not_payload_metadata"
    parity_row = next(item for item in baseline["parity_rows"] if item["source_window_id"] == window.id)
    assert parity_row["risk_type"] == forecast["risk_type"]
    assert parity_row["route"] == forecast["route"]
    assert parity_row["eta_minutes"] == forecast["eta_minutes"]
    assert parity_row["confidence"] == forecast["confidence"]
