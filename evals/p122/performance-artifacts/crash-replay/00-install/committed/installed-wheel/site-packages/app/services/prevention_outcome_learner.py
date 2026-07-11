"""Conservative offline P108 outcome labels and phase credit."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.services.prevention_counterfactual import estimate_counterfactual_effect

OUTCOME_LABELS = frozenset(
    {
        "prevented",
        "delayed",
        "unaffected",
        "naturally_recovered",
        "harmful",
        "inconclusive",
        "censored",
    }
)
PHASES = ("evidence_search", "forecast", "plan", "execution")
PHASE_WEIGHTS = {
    "evidence_search": 0.20,
    "forecast": 0.30,
    "plan": 0.25,
    "execution": 0.25,
}
LEAKY_EVIDENCE_SOURCES = frozenset({"private_scorer", "hidden_holdout", "future_outcome_label", "outcome_label"})


def classify_prevention_outcome(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Return the conservative P108 label with precedence reasons."""

    treatment = _mapping_or_empty(episode.get("treatment"))
    threshold = _float(episode.get("incident_threshold"), 1.0)
    treatment_severity = _float(treatment.get("max_severity"), 0.0)
    cf = estimate_counterfactual_effect(episode)
    reasons: list[str] = []

    if _has_harm(treatment, cf, treatment_severity, threshold):
        reasons.append("harm or guardrail breach overrides optimistic labels")
        return _label("harmful", reasons, cf)

    if not bool(episode.get("horizon_complete", True)) or _weak_horizon(episode):
        reasons.append("observation horizon is incomplete or below the declared minimum")
        return _label("censored", reasons, cf)

    if bool(episode.get("conflicting_evidence")):
        reasons.append("conflicting evidence is causally weak")
        return _label("inconclusive", reasons, cf)

    if cf["status"] != "identified":
        reasons.extend(str(reason) for reason in cf.get("reasons", []))
        return _label("inconclusive", reasons or ["counterfactual is not identifiable"], cf)

    if cf["natural_recovery"]:
        reasons.append("treatment and control recovered without a treatment-specific effect")
        return _label("naturally_recovered", reasons, cf)

    if cf["control_failed"] is True and cf["treatment_failed"] is False and cf["effect_direction"] == "beneficial":
        reasons.append("comparable control crossed the incident threshold while treatment stayed below it")
        return _label("prevented", reasons, cf)

    minimum_delay = _int(episode.get("minimum_useful_delay_seconds"), 0)
    useful_delay = cf.get("useful_delay_seconds")
    if (
        cf["control_failed"] is True
        and cf["treatment_failed"] is True
        and isinstance(useful_delay, int)
        and useful_delay >= minimum_delay
        and cf["effect_direction"] == "beneficial"
    ):
        reasons.append("both cohorts failed, but treatment crossed the threshold after the minimum useful delay")
        return _label("delayed", reasons, cf)

    reasons.append("comparable evidence shows no material treatment-specific effect")
    return _label("unaffected", reasons, cf)


def assign_phase_credit(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Assign evidence-bound phase credit without future or scorer leakage."""

    label_result = classify_prevention_outcome(episode)
    cf = label_result["counterfactual"]
    label = str(label_result["label"])
    evidence = _evidence_items(episode.get("evidence"))
    cutoffs = _mapping_or_empty(episode.get("phase_cutoffs"))
    rejected_evidence_ids: list[str] = []
    reasons: list[str] = []
    phases: dict[str, dict[str, Any]] = {}

    if label in {"prevented", "delayed"}:
        base_credit = max(0.0, _float(cf.get("effect_size"), 0.0))
    elif label == "harmful":
        base_credit = -max(0.1, abs(_float(cf.get("effect_size"), 0.0)))
    else:
        base_credit = 0.0

    for phase in PHASES:
        cutoff = _parse_time(cutoffs.get(phase))
        usable_ids: list[str] = []
        for item in evidence:
            evidence_id = str(item.get("id", ""))
            source = str(item.get("source", ""))
            observed_at = _parse_time(item.get("observed_at"))
            if source in LEAKY_EVIDENCE_SOURCES:
                if evidence_id:
                    rejected_evidence_ids.append(evidence_id)
                reasons.append(f"private scorer or hidden outcome evidence rejected for {phase}")
                continue
            if item.get("phase") != phase:
                continue
            if cutoff is None or observed_at is None or observed_at > cutoff:
                if evidence_id:
                    rejected_evidence_ids.append(evidence_id)
                reasons.append(f"post-cutoff evidence rejected for {phase}")
                continue
            if evidence_id:
                usable_ids.append(evidence_id)
        phase_credit = round(base_credit * PHASE_WEIGHTS[phase], 6) if usable_ids or base_credit <= 0 else 0.0
        phases[phase] = {
            "credit": phase_credit,
            "cutoff": cutoffs.get(phase),
            "used_evidence_ids": usable_ids,
        }

    total_credit = round(sum(_float(phase["credit"], 0.0) for phase in phases.values()), 6)
    return {
        "accepted": not reasons,
        "reasons": _dedupe(reasons),
        "label": label,
        "counterfactual": cf,
        "phases": phases,
        "total_credit": total_credit,
        "rejected_evidence_ids": _dedupe(rejected_evidence_ids),
    }


def _label(label: str, reasons: list[str], counterfactual: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "reasons": reasons,
        "counterfactual": dict(counterfactual),
        "allowed_labels": sorted(OUTCOME_LABELS),
    }


def _has_harm(treatment: Mapping[str, Any], counterfactual: Mapping[str, Any], treatment_severity: float, threshold: float) -> bool:
    if bool(treatment.get("guardrail_breached")) or bool(treatment.get("collateral_regression")):
        return True
    if counterfactual.get("effect_direction") == "harmful":
        return True
    return treatment_severity > threshold and bool(treatment.get("caused_by_intervention"))


def _weak_horizon(episode: Mapping[str, Any]) -> bool:
    required = _int(episode.get("required_horizon_seconds"), 0)
    observed = _int(episode.get("observed_horizon_seconds"), required)
    return required > 0 and observed < required


def _evidence_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def _dedupe(items: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(items))
