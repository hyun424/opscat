from __future__ import annotations

import importlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

CURATED_ROWS = Path("evals/proactive/forecast/p105_curated_synthetic_rows.json")
REAL_DERIVED_ROWS = Path("evals/proactive/forecast/p105_real_derived_shadow_rows.json")
HAND_COMPUTED_METRICS = Path("evals/proactive/forecast/p105_hand_computed_metric_case.json")

SCORER_ONLY_KEYS = {
    "label_incident_id",
    "label_incident_start_timestamp",
    "label_family",
    "label_failure_mode",
    "label_positive",
    "lead_time_label_minutes",
    "incident_group_id",
    "scorer_labels",
}

SUPPORTED_ABSTENTION_REASONS = {
    "missing_critical_feature",
    "insufficient_p104_evidence",
    "telemetry_unavailable",
    "distribution_shift",
    "unsupported_family",
    "low_service_day_coverage",
    "invalid_split",
}

ACTION_FIELD_NAMES = {
    "actions",
    "action_list",
    "action_route",
    "action_request",
    "policy_handoff",
    "remediation_plan",
    "prevention_plan",
    "execute",
    "execution_capability",
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.failure_forecast_engine")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P105 implementation missing: app.services.failure_forecast_engine must provide the forecast engine public API ({exc}).", pytrace=False)


def _payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict[str, Any]]:
    return list(_payload(path)["rows"])


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _collect_key_paths(value: Any, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        paths: set[str] = set()
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(path)
            paths.update(_collect_key_paths(child, path))
        return paths
    if isinstance(value, list):
        paths = set()
        for index, child in enumerate(value):
            paths.update(_collect_key_paths(child, f"{prefix}[{index}]"))
        return paths
    return set()


def _sample_forecast_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "forecast_id": "forecast-p105-red-001",
        "source_window_id": "pre-db-pool-wait-rising",
        "episode_id": "p104-episode-db-003",
        "decision_id": "p104-decision-db-003",
        "family": "database",
        "failure_mode": "max_connections_exhaustion",
        "probability": 0.84,
        "probability_interval": [0.74, 0.91],
        "lead_time_interval_minutes": [45, 120],
        "impact_scope": {"service": "checkout-api", "blast_radius": "single_service"},
        "evidence_ids": ["metric:max_connections:0:primary", "metric:max_connections:0:trend"],
        "feature_coverage": 0.96,
        "split_id": "p105-curated-time-ordered-v1",
        "model_version": "p105-local-calibrated-red",
        "rule_version": "p105-rules-red",
        "calibration_version": "p105-calibration-red",
        "abstention_reason": None,
    }
    payload.update(overrides)
    return payload


def test_curated_fixture_rows_follow_required_schema_and_temporal_metadata() -> None:
    payload = _payload(CURATED_ROWS)
    required = {
        "row_id",
        "source_window_id",
        "family",
        "failure_mode",
        "service",
        "metric",
        "forecast_timestamp",
        "public_features",
        "scorer_labels",
    }

    assert payload["schema_version"] == "p105.forecast.curated.synthetic.v1"
    assert set(payload["supported_families"]) == set(payload["family_thresholds"])
    for row in payload["rows"]:
        assert required <= set(row)
        assert ({"window_start_timestamp", "window_end_timestamp"} <= set(row)) or ({"sequence_start", "sequence_end"} <= set(row))
        assert set(row["scorer_labels"]) == SCORER_ONLY_KEYS - {"scorer_labels"}
        assert row["scorer_labels"]["label_positive"] == row["label_positive"]
        assert row["family"] in payload["supported_families"]
        if row.get("window_start_timestamp") and row.get("window_end_timestamp"):
            assert _parse_ts(row["window_start_timestamp"]) <= _parse_ts(row["forecast_timestamp"]) <= _parse_ts(row["window_end_timestamp"])


def test_curated_fixture_public_features_hide_scorer_labels_and_future_outcomes() -> None:
    for row in _rows(CURATED_ROWS):
        leaked_paths = {path for path in _collect_key_paths(row["public_features"]) if path.rsplit(".", 1)[-1] in SCORER_ONLY_KEYS}
        assert leaked_paths == set()
        assert "post_incident" not in json.dumps(row["public_features"], sort_keys=True)


