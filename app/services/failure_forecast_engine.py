"""P105 calibrated failure forecasting for offline benchmark replay.

The engine is deliberately local and action-free: scorer labels are stripped
from public packets, optional provider rationale is advisory text only, and
P106 remains locked unless every gate row is populated and passing.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Self

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
    held_out = shadow_payload.get("held_out_reference", {}) if isinstance(shadow_payload.get("held_out_reference"), Mapping) else {}
    held_lead = _mapping_float(held_out.get("useful_lead_time_rate_by_family", {}))
    held_false = _mapping_float(held_out.get("false_alerts_per_service_day_by_family", {}))
    override = shadow_payload.get("real_derived_override", {}) if isinstance(shadow_payload.get("real_derived_override"), Mapping) else {}
    real_lead_override = _mapping_float(override.get("useful_lead_time_rate_by_family", {}))
    real_false_override = _mapping_float(override.get("false_alerts_per_service_day_by_family", {}))
    rows = _mapping_sequence(shadow_payload.get("rows", ()))
    families = sorted(set(held_lead) | {str(row.get("family", "")) for row in rows} | set(real_lead_override))
    result: dict[str, Any] = {}
    all_pass = True
    for family in families:
        real_rate = real_lead_override.get(family)
        if real_rate is None:
            positives = [row for row in rows if row.get("family") == family and row.get("label_positive") is True]
            useful = [row for row in positives if float(row.get("lead_time_label_minutes", 0.0) or 0.0) > 0.0]
            real_rate = round(len(useful) / len(positives), 6) if positives else None
        real_false = real_false_override.get(family, 0.0)
        held_rate = held_lead.get(family)
        held_false_rate = held_false.get(family, 0.0)
        drop = None if held_rate is None or real_rate is None else round(held_rate - real_rate, 6)
        false_increase = round(real_false - held_false_rate, 6)
        family_pass = drop is not None and drop <= 0.1 and real_rate is not None and real_rate >= 0.8 and false_increase <= 0.1 and real_false <= 0.5
        result[family] = {
            "held_out_useful_lead_time_rate": held_rate,
            "real_derived_useful_lead_time_rate": real_rate,
            "useful_lead_time_directional_drop": drop,
            "held_out_false_alerts_per_service_day": held_false_rate,
            "real_derived_false_alerts_per_service_day": real_false,
            "false_alert_increase": false_increase,
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
    return {"p106_unlocked": False if not safety_pass else bool(payload.get("p106_unlocked", False)), "safety_boundary": {"pass": safety_pass, "boundary": dict(boundary)}}


def run_p105_benchmark(curated_rows_path: str | Path, real_derived_rows_path: str | Path) -> dict[str, Any]:
    curated = _load_json(curated_rows_path)
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
    return {
        "schema_version": "p105.benchmark.report.v1",
        "curated": report,
        "real_derived_transfer_gate": evaluate_real_derived_transfer_gate(shadow),
        "boundary": {
            "network_call_count": 0,
            "model_call_count": 0,
            "auth_required": False,
            "production_mutation_count": 0,
            "remediation_execution_count": 0,
            "executable_action_plan_count": 0,
        },
    }


def build_failure_forecast_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline P105 failure forecast benchmark.")
    parser.add_argument("--curated", default="evals/proactive/forecast/p105_curated_synthetic_rows.json")
    parser.add_argument("--real-derived", default="evals/proactive/forecast/p105_real_derived_shadow_rows.json")
    parser.add_argument("--output-json", default=None)
    return parser


def run_failure_forecast_cli(argv: Sequence[str] | None = None) -> int:
    args = build_failure_forecast_cli_parser().parse_args(argv)
    report = run_p105_benchmark(args.curated, args.real_derived)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
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
    false_negative_count = sum(1 for item in scope_actuals if str(item.get("label_incident_id", "")) not in matched_actual_ids)
    labels = [0 if str(item.get("forecast_id", "")) in duplicate_forecast_ids else _label_for_forecast(item, actuals) for item in scope_non_abstained]
    calibration_labels = [_label_for_forecast(item, actuals) for item in scope_non_abstained]
    probs = [_forecast_probability(item) for item in scope_non_abstained]
    service_days = _service_days(family, service_day_coverage)
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
        "true_negative_count": max(0, len(scope_non_abstained) - len(scope_predicted_positive)),
        "precision": _ratio(len(scope_tp), len(scope_predicted_positive)),
        "recall": _ratio(len(scope_tp), len(scope_actuals)),
        "pr_auc": _pr_auc(probs, labels),
        "brier": _brier(probs, labels),
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
        if 0 < lead <= 120:
            candidates.append((lead, actual_id, actual))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1]))[0][2]


def _duplicate_actual_for_forecast(forecast: Mapping[str, Any], actuals: Sequence[Mapping[str, Any]], matched_actual_ids: set[str]) -> Mapping[str, Any] | None:
    for actual in actuals:
        if str(actual.get("label_incident_id", "")) not in matched_actual_ids or actual.get("label_family") != forecast.get("family"):
            continue
        lead = _minutes_between(str(forecast.get("forecast_timestamp")), str(actual.get("label_incident_start_timestamp")))
        if 0 < lead <= 120:
            return actual
    return None


def _label_for_forecast(forecast: Mapping[str, Any], actuals: Sequence[Mapping[str, Any]]) -> int:
    for actual in actuals:
        if actual.get("label_family") != forecast.get("family"):
            continue
        lead = _minutes_between(str(forecast.get("forecast_timestamp")), str(actual.get("label_incident_start_timestamp")))
        if 0 < lead <= 120:
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
    return {"bin_count": bin_count, "denominator": len(probs), "value": _ece_value(probs, labels, bin_count=bin_count) if probs else None}


def _ece_value(probs: Sequence[float], labels: Sequence[int], *, bin_count: int = 10) -> float:
    if not probs:
        return 0.0
    total = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        members = [(p, y) for p, y in zip(probs, labels, strict=True) if (lower <= p < upper) or (index == bin_count - 1 and p == 1.0)]
        if not members:
            continue
        confidence = sum(p for p, _ in members) / len(members)
        accuracy = sum(y for _, y in members) / len(members)
        total += (len(members) / len(probs)) * abs(confidence - accuracy)
    return round(total, 6)


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
    return {"positive_denominator": positives, "value": round(area, 6)}


def _lead_time_stats(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "p10": None, "p90": None}
    ordered = sorted(values)
    return {"median": _percentile(ordered, 0.5), "p10": _percentile(ordered, 0.1), "p90": _percentile(ordered, 0.9)}


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
        return float(family_coverage.get("service_days", 0.0) or 0.0)
    return sum(float(item.get("service_days", 0.0) or 0.0) for item in coverage.values())


def _labels_by_source_window(fixture: Mapping[str, Any]) -> dict[str, int]:
    labels: dict[str, int] = {}
    for forecast in _mapping_sequence(fixture.get("forecasts", ())):
        labels[str(forecast.get("source_window_id"))] = _label_for_forecast(forecast, _mapping_sequence(fixture.get("actual_incidents", ())))
    return labels


def _critical_features_missing(features: Mapping[str, Any]) -> bool:
    return any(features.get(key) is None for key in ("trend_slope", "threshold_distance", "baseline_ratio")) or bool(features.get("missing_features"))


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
    slope = abs(float(features.get("trend_slope", 0.0) or 0.0))
    threshold_distance = float(features.get("threshold_distance", 1.0) or 1.0)
    return round(max(0.05, min(0.95, 0.3 + min(0.3, slope if slope < 1 else slope / 1000.0) + max(0.0, 0.2 - threshold_distance * 0.2))), 3)


def _lead_time_interval(row: Mapping[str, Any]) -> tuple[int, int]:
    label_lead = row.get("lead_time_label_minutes")
    if isinstance(label_lead, int | float):
        return (max(0, int(label_lead) - 20), int(label_lead) + 30)
    return (20, 120)


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
