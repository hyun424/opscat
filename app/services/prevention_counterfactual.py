"""Offline P108 treatment/control counterfactual estimates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


def estimate_counterfactual_effect(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Estimate bounded treatment-vs-control effect from declared offline windows."""

    treatment = _mapping_or_none(episode.get("treatment"))
    control = _mapping_or_none(episode.get("control"))
    reasons: list[str] = []

    if treatment is None:
        reasons.append("missing treatment cohort")
    if control is None:
        reasons.append("missing control cohort")
    if treatment is None or control is None:
        return _not_identifiable(reasons)

    if treatment.get("cohort_fingerprint") != control.get("cohort_fingerprint"):
        reasons.append("treatment/control fingerprint mismatch")
    if treatment.get("window") != control.get("window"):
        reasons.append("treatment/control declared windows differ")
    if treatment.get("telemetry_complete") is not True or control.get("telemetry_complete") is not True:
        reasons.append("treatment/control telemetry must be explicitly complete")
    if reasons:
        return _not_identifiable(reasons, comparable=False)

    threshold = _float(episode.get("incident_threshold"), 1.0)
    impact_scale = _float(episode.get("impact_scale"), 1.0)
    treatment_severity = _bounded(_float(treatment.get("max_severity"), 0.0), 0.0, 1.0)
    control_severity = _bounded(_float(control.get("max_severity"), 0.0), 0.0, 1.0)
    effect_size = _bounded(control_severity - treatment_severity, -1.0, 1.0)
    treatment_incident_at = _parse_time(treatment.get("incident_at"))
    control_incident_at = _parse_time(control.get("incident_at"))
    treatment_failed = treatment_severity >= threshold or treatment_incident_at is not None
    control_failed = control_severity >= threshold or control_incident_at is not None
    useful_delay_seconds = None
    if treatment_incident_at is not None and control_incident_at is not None:
        delay = int((treatment_incident_at - control_incident_at).total_seconds())
        if delay > 0:
            useful_delay_seconds = delay

    natural_recovery = bool(treatment.get("recovered_without_intervention")) and bool(control.get("recovered_without_intervention"))
    effect_direction = "neutral"
    if effect_size > 0.05:
        effect_direction = "beneficial"
    elif effect_size < -0.05:
        effect_direction = "harmful"

    avoided_impact = 0.0
    if effect_direction == "beneficial" and not natural_recovery:
        avoided_impact = round(effect_size * impact_scale, 6)

    return {
        "status": "identified",
        "reasons": [],
        "comparable": True,
        "effect_size": round(effect_size, 6),
        "effect_direction": effect_direction,
        "treatment_failed": treatment_failed,
        "control_failed": control_failed,
        "useful_delay_seconds": useful_delay_seconds,
        "avoided_impact": avoided_impact,
        "confidence": _confidence(treatment, control),
        "natural_recovery": natural_recovery,
    }


def _not_identifiable(reasons: list[str], *, comparable: bool = False) -> dict[str, Any]:
    return {
        "status": "not_identifiable",
        "reasons": reasons,
        "comparable": comparable,
        "effect_size": 0.0,
        "effect_direction": "unknown",
        "treatment_failed": None,
        "control_failed": None,
        "useful_delay_seconds": None,
        "avoided_impact": 0.0,
        "confidence": "not_identifiable",
        "natural_recovery": False,
    }


def _confidence(treatment: Mapping[str, Any], control: Mapping[str, Any]) -> str:
    sample_count = min(_int(treatment.get("sample_count"), 0), _int(control.get("sample_count"), 0))
    if sample_count >= 30:
        return "high"
    if sample_count >= 10:
        return "medium"
    return "low"


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bounded(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