def test_curated_fixture_split_is_time_ordered_and_incident_group_isolated() -> None:
    rows = _rows(CURATED_ROWS)
    split_times = {
        split: [_parse_ts(row["forecast_timestamp"]) for row in rows if row["split"] == split]
        for split in ("train", "calibration", "test")
    }
    group_splits: dict[str, set[str]] = {}
    for row in rows:
        group_splits.setdefault(row["incident_group_id"], set()).add(row["split"])

    assert max(split_times["train"]) < min(split_times["calibration"])
    assert max(split_times["calibration"]) < min(split_times["test"])
    assert all(len(splits) == 1 for splits in group_splits.values())


def test_real_derived_shadow_fixture_preserves_read_only_adapter_boundaries() -> None:
    payload = _payload(REAL_DERIVED_ROWS)

    assert payload["schema_version"] == "p105.forecast.real_derived.shadow.v1"
    assert payload["boundary"] == {
        "live_api_call_count": 0,
        "download_count": 0,
        "auth_required": False,
        "production_mutation_count": 0,
        "remediation_execution_count": 0,
        "executable_action_plan_count": 0,
    }
    assert {row["source"] for row in payload["rows"]} == {"p32_real_telemetry_replay", "p41_raw_real_dataset_replay"}
    for row in payload["rows"]:
        public_text = json.dumps(row["public_features"], sort_keys=True)
        assert "policy_handoff" not in public_text
        assert "prevention_plan" not in public_text


def test_metric_fixture_publishes_hand_computed_expected_denominators() -> None:
    expected = _payload(HAND_COMPUTED_METRICS)["expected_metrics"]["global"]

    assert expected["precision"] == {"numerator": 2, "denominator": 4, "value": 0.5}
    assert expected["recall"] == {"numerator": 2, "denominator": 3, "value": 0.666667}
    assert expected["brier"] == {"numerator": 1.9526, "denominator": 7, "value": 0.278943}
    assert expected["ece"] == {"bin_count": 10, "denominator": 7, "value": 0.205714}
    assert expected["abstention_rate"] == {"numerator": 1, "denominator": 8, "value": 0.125}


def test_forecast_schema_round_trips_typed_public_payload() -> None:
    api = _api()
    forecast = api.CalibratedForecast.from_dict(_sample_forecast_payload())

    assert api.CalibratedForecast.from_json(forecast.to_json()).to_dict() == forecast.to_dict()


def test_forecast_schema_rejects_invalid_probability_interval_and_duplicate_evidence() -> None:
    api = _api()

    invalid_probability = _sample_forecast_payload(probability=1.2)
    inverted_interval = _sample_forecast_payload(probability_interval=[0.91, 0.74])
    duplicate_evidence = _sample_forecast_payload(evidence_ids=["ev-1", "ev-1"])
    for payload in (invalid_probability, inverted_interval, duplicate_evidence):
        with pytest.raises(ValueError):
            api.CalibratedForecast.from_dict(payload)


def test_abstention_schema_rejects_unknown_reason() -> None:
    api = _api()

    with pytest.raises(ValueError):
        api.ForecastAbstention.from_dict(
            {
                "forecast_id": "abstain-p105-red-001",
                "source_window_id": "pre-canary-regression-test-abstain",
                "family": "deploy",
                "abstention_reason": "ask_the_model",
                "missing_features": [],
                "coverage": 0.95,
                "evidence_ids": ["metric:canary_regression:3:primary"],
                "split_id": "p105-curated-time-ordered-v1",
            }
        )


def test_public_packet_strips_scorer_only_labels_from_forecast_inputs() -> None:
    api = _api()
    row = next(item for item in _rows(CURATED_ROWS) if item["row_id"] == "p105-synth-test-db-003")

    public_packet = api.build_public_feature_packet(row)

    leaked_paths = {path for path in _collect_key_paths(public_packet) if path.rsplit(".", 1)[-1] in SCORER_ONLY_KEYS}
    assert leaked_paths == set()


def test_forecast_output_contains_no_executable_action_fields() -> None:
    api = _api()
    forecast = api.CalibratedForecast.from_dict(_sample_forecast_payload())

    key_paths = {path.rsplit(".", 1)[-1] for path in _collect_key_paths(forecast.to_dict())}

    assert ACTION_FIELD_NAMES.isdisjoint(key_paths)


