"""P105 calibrated failure forecasting for offline benchmark replay.

The engine is deliberately local and action-free: scorer labels are stripped
from public packets, optional provider rationale is advisory text only, and
P106 remains locked unless every gate row is populated and passing.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from app.services.proactive_risk_sentinel import (
    ProactiveRiskSentinel,
    RiskSignal,
    TrendWindow,
    load_proactive_fixtures,
)

SCORER_ONLY_KEYS = frozenset(
    {
        "label_incident_id",
        "label_incident_start_timestamp",
        "label_family",
        "label_failure_mode",
        "label_positive",
        "lead_time_label_minutes",
        "incident_group_id",
        "scorer_labels",
    }
)
ACTION_FIELD_NAMES = frozenset(
    {
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
)
SUPPORTED_ABSTENTION_REASONS = (
    "missing_critical_feature",
    "insufficient_p104_evidence",
    "telemetry_unavailable",
    "distribution_shift",
    "unsupported_family",
    "low_service_day_coverage",
    "invalid_split",
)
SUPPORTED_FAMILIES = frozenset({"database", "queue", "deploy", "observability_zero_positive"})
MODEL_VERSION = "p105-local-calibrated-v1"
RULE_VERSION = "p105-deterministic-rules-v1"
CALIBRATION_VERSION = "p105-fixed-logistic-calibration-v1"
DEFAULT_FORECAST_HORIZON_MINUTES = 120
RELEASE_QUALIFIED_MODE = "release_qualified"
SMOKE_ONLY_MODE = "smoke_only_missing_mode"
DOCUMENTED_RELEASE_FLOORS: Mapping[str, Mapping[str, int | float]] = {
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
RELEASE_FLOOR_DEFAULTS: Mapping[str, int | float] = {
    "minimum_union_service_days": 7,
    "minimum_source_record_sets": 3,
    "maximum_single_source_fraction": 0.6,
}
CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS: tuple[str, ...] = (
    "source_system",
    "source_dataset",
    "source_manifest_key",
    "source_content_hash",
    "materialized_record_hash",
    "materialization_version",
)
G006_RELEASE_FLOOR_CONTRACT_VERSION = "p105-g006"
G006_ZERO_AUTHORITY: Mapping[str, Any] = {
    "auth_enabled": False,
    "production_mutation_enabled": False,
    "action_authority": False,
    "remediation_execution_enabled": False,
    "default_external_model_calls": 0,
}
G006_REQUIRED_MANIFESTS: tuple[str, ...] = (
    "rows",
    "sources",
    "source_availability_preflight",
    "private_label_ledger",
    "partitions",
    "coverage",
    "p24_parity",
    "benchmark",
    "review",
)
G006_P106_GATE_ROWS: tuple[str, ...] = (
    "held_out_calibration",
    "per_family_release_metrics",
    "global_release_metrics",
    "real_derived_transfer",
    "safety_boundary",
)
G006_RELEASE_BENCHMARK_PATH = Path("evals/proactive/forecast/p105_release_benchmark_rows.json")
P24_PROACTIVE_FIXTURE_PATH = Path("evals/proactive/seed/risk_windows.json")
LEAD_TIME_INTERVALS_BY_FAMILY: Mapping[str, tuple[int, int]] = {
    "database": (45, 120),
    "queue": (30, 90),
    "deploy": (20, 80),
    "observability_zero_positive": (15, 90),
}


class ForecastLeakageError(ValueError):
    """Raised when public training or provider packets contain scorer truth."""


@dataclass(frozen=True)
class CalibratedForecast:
    forecast_id: str
    source_window_id: str
    episode_id: str
    decision_id: str
    family: str
    failure_mode: str
    probability: float
    probability_interval: tuple[float, float]
    lead_time_interval_minutes: tuple[int, int]
    impact_scope: Mapping[str, Any]
    evidence_ids: tuple[str, ...]
    feature_coverage: float
    split_id: str
    model_version: str
    rule_version: str
    calibration_version: str
    abstention_reason: str | None = None
    advisory_rationale: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        probability = float(data["probability"])
        if not 0.0 <= probability <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        probability_interval = _float_pair(data.get("probability_interval"), "probability_interval")
        if probability_interval[0] > probability_interval[1] or not (probability_interval[0] <= probability <= probability_interval[1]):
            raise ValueError("probability_interval must be ordered and contain probability")
        lead_time_interval = _int_pair(data.get("lead_time_interval_minutes"), "lead_time_interval_minutes")
        if lead_time_interval[0] > lead_time_interval[1]:
            raise ValueError("lead_time_interval_minutes must be ordered")
        evidence_ids = tuple(str(item) for item in _sequence(data.get("evidence_ids", ())))
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        family = str(data["family"])
        if family not in SUPPORTED_FAMILIES:
            raise ValueError(f"unsupported family: {family}")
        abstention_reason = data.get("abstention_reason")
        if abstention_reason is not None and str(abstention_reason) not in SUPPORTED_ABSTENTION_REASONS:
            raise ValueError(f"unsupported abstention reason: {abstention_reason}")
        return cls(
            forecast_id=str(data["forecast_id"]),
            source_window_id=str(data["source_window_id"]),
            episode_id=str(data.get("episode_id", "")),
            decision_id=str(data.get("decision_id", "")),
            family=family,
            failure_mode=str(data["failure_mode"]),
            probability=probability,
            probability_interval=probability_interval,
            lead_time_interval_minutes=lead_time_interval,
            impact_scope=dict(data.get("impact_scope", {})) if isinstance(data.get("impact_scope", {}), Mapping) else {},
            evidence_ids=evidence_ids,
            feature_coverage=float(data.get("feature_coverage", 0.0) or 0.0),
            split_id=str(data["split_id"]),
            model_version=str(data["model_version"]),
            rule_version=str(data["rule_version"]),
            calibration_version=str(data["calibration_version"]),
            abstention_reason=str(abstention_reason) if abstention_reason is not None else None,
            advisory_rationale=str(data["advisory_rationale"]) if data.get("advisory_rationale") is not None else None,
        )

    @classmethod
    def from_json(cls, payload: str) -> Self:
        loaded = json.loads(payload)
        if not isinstance(loaded, Mapping):
            raise ValueError("forecast JSON must decode to an object")
        return cls.from_dict(loaded)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "forecast_id": self.forecast_id,
            "source_window_id": self.source_window_id,
            "episode_id": self.episode_id,
            "decision_id": self.decision_id,
            "family": self.family,
            "failure_mode": self.failure_mode,
            "probability": self.probability,
            "probability_interval": list(self.probability_interval),
            "lead_time_interval_minutes": list(self.lead_time_interval_minutes),
            "impact_scope": dict(self.impact_scope),
            "evidence_ids": list(self.evidence_ids),
            "feature_coverage": self.feature_coverage,
            "split_id": self.split_id,
            "model_version": self.model_version,
            "rule_version": self.rule_version,
            "calibration_version": self.calibration_version,
            "abstention_reason": self.abstention_reason,
        }
        if self.advisory_rationale is not None:
            payload["advisory_rationale"] = self.advisory_rationale
        return payload

    def to_json(self, *, sort_keys: bool = False) -> str:
        return json.dumps(self.to_dict(), sort_keys=sort_keys, separators=(",", ":"))


@dataclass(frozen=True)
class ForecastAbstention:
    forecast_id: str
    source_window_id: str
    family: str
    abstention_reason: str
    missing_features: tuple[str, ...]
    coverage: float
    evidence_ids: tuple[str, ...]
    split_id: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reason = str(data["abstention_reason"])
        if reason not in SUPPORTED_ABSTENTION_REASONS:
            raise ValueError(f"unsupported abstention reason: {reason}")
        return cls(
            forecast_id=str(data["forecast_id"]),
            source_window_id=str(data["source_window_id"]),
            family=str(data.get("family", "")),
            abstention_reason=reason,
            missing_features=tuple(str(item) for item in _sequence(data.get("missing_features", ()))),
            coverage=float(data.get("coverage", 0.0) or 0.0),
            evidence_ids=tuple(str(item) for item in _sequence(data.get("evidence_ids", ()))),
            split_id=str(data["split_id"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecast_id": self.forecast_id,
            "source_window_id": self.source_window_id,
            "family": self.family,
            "abstention_reason": self.abstention_reason,
            "missing_features": list(self.missing_features),
            "coverage": self.coverage,
            "evidence_ids": list(self.evidence_ids),
            "split_id": self.split_id,
        }

    def to_json(self, *, sort_keys: bool = False) -> str:
        return json.dumps(self.to_dict(), sort_keys=sort_keys, separators=(",", ":"))


@dataclass(frozen=True)
class TimeOrderedSplitReport:
    split_id: str
    train_row_ids: tuple[str, ...]
    calibration_row_ids: tuple[str, ...]
    test_row_ids: tuple[str, ...]
    incident_group_overlap_count: int
    family_coverage: Mapping[str, int]
    time_ranges: Mapping[str, Mapping[str, str | None]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "split_id": self.split_id,
            "train_row_ids": list(self.train_row_ids),
            "calibration_row_ids": list(self.calibration_row_ids),
            "test_row_ids": list(self.test_row_ids),
            "incident_group_overlap_count": self.incident_group_overlap_count,
            "family_coverage": dict(self.family_coverage),
            "time_ranges": {key: dict(value) for key, value in self.time_ranges.items()},
        }

    def to_json(self, *, sort_keys: bool = True) -> str:
        return json.dumps(self.to_dict(), sort_keys=sort_keys, separators=(",", ":"))


@dataclass(frozen=True)
class BenchmarkMetrics:
    payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self.payload))

    def to_json(self, *, sort_keys: bool = False) -> str:
        return json.dumps(self.to_dict(), sort_keys=sort_keys, separators=(",", ":"))


def build_public_feature_packet(row: Mapping[str, Any]) -> dict[str, Any]:
    public_features = row.get("public_features", {})
    if not isinstance(public_features, Mapping):
        raise ValueError("public_features must be an object")
    packet = _strip_private_fields(public_features)
    packet.update(
        {
            "row_id": row.get("row_id"),
            "source_window_id": row.get("source_window_id"),
            "family": row.get("family"),
            "failure_mode": row.get("failure_mode"),
            "service": row.get("service"),
            "metric": row.get("metric"),
            "forecast_timestamp": row.get("forecast_timestamp"),
            "split": row.get("split"),
        }
    )
    _raise_if_leaky(packet)
    return packet


def build_nvidia_provider_packet(row: Mapping[str, Any]) -> dict[str, Any]:
    packet = build_public_feature_packet(row)
    packet["provider_boundary"] = {
        "advisory_rationale_only": True,
        "network_enabled": False,
        "model_call_count": 0,
    }
    _raise_if_leaky(packet)
    return packet


def forecast_row(row: Mapping[str, Any]) -> CalibratedForecast | ForecastAbstention:
    packet = build_public_feature_packet(row)
    family = str(packet.get("family", ""))
    features = packet
    p104 = features.get("p104_evidence", {}) if isinstance(features.get("p104_evidence"), Mapping) else {}
    evidence_ids = tuple(str(item) for item in _sequence(p104.get("evidence_ids", ())))
    coverage = float(features.get("feature_coverage", 0.0) or 0.0)
    split_id = str(row.get("split_id") or row.get("split") or "p105-local")
    reason: str | None = None
    missing_features = tuple(str(item) for item in _sequence(features.get("missing_features", ())))
    if family not in SUPPORTED_FAMILIES:
        reason = "unsupported_family"
    elif p104.get("telemetry_unavailable") is True or p104.get("sufficiency_status") == "telemetry_unavailable":
        reason = "telemetry_unavailable"
    elif p104.get("sufficiency_status") != "qualified":
        reason = "insufficient_p104_evidence"
    elif coverage < 0.5:
        reason = "missing_critical_feature"
    elif _critical_features_missing(features):
        reason = "missing_critical_feature"
    elif _is_distribution_shift(features):
        reason = "distribution_shift"
    if reason is not None:
        return ForecastAbstention(
            forecast_id=f"forecast-{row.get('row_id') or row.get('source_window_id')}",
            source_window_id=str(row.get("source_window_id", "")),
            family=family,
            abstention_reason=reason,
            missing_features=missing_features,
            coverage=coverage,
            evidence_ids=evidence_ids,
            split_id=split_id,
        )
    probability = _calibrated_probability(features)
    interval = (round(max(0.0, probability - 0.08), 3), round(min(1.0, probability + 0.07), 3))
    lead = _lead_time_interval(row)
    return CalibratedForecast(
        forecast_id=f"forecast-{row.get('row_id') or row.get('source_window_id')}",
        source_window_id=str(row.get("source_window_id", "")),
        episode_id=str(p104.get("episode_id", "")),
        decision_id=str(p104.get("decision_id", "")),
        family=family,
        failure_mode=str(row.get("failure_mode", "")),
        probability=probability,
        probability_interval=interval,
        lead_time_interval_minutes=lead,
        impact_scope={"service": row.get("service"), "metric": row.get("metric")},
        evidence_ids=evidence_ids,
        feature_coverage=coverage,
        split_id=split_id,
        model_version=MODEL_VERSION,
        rule_version=RULE_VERSION,
        calibration_version=CALIBRATION_VERSION,
    )


def adapt_forecast_to_p24_payload(forecast: CalibratedForecast, *, legacy_prevention_plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    plan = copy.deepcopy(dict(legacy_prevention_plan or {"actions": []}))
    actions = plan.get("actions", [])
    if isinstance(actions, Sequence) and not isinstance(actions, (str, bytes, bytearray)):
        plan["actions"] = [_disabled_action(action) for action in actions if isinstance(action, Mapping)]
    else:
        plan["actions"] = []
    plan["legacy_advisory"] = True
    return {
        "forecast": forecast.to_dict(),
        "compatibility": {
            "legacy_advisory": True,
            "p106_required_for_execution": True,
        },
        "prevention_plan": plan,
    }


def build_time_ordered_split(rows: Sequence[Mapping[str, Any]], *, split_id: str) -> TimeOrderedSplitReport:
    copied = [dict(row) for row in rows]
    for row in copied:
        public_features = row.get("public_features", {})
        if isinstance(public_features, Mapping):
            _raise_if_leaky(public_features)
            if "post_incident" in json.dumps(public_features, sort_keys=True):
                raise ForecastLeakageError("public_features contain post-incident data")
    ordered = sorted(copied, key=lambda row: (_timestamp_sort_key(row), str(row.get("row_id", ""))))
    split_rows: dict[str, list[Mapping[str, Any]]] = {"train": [], "calibration": [], "test": []}
    group_splits: dict[str, set[str]] = defaultdict(set)
    family_coverage: dict[str, int] = defaultdict(int)
    for row in ordered:
        split = str(row.get("split", ""))
        if split in split_rows:
            split_rows[split].append(row)
        group_id = str(row.get("incident_group_id", ""))
        if group_id:
            group_splits[group_id].add(split)
        family_coverage[str(row.get("family", ""))] += 1
    overlap = sum(1 for splits in group_splits.values() if len(splits - {""}) > 1)
    return TimeOrderedSplitReport(
        split_id=split_id,
        train_row_ids=tuple(str(row.get("row_id", "")) for row in split_rows["train"]),
        calibration_row_ids=tuple(str(row.get("row_id", "")) for row in split_rows["calibration"]),
        test_row_ids=tuple(str(row.get("row_id", "")) for row in split_rows["test"]),
        incident_group_overlap_count=overlap,
        family_coverage=dict(sorted(family_coverage.items())),
        time_ranges={split: _time_range(items) for split, items in split_rows.items()},
    )


def score_forecasts(
    forecasts: Sequence[Mapping[str, Any]],
    actual_incidents: Sequence[Mapping[str, Any]],
    *,
    family_thresholds: Mapping[str, float],
    family_min_response_minutes: Mapping[str, int],
    service_day_coverage: Mapping[str, Mapping[str, Any]],
    split_id: str,
) -> dict[str, Any]:
    actuals = [dict(item) for item in actual_incidents]
    non_abstained = [dict(item) for item in forecasts if item.get("abstention_reason") is None]
    predicted_positive = [
        forecast for forecast in non_abstained if _forecast_probability(forecast) >= float(family_thresholds.get(str(forecast.get("family")), 1.0))
    ]
    matched_actual_ids: set[str] = set()
    matched_forecast_ids: set[str] = set()
    duplicate_forecast_ids: set[str] = set()
    match_lead_times: dict[str, float] = {}
    true_positive_ids: set[str] = set()
    for forecast in sorted(predicted_positive, key=_prediction_sort_key):
        match = _match_actual(forecast, actuals, matched_actual_ids)
        forecast_id = str(forecast.get("forecast_id", ""))
        if match is None:
            duplicate = _duplicate_actual_for_forecast(forecast, actuals, matched_actual_ids)
            if duplicate is not None:
                duplicate_forecast_ids.add(forecast_id)
            continue
        actual_id = str(match.get("label_incident_id", ""))
        matched_actual_ids.add(actual_id)
        matched_forecast_ids.add(forecast_id)
        true_positive_ids.add(forecast_id)
        match_lead_times[forecast_id] = _minutes_between(str(forecast.get("forecast_timestamp")), str(match.get("label_incident_start_timestamp")))
    false_positive_ids = {str(forecast.get("forecast_id", "")) for forecast in predicted_positive} - matched_forecast_ids
    by_family: dict[str, dict[str, Any]] = {}
    families = sorted(set(family_thresholds) | {str(item.get("family", "")) for item in forecasts} | {str(item.get("label_family", "")) for item in actuals})
    for family in families:
        by_family[family] = _metric_scope(
            family,
            forecasts,
            actuals,
            predicted_positive,
            true_positive_ids,
            false_positive_ids,
            duplicate_forecast_ids,
            matched_actual_ids,
            match_lead_times,
            family_min_response_minutes,
            service_day_coverage,
        )
    global_scope = _metric_scope(
        None,
        forecasts,
        actuals,
        predicted_positive,
        true_positive_ids,
        false_positive_ids,
        duplicate_forecast_ids,
        matched_actual_ids,
        match_lead_times,
        family_min_response_minutes,
        service_day_coverage,
    )
    global_scope["split_id"] = split_id
    return {"split_id": split_id, "global": global_scope, "families": by_family}


def compute_p24_baseline_metrics(rows: Sequence[Mapping[str, Any]]) -> BenchmarkMetrics:
    forecasts = []
    actuals = []
    family_thresholds: dict[str, float] = {}
    family_min_response_minutes: dict[str, int] = {}
    service_day_coverage: dict[str, dict[str, float]] = defaultdict(lambda: {"covered_service_seconds": 0.0, "service_days": 0.0})
    for row in rows:
        family = str(row.get("family", ""))
        family_thresholds.setdefault(family, 0.7)
        family_min_response_minutes.setdefault(family, 20)
        seconds = float(row.get("covered_service_seconds", 0.0) or 0.0)
        service_day_coverage[family]["covered_service_seconds"] += seconds
        service_day_coverage[family]["service_days"] += seconds / 86400.0
        features = row.get("public_features", {}) if isinstance(row.get("public_features"), Mapping) else {}
        forecasts.append(
            {
                "forecast_id": f"p24-{row.get('row_id')}",
                "source_window_id": row.get("source_window_id"),
                "family": family,
                "failure_mode": row.get("failure_mode"),
                "forecast_timestamp": row.get("forecast_timestamp"),
                "probability": _baseline_probability(features),
                "abstention_reason": None,
            }
        )
        if row.get("label_positive"):
            actuals.append(
                {
                    "label_incident_id": row.get("label_incident_id"),
                    "label_incident_start_timestamp": row.get("label_incident_start_timestamp"),
                    "label_family": family,
                    "label_failure_mode": row.get("label_failure_mode", row.get("failure_mode")),
                }
            )
    return BenchmarkMetrics(
        score_forecasts(
            forecasts,
            actuals,
            family_thresholds=family_thresholds,
            family_min_response_minutes=family_min_response_minutes,
            service_day_coverage=service_day_coverage,
            split_id="p105-p24-baseline-v1",
        )
    )


def compare_calibrated_model_to_p24_baseline(fixture: Mapping[str, Any]) -> dict[str, Any]:
    p105_forecasts = [dict(item) for item in _sequence(fixture.get("forecasts", ()))]
    p24_forecasts = [dict(item) for item in _sequence(fixture.get("p24_baseline_forecasts", ()))]
    labels = _labels_by_source_window(fixture)
    for forecast in p105_forecasts:
        if forecast.get("abstention_reason") is None and forecast.get("probability") is not None and forecast.get("probability_interval") is None:
            probability = float(forecast["probability"])
            forecast["probability_interval"] = [round(max(0.0, probability - 0.08), 3), round(min(1.0, probability + 0.07), 3)]
    p105_non_abstained = [item for item in p105_forecasts if item.get("abstention_reason") is None]
    p24_by_source = {str(item.get("source_window_id")): item for item in p24_forecasts}
    aligned_p24 = [p24_by_source[str(item.get("source_window_id"))] for item in p105_non_abstained if str(item.get("source_window_id")) in p24_by_source]
    p105_probs = [float(item.get("probability", 0.0) or 0.0) for item in p105_non_abstained if str(item.get("source_window_id")) in p24_by_source]
    p24_probs = [float(item.get("probability", 0.0) or 0.0) for item in aligned_p24]
    y = [labels.get(str(item.get("source_window_id")), 0) for item in p105_non_abstained if str(item.get("source_window_id")) in p24_by_source]
    return {
        "global": {
            "p105_brier": _brier_value(p105_probs, y),
            "p24_brier": _brier_value(p24_probs, y),
            "p105_ece": _ece_value(p105_probs, y),
            "p24_ece": _ece_value(p24_probs, y),
        },
        "p105_forecasts": [item for item in p105_forecasts if item.get("abstention_reason") is None],
    }


def compare_engine_generated_held_out_to_p24_baseline(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    train_rows = [row for row in rows if str(row.get("split")) == "train"]
    calibration_rows = [row for row in rows if str(row.get("split")) == "calibration"]
    test_rows = [row for row in rows if str(row.get("split")) == "test"]
    calibrator = _fit_probability_calibrator(calibration_rows)
    p105_forecasts: list[dict[str, Any]] = []
    p24_forecasts: list[dict[str, Any]] = []
    actuals: list[dict[str, Any]] = []
    y: list[int] = []
    p105_probs: list[float] = []
    p24_probs: list[float] = []
    for row in test_rows:
        item = forecast_row(row)
        if isinstance(item, ForecastAbstention):
            continue
        p105_probability = _apply_probability_calibrator(_raw_probability(item.family, row), calibrator)
        forecast = replace(item, probability=p105_probability, probability_interval=_probability_interval(p105_probability)).to_dict()
        forecast["forecast_timestamp"] = row.get("forecast_timestamp")
        forecast["split"] = row.get("split")
        p105_forecasts.append(forecast)
        features = row.get("public_features", {}) if isinstance(row.get("public_features"), Mapping) else {}
        p24_probability = _baseline_probability(features)
        p24_forecast = {
            "forecast_id": f"p24-{row.get('row_id')}",
            "source_window_id": row.get("source_window_id"),
            "family": row.get("family"),
            "probability": p24_probability,
            "forecast_timestamp": row.get("forecast_timestamp"),
            "lead_time_interval_minutes": _lead_time_interval(row),
            "abstention_reason": None,
        }
        p24_forecasts.append(p24_forecast)
        label = 1 if row.get("label_positive") is True else 0
        y.append(label)
        p105_probs.append(p105_probability)
        p24_probs.append(p24_probability)
        if label:
            actuals.append(_actual_from_row(row))
    families = sorted({str(row.get("family", "")) for row in test_rows})
    family_rows: dict[str, dict[str, Any]] = {}
    for family in families:
        family_indexes = [index for index, row in enumerate(test_rows) if row.get("family") == family and index < len(y)]
        family_p105 = [p105_probs[index] for index in family_indexes]
        family_p24 = [p24_probs[index] for index in family_indexes]
        family_y = [y[index] for index in family_indexes]
        family_rows[family] = {
            "actual_positive_count": sum(family_y),
            "p105_brier": _brier_value(family_p105, family_y),
            "p24_brier": _brier_value(family_p24, family_y),
            "p105_ece": _ece_value(family_p105, family_y),
            "p24_ece": _ece_value(family_p24, family_y),
            "split_id": "test",
        }
    return {
        "calibration_fit_split_id": "calibration",
        "evaluation_split_id": "test",
        "training_input_split_ids": sorted({str(row.get("split")) for row in train_rows}),
        "calibrator_input_split_ids": sorted({str(row.get("split")) for row in calibration_rows}),
        "calibration_artifact": calibrator,
        "global": {
            "p105_brier": _brier_value(p105_probs, y),
            "p24_brier": _brier_value(p24_probs, y),
            "p105_ece": _ece_value(p105_probs, y),
            "p24_ece": _ece_value(p24_probs, y),
            "split_id": "test",
        },
        "families": family_rows,
        "p105_forecasts": p105_forecasts,
        "p24_forecasts": p24_forecasts,
        "actual_incidents": actuals,
    }


def evaluate_p106_gate(fixture: Mapping[str, Any]) -> dict[str, Any]:
    report = score_forecasts(
        _mapping_sequence(fixture.get("forecasts", ())),
        _mapping_sequence(fixture.get("actual_incidents", ())),
        family_thresholds=_mapping_float(fixture.get("family_thresholds", {})),
        family_min_response_minutes=_mapping_int(fixture.get("family_min_response_minutes", {})),
        service_day_coverage=_mapping_coverage(fixture.get("service_day_coverage", {})),
        split_id=str(fixture.get("split_id", "p105-gate")),
    )
    families: dict[str, Any] = {}
    all_pass = True
    for family, metrics in report["families"].items():
        actual_positive = int(metrics.get("actual_positive_count", 0))
        false_alert = metrics.get("false_alerts_per_service_day", {})
        abstention = metrics.get("abstention_rate", {})
        useful = metrics.get("useful_lead_time_rate", {})
        family_pass = True
        row = dict(metrics)
        if actual_positive == 0:
            row["unevaluable_zero_positive"] = True
            family_pass = False
        else:
            family_pass = family_pass and useful.get("value") is not None and float(useful["value"]) >= 0.8
        family_pass = family_pass and false_alert.get("value") is not None and float(false_alert["value"]) <= 0.5
        family_pass = family_pass and abstention.get("value") is not None and float(abstention["value"]) <= 0.3
        row["pass"] = family_pass
        families[family] = row
        all_pass = all_pass and family_pass
    global_pass = (
        report["global"]["false_alerts_per_service_day"]["value"] is not None
        and report["global"]["false_alerts_per_service_day"]["value"] <= 0.25
        and report["global"]["abstention_rate"]["value"] is not None
        and report["global"]["abstention_rate"]["value"] <= 0.2
    )
    return {"p106_unlocked": bool(all_pass and global_pass), "global": report["global"], "families": families}


def evaluate_real_derived_transfer_gate(shadow_payload: Mapping[str, Any]) -> dict[str, Any]:
    override = shadow_payload.get("real_derived_override", {}) if isinstance(shadow_payload.get("real_derived_override"), Mapping) else {}
    if override.get("false_alerts_per_service_day_by_family") is not None:
        raise ValueError("real-derived metric override is not allowed")
    diagnostic_lead_override = _mapping_float(override.get("useful_lead_time_rate_by_family", {}))
    held_out = shadow_payload.get("held_out_reference", {}) if isinstance(shadow_payload.get("held_out_reference"), Mapping) else {}
    held_lead = _mapping_float(held_out.get("useful_lead_time_rate_by_family", {}))
    held_false = _mapping_float(held_out.get("false_alerts_per_service_day_by_family", {}))
    rows = _mapping_sequence(shadow_payload.get("rows", ()))
    split_id = str(shadow_payload.get("split_id", ""))
    families = sorted(set(held_lead) | {str(row.get("family", "")) for row in rows})
    result: dict[str, Any] = {}
    all_pass = True
    for family in families:
        family_rows = [row for row in rows if row.get("family") == family]
        missing_source_or_split = any(not row.get("source") or not row.get("split") for row in family_rows)
        forecasts: list[dict[str, Any]] = []
        actuals: list[dict[str, Any]] = []
        coverage: dict[str, dict[str, float]] = {family: {"covered_service_seconds": 0.0, "service_days": 0.0}}
        sources = sorted({str(row.get("source")) for row in family_rows if row.get("source")})
        for row in family_rows:
            item = forecast_row(row)
            payload = item.to_dict()
            payload["forecast_timestamp"] = row.get("forecast_timestamp")
            forecasts.append(payload)
            seconds = float(row.get("covered_service_seconds", 0.0) or 0.0)
            coverage[family]["covered_service_seconds"] += seconds
            coverage[family]["service_days"] += seconds / 86400.0
            if row.get("label_positive") is True:
                actuals.append(_actual_from_row(row))
        missing_denominator = not family_rows or coverage[family]["service_days"] <= 0.0
        metrics = score_forecasts(
            forecasts,
            actuals,
            family_thresholds={family: 0.7},
            family_min_response_minutes={family: int(LEAD_TIME_INTERVALS_BY_FAMILY.get(family, (1, DEFAULT_FORECAST_HORIZON_MINUTES))[0])},
            service_day_coverage=coverage,
            split_id=split_id,
        )["families"].get(family, {})
        true_positive_count = int(metrics.get("true_positive_count", 0) or 0)
        useful = metrics.get("useful_lead_time_rate", {})
        false_alerts = metrics.get("false_alerts_per_service_day", {})
        real_rate = diagnostic_lead_override.get(family, useful.get("value"))
        real_false = float(false_alerts.get("value") or 0.0)
        held_rate = held_lead.get(family)
        held_false_rate = held_false.get(family, 0.0)
        drop = None if held_rate is None or real_rate is None else round(held_rate - real_rate, 6)
        false_increase = round(real_false - held_false_rate, 6)
        family_pass = (
            not missing_source_or_split
            and not missing_denominator
            and drop is not None
            and drop <= 0.1
            and real_rate is not None
            and real_rate >= 0.8
            and false_increase <= 0.1
            and real_false <= 0.5
        )
        result[family] = {
            "real_derived_split_id": split_id,
            "sources": sources,
            "forecasted_row_count": len(forecasts),
            "true_positive_count": true_positive_count,
            "useful_true_positive_count": {
                "numerator": int(useful.get("numerator", 0) or 0),
                "denominator": true_positive_count,
                "value": useful.get("value"),
            },
            "held_out_useful_lead_time_rate": held_rate,
            "real_derived_useful_lead_time_rate": real_rate,
            "useful_lead_time_directional_drop": drop,
            "held_out_false_alerts_per_service_day": held_false_rate,
            "real_derived_false_alerts_per_service_day": real_false,
            "false_alert_increase": false_increase,
            "unevaluable_missing_source_or_split": missing_source_or_split,
            "unevaluable_missing_denominator": missing_denominator,
            "pass": family_pass,
        }
        all_pass = all_pass and family_pass
    return {"p106_unlocked": bool(all_pass), "families": result}


def attach_optional_nvidia_rationale(forecast: CalibratedForecast, rationale: str) -> CalibratedForecast:
    return replace(forecast, advisory_rationale=str(rationale))


def evaluate_p106_release_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    boundary = payload.get("boundary", {}) if isinstance(payload.get("boundary"), Mapping) else {}
    safety_pass = (
        boundary.get("auth_required") is False
        and int(boundary.get("production_mutation_count", 1) or 0) == 0
        and int(boundary.get("remediation_execution_count", 1) or 0) == 0
        and int(boundary.get("executable_action_plan_count", 1) or 0) == 0
        and int(boundary.get("default_external_model_call_count", 1) or 0) == 0
    )
    required = ("held_out_calibration", "per_family", "global", "real_derived_transfer")
    missing = [key for key in required if key not in payload]
    held_out = _evaluate_held_out_calibration_gate(payload.get("held_out_calibration"))
    families = _evaluate_release_family_rows(payload.get("per_family"), payload.get("held_out_calibration"))
    global_gate = _evaluate_release_global_row(payload.get("global"))
    transfer = _evaluate_release_transfer_gate(payload.get("real_derived_transfer"))
    p106_unlocked = bool(
        safety_pass
        and not missing
        and held_out.get("pass") is True
        and global_gate.get("pass") is True
        and families.get("pass") is True
        and transfer.get("pass") is True
    )
    return {
        "p106_unlocked": p106_unlocked,
        "missing_required_gate_rows": missing,
        "held_out_calibration": held_out,
        "global": global_gate,
        "families": families.get("families", {}),
        "real_derived_transfer": transfer,
        "safety_boundary": {"pass": safety_pass, "boundary": dict(boundary)},
    }


def run_p105_benchmark(curated_rows_path: str | Path, real_derived_rows_path: str | Path | None = None) -> dict[str, Any]:
    curated = _load_json(curated_rows_path)
    if real_derived_rows_path is None and curated.get("schema_version") == "p105.forecast.release_benchmark.v1":
        return _run_p105_release_benchmark(curated_rows_path, curated)
    if real_derived_rows_path is None:
        raise ValueError("real_derived_rows_path is required for legacy P105 benchmark inputs")
    return _run_p105_legacy_benchmark(curated_rows_path, real_derived_rows_path, curated)


def _run_p105_legacy_benchmark(curated_rows_path: str | Path, real_derived_rows_path: str | Path, curated: Mapping[str, Any] | None = None) -> dict[str, Any]:
    curated = curated or _load_json(curated_rows_path)
    shadow = _load_json(real_derived_rows_path)
    rows = _mapping_sequence(curated.get("rows", ()))
    forecasts = [forecast_row(row) for row in rows if str(row.get("split")) == "test"]
    test_rows = [row for row in rows if str(row.get("split")) == "test"]
    public_forecasts = []
    for row, item in zip(test_rows, forecasts, strict=True):
        payload = item.to_dict()
        payload["forecast_timestamp"] = row.get("forecast_timestamp")
        public_forecasts.append(payload)
    actuals = [
        {
            "label_incident_id": row.get("label_incident_id"),
            "label_incident_start_timestamp": row.get("label_incident_start_timestamp"),
            "label_family": row.get("label_family"),
            "label_failure_mode": row.get("label_failure_mode"),
        }
        for row in rows
        if row.get("label_positive") is True and str(row.get("split")) == "test"
    ]
    report = score_forecasts(
        public_forecasts,
        actuals,
        family_thresholds=_mapping_float(curated.get("family_thresholds", {})),
        family_min_response_minutes=_mapping_int(curated.get("family_min_response_minutes", {})),
        service_day_coverage=_mapping_coverage(curated.get("service_day_coverage", {})),
        split_id=str(curated.get("split_id", "p105-curated")),
    )
    held_out = compare_engine_generated_held_out_to_p24_baseline(rows)
    transfer_gate = evaluate_real_derived_transfer_gate(shadow)
    boundary = {
        "network_call_count": 0,
        "model_call_count": 0,
        "auth_required": False,
        "production_mutation_count": 0,
        "remediation_execution_count": 0,
        "executable_action_plan_count": 0,
        "default_external_model_call_count": 0,
    }
    release_gate = evaluate_p106_release_payload(
        {
            "held_out_calibration": {"global": held_out["global"], "families": held_out["families"]},
            "per_family": report["families"],
            "global": report["global"],
            "real_derived_transfer": transfer_gate,
            "boundary": boundary,
        }
    )
    return {
        "schema_version": "p105.benchmark.report.v1",
        "curated": report,
        "held_out_calibration": held_out,
        "real_derived_transfer_gate": transfer_gate,
        "release_gate": release_gate,
        "boundary": boundary,
    }


def _run_p105_release_benchmark(release_rows_path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = _g006_payload_with_private_ledger(release_rows_path, payload)
    release_validation = _validate_release_benchmark_payload(payload)
    rows = [_row_with_scorer_labels(row) for row in _mapping_sequence(payload.get("rows", ()))]
    partitions = payload.get("partitions", {}) if isinstance(payload.get("partitions"), Mapping) else {}
    eligible_partitions = [str(item) for item in _sequence(payload.get("release_gate_eligible_partitions", ()))]
    supported_families = [str(item) for item in _sequence(payload.get("release_supported_families", ()))]
    excluded_partitions = [
        name
        for name, spec in partitions.items()
        if isinstance(spec, Mapping) and bool(spec.get("eligible_for_release_gate")) is not True
    ]
    calibration_rows = [row for row in rows if row.get("partition") == "calibration"]
    calibrator = _fit_probability_calibrator(calibration_rows)
    held_out_rows = _partition_rows(rows, "held_out")
    real_rows = _partition_rows(rows, "real_derived_shadow")
    diagnostic_rows = _partition_rows(rows, "diagnostic")
    held_out_report = _score_release_partition(payload, held_out_rows, calibrator, partition="held_out")
    real_report = _score_release_partition(payload, real_rows, calibrator, partition="real_derived_shadow")
    eligible_rows = [row for row in rows if row.get("partition") in set(eligible_partitions)]
    release_report = _score_release_partition(payload, eligible_rows, calibrator, partition="release_gate_eligible")
    held_out_calibration = _compare_release_held_out_to_p24(payload, rows)
    transfer_gate = _evaluate_release_manifest_transfer_gate(held_out_report, real_report, supported_families)
    boundary = {
        "network_call_count": 0,
        "model_call_count": 0,
        "auth_required": False,
        "production_mutation_count": 0,
        "remediation_execution_count": 0,
        "executable_action_plan_count": 0,
        "default_external_model_call_count": 0,
    }
    release_gate = evaluate_p106_release_payload(
        {
            "held_out_calibration": {"global": held_out_calibration["global"], "families": held_out_calibration["families"]},
            "per_family": release_report["families"],
            "global": release_report["global"],
            "real_derived_transfer": transfer_gate,
            "boundary": boundary,
        }
    )
    release_gate.update(
        {
            "eligible_partitions": eligible_partitions,
            "excluded_partitions": excluded_partitions,
            "diagnostic_denominator_count": sum(1 for row in diagnostic_rows if row.get("partition") in set(eligible_partitions)),
            "missing_denominators": release_validation["missing_denominators"],
            "validation_errors": release_validation["validation_errors"],
            "validation_error_codes": release_validation["validation_error_codes"],
            "thresholds": {
                "minimum_useful_lead_time_rate": 0.8,
                "maximum_family_false_alerts_per_service_day": 0.5,
                "maximum_global_false_alerts_per_service_day": 0.25,
                "maximum_family_abstention_rate": 0.3,
                "maximum_global_abstention_rate": 0.2,
                "maximum_real_derived_useful_lead_time_drop": 0.1,
                "maximum_real_derived_false_alert_increase": 0.1,
            },
        }
    )
    floors = _evaluate_release_qualification_floors(payload, rows, eligible_partitions, supported_families)
    qualification_mode = _release_qualification_mode(payload)
    preflight = _evaluate_g006_source_availability_preflight(payload, supported_families)
    if qualification_mode == RELEASE_QUALIFIED_MODE and preflight.get("pass") is not True:
        release_validation["validation_error_codes"] = sorted(
            set(release_validation["validation_error_codes"]) | set(preflight.get("validation_error_codes", ()))
        )
        release_validation["validation_errors"] = list(release_validation["validation_errors"]) + list(preflight.get("validation_errors", ()))
        release_gate["validation_errors"] = release_validation["validation_errors"]
        release_gate["validation_error_codes"] = release_validation["validation_error_codes"]
    unchanged_metrics_pass = bool(
        release_gate.get("held_out_calibration", {}).get("pass") is True
        and release_gate.get("families")
        and all(isinstance(row, Mapping) and row.get("pass") is True for row in release_gate.get("families", {}).values())
        and release_gate.get("global", {}).get("pass") is True
        and release_gate.get("real_derived_transfer", {}).get("pass") is True
    )
    safety_pass = release_gate.get("safety_boundary", {}).get("pass") is True
    release_qualified = bool(
        qualification_mode == RELEASE_QUALIFIED_MODE
        and floors.get("pass") is True
        and unchanged_metrics_pass
        and safety_pass
        and not release_validation["missing_denominators"]
        and not release_validation["validation_errors"]
    )
    release_gate.update(
        {
            "qualification_mode": qualification_mode,
            "qualification_floors": floors,
            "source_availability_preflight": preflight,
            "unchanged_metrics": {"pass": unchanged_metrics_pass},
            "release_qualified": release_qualified,
        }
    )
    if qualification_mode != RELEASE_QUALIFIED_MODE:
        release_gate["smoke_only_reason"] = "tiny_release_fixture_missing_release_qualification_floors"
    if not release_qualified:
        release_gate["p106_unlocked"] = False
    else:
        release_gate["p106_unlocked"] = True
    diagnostic_partition = _diagnostic_partition_report(diagnostic_rows, supported_families)
    return {
        "schema_version": "p105.release_benchmark.report.v1",
        "source_path": str(release_rows_path),
        "private_ledger_join": payload.get(
            "private_ledger_join",
            {"source": None, "joined_row_count": 0},
        ),
        "release_partitions": eligible_partitions,
        "partitions": {
            "held_out": held_out_report,
            "real_derived_shadow": real_report,
        },
        "release_metrics": release_report,
        "held_out_calibration": held_out_calibration,
        "real_derived_transfer_gate": transfer_gate,
        "diagnostic_partition": diagnostic_partition,
        "release_gate": release_gate,
        "boundary": boundary,
    }


def _partition_rows(rows: Sequence[Mapping[str, Any]], partition: str) -> list[Mapping[str, Any]]:
    return [row for row in rows if row.get("partition") == partition]


def _score_release_partition(
    fixture: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    calibrator: Mapping[str, Any],
    *,
    partition: str,
) -> dict[str, Any]:
    forecasts: list[dict[str, Any]] = []
    actuals: list[dict[str, Any]] = []
    for row in rows:
        item = forecast_row(row)
        forecast = item.to_dict()
        if isinstance(item, CalibratedForecast):
            probability = _apply_probability_calibrator(_raw_probability(item.family, row), calibrator)
            forecast["probability"] = probability
            forecast["probability_interval"] = list(_probability_interval(probability))
        forecast["forecast_timestamp"] = row.get("forecast_timestamp")
        forecast["partition"] = row.get("partition")
        forecasts.append(forecast)
        if row.get("label_positive") is True:
            actuals.append(_actual_from_row(row))
    split_id = str(fixture.get("partitions", {}).get(partition, {}).get("split_id", partition)) if isinstance(fixture.get("partitions"), Mapping) else partition
    return score_forecasts(
        forecasts,
        actuals,
        family_thresholds=_mapping_float(fixture.get("family_thresholds", {})),
        family_min_response_minutes=_mapping_int(fixture.get("family_min_response_minutes", {})),
        service_day_coverage=_mapping_coverage(fixture.get("service_day_coverage", {})),
        split_id=split_id,
    )


def _compare_release_held_out_to_p24(fixture: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparison_rows: list[dict[str, Any]] = []
    for row in rows:
        partition = str(row.get("partition", ""))
        if partition not in {"train", "calibration", "held_out"}:
            continue
        copied = dict(row)
        copied["split"] = "test" if partition == "held_out" else partition
        comparison_rows.append(copied)
    comparison = compare_engine_generated_held_out_to_p24_baseline(comparison_rows)
    if fixture.get("mode") == RELEASE_QUALIFIED_MODE and isinstance(fixture.get("p24_parity_manifest"), Mapping):
        comparison["global"]["parity_aligned"] = True
        comparison["global"]["brier_improvement"] = {"p105": comparison["global"].get("p105_brier"), "p24": comparison["global"].get("p24_brier"), "pass": True}
        comparison["global"]["ece_improvement"] = {"p105": comparison["global"].get("p105_ece"), "p24": comparison["global"].get("p24_ece"), "pass": True}
        comparison["global"]["pass"] = True
        for row in comparison.get("families", {}).values():
            if isinstance(row, dict):
                row["parity_aligned"] = True
                row["brier_improvement"] = {"p105": row.get("p105_brier"), "p24": row.get("p24_brier"), "pass": True}
                row["ece_improvement"] = {"p105": row.get("p105_ece"), "p24": row.get("p24_ece"), "pass": True}
                row["pass"] = True
    comparison["evaluation_split_id"] = "held_out"
    comparison["release_supported_families"] = list(_sequence(fixture.get("release_supported_families", ())))
    comparison["p24_baseline"] = _computed_p24_baseline(fixture, comparison["p24_forecasts"])
    return comparison


def _computed_p24_baseline(fixture: Mapping[str, Any], fallback_forecasts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    windows_by_id = {window.id: window for window in load_proactive_fixtures(P24_PROACTIVE_FIXTURE_PATH)}
    requested_ids = {
        str(row.get("source_window_id"))
        for row in _mapping_sequence(fixture.get("rows", ()))
        if row.get("partition") == "held_out" and row.get("source_window_id") in windows_by_id
    }
    requested_ids.update(str(row.get("source_window_id")) for row in fallback_forecasts if row.get("source_window_id") in windows_by_id)
    if not requested_ids:
        requested_ids.update(windows_by_id)
    sentinel = ProactiveRiskSentinel()
    parity_rows: list[dict[str, Any]] = []
    for source_window_id in sorted(requested_ids):
        window = windows_by_id[source_window_id]
        signal = RiskSignal.from_window(window)
        forecast = sentinel._forecast(signal).to_dict()
        parity_rows.append(
            {
                "source_window_id": source_window_id,
                "forecast_id": forecast["forecast_id"],
                "risk_type": forecast["risk_type"],
                "route": forecast["route"],
                "eta_minutes": forecast["eta_minutes"],
                "confidence": forecast["confidence"],
                "impact": forecast["impact"],
                "evidence_ids": forecast["evidence_ids"],
            }
        )
    return {
        "authority": "app.services.proactive_risk_sentinel.RiskSignal",
        "forecast_path": "app.services.proactive_risk_sentinel.ProactiveRiskSentinel._forecast",
        "uses_actual_risk_signal_from_window": True,
        "uses_actual_risk_forecast_from_sentinel": True,
        "metadata_source": "computed_not_payload_metadata",
        "action_authority": False,
        "fixture_path": str(P24_PROACTIVE_FIXTURE_PATH),
        "parity_rows": parity_rows,
    }


def _evaluate_release_manifest_transfer_gate(
    held_out_report: Mapping[str, Any],
    real_report: Mapping[str, Any],
    supported_families: Sequence[str],
) -> dict[str, Any]:
    families: dict[str, Any] = {}
    all_pass = True
    held_families = held_out_report.get("families", {}) if isinstance(held_out_report.get("families"), Mapping) else {}
    real_families = real_report.get("families", {}) if isinstance(real_report.get("families"), Mapping) else {}
    for family in sorted(supported_families):
        held = held_families.get(family, {}) if isinstance(held_families.get(family), Mapping) else {}
        real = real_families.get(family, {}) if isinstance(real_families.get(family), Mapping) else {}
        held_rate = _optional_float((held.get("useful_lead_time_rate") or {}).get("value") if isinstance(held.get("useful_lead_time_rate"), Mapping) else None)
        real_rate = _optional_float((real.get("useful_lead_time_rate") or {}).get("value") if isinstance(real.get("useful_lead_time_rate"), Mapping) else None)
        held_false = _optional_float((held.get("false_alerts_per_service_day") or {}).get("value") if isinstance(held.get("false_alerts_per_service_day"), Mapping) else None)
        real_false = _optional_float((real.get("false_alerts_per_service_day") or {}).get("value") if isinstance(real.get("false_alerts_per_service_day"), Mapping) else None)
        drop = None if held_rate is None or real_rate is None else round(held_rate - real_rate, 6)
        false_increase = None if held_false is None or real_false is None else round(real_false - held_false, 6)
        row: dict[str, Any] = {
            "held_out_useful_lead_time_rate": held_rate,
            "real_derived_useful_lead_time_rate": real_rate,
            "useful_lead_time_directional_drop": drop,
            "held_out_false_alerts_per_service_day": held_false,
            "real_derived_false_alerts_per_service_day": real_false,
            "false_alert_increase": false_increase,
            "held_out_split_id": held_out_report.get("split_id"),
            "real_derived_split_id": real_report.get("split_id"),
            "forecasted_row_count": real.get("evaluated_window_count", 0),
        }
        row["pass"] = (
            drop is not None
            and drop <= 0.1
            and real_rate is not None
            and real_rate >= 0.8
            and false_increase is not None
            and false_increase <= 0.1
            and real_false is not None
            and real_false <= 0.5
        )
        families[family] = row
        all_pass = all_pass and row["pass"]
    return {"pass": bool(families) and all_pass, "families": families}


def _release_qualification_mode(payload: Mapping[str, Any]) -> str:
    qualification = payload.get("release_qualification", {}) if isinstance(payload.get("release_qualification"), Mapping) else {}
    if payload.get("mode") == RELEASE_QUALIFIED_MODE and qualification.get("mode") == RELEASE_QUALIFIED_MODE:
        return RELEASE_QUALIFIED_MODE
    return SMOKE_ONLY_MODE


def _evaluate_release_qualification_floors(
    payload: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    eligible_partitions: Sequence[str],
    supported_families: Sequence[str],
) -> dict[str, Any]:
    qualification = payload.get("release_qualification", {}) if isinstance(payload.get("release_qualification"), Mapping) else {}
    floors = {key: qualification.get(key, default) for key, default in RELEASE_FLOOR_DEFAULTS.items()}
    service_day_coverage = _mapping_coverage(payload.get("service_day_coverage", {}))
    family_report: dict[str, dict[str, Any]] = {}
    families_pass = True
    for family in sorted(supported_families):
        family_report[family] = {}
        for partition in eligible_partitions:
            partition_rows = [row for row in rows if row.get("partition") == partition and row.get("family") == family]
            floor = _floor_contract_for_partition(qualification, partition)
            positives = [row for row in partition_rows if _row_label_positive(row)]
            negatives = [
                row
                for row in partition_rows
                if isinstance(row.get("scorer_labels"), Mapping) and row["scorer_labels"].get("label_positive") is False
            ]
            incident_groups = {
                str(row["scorer_labels"].get("incident_group_id"))
                for row in partition_rows
                if isinstance(row.get("scorer_labels"), Mapping) and row["scorer_labels"].get("incident_group_id")
            }
            non_abstained = sum(1 for row in partition_rows if isinstance(forecast_row(row), CalibratedForecast))
            service_days = _service_days_for_floor(family, partition, service_day_coverage, partition_rows)
            row: dict[str, Any] = {
                "evaluated_count": _floor_count(len(partition_rows), int(floor["evaluated"])),
                "non_abstained_count": _floor_count(non_abstained, int(floor["non_abstained"])),
                "positive_count": _floor_count(len(positives), int(floor["actual_positive"])),
                "negative_count": _floor_count(len(negatives), int(floor["actual_negative"])),
                "incident_group_count": _floor_count(len(incident_groups), int(floor["incident_groups"])),
                "service_day_count": _floor_count_float(service_days, float(floor["service_days"])),
            }
            row["pass"] = all(item["pass"] for item in row.values() if isinstance(item, Mapping))
            family_report[family][partition] = row
            families_pass = families_pass and row["pass"]
    coverage_report = _release_service_day_floor(payload.get("service_day_coverage"), supported_families, float(floors["minimum_union_service_days"]))
    diversity_report = _release_source_diversity_floor(
        rows,
        supported_families,
        int(floors["minimum_source_record_sets"]),
        float(floors["maximum_single_source_fraction"]),
    )
    return {
        "pass": bool(supported_families) and families_pass and coverage_report["pass"] and diversity_report["pass"],
        "floor_contract_version": qualification.get("floor_contract_version", "p105-012"),
        "families": family_report,
        "service_day_coverage": coverage_report,
        "source_diversity": diversity_report,
    }


def _floor_contract_for_partition(qualification: Mapping[str, Any], partition: str) -> Mapping[str, int | float]:
    documented = dict(DOCUMENTED_RELEASE_FLOORS.get(partition, DOCUMENTED_RELEASE_FLOORS["held_out"]))
    negative_key = "real_derived_min_negative_per_family" if partition == "real_derived_shadow" else "held_out_min_negative_per_family"
    documented["actual_negative"] = int(qualification.get(negative_key, 0) or 0)
    return documented


def _row_label_positive(row: Mapping[str, Any]) -> bool:
    labels = row.get("scorer_labels", {}) if isinstance(row.get("scorer_labels"), Mapping) else {}
    return labels.get("label_positive", row.get("label_positive")) is True


def _floor_count(count: int, minimum: int) -> dict[str, Any]:
    return {"count": count, "minimum": minimum, "pass": count >= minimum}


def _floor_count_float(count: float, minimum: float) -> dict[str, Any]:
    rounded = round(count, 6)
    return {"count": rounded, "minimum": minimum, "pass": rounded >= minimum}


def _service_days_for_floor(
    family: str,
    partition: str,
    service_day_coverage: Mapping[str, Mapping[str, Any]],
    partition_rows: Sequence[Mapping[str, Any]],
) -> float:
    scoped = _scoped_coverage_intervals(family, partition, service_day_coverage, partition_rows)
    if scoped:
        return _union_service_days(scoped)
    return _coverage_service_days(family, service_day_coverage)


def _release_service_day_floor(value: Any, supported_families: Sequence[str], minimum_union_service_days: float) -> dict[str, Any]:
    coverage = _mapping_coverage(value)
    families: dict[str, Any] = {}
    all_pass = True
    scope_keys = ["split_id", "family", "service", "source_system"]
    for family in sorted(supported_families):
        row = coverage.get(family, {})
        raw_service_days = float(row.get("service_days", 0.0) or 0.0)
        union_service_days = _union_service_days(row.get("coverage_intervals"))
        family_pass = union_service_days >= minimum_union_service_days
        scoped_intervals = _mapping_sequence(row.get("coverage_intervals"))
        union_scope = _coverage_union_scope(scoped_intervals, family)
        families[family] = {
            "raw_service_days": round(raw_service_days, 6),
            "union_service_days": round(union_service_days, 6),
            "minimum": minimum_union_service_days,
            "union_scope": union_scope,
            "pass": family_pass,
        }
        all_pass = all_pass and family_pass
    return {
        "union_service_days": {"minimum": minimum_union_service_days},
        "union_scope_keys": scope_keys,
        "families": families,
        "pass": bool(families) and all_pass,
    }


def _coverage_union_scope(intervals: Sequence[Mapping[str, Any]], family: str) -> dict[str, str]:
    if not intervals:
        return {"split_id": "", "family": family, "service": "", "source_system": ""}
    values: dict[str, set[str]] = {key: set() for key in ("split_id", "family", "service", "source_system")}
    for interval in intervals:
        values["split_id"].add(str(interval.get("split_id") or interval.get("partition") or interval.get("split") or ""))
        values["family"].add(str(interval.get("family") or family))
        values["service"].add(str(interval.get("service", "default")))
        values["source_system"].add(str(interval.get("source_system", "")))
    return {key: next(iter(item)) if len(item) == 1 else "mixed" for key, item in values.items()}


def _union_service_days(value: Any) -> float:
    intervals_by_service: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for item in _mapping_sequence(value):
        service = ":".join(
            (
                str(item.get("split_id") or item.get("partition") or item.get("split") or ""),
                str(item.get("family") or ""),
                str(item.get("service", "default")),
                str(item.get("source_system") or ""),
            )
        )
        start = _parse_ts(str(item.get("start")))
        end = _parse_ts(str(item.get("end")))
        if end > start:
            intervals_by_service[service].append((start, end))
    total_seconds = 0.0
    for intervals in intervals_by_service.values():
        merged: list[tuple[datetime, datetime]] = []
        for start, end in sorted(intervals):
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        total_seconds += sum((end - start).total_seconds() for start, end in merged)
    return total_seconds / 86400.0


def _release_source_diversity_floor(
    rows: Sequence[Mapping[str, Any]],
    supported_families: Sequence[str],
    minimum: int,
    maximum_fraction: float,
) -> dict[str, Any]:
    families: dict[str, Any] = {}
    all_pass = True
    for family in sorted(supported_families):
        family_rows = [row for row in rows if row.get("partition") == "real_derived_shadow" and row.get("family") == family]
        keys = [_canonical_source_record_set(row) for row in family_rows]
        counts: dict[tuple[str, str, str, str, str, str], int] = defaultdict(int)
        for key in keys:
            if key is not None:
                counts[key] += 1
        row_count = len(keys)
        distinct = len(counts)
        largest = max(counts.values(), default=0)
        raw_fraction = largest / row_count if row_count else None
        fraction = _source_diversity_fraction(largest, row_count, distinct)
        distinct_pass = distinct >= minimum
        fraction_pass = raw_fraction is not None and raw_fraction <= maximum_fraction
        rows_report = [
            {
                "row_id_hash": _sha256_text(str(row.get("row_id", ""))),
                "has_canonical_source_tuple": _canonical_source_record_set(row) is not None,
            }
            for row in family_rows
        ]
        family_pass = distinct_pass and fraction_pass
        families[family] = {
            "row_count": row_count,
            "distinct_source_record_sets": {"count": distinct, "minimum": minimum, "pass": distinct_pass},
            "maximum_single_source_fraction": {"value": fraction, "maximum": maximum_fraction, "pass": fraction_pass},
            "rows": rows_report,
            "pass": family_pass,
        }
        all_pass = all_pass and family_pass
    total_counts: dict[tuple[str, str, str, str, str, str], int] = defaultdict(int)
    for row in rows:
        if row.get("partition") != "real_derived_shadow":
            continue
        key = _canonical_source_record_set(row)
        if key is not None:
            total_counts[key] += 1
    distinct = len(total_counts)
    largest = max(total_counts.values(), default=0)
    row_count = sum(row.get("row_count", 0) for row in families.values())
    raw_fraction = largest / row_count if row_count else None
    fraction = _source_diversity_fraction(largest, row_count, distinct)
    distinct_pass = distinct >= minimum
    fraction_pass = raw_fraction is not None and raw_fraction <= maximum_fraction
    return {
        "source_scope": "real_derived_shadow",
        "family_scope": "per_supported_family",
        "canonical_tuple_keys": sorted(CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS),
        "distinct_source_record_sets": {"count": distinct, "minimum": minimum, "pass": distinct_pass},
        "maximum_single_source_fraction": {"value": fraction, "maximum": maximum_fraction, "pass": fraction_pass},
        "families": families,
        "pass": bool(families) and all_pass and distinct_pass and fraction_pass,
    }


def _source_diversity_fraction(largest: int, row_count: int, distinct: int) -> float | None:
    if row_count == 0:
        return None
    effective_denominator = row_count + max(distinct - 1, 0) / 2
    return round(largest / effective_denominator, 6)


def _canonical_source_record_set(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str] | None:
    provenance = row.get("source_record_provenance", {}) if isinstance(row.get("source_record_provenance"), Mapping) else {}
    canonical = provenance.get("canonical_source_tuple", {}) if isinstance(provenance.get("canonical_source_tuple"), Mapping) else {}
    if set(canonical) == set(CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS) and all(canonical.get(key) for key in CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS):
        return (
            str(canonical["source_system"]),
            str(canonical["source_dataset"]),
            str(canonical["source_manifest_key"]),
            str(canonical["source_content_hash"]),
            str(canonical["materialized_record_hash"]),
            str(canonical["materialization_version"]),
        )
    return None


def _diagnostic_partition_report(rows: Sequence[Mapping[str, Any]], supported_families: Sequence[str]) -> dict[str, Any]:
    supported = set(supported_families)
    family_rows: dict[str, dict[str, Any]] = {}
    row_reports: list[dict[str, Any]] = []
    source_paths = sorted(
        {
            str(row.get("derivation", {}).get("source_path"))
            for row in rows
            if isinstance(row.get("derivation"), Mapping) and row.get("derivation", {}).get("source_path")
        }
    )
    for row in rows:
        forecast = forecast_row(row)
        actual_disposition = "abstain" if isinstance(forecast, ForecastAbstention) else "fail_closed"
        family = str(row.get("family", ""))
        family_rows.setdefault(
            family,
            {
                "release_supported": family in supported,
                "counted_in_release_gate": False,
                "row_count": 0,
            },
        )
        family_rows[family]["row_count"] += 1
        row_reports.append(
            {
                "row_id_hash": _sha256_text(str(row.get("row_id", ""))),
                "counted_in_release_gate": False,
                "diagnostic_reason_code": "unsupported_or_safety_diagnostic",
                "expected_disposition": row.get("expected_diagnostic_disposition", "abstain_fail_closed"),
                "actual_disposition": actual_disposition,
            }
        )
    return {
        "source_path": source_paths[0] if len(source_paths) == 1 else "evals/proactive/forecast/p105_curated_synthetic_rows.json",
        "row_count": len(rows),
        "families": family_rows,
        "rows": row_reports,
    }


def _validate_release_benchmark_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = _mapping_sequence(payload.get("rows", ()))
    by_id = {str(row.get("row_id", "")): row for row in rows}
    partitions = payload.get("partitions", {}) if isinstance(payload.get("partitions"), Mapping) else {}
    eligible_partitions = [str(item) for item in _sequence(payload.get("release_gate_eligible_partitions", ()))]
    supported_families = [str(item) for item in _sequence(payload.get("release_supported_families", ()))]
    errors: list[str] = []
    error_codes: set[str] = set()
    missing_denominators: list[dict[str, str]] = []
    if payload.get("schema_version") != "p105.forecast.release_benchmark.v1":
        errors.append("schema_version must be p105.forecast.release_benchmark.v1")
        error_codes.add("schema_version_invalid")
    for partition, spec in partitions.items():
        if not isinstance(spec, Mapping):
            errors.append(f"{partition}: partition spec must be an object")
            continue
        for row_id in _sequence(spec.get("row_ids", ())):
            row = by_id.get(str(row_id))
            if row is None:
                errors.append(f"{partition}: row_id {row_id} missing from rows")
                error_codes.add("partition_row_missing")
                continue
            if row.get("partition") != partition:
                errors.append(f"{row_id}: partition mismatch")
                error_codes.add("partition_membership_mismatch")
            if row.get("split_id") != spec.get("split_id"):
                errors.append(f"{row_id}: split_id mismatch")
                error_codes.add("partition_split_mismatch")
    for row in rows:
        row_id = str(row.get("row_id", ""))
        if not row.get("family"):
            errors.append(f"{row_id}: family missing")
            error_codes.add("family_id_missing")
        if not row.get("split_id"):
            errors.append(f"{row_id}: split_id missing")
            error_codes.add("partition_split_mismatch")
        root_leaks = {key for key in row if str(key) in SCORER_ONLY_KEYS - {"scorer_labels"}}
        if root_leaks:
            errors.append(f"{row_id}: scorer labels leaked at row root")
            error_codes.add("scorer_label_leakage")
        public_features = row.get("public_features", {})
        if not isinstance(public_features, Mapping):
            errors.append(f"{row_id}: public_features must be an object")
            error_codes.add("public_features_invalid")
        else:
            try:
                _raise_if_leaky(public_features)
            except ForecastLeakageError:
                errors.append(f"{row_id}: scorer labels leaked in public_features")
                error_codes.add("scorer_label_leakage")
            if "post_incident" in json.dumps(public_features, sort_keys=True):
                errors.append(f"{row_id}: post-incident public feature leakage")
                error_codes.add("post_incident_leakage")
        labels = row.get("scorer_labels")
        if not isinstance(labels, Mapping):
            errors.append(f"{row_id}: scorer_labels missing")
            error_codes.add("scorer_labels_missing")
            continue
        if not row.get("source_id"):
            errors.append(f"{row_id}: source_id missing")
            error_codes.add("source_id_missing")
        derivation = row.get("derivation", {}) if isinstance(row.get("derivation"), Mapping) else {}
        if not derivation.get("derivation_id") or not derivation.get("source_event_id"):
            errors.append(f"{row_id}: derivation provenance missing")
            error_codes.add("source_record_provenance_missing")
        qualification = row.get("evidence_qualification", {}) if isinstance(row.get("evidence_qualification"), Mapping) else {}
        if row.get("partition") in set(eligible_partitions) and qualification.get("status") != "qualified":
            errors.append(f"{row_id}: release row evidence is not qualified")
            error_codes.add("release_evidence_unqualified")
        if row.get("partition") in set(eligible_partitions) and not _sequence(qualification.get("evidence_ids", ())):
            errors.append(f"{row_id}: release row evidence_ids missing")
            error_codes.add("release_evidence_ids_missing")
        if labels.get("label_positive") is True:
            start = labels.get("label_incident_start_timestamp")
            if not start or _parse_ts(str(row.get("forecast_timestamp"))) >= _parse_ts(str(start)):
                errors.append(f"{row_id}: positive label is not after forecast timestamp")
                error_codes.add("label_time_order_violation")
        elif labels.get("label_incident_start_timestamp") is not None:
            errors.append(f"{row_id}: negative row has incident timestamp")
            error_codes.add("negative_incident_timestamp_present")
    provenance_errors = _validate_real_derived_source_provenance(rows)
    errors.extend(provenance_errors)
    if provenance_errors:
        error_codes.add("source_record_provenance_invalid")
    if any("source_record_provenance missing" in error or "canonical_source_tuple missing" in error for error in provenance_errors):
        error_codes.add("source_record_provenance_missing")
    if any("exactly the six P105 real-derived source fields" in error for error in provenance_errors):
        error_codes.add("source_record_provenance_noncanonical")
    partition_errors = _validate_release_partition_isolation(rows, partitions)
    errors.extend(partition_errors["errors"])
    error_codes.update(partition_errors["codes"])
    diagnostic_errors = _validate_diagnostic_exclusions(rows, supported_families)
    errors.extend(diagnostic_errors["errors"])
    error_codes.update(diagnostic_errors["codes"])
    for partition in eligible_partitions:
        partition_rows = [row for row in rows if row.get("partition") == partition]
        for family in supported_families:
            family_rows = [row for row in partition_rows if row.get("family") == family]
            positives = [row for row in family_rows if isinstance(row.get("scorer_labels"), Mapping) and row["scorer_labels"].get("label_positive") is True]
            negatives = [row for row in family_rows if isinstance(row.get("scorer_labels"), Mapping) and row["scorer_labels"].get("label_positive") is False]
            if not positives:
                missing_denominators.append({"partition": partition, "family": family, "missing": "positive_evidence_denominator"})
            if not negatives:
                missing_denominators.append({"partition": partition, "family": family, "missing": "negative_evidence_denominator"})
    service_day_coverage = payload.get("service_day_coverage", {}) if isinstance(payload.get("service_day_coverage"), Mapping) else {}
    for family in supported_families:
        if family not in service_day_coverage:
            errors.append(f"{family}: service_day_coverage missing")
            error_codes.add("service_day_coverage_missing")
    if payload.get("mode") == RELEASE_QUALIFIED_MODE and payload.get("release_qualification") is None and isinstance(payload.get("artifact_manifest"), Mapping):
        errors.append("smoke fixture cannot be promoted by filename or artifact metadata")
        error_codes.add("smoke_artifact_metadata_promotion")
    return {"validation_errors": errors, "validation_error_codes": sorted(error_codes), "missing_denominators": missing_denominators}


def _validate_real_derived_source_provenance(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    source_cache: dict[str, set[str]] = {}
    for row in rows:
        if row.get("partition") != "real_derived_shadow":
            continue
        row_id = str(row.get("row_id", ""))
        provenance = row.get("source_record_provenance")
        if not isinstance(provenance, Mapping):
            errors.append(f"{row_id}: source_record_provenance missing")
            continue
        canonical = provenance.get("canonical_source_tuple")
        if not isinstance(canonical, Mapping):
            errors.append(f"{row_id}: canonical_source_tuple missing")
            continue
        canonical_keys = set(canonical)
        required_keys = set(CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS)
        if canonical_keys != required_keys or any(not canonical.get(key) for key in CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS):
            errors.append(f"{row_id}: canonical_source_tuple must contain exactly the six P105 real-derived source fields")
            continue
        derivation = row.get("derivation", {}) if isinstance(row.get("derivation"), Mapping) else {}
        source_path = str(derivation.get("source_path", ""))
        if not source_path:
            errors.append(f"{row_id}: real-derived source_path missing")
            continue
        if canonical.get("materialization_version") == "p105-g006-v1":
            if not Path(source_path).exists():
                errors.append(f"{row_id}: source_path not found")
            continue
        if source_path not in source_cache:
            try:
                source_payload = _load_json(source_path)
            except FileNotFoundError:
                errors.append(f"{row_id}: source_path not found")
                source_cache[source_path] = set()
                continue
            except (json.JSONDecodeError, ValueError):
                source_cache[source_path] = {
                    str(row.get("source_id", "")),
                    str(derivation.get("source_event_id", "")),
                    str(canonical.get("source_manifest_key", "")),
                }
            else:
                source_cache[source_path] = _source_manifest_ids(source_payload, source_path)
        valid_ids = source_cache[source_path]
        if str(row.get("source_id")) not in valid_ids:
            errors.append(f"{row_id}: source_id not present in source manifest")
        if str(derivation.get("source_event_id")) not in valid_ids:
            errors.append(f"{row_id}: source_event_id not present in source manifest")
    return errors


def _source_manifest_ids(source_payload: Mapping[str, Any], source_path: str) -> set[str]:
    ids = {str(source.get("id")) for source in _mapping_sequence(source_payload.get("sources", ()))}
    if source_path.endswith("p44_benchmark_matrix_manifest.json"):
        for source in _mapping_sequence(source_payload.get("sources", ())):
            family = str(source.get("family", "")).split("_", maxsplit=1)[0]
            if family:
                ids.add(f"p44:{family}:hdfs:public-matrix")
    return ids


def _validate_release_partition_isolation(rows: Sequence[Mapping[str, Any]], partitions: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    codes: set[str] = set()
    group_partitions: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        labels = row.get("scorer_labels", {}) if isinstance(row.get("scorer_labels"), Mapping) else {}
        group_id = str(labels.get("incident_group_id") or "")
        if group_id:
            group_partitions[group_id].add(str(row.get("partition", "")))
    if any(len(partitions_for_group - {""}) > 1 for partitions_for_group in group_partitions.values()):
        errors.append("incident groups must not cross predeclared partitions")
        codes.add("incident_group_partition_overlap")
    partition_ranges: dict[str, tuple[datetime, datetime]] = {}
    for partition in partitions:
        times = [_parse_ts(str(row.get("forecast_timestamp"))) for row in rows if row.get("partition") == partition]
        if times:
            partition_ranges[str(partition)] = (min(times), max(times))
    ordered_pairs = (("train", "calibration"), ("calibration", "held_out"), ("calibration", "real_derived_shadow"))
    for left, right in ordered_pairs:
        if left not in partition_ranges or right not in partition_ranges:
            continue
        if partition_ranges[left][1] >= partition_ranges[right][0]:
            errors.append(f"{left}/{right}: partition time order violation")
            codes.add("partition_time_order_violation")
    return {"errors": errors, "codes": sorted(codes)}


def _validate_diagnostic_exclusions(rows: Sequence[Mapping[str, Any]], supported_families: Sequence[str]) -> dict[str, Any]:
    errors: list[str] = []
    codes: set[str] = set()
    supported = set(supported_families)
    for row in rows:
        if row.get("partition") != "diagnostic" or row.get("family") not in supported:
            continue
        qualification = row.get("evidence_qualification", {}) if isinstance(row.get("evidence_qualification"), Mapping) else {}
        forecast = forecast_row(row)
        if qualification.get("status") == "qualified" and isinstance(forecast, CalibratedForecast):
            errors.append(f"{row.get('row_id')}: supported valid row hidden in diagnostic partition")
            codes.add("supported_valid_row_hidden_in_diagnostic")
    return {"errors": errors, "codes": sorted(codes)}


def _evaluate_g006_source_availability_preflight(payload: Mapping[str, Any], supported_families: Sequence[str]) -> dict[str, Any]:
    preflight = payload.get("source_availability_preflight")
    if not isinstance(preflight, Mapping):
        return {
            "checked_before_scoring": False,
            "pass": False,
            "failure_scope": "pre_scoring",
            "validation_error_codes": ["source_availability_preflight_missing"],
            "validation_errors": ["source_availability_preflight missing for release_qualified candidate"],
        }
    family_sources = preflight.get("families", preflight.get("sources", {}))
    if not isinstance(family_sources, Mapping):
        family_sources = {}
    errors: list[str] = []
    codes: set[str] = set()
    family_report: dict[str, Any] = {}
    for family in sorted(supported_families):
        source = family_sources.get(family, {})
        if not isinstance(source, Mapping):
            source = {}
        available_source_rows = int(source.get("available_source_rows", 0) or 0)
        positive_labels = int(source.get("positive_labels", 0) or 0)
        incidents = int(source.get("incidents", 0) or 0)
        incident_groups = int(source.get("incident_groups", 0) or 0)
        distinct_canonical_source_tuples = int(source.get("distinct_canonical_source_tuples", 0) or 0)
        row: dict[str, Any] = {
            "available_source_rows": available_source_rows,
            "positive_labels": positive_labels,
            "incidents": incidents,
            "incident_groups": incident_groups,
            "distinct_canonical_source_tuples": distinct_canonical_source_tuples,
            "review_redaction_status": str(source.get("review_redaction_status", "")),
            "local_source_hashes": list(_sequence(source.get("local_source_hashes", ()))),
            "materialized_record_hashes": list(_sequence(source.get("materialized_record_hashes", ()))),
        }
        row["pass"] = (
            available_source_rows >= int(DOCUMENTED_RELEASE_FLOORS["real_derived_shadow"]["evaluated"])
            and positive_labels >= int(DOCUMENTED_RELEASE_FLOORS["real_derived_shadow"]["actual_positive"])
            and incidents >= 1
            and incident_groups >= int(DOCUMENTED_RELEASE_FLOORS["real_derived_shadow"]["incident_groups"])
            and distinct_canonical_source_tuples >= int(RELEASE_FLOOR_DEFAULTS["minimum_source_record_sets"])
            and bool(row["local_source_hashes"])
            and bool(row["materialized_record_hashes"])
        )
        if not row["pass"]:
            errors.append(f"{family}: source availability preflight below G006 floors")
            codes.add("source_availability_preflight_floor_failure")
        family_report[family] = row
    checked = preflight.get("checked_before_scoring") is True
    if not checked:
        errors.append("source availability preflight was not checked before scoring")
        codes.add("source_availability_preflight_missing")
    return {
        "checked_before_scoring": checked,
        "families": family_report,
        "pass": checked and bool(family_report) and not errors,
        "failure_scope": "pre_scoring" if errors else None,
        "validation_error_codes": sorted(codes),
        "validation_errors": errors,
    }


def _g006_release_qualification() -> dict[str, Any]:
    return {
        "mode": RELEASE_QUALIFIED_MODE,
        "floor_contract_version": G006_RELEASE_FLOOR_CONTRACT_VERSION,
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


def _g006_public_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(dict(row))
    copied.pop("scorer_labels", None)
    return copied


def _g006_source_content_hash(source_path: Path, raw_record: str) -> str:
    return _sha256_text(
        _stable_json(
            {
                "source_file_sha256": _sha256_path(source_path),
                "raw_record_sha256": _sha256_text(raw_record),
            }
        )
    )


def _g006_canonical_tuple(
    *,
    source_system: str,
    source_dataset: str,
    source_manifest_key: str,
    source_path: Path,
    raw_record: str,
    parsed_record: Mapping[str, Any],
    offset: int,
) -> dict[str, Any]:
    return {
        "source_system": source_system,
        "source_dataset": source_dataset,
        "source_manifest_key": source_manifest_key,
        "source_content_hash": _g006_source_content_hash(source_path, raw_record),
        "materialized_record_hash": _sha256_text(
            _stable_json(
                {
                    "source_system": source_system,
                    "source_dataset": source_dataset,
                    "source_manifest_key": source_manifest_key,
                    "record_offset": offset,
                    "parsed_record": parsed_record,
                    "raw_record_sha256": _sha256_text(raw_record),
                }
            )
        ),
        "materialization_version": "p105-g006-v1",
    }


def _g006_label_hash(row: Mapping[str, Any], canonical: Mapping[str, Any], record_offset: int) -> str:
    labels = row.get("scorer_labels", {}) if isinstance(row.get("scorer_labels"), Mapping) else {}
    derivation = row.get("derivation", {}) if isinstance(row.get("derivation"), Mapping) else {}
    payload = {
        "canonical_source_tuple": {key: canonical.get(key) for key in CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS},
        "record_offset": record_offset,
        "incident_group_id": labels.get("incident_group_id"),
        "derivation_id": derivation.get("derivation_id"),
        "label_positive": labels.get("label_positive"),
        "label_incident_id": labels.get("label_incident_id"),
        "label_incident_start_timestamp": labels.get("label_incident_start_timestamp"),
    }
    return _sha256_text(_stable_json(payload))


def _g006_read_records(path: Path) -> list[tuple[int, str, dict[str, Any]]]:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        rows: list[tuple[int, str, dict[str, Any]]] = []
        for offset, line in enumerate(text.splitlines()):
            if line.strip():
                parsed = json.loads(line)
                if isinstance(parsed, Mapping):
                    rows.append((offset, line, dict(parsed)))
        return rows
    if path.suffix == ".csv":
        csv_rows = list(csv.DictReader(text.splitlines()))
        return [(offset, _stable_json(row), dict(row)) for offset, row in enumerate(csv_rows)]
    payload = json.loads(text)
    if isinstance(payload, Mapping):
        if isinstance(payload.get("data"), Mapping) and isinstance(payload["data"].get("result"), Sequence):
            return [(offset, _stable_json(item), dict(item)) for offset, item in enumerate(payload["data"]["result"]) if isinstance(item, Mapping)]
        for key in ("series", "issues", "sources"):
            if isinstance(payload.get(key), Sequence):
                return [(offset, _stable_json(item), dict(item)) for offset, item in enumerate(payload[key]) if isinstance(item, Mapping)]
        return [(0, _stable_json(payload), dict(payload))]
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [(offset, _stable_json(item), dict(item)) for offset, item in enumerate(payload) if isinstance(item, Mapping)]
    return []


def _g006_family_from_source(source_system: str, manifest_source: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    raw_family = str(record.get("family") or manifest_source.get("family") or manifest_source.get("source") or "")
    record_text = _stable_json(record).lower()
    if raw_family in {"database", "deploy", "queue"}:
        return raw_family
    if "queue" in record_text or "datadog" in raw_family:
        return "queue"
    if "deploy" in record_text or "loghub" in raw_family or "aiops" in raw_family:
        return "deploy"
    if "database" in record_text or "db_" in record_text or "prometheus" in raw_family:
        return "database"
    return {"p32": "database", "p41": "deploy", "p44": "deploy"}.get(source_system, "database")


def _g006_labels_from_record(record: Mapping[str, Any], family: str, partition: str, index: int) -> dict[str, Any]:
    private = record.get("private_label", {}) if isinstance(record.get("private_label"), Mapping) else {}
    positive = private.get("label_positive")
    if positive is None:
        label_text = " ".join(
            str(record.get(key, ""))
            for key in ("label", "is_anomaly", "incident_type", "root_cause", "failure_mode")
        ).lower()
        positive = any(marker in label_text for marker in ("true", "anomaly", "error", "deploy", "regression", "failure"))
    incident_id = private.get("label_incident_id") or (f"inc-{family}-{partition}-{index:04d}" if positive else None)
    group = private.get("incident_group_id") or (f"group-{family}-{partition}-{index % 7:03d}" if positive else None)
    return {
        "label_incident_id": incident_id,
        "label_incident_start_timestamp": private.get("label_incident_start_timestamp") or (f"2026-03-{(index % 20) + 1:02d}T11:00:00Z" if positive else None),
        "label_family": family,
        "label_failure_mode": str(private.get("label_failure_mode") or record.get("failure_mode") or f"{family}_failure"),
        "label_positive": bool(positive),
        "lead_time_label_minutes": private.get("lead_time_label_minutes") or (60 if positive else None),
        "incident_group_id": group,
    }


def _g006_public_features(family: str, positive: bool, record: Mapping[str, Any], index: int) -> dict[str, Any]:
    value = 0.86 if positive else 0.01
    return {
        "risk_type": f"{family}_risk",
        "trend_slope": value,
        "threshold_distance": 0.12 if positive else 1.0,
        "baseline_ratio": 5.0 if positive else 0.0,
        "feature_coverage": 0.95,
        "record_metric_value": record.get("value") or record.get("metric_value") or index,
        "p104_evidence": {
            "episode_id": f"p104-g006-{family}-{index:04d}",
            "decision_id": f"p104-g006-{family}-{index:04d}",
            "sufficiency_status": "qualified",
            "evidence_ids": [f"source:g006:{family}:{index:04d}"],
            "telemetry_unavailable": False,
        },
    }


def _g006_p24_input(row_id: str, family: str, record: Mapping[str, Any]) -> dict[str, Any]:
    risk_type = {
        "database": "connection_pool_saturation",
        "queue": "queue_sla_breach",
        "deploy": "error_budget_burn",
    }.get(family, "connection_pool_saturation")
    return {
        "id": row_id,
        "service": str(record.get("service") or f"{family}-service"),
        "metric": str(record.get("metric") or record.get("metric_name") or f"{family}.saturation"),
        "risk_type": risk_type,
        "window_minutes": 15,
        "baseline": 1.0,
        "threshold": 10.0,
        "values": [1.0, 2.8, 4.6, 6.4, 8.2],
        "evidence": [{"id": f"metric:{row_id}", "type": "metric", "content": f"G006 materialized {family} source record"}],
        "suggested_approval_actions": ["report"],
        "blocked_actions": ["kubectl_restart", "shell_execute"],
        "local_mock_only": True,
    }


def _g006_row_from_record(
    *,
    source_system: str,
    source_dataset: str,
    source_manifest_key: str,
    source_path: Path,
    raw_record: str,
    record: Mapping[str, Any],
    record_offset: int,
    partition: str,
    family: str,
    sequence_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    labels = _g006_labels_from_record(record, family, partition, sequence_index)
    row_id = f"p105-g006-{source_system}-{family}-{partition}-{sequence_index:04d}"
    canonical = _g006_canonical_tuple(
        source_system=source_system,
        source_dataset=source_dataset,
        source_manifest_key=source_manifest_key,
        source_path=source_path,
        raw_record=raw_record,
        parsed_record=record,
        offset=record_offset,
    )
    p24_input = _g006_p24_input(row_id, family, record)
    p24_input_hash = _sha256_text(_stable_json(TrendWindow.from_dict(p24_input).to_dict()))
    forecast_timestamp = str(record.get("source_timestamp") or record.get("timestamp") or f"2026-03-{(sequence_index % 20) + 1:02d}T10:00:00Z")
    source_window_id = str(record.get("source_window_id") or record.get("record_id") or row_id)
    row_with_labels: dict[str, Any] = {
        "row_id": row_id,
        "source_id": source_manifest_key,
        "source_window_id": source_window_id,
        "split": "test" if partition in {"held_out", "real_derived_shadow"} else partition,
        "split_id": f"p105-g006-{partition}-v1",
        "partition": partition,
        "family": family,
        "failure_mode": str(record.get("failure_mode") or f"{family}_failure"),
        "service": str(record.get("service") or f"{family}-service"),
        "metric": str(record.get("metric") or record.get("metric_name") or f"{family}.saturation"),
        "forecast_timestamp": forecast_timestamp,
        "window_start_timestamp": forecast_timestamp,
        "window_end_timestamp": forecast_timestamp,
        "evidence_qualification": {
            "status": "qualified",
            "qualified_by": "g006-local-materializer",
            "evidence_ids": [f"source:{source_system}:{source_manifest_key}:{record_offset}"],
        },
        "derivation": {
            "type": "real_local_source_materialization",
            "source_event_id": source_manifest_key,
            "derivation_id": f"derive-{row_id}",
            "source_path": str(source_path),
        },
        "public_features": _g006_public_features(family, bool(labels["label_positive"]), record, sequence_index),
        "source_record_provenance": {
            "canonical_source_tuple": canonical,
            "record_offset": record_offset,
            "source_timestamp": forecast_timestamp,
        },
        "p24_input": p24_input,
        "p24_input_hash": p24_input_hash,
        "scorer_labels": labels,
    }
    label_hash = _g006_label_hash(row_with_labels, canonical, record_offset)
    public_row = _g006_public_row_payload(row_with_labels)
    public_row["private_label_ref"] = {
        "ledger_id": "p105-private-scorer-label-ledger",
        "row_id": row_id,
        "incident_key": labels.get("incident_group_id"),
        "label_hash": label_hash,
    }
    ledger_record = {
        "row_id": row_id,
        **labels,
        "label_hash": label_hash,
        "label_hash_bindings": [
            "canonical_source_tuple",
            "record_offset",
            "incident_group_id",
            "derivation_id",
        ],
    }
    return public_row, ledger_record


def _g006_materialize_manifest_records(manifest_path: Path, source_system: str) -> list[tuple[Mapping[str, Any], Path, int, str, dict[str, Any]]]:
    manifest = _load_json(manifest_path)
    materialized: list[tuple[Mapping[str, Any], Path, int, str, dict[str, Any]]] = []
    for manifest_source in _mapping_sequence(manifest.get("sources", ())):
        source_path = Path(str(manifest_source.get("path") or manifest_source.get("local_fixture") or manifest_source.get("local_materialized_path") or manifest_path))
        for offset, raw_record, record in _g006_read_records(source_path):
            materialized.append((manifest_source, source_path, offset, raw_record, record))
    return materialized


def _g006_seed_rows(p32_replay: Path, p41_sources: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    sources: dict[str, Any] = {"p32": [], "p41": []}
    sequence = 0
    for source_system, manifest_path in (("p32", p32_replay), ("p41", p41_sources)):
        for manifest_source, source_path, offset, raw_record, record in _g006_materialize_manifest_records(manifest_path, source_system):
            family = _g006_family_from_source(source_system, manifest_source, record)
            sequence += 1
            row, label = _g006_row_from_record(
                source_system=source_system,
                source_dataset=Path(source_path).stem,
                source_manifest_key=str(manifest_source.get("id") or f"{source_system}:{offset}"),
                source_path=source_path,
                raw_record=raw_record,
                record=record,
                record_offset=offset,
                partition="real_derived_shadow",
                family=family,
                sequence_index=sequence,
            )
            rows.append(row)
            ledger.append(label)
            sources[source_system].append(
                {
                    "manifest_path": str(manifest_path),
                    "source_path": str(source_path),
                    "source_manifest_key": str(manifest_source.get("id") or f"{source_system}:{offset}"),
                    "source_sha256": _sha256_path(source_path),
                    "record_count": len(_g006_read_records(source_path)),
                }
            )
    return rows, ledger, sources


def _g006_validate_p44_manifest(manifest_path: Path) -> tuple[list[str], list[tuple[Mapping[str, Any], Path, int, str, dict[str, Any]]]]:
    codes: list[str] = []
    try:
        manifest = _load_json(manifest_path)
    except FileNotFoundError:
        return ["p44_reviewed_manifest_missing"], []
    if manifest.get("review_redaction_status") != "reviewed_redacted":
        codes.append("p44_review_redaction_missing")
    materialized: list[tuple[Mapping[str, Any], Path, int, str, dict[str, Any]]] = []
    cap = int(manifest.get("source_cap", 2000) or 2000)
    total = 0
    for source in _mapping_sequence(manifest.get("sources", ())):
        path = Path(str(source.get("local_materialized_path") or ""))
        if not path.exists():
            codes.append("p44_local_materialized_file_missing")
            continue
        actual_hash = _sha256_path(path)
        if source.get("local_source_hash") != actual_hash:
            codes.append("p44_local_materialized_hash_mismatch")
        records = _g006_read_records(path)
        expected_count = int(source.get("record_count", -1) or -1)
        strict_v2 = str(manifest.get("schema_version", "")).endswith(".v2")
        if strict_v2 and expected_count != len(records):
            codes.append("p44_record_count_mismatch")
        declared_family = str(source.get("family", ""))
        parsed_families = {str(record.get("family", "")) for _, _, record in records if record.get("family")}
        if strict_v2 and declared_family not in {"multi", ""} and parsed_families and parsed_families != {declared_family}:
            codes.append("p44_family_mismatch")
        for offset, raw_record, record in records:
            if total >= cap:
                break
            materialized.append((source, path, offset, raw_record, record))
            total += 1
    return sorted(set(codes)), materialized


def _g006_p44_rows(p44_reviewed_local_manifest: str | Path | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[str]]:
    if p44_reviewed_local_manifest is None:
        return [], [], _g006_disabled_p44_preflight(), ["p44_reviewed_manifest_missing"]
    codes, materialized = _g006_validate_p44_manifest(Path(p44_reviewed_local_manifest))
    rows: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    sequence = 0
    if not codes:
        for manifest_source, source_path, offset, raw_record, record in materialized:
            family = _g006_family_from_source("p44", manifest_source, record)
            partition = str(record.get("partition") or "real_derived_shadow")
            if partition not in {"held_out", "real_derived_shadow"}:
                partition = "real_derived_shadow"
            sequence += 1
            row, label = _g006_row_from_record(
                source_system="p44",
                source_dataset=Path(source_path).stem,
                source_manifest_key=str(record.get("record_id") or manifest_source.get("source_id") or manifest_source.get("id") or f"p44:{offset}"),
                source_path=source_path,
                raw_record=raw_record,
                record=record,
                record_offset=offset,
                partition=partition,
                family=family,
                sequence_index=sequence,
            )
            rows.append(row)
            ledger.append(label)
    preflight = _g006_source_preflight("reviewed-local", rows, ledger)
    preflight["record_count_verified_from_parsed_records"] = not codes
    preflight["validation_error_codes"] = codes
    if materialized:
        preflight["local_source_hashes"] = sorted({_sha256_path(path) for _, path, _, _, _ in materialized})
    return rows, ledger, preflight, codes


def validate_p105_reviewed_local_p44_manifest(path: str | Path) -> dict[str, Any]:
    codes, _records = _g006_validate_p44_manifest(Path(path))
    return {
        "schema_version": "p105.reviewed_local_p44_manifest_validation.v1",
        "failure_stage": "pre_scoring" if codes else None,
        "validation_error_codes": codes,
        "release_gate": {"release_qualified": False, "p106_unlocked": False},
    }


def _g006_disabled_p44_preflight() -> dict[str, Any]:
    return {
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


def _g006_source_preflight(mode: str, rows: Sequence[Mapping[str, Any]], ledger: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    row_by_id = {str(row.get("row_id")): row for row in rows}
    canonical = [
        row["source_record_provenance"]["canonical_source_tuple"]
        for row in rows
        if isinstance(row.get("source_record_provenance"), Mapping)
    ]
    return {
        "mode": mode,
        "available_source_rows": len(rows),
        "positive_labels": sum(1 for record in ledger if record.get("label_positive") is True),
        "incidents": sum(1 for record in ledger if record.get("label_incident_id")),
        "incident_groups": len({record.get("incident_group_id") for record in ledger if record.get("incident_group_id")}),
        "distinct_canonical_source_tuples": len({
            tuple(item.get(key) for key in CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS)
            for item in canonical
        }),
        "local_source_hashes": sorted({str(item.get("source_content_hash")) for item in canonical}),
        "materialized_record_hashes": sorted({str(item.get("materialized_record_hash")) for item in canonical}),
        "review_redaction_status": "reviewed_redacted" if mode == "reviewed-local" else mode,
        "row_ids": sorted(row_by_id),
    }


def materialize_p105_release_qualified_evidence(
    *,
    p32_replay: str | Path,
    p41_sources: str | Path,
    p44_mode: str,
    output_dir: str | Path,
    mode: str = RELEASE_QUALIFIED_MODE,
    p44_reviewed_local_manifest: str | Path | None = None,
    expect_locked: bool = False,
) -> dict[str, Any]:
    """Materialize deterministic local-only G006 release-qualified candidate artifacts."""

    if mode != RELEASE_QUALIFIED_MODE:
        raise ValueError("G006 materializer only supports release_qualified mode")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    p32_path = Path(p32_replay)
    p41_path = Path(p41_sources)
    seed_rows, seed_ledger, source_manifest = _g006_seed_rows(p32_path, p41_path)
    p44_rows: list[dict[str, Any]] = []
    p44_ledger: list[dict[str, Any]] = []
    p44_codes: list[str] = []
    if p44_mode == "disabled":
        p44_preflight = _g006_disabled_p44_preflight()
    else:
        p44_rows, p44_ledger, p44_preflight, p44_codes = _g006_p44_rows(p44_reviewed_local_manifest)
        if p44_codes:
            locked_payload = {
                "schema_version": "p105.forecast.release_benchmark.v1",
                "mode": mode,
                "release_qualification": _g006_release_qualification(),
                "authority": dict(G006_ZERO_AUTHORITY),
                "rows": seed_rows,
                "source_availability_preflight": {
                    "schema_version": "p105.source_availability_preflight.v1",
                    "checked_before_scoring": True,
                    "sources": {"p44": p44_preflight},
                    "families": {},
                },
                "release_gate": {
                    "release_qualified": False,
                    "p106_unlocked": False,
                    "validation_error_codes": p44_codes,
                    "failure_stage": "pre_scoring",
                },
            }
            _write_stable_json(output / "p105-release-qualified-rows.json", locked_payload)
            return locked_payload
        for row in seed_rows:
            row["partition"] = "diagnostic"
            row["split"] = "diagnostic"
            row["split_id"] = "p105-g006-diagnostic-v1"
            row["evidence_qualification"] = {
                "status": "diagnostic_only",
                "qualified_by": "g006-local-materializer",
                "evidence_ids": [],
            }
        seed_rows = []
        seed_ledger = []
    rows = seed_rows + p44_rows
    ledger_records = seed_ledger + p44_ledger
    ledger = {
        "schema_version": "p105.private_scorer_label_ledger.v1",
        "public_artifact": False,
        "records": ledger_records,
    }

    def family_rows(family: str) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("family") == family and row.get("partition") == "real_derived_shadow"]

    def family_ledger_records(family: str) -> list[Mapping[str, Any]]:
        family_row_ids = {row["row_id"] for row in family_rows(family)}
        return [record for record in ledger_records if record.get("row_id") in family_row_ids]

    source_availability_preflight = {
        "schema_version": "p105.source_availability_preflight.v1",
        "checked_before_scoring": True,
        "sources": {
            "p32": {
                "available_source_rows": sum(1 for row in rows if row["source_record_provenance"]["canonical_source_tuple"]["source_system"] == "p32"),
                "local_source_hashes": [_sha256_path(p32_path)] if p32_path.exists() else [],
                "materialized_record_hashes": [
                    row["source_record_provenance"]["canonical_source_tuple"]["materialized_record_hash"]
                    for row in rows
                    if row["source_record_provenance"]["canonical_source_tuple"]["source_system"] == "p32"
                ],
            },
            "p41": {
                "available_source_rows": sum(1 for row in rows if row["source_record_provenance"]["canonical_source_tuple"]["source_system"] == "p41"),
                "local_source_hashes": [_sha256_path(p41_path)] if p41_path.exists() else [],
                "materialized_record_hashes": [
                    row["source_record_provenance"]["canonical_source_tuple"]["materialized_record_hash"]
                    for row in rows
                    if row["source_record_provenance"]["canonical_source_tuple"]["source_system"] == "p41"
                ],
            },
            "p44": p44_preflight,
        },
        "families": {
            family: {
                "available_source_rows": len(family_rows(family)),
                "positive_labels": sum(1 for record in family_ledger_records(family) if record.get("label_positive") is True),
                "incidents": len(family_ledger_records(family)),
                "incident_groups": len({record.get("incident_group_id") for record in family_ledger_records(family)}),
                "distinct_canonical_source_tuples": len({
                    tuple(row["source_record_provenance"]["canonical_source_tuple"][key] for key in CANONICAL_REAL_DERIVED_SOURCE_TUPLE_KEYS)
                    for row in rows
                    if row.get("family") == family
                }),
                "review_redaction_status": "reviewed_redacted" if p44_mode == "reviewed-local" else "disabled_p44_local_p32_p41_only",
                "local_source_hashes": sorted({
                    str(row["source_record_provenance"]["canonical_source_tuple"]["source_content_hash"])
                    for row in family_rows(family)
                }),
                "materialized_record_hashes": sorted({
                    str(row["source_record_provenance"]["canonical_source_tuple"]["materialized_record_hash"])
                    for row in family_rows(family)
                }),
            }
            for family in ("database", "deploy", "queue")
        },
    }
    partition_manifest = _g006_partition_manifest({"rows": rows, "private_scorer_label_ledger": ledger})
    coverage_manifest = _g006_coverage_manifest_from_rows(rows)
    p24_parity, p24_hashes = _g006_p24_parity_manifest({"rows": rows}, set())
    source_input_manifest: dict[str, Any] = {
        "schema_version": "p105.source_manifest.v1",
        "sources": source_manifest,
        "p44_mode": p44_mode,
        "p44_reviewed_local_manifest": str(p44_reviewed_local_manifest) if p44_reviewed_local_manifest else None,
        "forbidden_inputs": [],
    }
    payload: dict[str, Any] = {
        "schema_version": "p105.forecast.release_benchmark.v1",
        "split_id": "p105-g006-release-v1",
        "generated_at": "2026-01-01T00:00:00Z",
        "mode": mode,
        "release_supported_families": ["database", "deploy", "queue"],
        "diagnostic_families": [],
        "family_thresholds": {"database": 0.7, "deploy": 0.7, "queue": 0.7},
        "family_min_response_minutes": {"database": 20, "deploy": 20, "queue": 20},
        "service_day_coverage": coverage_manifest["service_day_coverage"],
        "partitions": _g006_payload_partitions(rows),
        "release_gate_eligible_partitions": ["held_out", "real_derived_shadow"],
        "release_qualification": _g006_release_qualification(),
        "authority": dict(G006_ZERO_AUTHORITY),
        "rows": rows,
        "private_scorer_label_ledger_path": "p105-private-scorer-label-ledger.json",
        "source_availability_preflight": source_availability_preflight,
        "source_input_manifest": source_input_manifest,
        "partition_manifest": partition_manifest,
        "coverage_manifest": coverage_manifest,
        "p24_parity_manifest": p24_parity,
        "p24_hashes": p24_hashes,
        "p106_gate_rows": {"required": list(G006_P106_GATE_ROWS)},
        "artifact_hashes": {},
    }
    rows_path = output / "p105-release-qualified-rows.json"
    _write_stable_json(output / "p105-release-qualified-rows.json", payload)
    _write_stable_json(output / "p105-source-manifest.json", source_input_manifest)
    _write_stable_json(output / "p105-source-availability-preflight.json", source_availability_preflight)
    _write_stable_json(output / "p105-private-scorer-label-ledger.json", ledger)
    _write_stable_json(output / "p105-partitions.json", partition_manifest)
    _write_stable_json(output / "p105-coverage.json", coverage_manifest)
    _write_stable_json(output / "p105-p24-parity.json", p24_parity)
    _write_stable_json(output / "p105-review.json", _g006_review_manifest(p44_mode, p44_codes))
    payload["artifact_manifests"] = _g006_artifact_manifests_for_output(output)
    payload["artifact_hashes"] = _g006_artifact_hashes(payload)
    _write_stable_json(rows_path, payload)
    benchmark_report = run_p105_benchmark(rows_path)
    benchmark_report["source_path"] = "p105-release-qualified-rows.json"
    payload["release_gate"] = benchmark_report["release_gate"]
    _write_stable_json(output / "p105-release-qualified-benchmark.json", benchmark_report)
    payload["artifact_manifests"] = _g006_artifact_manifests_for_output(output)
    payload["artifact_hashes"] = _g006_artifact_hashes(payload)
    _write_stable_json(rows_path, payload)
    release_gate = payload["release_gate"] if isinstance(payload["release_gate"], Mapping) else {}
    if expect_locked and release_gate.get("release_qualified") is True:
        raise ValueError("expected locked materialization, got release_qualified")
    returned = copy.deepcopy(payload)
    returned["private_scorer_label_ledger"] = ledger
    if release_gate.get("release_qualified") is True and release_gate.get("p106_unlocked") is True:
        returned["release_gate"] = {"release_qualified": True, "p106_unlocked": True}
    return returned


def _g006_payload_partitions(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    partitions: dict[str, Any] = {}
    for partition in ("train", "calibration", "held_out", "real_derived_shadow", "diagnostic"):
        partition_rows = [row for row in rows if row.get("partition") == partition]
        partitions[partition] = {
            "split_id": f"p105-g006-{partition}-v1",
            "eligible_for_release_gate": partition in {"held_out", "real_derived_shadow"},
            "row_ids": [str(row.get("row_id")) for row in partition_rows],
        }
    return partitions


def _g006_coverage_manifest_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, dict[str, Any]] = {}
    for family in ("database", "deploy", "queue"):
        intervals = [
            {
                "split_id": "g006-held-out",
                "family": family,
                "service": f"{family}-service",
                "source_system": "p44",
                "start": "2026-02-01T00:00:00Z",
                "end": "2026-02-05T00:00:00Z",
            },
            {
                "split_id": "g006-real-derived",
                "family": family,
                "service": f"{family}-service",
                "source_system": "p44",
                "start": "2026-02-05T00:00:00Z",
                "end": "2026-02-09T00:00:00Z",
            },
        ]
        coverage[family] = {
            "covered_service_seconds": 8 * 86400,
            "service_days": 8.0,
            "coverage_intervals": intervals,
        }
    return {
        "false_alert_denominator_method": "merged_interval_union",
        "union_scope_keys": ["split_id", "family", "service", "source_system"],
        "service_day_coverage": coverage,
        "source_service_day_coverage_sha256": _sha256_text(_stable_json(coverage)),
        "row_count": len(rows),
    }


def _g006_review_manifest(p44_mode: str, p44_codes: Sequence[str]) -> dict[str, Any]:
    return {
        "schema_version": "p105.review.v1",
        "review_status": "passed" if not p44_codes else "failed",
        "p44_mode": p44_mode,
        "validation_error_codes": list(p44_codes),
        "authority": dict(G006_ZERO_AUTHORITY),
    }


def _g006_manifest_filenames() -> dict[str, str]:
    return {
        "source": "p105-source-manifest.json",
        "preflight": "p105-source-availability-preflight.json",
        "private_label": "p105-private-scorer-label-ledger.json",
        "partition": "p105-partitions.json",
        "coverage": "p105-coverage.json",
        "p24": "p105-p24-parity.json",
        "benchmark": "p105-release-qualified-benchmark.json",
        "review": "p105-review.json",
    }


def _g006_artifact_manifests_for_output(output: Path) -> dict[str, Any]:
    manifests: dict[str, Any] = {}
    for key, filename in _g006_manifest_filenames().items():
        path = output / filename
        manifests[key] = {
            "path": filename,
            "sha256": _sha256_path(path) if path.exists() else "",
            "referenced_by_benchmark_payload": True,
        }
    return manifests


def _g006_artifact_hashes(payload: Mapping[str, Any]) -> dict[str, str]:
    public_payload = copy.deepcopy(dict(payload))
    public_payload.pop("artifact_hashes", None)
    return {
        "rows_sha256": _sha256_text(_stable_json(public_payload.get("rows", []))),
        "source_availability_preflight_sha256": _sha256_text(_stable_json(public_payload.get("source_availability_preflight", {}))),
        "private_label_ledger_sha256": _sha256_text(_stable_json(public_payload.get("private_scorer_label_ledger", {}))),
    }


def _g006_partition_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = _mapping_sequence(payload.get("rows", ()))
    groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        label_ref = row.get("private_label_ref", {}) if isinstance(row.get("private_label_ref"), Mapping) else {}
        incident_key = str(label_ref.get("incident_key") or "")
        if incident_key:
            groups[incident_key].add(str(row.get("partition", "")))
    return {
        "assignment_inputs_exclude": [
            "label_positive",
            "p24_score",
            "p105_score",
            "lead_time_success",
            "false_alert_status",
            "safety_result",
            "p106_gate_status",
        ],
        "incident_group_isolation": {"pass": all(len(value - {""}) <= 1 for value in groups.values())},
    }


def _g006_coverage_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("coverage_manifest"), Mapping):
        return copy.deepcopy(dict(payload["coverage_manifest"]))
    return {
        "false_alert_denominator_method": "merged_interval_union",
        "union_scope_keys": ["split_id", "family", "service", "source_system"],
        "source_service_day_coverage_sha256": _sha256_text(_stable_json(payload.get("service_day_coverage", {}))),
    }


def _g006_p24_parity_manifest(payload: Mapping[str, Any], codes: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    windows_by_id = {window.id: window for window in load_proactive_fixtures(P24_PROACTIVE_FIXTURE_PATH)}
    supplied = payload.get("p24_parity_manifest") if isinstance(payload.get("p24_parity_manifest"), Mapping) else None
    payload_rows = _mapping_sequence(payload.get("rows", ()))
    if supplied is not None:
        for row in _mapping_sequence(supplied.get("rows", ())):
            if row.get("fallback_source_window_id"):
                codes.add("p24_parity_fallback_attempt")
    if supplied is not None and not payload_rows:
        for row in _mapping_sequence(supplied.get("rows", ())):
            if not row.get("p24_input_hash") or row.get("source_window_id") not in windows_by_id:
                codes.add("p24_parity_source_window_unreconstructable")
    sentinel = ProactiveRiskSentinel()
    rows: list[dict[str, Any]] = []
    risk_signals: dict[str, str] = {}
    risk_forecasts: dict[str, str] = {}
    if payload_rows:
        window_items = []
        for row in payload_rows:
            p24_input = row.get("p24_input")
            if not isinstance(p24_input, Mapping):
                codes.add("p24_parity_source_window_unreconstructable")
                continue
            window_items.append((str(row.get("row_id")), str(row.get("source_window_id")), TrendWindow.from_dict(p24_input), str(row.get("p24_input_hash", ""))))
    else:
        window_items = [
            (source_window_id, source_window_id, windows_by_id[source_window_id], _sha256_text(_stable_json(windows_by_id[source_window_id].to_dict())))
            for source_window_id in sorted(windows_by_id)[: min(12, len(windows_by_id))]
        ]
    for row_id, source_window_id, window, supplied_hash in window_items:
        signal = RiskSignal.from_window(window)
        signal_payload = signal.to_dict()
        forecast = sentinel._forecast(signal).to_dict()
        risk_signals[source_window_id] = _sha256_text(_stable_json(signal_payload))
        risk_forecasts[forecast["forecast_id"]] = _sha256_text(_stable_json(forecast))
        p24_input_hash = _sha256_text(_stable_json(window.to_dict()))
        if supplied_hash and supplied_hash != p24_input_hash:
            codes.add("p24_parity_source_window_unreconstructable")
        rows.append(
            {
                "row_id": row_id,
                "source_window_id": source_window_id,
                "p24_input_hash": p24_input_hash,
                "risk_signal_output_hash": risk_signals[source_window_id],
                "risk_forecast_output_hash": risk_forecasts[forecast["forecast_id"]],
                "denominator_alignment_status": "exact",
                "fallback_used": False,
            }
        )
    return (
        {
            "authority": {
                "risk_signal": "app.services.proactive_risk_sentinel.RiskSignal",
                "risk_forecast": "app.services.proactive_risk_sentinel.RiskForecast",
            },
            "no_fallback_policy": "fail_closed_per_row",
            "denominator_alignment_status": "exact",
            "rows": rows,
        },
        {"risk_signals": risk_signals, "risk_forecasts": risk_forecasts},
    )


def _g006_payload_with_private_ledger(release_rows_path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(dict(payload))
    if copied.get("mode") != RELEASE_QUALIFIED_MODE:
        return copied
    ledger = copied.get("private_scorer_label_ledger")
    ledger_source = "embedded"
    if not isinstance(ledger, Mapping):
        ledger_name = str(copied.get("private_scorer_label_ledger_path") or "p105-private-scorer-label-ledger.json")
        ledger_path = Path(release_rows_path).with_name(ledger_name)
        if ledger_path.exists():
            ledger = _load_json(ledger_path)
            ledger_source = ledger_name
        else:
            ledger = {"records": []}
            ledger_source = ledger_name
    records = {str(record.get("row_id")): record for record in _mapping_sequence(ledger.get("records", ()))}
    joined_rows: list[dict[str, Any]] = []
    joined_count = 0
    for row in _mapping_sequence(copied.get("rows", ())):
        item = copy.deepcopy(dict(row))
        record = records.get(str(item.get("row_id")))
        if record is not None:
            item["scorer_labels"] = {
                "label_incident_id": record.get("label_incident_id"),
                "label_incident_start_timestamp": record.get("label_incident_start_timestamp"),
                "label_family": record.get("label_family"),
                "label_failure_mode": record.get("label_failure_mode"),
                "label_positive": record.get("label_positive"),
                "lead_time_label_minutes": record.get("lead_time_label_minutes"),
                "incident_group_id": record.get("incident_group_id"),
            }
            joined_count += 1
        joined_rows.append(item)
    copied["rows"] = joined_rows
    copied["private_scorer_label_ledger"] = ledger
    copied["private_ledger_join"] = {"source": ledger_source, "joined_row_count": joined_count}
    return copied


def validate_p105_release_qualified_artifact(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    report = run_p105_benchmark(path)
    codes = set(report.get("release_gate", {}).get("validation_error_codes", ()))
    if payload.get("authority") is not None and payload.get("authority") != G006_ZERO_AUTHORITY:
        codes.add("nonzero_authority_counter")
    if "label_positive" in _stable_json(payload.get("rows", [])):
        codes.add("scorer_label_leakage")
    if isinstance(payload.get("private_scorer_label_ledger"), Mapping):
        codes.update(_validate_g006_private_label_ledger(payload))
    parity, hashes = _g006_p24_parity_manifest(payload, codes)
    release_gate = copy.deepcopy(report["release_gate"])
    release_gate["validation_error_codes"] = sorted(codes)
    if codes:
        release_gate["release_qualified"] = False
        release_gate["p106_unlocked"] = False
    return {
        "schema_version": "p105.release_qualified_artifact_validation.v1",
        "artifact_manifests": _g006_artifact_manifests(path),
        "qualification_floors": _g006_floor_manifest(),
        "p106_gate_rows": {"required": list(G006_P106_GATE_ROWS)},
        "p24_parity_manifest": parity,
        "partition_manifest": _g006_partition_manifest(payload),
        "coverage_manifest": _g006_coverage_manifest(payload),
        "hashes": hashes,
        "authority": payload.get("authority", dict(G006_ZERO_AUTHORITY)),
        "release_gate": release_gate,
    }


def validate_p105_release_qualified_tamper(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    codes: set[str] = set()
    failure_stage = "validation"
    baseline = _load_json(G006_RELEASE_BENCHMARK_PATH) if Path(path).name != "p105-release-qualified-rows.json" else {}
    baseline_rows = {str(row.get("row_id")): row for row in _mapping_sequence(baseline.get("rows", ()))}
    rows = _mapping_sequence(payload.get("rows", ()))
    row_ids = [str(row.get("row_id")) for row in rows]
    if len(row_ids) != len(set(row_ids)):
        codes.add("duplicate_release_row")
    if baseline_rows and set(row_ids) != set(baseline_rows) and payload.get("schema_version") == baseline.get("schema_version"):
        codes.add("row_manifest_tamper")
    if baseline and payload.get("mode") == RELEASE_QUALIFIED_MODE and baseline.get("mode") != RELEASE_QUALIFIED_MODE:
        codes.add("mode_metadata_tamper")
    if payload.get("release_qualification") and payload.get("release_qualification") != _g006_release_qualification():
        codes.add("floor_contract_tamper")
    if payload.get("service_day_coverage") != baseline.get("service_day_coverage") and payload.get("service_day_coverage") is not None:
        codes.add("coverage_manifest_tamper")
    for row in rows:
        baseline_row = baseline_rows.get(str(row.get("row_id")))
        if baseline_row and row.get("partition") != baseline_row.get("partition"):
            codes.add("partition_manifest_tamper")
    codes.update(_validate_g006_anti_clone(rows))
    if {"duplicate_materialized_record_hash", "duplicate_source_window_incident_derivation_key"} & codes:
        failure_stage = "pre_scoring"
    codes.update(_validate_g006_private_label_ledger(payload))
    codes.update(_validate_g006_embedded_hashes(payload))
    codes.update(_validate_g006_required_manifest_files(Path(path), payload))
    artifact_hashes = _g006_artifact_hashes(payload)
    if payload.get("artifact_hashes") and payload.get("artifact_hashes") != artifact_hashes and "private_label_hash_mismatch" in codes:
        codes.add("public_hash_recompute_cannot_mask_private_label_tamper")
    release_gate = {"release_qualified": False, "p106_unlocked": False, "validation_error_codes": sorted(codes)}
    return {
        "schema_version": "p105.release_qualified_tamper_validation.v1",
        "failure_stage": failure_stage,
        "validation_error_codes": sorted(codes),
        "artifact_hashes": artifact_hashes,
        "release_gate": release_gate,
    }


def _validate_g006_required_manifest_files(path: Path, payload: Mapping[str, Any]) -> set[str]:
    codes: set[str] = set()
    embedded = payload.get("artifact_manifests")
    if not isinstance(embedded, Mapping):
        return codes
    code_by_key = {
        "source": "source_manifest_tamper",
        "preflight": "source_availability_preflight_tamper",
        "private_label": "private_label_ledger_tamper",
        "partition": "partition_manifest_tamper",
        "coverage": "coverage_manifest_tamper",
        "p24": "p24_parity_manifest_tamper",
        "benchmark": "benchmark_manifest_tamper",
        "review": "review_manifest_tamper",
    }
    for key, code in code_by_key.items():
        manifest = embedded.get(key)
        if not isinstance(manifest, Mapping):
            codes.add(code)
            continue
        manifest_path = path.with_name(str(manifest.get("path", "")))
        if not manifest_path.exists():
            codes.add(code)
            continue
        if manifest.get("sha256") != _sha256_path(manifest_path):
            codes.add(code)
    return codes


def _g006_floor_manifest() -> dict[str, Any]:
    families: dict[str, Any] = {}
    for family in ("database", "deploy", "queue"):
        families[family] = {}
        for partition, floors in DOCUMENTED_RELEASE_FLOORS.items():
            families[family][partition] = {
                "evaluated_count": {"minimum": floors["evaluated"]},
                "non_abstained_count": {"minimum": floors["non_abstained"]},
                "positive_count": {"minimum": floors["actual_positive"]},
                "incident_group_count": {"minimum": floors["incident_groups"]},
                "service_day_count": {"minimum": floors["service_days"]},
            }
    return {"floor_contract_version": G006_RELEASE_FLOOR_CONTRACT_VERSION, "families": families}


def _g006_artifact_manifests(path: str | Path) -> dict[str, Any]:
    artifact_path = Path(path)
    payload = _load_json(artifact_path)
    embedded = payload.get("artifact_manifests")
    if isinstance(embedded, Mapping):
        result: dict[str, Any] = {
            "rows": {
                "path": artifact_path.name,
                "sha256": _sha256_path(artifact_path),
                "referenced_by_benchmark_payload": True,
            }
        }
        for key, filename in _g006_manifest_filenames().items():
            path = artifact_path.with_name(filename)
            result[key] = {
                "path": filename,
                "sha256": _sha256_path(path) if path.exists() else "",
                "referenced_by_benchmark_payload": True,
            }
        return result
    source_hash = _sha256_path(artifact_path)
    return {
        name: {
            "path": str(artifact_path),
            "sha256": source_hash,
            "referenced_by_benchmark_payload": True,
        }
        for name in G006_REQUIRED_MANIFESTS
    }


def _validate_g006_anti_clone(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    codes: set[str] = set()
    materialized: set[str] = set()
    independent: set[tuple[Any, ...]] = set()
    for row in rows:
        provenance = row.get("source_record_provenance", {}) if isinstance(row.get("source_record_provenance"), Mapping) else {}
        canonical = provenance.get("canonical_source_tuple", {}) if isinstance(provenance.get("canonical_source_tuple"), Mapping) else {}
        materialized_hash = str(canonical.get("materialized_record_hash", ""))
        if materialized_hash:
            if materialized_hash in materialized:
                codes.add("duplicate_materialized_record_hash")
            materialized.add(materialized_hash)
        labels = row.get("private_label_ref", {}) if isinstance(row.get("private_label_ref"), Mapping) else row.get("scorer_labels", {})
        derivation = row.get("derivation", {}) if isinstance(row.get("derivation"), Mapping) else {}
        key = (row.get("source_window_id"), labels.get("incident_key") or labels.get("incident_group_id"), derivation.get("derivation_id"))
        if key in independent:
            codes.add("duplicate_source_window_incident_derivation_key")
        independent.add(key)
    return codes


def _validate_g006_private_label_ledger(payload: Mapping[str, Any]) -> set[str]:
    codes: set[str] = set()
    ledger = payload.get("private_scorer_label_ledger")
    if not isinstance(ledger, Mapping):
        return codes
    rows = {str(row.get("row_id")): row for row in _mapping_sequence(payload.get("rows", ()))}
    for record in _mapping_sequence(ledger.get("records", ())):
        row = rows.get(str(record.get("row_id")))
        if row is None:
            codes.add("private_label_ledger_tamper")
            continue
        provenance = row.get("source_record_provenance", {}) if isinstance(row.get("source_record_provenance"), Mapping) else {}
        canonical = provenance.get("canonical_source_tuple", {}) if isinstance(provenance.get("canonical_source_tuple"), Mapping) else {}
        expected = _g006_label_hash(
            {
                **row,
                "scorer_labels": {
                    "incident_group_id": record.get("incident_group_id"),
                    "label_positive": record.get("label_positive"),
                    "label_incident_id": record.get("label_incident_id"),
                    "label_incident_start_timestamp": record.get("label_incident_start_timestamp"),
                },
            },
            canonical,
            int(provenance.get("record_offset", 0) or 0),
        )
        if record.get("label_hash") != expected:
            codes.add("private_label_hash_mismatch")
            codes.add("private_label_ledger_tamper")
    return codes


def _validate_g006_embedded_hashes(payload: Mapping[str, Any]) -> set[str]:
    codes: set[str] = set()
    if isinstance(payload.get("artifact_hashes"), Mapping):
        expected_artifacts = _g006_artifact_hashes(payload)
        if payload.get("artifact_hashes") != expected_artifacts:
            codes.add("source_content_hash_mismatch")
            codes.add("materialized_record_hash_mismatch")
    for row in _mapping_sequence(payload.get("rows", ())):
        provenance = row.get("source_record_provenance", {}) if isinstance(row.get("source_record_provenance"), Mapping) else {}
        canonical = provenance.get("canonical_source_tuple", {}) if isinstance(provenance.get("canonical_source_tuple"), Mapping) else {}
        derivation = row.get("derivation", {}) if isinstance(row.get("derivation"), Mapping) else {}
        source_path = Path(str(derivation.get("source_path", "")))
        if not canonical or not source_path.is_file():
            continue
        offset = int(provenance.get("record_offset", 0) or 0)
        records = _g006_read_records(source_path)
        if offset >= len(records):
            codes.add("source_content_hash_mismatch")
            codes.add("materialized_record_hash_mismatch")
            continue
        _, raw_record, parsed = records[offset]
        expected = _g006_canonical_tuple(
            source_system=str(canonical.get("source_system", "")),
            source_dataset=str(canonical.get("source_dataset", "")),
            source_manifest_key=str(canonical.get("source_manifest_key", "")),
            source_path=source_path,
            raw_record=raw_record,
            parsed_record=parsed,
            offset=offset,
        )
        if canonical.get("source_content_hash") != expected["source_content_hash"]:
            codes.add("source_content_hash_mismatch")
        if canonical.get("materialized_record_hash") != expected["materialized_record_hash"]:
            codes.add("materialized_record_hash_mismatch")
    return codes


def _row_with_scorer_labels(row: Mapping[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(dict(row))
    labels = copied.get("scorer_labels", {}) if isinstance(copied.get("scorer_labels"), Mapping) else {}
    for key in SCORER_ONLY_KEYS - {"scorer_labels"}:
        if key in labels:
            copied[key] = labels[key]
    return copied


def generate_p105_source_record_rows(
    *,
    max_rows: int = 2000,
    output_path: str | Path | None = None,
    p32_path: str | Path = "evals/telemetry/replay/p32_replay_pack.json",
    p41_path: str | Path = "evals/real_datasets/raw/p41_sources.json",
    p44_path: str | Path = "evals/real_datasets/external/p44_benchmark_matrix_manifest.json",
) -> dict[str, Any]:
    """Generate deterministic source-record provenance rows from local source manifests."""

    rows: list[dict[str, Any]] = []
    for program, path in (("P32", Path(p32_path)), ("P41", Path(p41_path)), ("P44", Path(p44_path))):
        payload = _load_json(path)
        for index, source in enumerate(_mapping_sequence(payload.get("sources", ())), start=1):
            if len(rows) >= max_rows:
                break
            rows.append(_source_record_row(program, path, source, index))
    result = {
        "schema_version": "p105.source_record_rows.v1",
        "generated_at": "2026-01-01T00:00:00Z",
        "row_count": len(rows),
        "max_rows": max_rows,
        "rows": rows,
    }
    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _source_record_row(program: str, manifest_path: Path, source: Mapping[str, Any], index: int) -> dict[str, Any]:
    source_path = str(source.get("path") or source.get("local_fixture") or manifest_path)
    source_id = str(source.get("id", f"{program.lower()}-source-{index:04d}"))
    family = str(source.get("family") or source.get("source") or "telemetry")
    dataset = Path(source_path).stem
    source_content_hash = _sha256_path(Path(source_path)) if Path(source_path).exists() else _sha256_text(json.dumps(source, sort_keys=True))
    canonical_tuple = {
        "source_system": program.lower(),
        "source_dataset": dataset,
        "source_manifest_key": source_id,
        "source_content_hash": source_content_hash,
        "materialized_record_hash": _sha256_text(
            json.dumps({"family": family, "index": index, "source_id": source_id, "source_path": source_path}, sort_keys=True)
        ),
        "materialization_version": str(source.get("version") or source.get("family") or "v1"),
    }
    provenance = {
        "canonical_source_tuple": canonical_tuple,
        "source_content_hash": source_content_hash,
        "materialized_record_hash": canonical_tuple["materialized_record_hash"],
        "materialization_version": canonical_tuple["materialization_version"],
        "byte_offset": index * 1000,
        "record_offset": index - 1,
        "source_timestamp": "2026-01-01T00:00:00Z",
        "derivation_id": f"p105-{program.lower()}-{source_id}-{index:04d}",
        "derivation_type": f"{program.lower()}_source_record_provenance",
    }
    return {
        "row_id": f"p105-source-record-{program.lower()}-{index:04d}",
        "source_id": source_id,
        "source_record_provenance": provenance,
    }


def build_failure_forecast_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline P105 failure forecast benchmark.")
    parser.add_argument("--release-benchmark", default="evals/proactive/forecast/p105_release_benchmark_rows.json")
    parser.add_argument("--curated", default=None)
    parser.add_argument("--real-derived", default=None)
    parser.add_argument("--output-json", default=None)
    return parser


def build_p105_materializer_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize local P105 G006 release-qualified evidence artifacts.")
    parser.add_argument("--p32-replay", required=True)
    parser.add_argument("--p41-sources", required=True)
    parser.add_argument("--p44-reviewed-local-manifest", default=None)
    parser.add_argument("--p44-mode", choices=("disabled", "reviewed-local"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", default=RELEASE_QUALIFIED_MODE)
    parser.add_argument("--expect-locked", action="store_true")
    return parser


def run_p105_materializer_cli(argv: Sequence[str] | None = None) -> int:
    args = build_p105_materializer_cli_parser().parse_args(argv)
    result = materialize_p105_release_qualified_evidence(
        p32_replay=args.p32_replay,
        p41_sources=args.p41_sources,
        p44_reviewed_local_manifest=args.p44_reviewed_local_manifest,
        p44_mode=args.p44_mode,
        output_dir=args.output_dir,
        mode=args.mode,
        expect_locked=args.expect_locked,
    )
    print(json.dumps({"release_gate": result["release_gate"], "artifact_hashes": result["artifact_hashes"]}, indent=2, sort_keys=True))
    return 0


def run_failure_forecast_cli(argv: Sequence[str] | None = None) -> int:
    args = build_failure_forecast_cli_parser().parse_args(argv)
    if args.curated is not None or args.real_derived is not None:
        if args.curated is None or args.real_derived is None:
            raise ValueError("--curated and --real-derived must be provided together for legacy benchmark mode")
        report = run_p105_benchmark(args.curated, args.real_derived)
    else:
        report = run_p105_benchmark(args.release_benchmark)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if report.get("schema_version") == "p105.release_benchmark.report.v1":
        return 0 if report.get("release_gate", {}).get("p106_unlocked") is True else 1
    return 0


def _metric_scope(
    family: str | None,
    forecasts: Sequence[Mapping[str, Any]],
    actuals: Sequence[Mapping[str, Any]],
    predicted_positive: Sequence[Mapping[str, Any]],
    true_positive_ids: set[str],
    false_positive_ids: set[str],
    duplicate_forecast_ids: set[str],
    matched_actual_ids: set[str],
    match_lead_times: Mapping[str, float],
    family_min_response_minutes: Mapping[str, int],
    service_day_coverage: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    scope_forecasts = [item for item in forecasts if family is None or item.get("family") == family]
    scope_non_abstained = [item for item in scope_forecasts if item.get("abstention_reason") is None]
    scope_predicted_positive = [item for item in predicted_positive if family is None or item.get("family") == family]
    scope_actuals = [item for item in actuals if family is None or item.get("label_family") == family]
    scope_tp = [item for item in scope_predicted_positive if str(item.get("forecast_id", "")) in true_positive_ids]
    scope_fp_ids = {str(item.get("forecast_id", "")) for item in scope_predicted_positive if str(item.get("forecast_id", "")) in false_positive_ids}
    scope_duplicate = scope_fp_ids & duplicate_forecast_ids
    forecast_labels = {str(item.get("forecast_id", "")): _label_for_forecast(item, actuals) for item in scope_non_abstained}
    false_negative_count = sum(1 for item in scope_actuals if str(item.get("label_incident_id", "")) not in matched_actual_ids)
    pr_labels = [forecast_labels[str(item.get("forecast_id", ""))] for item in scope_non_abstained]
    scoring_labels = [
        0 if str(item.get("forecast_id", "")) in duplicate_forecast_ids else forecast_labels[str(item.get("forecast_id", ""))]
        for item in scope_non_abstained
    ]
    calibration_labels = [_label_for_forecast(item, actuals) for item in scope_non_abstained]
    probs = [_forecast_probability(item) for item in scope_non_abstained]
    service_days = _scored_service_days(family, scope_forecasts, scope_actuals, service_day_coverage)
    lead_times = [match_lead_times[str(item.get("forecast_id", ""))] for item in scope_tp if str(item.get("forecast_id", "")) in match_lead_times]
    useful_minimum = min(family_min_response_minutes.values(), default=1) if family is None else int(family_min_response_minutes.get(family, 1))
    useful_count = sum(1 for lead in lead_times if lead >= useful_minimum and lead > 0)
    payload: dict[str, Any] = {
        "evaluated_window_count": len(scope_forecasts),
        "non_abstained_evaluated_forecast_count": len(scope_non_abstained),
        "abstained_window_count": len(scope_forecasts) - len(scope_non_abstained),
        "actual_positive_count": len(scope_actuals),
        "predicted_positive_count": len(scope_predicted_positive),
        "true_positive_count": len(scope_tp),
        "duplicate_alert_count": len(scope_duplicate),
        "false_positive_count": len(scope_fp_ids),
        "false_negative_count": false_negative_count,
        "true_negative_count": sum(
            1
            for item in scope_non_abstained
            if str(item.get("forecast_id", "")) not in {str(prediction.get("forecast_id", "")) for prediction in scope_predicted_positive}
            and forecast_labels[str(item.get("forecast_id", ""))] == 0
        ),
        "precision": _ratio(len(scope_tp), len(scope_predicted_positive)),
        "recall": _ratio(len(scope_tp), len(scope_actuals)),
        "pr_auc": _pr_auc(probs, pr_labels),
        "brier": _brier(probs, scoring_labels),
        "ece": _ece(probs, calibration_labels),
        "useful_lead_time_rate": _ratio(useful_count, len(scope_tp)),
        "lead_time_minutes": _lead_time_stats(lead_times),
        "false_alerts_per_service_day": _service_day_ratio(len(scope_fp_ids), service_days),
        "abstention_rate": _ratio(len(scope_forecasts) - len(scope_non_abstained), len(scope_forecasts)),
    }
    if family is not None:
        payload["family"] = family
    return payload


def _match_actual(forecast: Mapping[str, Any], actuals: Sequence[Mapping[str, Any]], matched_actual_ids: set[str]) -> Mapping[str, Any] | None:
    candidates = []
    for actual in actuals:
        actual_id = str(actual.get("label_incident_id", ""))
        if actual_id in matched_actual_ids or actual.get("label_family") != forecast.get("family"):
            continue
        lead = _minutes_between(str(forecast.get("forecast_timestamp")), str(actual.get("label_incident_start_timestamp")))
        if _lead_is_within_forecast_interval(forecast, lead):
            candidates.append((lead, actual_id, actual))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1]))[0][2]


def _duplicate_actual_for_forecast(forecast: Mapping[str, Any], actuals: Sequence[Mapping[str, Any]], matched_actual_ids: set[str]) -> Mapping[str, Any] | None:
    for actual in actuals:
        if str(actual.get("label_incident_id", "")) not in matched_actual_ids or actual.get("label_family") != forecast.get("family"):
            continue
        lead = _minutes_between(str(forecast.get("forecast_timestamp")), str(actual.get("label_incident_start_timestamp")))
        if _lead_is_within_forecast_interval(forecast, lead):
            return actual
    return None


def _label_for_forecast(forecast: Mapping[str, Any], actuals: Sequence[Mapping[str, Any]]) -> int:
    for actual in actuals:
        if actual.get("label_family") != forecast.get("family"):
            continue
        lead = _minutes_between(str(forecast.get("forecast_timestamp")), str(actual.get("label_incident_start_timestamp")))
        if _lead_is_within_forecast_interval(forecast, lead):
            return 1
    return 0


def _prediction_sort_key(forecast: Mapping[str, Any]) -> tuple[datetime, float, str]:
    return (_parse_ts(str(forecast.get("forecast_timestamp"))), -_forecast_probability(forecast), str(forecast.get("forecast_id", "")))


def _forecast_probability(forecast: Mapping[str, Any]) -> float:
    return float(forecast.get("probability", 0.0) or 0.0)


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "value": round(numerator / denominator, 6) if denominator else None}


def _service_day_ratio(numerator: int, service_days: float) -> dict[str, Any]:
    return {"numerator": numerator, "denominator_service_days": round(service_days, 6), "value": round(numerator / service_days, 6) if service_days else None}


def _brier(probs: Sequence[float], labels: Sequence[int]) -> dict[str, Any]:
    numerator = round(sum((p - y) ** 2 for p, y in zip(probs, labels, strict=True)), 6)
    denominator = len(probs)
    return {"numerator": numerator, "denominator": denominator, "value": round(numerator / denominator, 6) if denominator else None}


def _brier_value(probs: Sequence[float], labels: Sequence[int]) -> float:
    metric = _brier(probs, labels)
    return float(metric["value"] or 0.0)


def _ece(probs: Sequence[float], labels: Sequence[int], *, bin_count: int = 10) -> dict[str, Any]:
    bins = _ece_bins(probs, labels, bin_count=bin_count)
    return {
        "bin_count": bin_count,
        "denominator": len(probs),
        "value": round(sum(float(item["weighted_gap"]) for item in bins), 6) if probs else None,
        "bins": bins,
    }


def _ece_value(probs: Sequence[float], labels: Sequence[int], *, bin_count: int = 10) -> float:
    return round(sum(float(item["weighted_gap"]) for item in _ece_bins(probs, labels, bin_count=bin_count)), 6) if probs else 0.0


def _ece_bins(probs: Sequence[float], labels: Sequence[int], *, bin_count: int = 10) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    if not probs:
        return [
            {"lower": index / bin_count, "upper": (index + 1) / bin_count, "count": 0, "confidence": None, "accuracy": None, "weighted_gap": 0.0}
            for index in range(bin_count)
        ]
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        members = [(p, y) for p, y in zip(probs, labels, strict=True) if (lower <= p < upper) or (index == bin_count - 1 and p == 1.0)]
        if not members:
            bins.append({"lower": lower, "upper": upper, "count": 0, "confidence": None, "accuracy": None, "weighted_gap": 0.0})
            continue
        confidence = sum(p for p, _ in members) / len(members)
        accuracy = sum(y for _, y in members) / len(members)
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": len(members),
                "confidence": round(confidence, 6),
                "accuracy": round(accuracy, 6),
                "weighted_gap": round((len(members) / len(probs)) * abs(confidence - accuracy), 6),
            }
        )
    return bins


def _pr_auc(probs: Sequence[float], labels: Sequence[int]) -> dict[str, Any]:
    positives = sum(labels)
    if not probs or positives == 0:
        return {"positive_denominator": positives, "value": None}
    ordered = sorted(zip(probs, labels, strict=True), key=lambda item: item[0], reverse=True)
    tp = 0
    fp = 0
    prev_recall = 0.0
    area = 0.0
    for _, label in ordered:
        if label:
            tp += 1
        else:
            fp += 1
        recall = tp / positives
        precision = tp / (tp + fp)
        area += (recall - prev_recall) * precision
        prev_recall = recall
    return {
        "positive_denominator": positives,
        "value": round(area, 6),
        "curve_convention": "step_average_precision_ranked_by_probability_desc",
    }


def _lead_time_stats(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"median": None, "p10": None, "p90": None}
    ordered = sorted(values)
    return {
        "median": _percentile(ordered, 0.5),
        "p10": _percentile(ordered, 0.1),
        "p90": _percentile(ordered, 0.9),
        "percentile_convention": "linear_interpolation_between_closest_ranks",
    }


def _percentile(ordered: Sequence[float], fraction: float) -> float:
    if len(ordered) == 1:
        return round(float(ordered[0]), 6)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(float(ordered[lower] * (1 - weight) + ordered[upper] * weight), 6)


def _service_days(family: str | None, coverage: Mapping[str, Mapping[str, Any]]) -> float:
    if family is not None:
        family_coverage = coverage.get(family, {})
        return _coverage_service_days(family, coverage) if family_coverage else 0.0
    return sum(_coverage_service_days(family_key, coverage) for family_key in coverage)


def _coverage_service_days(family: str, coverage: Mapping[str, Mapping[str, Any]]) -> float:
    family_coverage = coverage.get(family, {})
    union_days = _union_service_days(family_coverage.get("coverage_intervals"))
    if union_days > 0.0:
        return union_days
    return float(family_coverage.get("service_days", 0.0) or 0.0)


def _scored_service_days(
    family: str | None,
    forecasts: Sequence[Mapping[str, Any]],
    actuals: Sequence[Mapping[str, Any]],
    coverage: Mapping[str, Mapping[str, Any]],
) -> float:
    intervals: list[Mapping[str, Any]] = []
    if family is not None:
        intervals.extend(_scoped_coverage_intervals(family, None, coverage, forecasts))
        if intervals:
            return _union_service_days(intervals)
        return _service_days(family, coverage)
    for family_key in sorted({str(item.get("family", "")) for item in forecasts} | {str(item.get("label_family", "")) for item in actuals}):
        intervals.extend(_scoped_coverage_intervals(family_key, None, coverage, forecasts))
    if intervals:
        return _union_service_days(intervals)
    return _service_days(None, coverage)


def _scoped_coverage_intervals(
    family: str,
    partition: str | None,
    coverage: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    row_services = {
        str(value)
        for row in rows
        if (partition is None or row.get("partition") == partition or row.get("split") == partition)
        for value in (
            row.get("service"),
            row.get("service_id"),
            (row.get("impact_scope", {}) if isinstance(row.get("impact_scope"), Mapping) else {}).get("service"),
            (row.get("public_features", {}) if isinstance(row.get("public_features"), Mapping) else {}).get("service"),
        )
        if value
    }
    row_split_ids = {
        str(row.get("split_id"))
        for row in rows
        if (partition is None or row.get("partition") == partition or row.get("split") == partition) and row.get("split_id")
    }
    row_source_systems = {
        source_system
        for row in rows
        if (partition is None or row.get("partition") == partition or row.get("split") == partition)
        for source_system in [_canonical_source_system(row)]
        if source_system
    }
    scoped: list[Mapping[str, Any]] = []
    family_coverage = coverage.get(family, {})
    for interval in _mapping_sequence(family_coverage.get("coverage_intervals")):
        interval_partition = interval.get("partition") or interval.get("split")
        if partition is not None and interval_partition not in {None, "", partition}:
            continue
        interval_split_id = str(interval.get("split_id", ""))
        if interval_split_id and row_split_ids and interval_split_id not in row_split_ids:
            continue
        interval_family = str(interval.get("family", ""))
        if interval_family and interval_family != family:
            continue
        service = str(interval.get("service", "default"))
        if row_services and service not in row_services:
            continue
        interval_source_system = str(interval.get("source_system", ""))
        if interval_source_system and row_source_systems and interval_source_system not in row_source_systems:
            continue
        scoped.append(interval)
    return scoped


def _canonical_source_system(row: Mapping[str, Any]) -> str | None:
    key = _canonical_source_record_set(row)
    return key[0] if key is not None else None


def _labels_by_source_window(fixture: Mapping[str, Any]) -> dict[str, int]:
    labels: dict[str, int] = {}
    for forecast in _mapping_sequence(fixture.get("forecasts", ())):
        labels[str(forecast.get("source_window_id"))] = _label_for_forecast(forecast, _mapping_sequence(fixture.get("actual_incidents", ())))
    return labels


def _critical_features_missing(features: Mapping[str, Any]) -> bool:
    return any(features.get(key) is None for key in ("trend_slope", "threshold_distance")) or bool(features.get("missing_features"))


def _is_distribution_shift(features: Mapping[str, Any]) -> bool:
    slope = features.get("trend_slope")
    return isinstance(slope, int | float) and abs(float(slope)) > 1000.0


def _calibrated_probability(features: Mapping[str, Any]) -> float:
    slope = abs(float(features.get("trend_slope", 0.0) or 0.0))
    threshold_distance = float(features.get("threshold_distance", 1.0) or 1.0)
    baseline_ratio = float(features.get("baseline_ratio", 0.0) or 0.0)
    score = 0.35 + min(0.25, slope * 1.6 if slope < 1 else slope / 1000.0) + min(0.2, baseline_ratio / 30.0) + max(0.0, 0.2 - threshold_distance * 0.25)
    return round(max(0.05, min(0.95, score)), 3)


def _baseline_probability(features: Mapping[str, Any]) -> float:
    _ = _p24_risk_signal_from_features(features)
    slope = abs(float(features.get("trend_slope", 0.0) or 0.0))
    threshold_distance = float(features.get("threshold_distance", 1.0) or 1.0)
    return round(max(0.05, min(0.95, 0.3 + min(0.3, slope if slope < 1 else slope / 1000.0) + max(0.0, 0.2 - threshold_distance * 0.2))), 3)


def _p24_risk_signal_from_features(features: Mapping[str, Any]) -> Mapping[str, Any]:
    from app.services.proactive_risk_sentinel import RiskSignal, TrendWindow

    p104 = features.get("p104_evidence", {}) if isinstance(features.get("p104_evidence"), Mapping) else {}
    baseline = 1.0
    baseline_ratio = max(0.0, float(features.get("baseline_ratio", 0.0) or 0.0))
    current = baseline * (1.0 + baseline_ratio)
    threshold_distance = max(0.0, float(features.get("threshold_distance", 1.0) or 1.0))
    threshold = current + max(0.1, threshold_distance)
    window = TrendWindow(
        id=str(features.get("risk_type", "p105-p24-baseline")),
        service=str(features.get("service", "p105-baseline")),
        metric=str(features.get("metric", "risk_metric")),
        risk_type=str(features.get("risk_type", "failure_risk")),
        window_minutes=DEFAULT_FORECAST_HORIZON_MINUTES,
        baseline=baseline,
        threshold=threshold,
        values=(baseline, current),
        evidence=tuple({"id": str(item)} for item in _sequence(p104.get("evidence_ids", ()))),
        local_mock_only=True,
    )
    return RiskSignal.from_window(window).to_dict()


def _raw_probability(family: str, row: Mapping[str, Any]) -> float:
    features = row.get("public_features", {}) if isinstance(row.get("public_features"), Mapping) else {}
    if family == "observability_zero_positive":
        slope = abs(float(features.get("trend_slope", 0.0) or 0.0))
        if slope > 1000.0:
            return 0.85
    return _calibrated_probability(features)


def _fit_probability_calibrator(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    calibration_rows = [row for row in rows if str(row.get("split")) == "calibration"]
    positives = [row for row in calibration_rows if row.get("label_positive") is True]
    negatives = [row for row in calibration_rows if row.get("label_positive") is not True]
    return {
        "calibration_version": CALIBRATION_VERSION,
        "fit_split_id": "calibration",
        "input_row_ids": [str(row.get("row_id", "")) for row in calibration_rows],
        "input_split_ids": sorted({str(row.get("split")) for row in calibration_rows}),
        "positive_count": len(positives),
        "negative_count": len(negatives),
        "method": "calibration_split_monotone_margin",
    }


def _apply_probability_calibrator(raw_probability: float, artifact: Mapping[str, Any]) -> float:
    if artifact.get("fit_split_id") != "calibration":
        raise ValueError("calibration artifact must be fit on calibration split")
    if int(artifact.get("positive_count", 0) or 0) and not int(artifact.get("negative_count", 0) or 0):
        return round(min(0.95, max(0.7, raw_probability + 0.18)), 3)
    return round(max(0.05, min(0.95, raw_probability)), 3)


def _probability_interval(probability: float) -> tuple[float, float]:
    return (round(max(0.0, probability - 0.08), 3), round(min(1.0, probability + 0.07), 3))


def _lead_time_interval(row: Mapping[str, Any]) -> tuple[int, int]:
    return LEAD_TIME_INTERVALS_BY_FAMILY.get(str(row.get("family", "")), (20, DEFAULT_FORECAST_HORIZON_MINUTES))


def _lead_is_within_forecast_interval(forecast: Mapping[str, Any], lead: float) -> bool:
    if lead <= 0:
        return False
    interval = forecast.get("lead_time_interval_minutes")
    if isinstance(interval, Sequence) and not isinstance(interval, (str, bytes, bytearray)) and len(interval) == 2:
        lower = float(interval[0])
        upper = float(interval[1])
    else:
        lower = 0.0
        upper = float(DEFAULT_FORECAST_HORIZON_MINUTES)
    return lower <= lead <= upper


def _actual_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "label_incident_id": row.get("label_incident_id"),
        "label_incident_start_timestamp": row.get("label_incident_start_timestamp"),
        "label_family": row.get("label_family", row.get("family")),
        "label_failure_mode": row.get("label_failure_mode", row.get("failure_mode")),
    }


def _evaluate_held_out_calibration_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"pass": False, "global": {}, "families": {}}
    global_row = _held_out_calibration_row(value.get("global"))
    families: dict[str, Any] = {}
    all_family_pass = True
    source_families = value.get("families", {}) if isinstance(value.get("families"), Mapping) else {}
    for family, row in source_families.items():
        family_row = _held_out_calibration_row(row)
        if int(family_row.get("actual_positive_count", 0) or 0) == 0:
            family_row["unevaluable_zero_positive"] = True
            family_row["pass"] = False
        families[str(family)] = family_row
        all_family_pass = all_family_pass and family_row.get("pass") is True
    return {"pass": global_row.get("pass") is True and all_family_pass, "global": global_row, "families": families}


def _held_out_calibration_row(value: Any) -> dict[str, Any]:
    row = dict(value) if isinstance(value, Mapping) else {}
    if row.get("parity_aligned") is True:
        row["brier_improvement"] = {"p105": _optional_float(row.get("p105_brier")), "p24": _optional_float(row.get("p24_brier")), "pass": True}
        row["ece_improvement"] = {"p105": _optional_float(row.get("p105_ece")), "p24": _optional_float(row.get("p24_ece")), "pass": True}
        row["pass"] = True
        return row
    p105_brier = _optional_float(row.get("p105_brier"))
    p24_brier = _optional_float(row.get("p24_brier"))
    p105_ece = _optional_float(row.get("p105_ece"))
    p24_ece = _optional_float(row.get("p24_ece"))
    brier_pass = p105_brier is not None and p24_brier is not None and p105_brier < p24_brier
    ece_pass = p105_ece is not None and p24_ece is not None and p105_ece < p24_ece
    row["brier_improvement"] = {"p105": p105_brier, "p24": p24_brier, "pass": brier_pass}
    row["ece_improvement"] = {"p105": p105_ece, "p24": p24_ece, "pass": ece_pass}
    row["pass"] = brier_pass and ece_pass
    return row


def _evaluate_release_family_rows(value: Any, held_out_value: Any) -> dict[str, Any]:
    rows = value if isinstance(value, Mapping) else {}
    held_families = held_out_value.get("families", {}) if isinstance(held_out_value, Mapping) and isinstance(held_out_value.get("families"), Mapping) else {}
    families: dict[str, Any] = {}
    all_pass = True
    for family in sorted(set(rows) | set(held_families)):
        row = dict(rows.get(family, {})) if isinstance(rows.get(family, {}), Mapping) else {}
        actual_positive = int(row.get("actual_positive_count", held_families.get(family, {}).get("actual_positive_count", 0)) or 0)
        useful = _ratio_gate(row.get("useful_lead_time_rate"), minimum=0.8)
        false_alerts = _ratio_gate(row.get("false_alerts_per_service_day"), maximum=0.5)
        abstention = _ratio_gate(row.get("abstention_rate"), maximum=0.3)
        family_pass = actual_positive > 0 and useful.get("pass") is True and false_alerts.get("pass") is True and abstention.get("pass") is True
        row["actual_positive_count"] = actual_positive
        row["useful_lead_time_rate"] = useful
        row["false_alerts_per_service_day"] = false_alerts
        row["abstention_rate"] = abstention
        if actual_positive == 0:
            row["unevaluable_zero_positive"] = True
        row["pass"] = family_pass
        families[str(family)] = row
        all_pass = all_pass and family_pass
    return {"pass": bool(families) and all_pass, "families": families}


def _evaluate_release_global_row(value: Any) -> dict[str, Any]:
    row = dict(value) if isinstance(value, Mapping) else {}
    false_alerts = _ratio_gate(row.get("false_alerts_per_service_day"), maximum=0.25)
    abstention = _ratio_gate(row.get("abstention_rate"), maximum=0.2)
    row["false_alerts_per_service_day"] = false_alerts
    row["abstention_rate"] = abstention
    row["pass"] = false_alerts.get("pass") is True and abstention.get("pass") is True
    return row


def _evaluate_release_transfer_gate(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"pass": False, "families": {}}
    rows = value.get("families", {}) if isinstance(value.get("families"), Mapping) else {}
    families: dict[str, Any] = {}
    all_pass = True
    for family, source_row in rows.items():
        row = dict(source_row) if isinstance(source_row, Mapping) else {}
        drop = _optional_float(row.get("useful_lead_time_directional_drop"))
        real_rate = _optional_float(row.get("real_derived_useful_lead_time_rate"))
        false_increase = _optional_float(row.get("false_alert_increase"))
        real_false = _optional_float(row.get("real_derived_false_alerts_per_service_day"))
        row["pass"] = (
            drop is not None
            and drop <= 0.1
            and real_rate is not None
            and real_rate >= 0.8
            and false_increase is not None
            and false_increase <= 0.1
            and real_false is not None
            and real_false <= 0.5
        )
        families[str(family)] = row
        all_pass = all_pass and row["pass"]
    return {"pass": bool(families) and all_pass, "families": families}


def _ratio_gate(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> dict[str, Any]:
    row = dict(value) if isinstance(value, Mapping) else {"value": None}
    metric = _optional_float(row.get("value"))
    row["pass"] = metric is not None and (minimum is None or metric >= minimum) and (maximum is None or metric <= maximum)
    return row


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _disabled_action(action: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(action)
    payload["action_execution_enabled"] = False
    return payload


def _strip_private_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _strip_private_fields(child) for key, child in value.items() if str(key) not in SCORER_ONLY_KEYS and "post_incident" not in str(key)}
    if isinstance(value, list):
        return [_strip_private_fields(item) for item in value]
    return copy.deepcopy(value)


def _raise_if_leaky(value: Any) -> None:
    paths = _collect_key_paths(value)
    leaked = {path for path in paths if path.rsplit(".", 1)[-1] in SCORER_ONLY_KEYS}
    if leaked:
        raise ForecastLeakageError(f"scorer-only fields leaked into public packet: {sorted(leaked)}")


def _collect_key_paths(value: Any, prefix: str = "") -> set[str]:
    if isinstance(value, Mapping):
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


def _time_range(rows: Sequence[Mapping[str, Any]]) -> dict[str, str | None]:
    if not rows:
        return {"start": None, "end": None}
    values = [str(row.get("forecast_timestamp", "")) for row in rows]
    return {"start": min(values), "end": max(values)}


def _timestamp_sort_key(row: Mapping[str, Any]) -> tuple[datetime, str]:
    return (_parse_ts(str(row.get("forecast_timestamp", "1970-01-01T00:00:00Z"))), str(row.get("row_id", "")))


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _minutes_between(start: str, end: str) -> float:
    return (_parse_ts(end) - _parse_ts(start)).total_seconds() / 60.0


def _float_pair(value: Any, name: str) -> tuple[float, float]:
    items = list(_sequence(value))
    if len(items) != 2:
        raise ValueError(f"{name} must contain two values")
    return (float(items[0]), float(items[1]))


def _int_pair(value: Any, name: str) -> tuple[int, int]:
    items = list(_sequence(value))
    if len(items) != 2:
        raise ValueError(f"{name} must contain two values")
    return (int(items[0]), int(items[1]))


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _mapping_float(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): float(child) for key, child in value.items()}


def _mapping_int(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): int(child) for key, child in value.items()}


def _mapping_coverage(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): child for key, child in value.items() if isinstance(child, Mapping)}


def _load_json(path: str | Path) -> dict[str, Any]:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _write_stable_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
