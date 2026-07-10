"""Deterministic expected-value scoring for P106 preventive actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreventiveExpectedValueScore:
    expected_value: float
    components: dict[str, float]
    selected_baseline: str
    eligible_for_intervention: bool
    reasons: tuple[str, ...] = ()
    tie_break_trace: tuple[str, ...] = ()


def score_preventive_candidate(
    *,
    probability: float,
    avoided_impact: float,
    intervention_harm: float,
    operational_cost: float,
    uncertainty_penalty: float,
    false_alert_penalty: float,
    reversible: bool = True,
    minimum_probability: float = 0.3,
    minimum_expected_value: float = 0.0,
) -> PreventiveExpectedValueScore:
    benefit = probability * avoided_impact
    expected_value = benefit - intervention_harm - operational_cost - uncertainty_penalty - false_alert_penalty
    components = {
        "probability_x_avoided_impact": benefit,
        "intervention_harm": intervention_harm,
        "operational_cost": operational_cost,
        "uncertainty_penalty": uncertainty_penalty,
        "false_alert_penalty": false_alert_penalty,
    }
    reasons: list[str] = []
    if probability < minimum_probability:
        reasons.append("probability below intervention threshold")
    if expected_value <= minimum_expected_value:
        reasons.append("expected value does not beat observe baseline")
    if reversible is not True:
        reasons.append("irreversible candidate cannot be selected")
    eligible = not reasons
    return PreventiveExpectedValueScore(
        expected_value=expected_value,
        components=components,
        selected_baseline="intervention" if eligible else "observe",
        eligible_for_intervention=eligible,
        reasons=tuple(reasons),
    )


def rank_preventive_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(candidate: dict[str, Any]) -> tuple[float, int, int, str]:
        return (
            -float(candidate.get("expected_value", 0.0)),
            int(candidate.get("blast_radius_order", 999)),
            0 if candidate.get("reversible") is True else 1,
            str(candidate.get("candidate_id", "")),
        )

    ranked = [dict(candidate) for candidate in sorted(candidates, key=key)]
    for index, candidate in enumerate(ranked):
        candidate["tie_break_trace"] = (
            f"rank={index + 1}",
            f"expected_value={candidate.get('expected_value')}",
            f"blast_radius_order={candidate.get('blast_radius_order')}",
            f"reversible={candidate.get('reversible')}",
        )
    return ranked