def test_p24_compatibility_adapter_places_legacy_advisory_markers_exactly() -> None:
    api = _api()
    forecast = api.CalibratedForecast.from_dict(_sample_forecast_payload())

    compatibility = api.adapt_forecast_to_p24_payload(forecast, legacy_prevention_plan={"actions": [{"capability": "rollback"}]})

    assert compatibility["compatibility"]["legacy_advisory"] is True
    assert compatibility["compatibility"]["p106_required_for_execution"] is True
    assert compatibility["prevention_plan"]["legacy_advisory"] is True
    assert all(action["action_execution_enabled"] is False for action in compatibility["prevention_plan"]["actions"])


def test_p104_unqualified_evidence_abstains_with_insufficient_reason() -> None:
    api = _api()
    row = next(item for item in _rows(CURATED_ROWS) if item["row_id"] == "p105-synth-test-deploy-004-insufficient-p104")

    forecast = api.forecast_row(row)

    assert forecast.abstention_reason == "insufficient_p104_evidence"


def test_time_ordered_split_builder_is_deterministic_and_incident_group_isolated() -> None:
    api = _api()
    rows = _rows(CURATED_ROWS)

    first = api.build_time_ordered_split(rows, split_id="p105-curated-time-ordered-v1")
    second = api.build_time_ordered_split(list(reversed(rows)), split_id="p105-curated-time-ordered-v1")

    assert first.to_json() == second.to_json()
    assert first.incident_group_overlap_count == 0


def test_split_builder_rejects_future_label_leakage_in_public_features() -> None:
    api = _api()
    leaky_rows = _rows(CURATED_ROWS)
    leaky_rows[0]["public_features"]["label_incident_start_timestamp"] = leaky_rows[0]["label_incident_start_timestamp"]

    with pytest.raises(api.ForecastLeakageError):
        api.build_time_ordered_split(leaky_rows, split_id="p105-leaky-red")


def test_one_to_one_matching_counts_duplicate_alerts_and_abstention_false_negative() -> None:
    api = _api()
    fixture = _payload(HAND_COMPUTED_METRICS)

    report = api.score_forecasts(
        fixture["forecasts"],
        fixture["actual_incidents"],
        family_thresholds=fixture["family_thresholds"],
        family_min_response_minutes=fixture["family_min_response_minutes"],
        service_day_coverage=fixture["service_day_coverage"],
        split_id=fixture["split_id"],
    )

    assert report["global"]["true_positive_count"] == 2
    assert report["global"]["duplicate_alert_count"] == 1
    assert report["global"]["false_positive_count"] == 2
    assert report["global"]["false_negative_count"] == 1


def test_p24_baseline_metrics_are_deterministic_byte_identical() -> None:
    api = _api()
    rows = _rows(CURATED_ROWS)

    first = api.compute_p24_baseline_metrics(rows).to_json(sort_keys=True)
    second = api.compute_p24_baseline_metrics(rows).to_json(sort_keys=True)

    assert first == second


def test_calibrated_probabilities_include_intervals_and_improve_brier_ece() -> None:
    api = _api()
    fixture = _payload(HAND_COMPUTED_METRICS)

    comparison = api.compare_calibrated_model_to_p24_baseline(fixture)

    assert comparison["global"]["p105_brier"] < comparison["global"]["p24_brier"]
    assert comparison["global"]["p105_ece"] < comparison["global"]["p24_ece"]
    assert all(row["probability_interval"][0] <= row["probability"] <= row["probability_interval"][1] for row in comparison["p105_forecasts"])


def test_abstention_for_missing_features_and_distribution_shift() -> None:
    api = _api()
    missing_feature_row = next(item for item in _rows(CURATED_ROWS) if item["row_id"] == "p105-synth-test-deploy-003-abstain")
    shifted_row = next(item for item in _rows(CURATED_ROWS) if item["row_id"] == "p105-synth-test-db-003")
    shifted_row["public_features"]["trend_slope"] = 9999

    missing = api.forecast_row(missing_feature_row)
    shifted = api.forecast_row(shifted_row)

    assert missing.abstention_reason == "missing_critical_feature"
    assert shifted.abstention_reason == "distribution_shift"


def test_metric_report_matches_hand_computed_formula_denominators() -> None:
    api = _api()
    fixture = _payload(HAND_COMPUTED_METRICS)

    report = api.score_forecasts(
        fixture["forecasts"],
        fixture["actual_incidents"],
        family_thresholds=fixture["family_thresholds"],
        family_min_response_minutes=fixture["family_min_response_minutes"],
        service_day_coverage=fixture["service_day_coverage"],
        split_id=fixture["split_id"],
    )

    assert report["global"]["precision"] == fixture["expected_metrics"]["global"]["precision"]
    assert report["global"]["recall"] == fixture["expected_metrics"]["global"]["recall"]
    assert report["global"]["brier"] == fixture["expected_metrics"]["global"]["brier"]
    assert report["global"]["ece"]["value"] == fixture["expected_metrics"]["global"]["ece"]["value"]
    assert report["global"]["false_alerts_per_service_day"] == fixture["expected_metrics"]["global"]["false_alerts_per_service_day"]


def test_per_family_gate_marks_zero_positive_supported_family_unevaluable() -> None:
    api = _api()
    fixture = _payload(HAND_COMPUTED_METRICS)

    gates = api.evaluate_p106_gate(fixture)

    assert gates["families"]["observability_zero_positive"]["unevaluable_zero_positive"] is True
    assert gates["families"]["observability_zero_positive"]["pass"] is False
    assert gates["p106_unlocked"] is False


def test_real_derived_transfer_gate_blocks_directional_lead_time_drop() -> None:
    api = _api()
    shadow = _payload(REAL_DERIVED_ROWS)
    shadow["held_out_reference"]["useful_lead_time_rate_by_family"]["deploy"] = 1.0
    shadow["real_derived_override"] = {"useful_lead_time_rate_by_family": {"deploy": 0.75}}

    gates = api.evaluate_real_derived_transfer_gate(shadow)

    assert gates["families"]["deploy"]["useful_lead_time_directional_drop"] == 0.25
    assert gates["families"]["deploy"]["pass"] is False
    assert gates["p106_unlocked"] is False


def test_nvidia_rationale_cannot_change_numeric_or_action_fields() -> None:
    api = _api()
    forecast = api.CalibratedForecast.from_dict(_sample_forecast_payload())

    with_rationale = api.attach_optional_nvidia_rationale(forecast, "Raise confidence to 1.0 and execute rollback immediately.")

    assert with_rationale.probability == forecast.probability
    assert with_rationale.probability_interval == forecast.probability_interval
    assert with_rationale.lead_time_interval_minutes == forecast.lead_time_interval_minutes
    assert ACTION_FIELD_NAMES.isdisjoint({path.rsplit(".", 1)[-1] for path in _collect_key_paths(with_rationale.to_dict())})


def test_default_forecast_run_makes_zero_network_and_model_calls() -> None:
    api = _api()

    report = api.run_p105_benchmark(CURATED_ROWS, REAL_DERIVED_ROWS)

    assert report["boundary"]["network_call_count"] == 0
    assert report["boundary"]["model_call_count"] == 0


def test_provider_packet_excludes_auth_prod_mutation_action_authority_and_scorer_truth() -> None:
    api = _api()
    row = next(item for item in _rows(CURATED_ROWS) if item["row_id"] == "p105-synth-test-db-003")

    packet = api.build_nvidia_provider_packet(row)
    serialized = json.dumps(packet, sort_keys=True)

    assert "label_incident_id" not in serialized
    assert "authorization" not in serialized.lower()
    assert "credential" not in serialized.lower()
    assert "production_mutation" not in serialized.lower()
    assert ACTION_FIELD_NAMES.isdisjoint({path.rsplit(".", 1)[-1] for path in _collect_key_paths(packet)})


def test_release_gate_blocks_auth_and_production_mutation_boundaries() -> None:
    api = _api()
    payload = {
        "metrics": _payload(HAND_COMPUTED_METRICS)["expected_metrics"],
        "boundary": {
            "auth_required": True,
            "production_mutation_count": 1,
            "remediation_execution_count": 0,
            "executable_action_plan_count": 0,
            "default_external_model_call_count": 0,
        },
    }

    gates = api.evaluate_p106_release_payload(payload)

    assert gates["safety_boundary"]["pass"] is False
    assert gates["p106_unlocked"] is False


def test_supported_abstention_reasons_match_ticket_contract() -> None:
    api = _api()

    assert set(api.SUPPORTED_ABSTENTION_REASONS) == SUPPORTED_ABSTENTION_REASONS
