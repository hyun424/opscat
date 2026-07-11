"""Deterministic cross-system shift and out-of-distribution reporting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p120_governance import zero_authority_counters

P120_SHIFT_DIMENSIONS = (
    "modality_missingness",
    "signal_distribution",
    "topology",
    "incident_family",
    "action_family",
    "ontology_ambiguity",
    "source_origin",
    "temporal",
    "calibration",
    "contradiction_rate",
    "authority_novelty",
)


def build_ood_report(
    *, system_id: str, dataset_id: str, reference: Mapping[str, float], observed: Mapping[str, float], threshold: float, evidence_refs: Sequence[str], affected_denominator: int
) -> dict[str, Any]:
    if not system_id or not dataset_id or affected_denominator <= 0 or not 0 <= threshold <= 1 or not evidence_refs:
        raise ValueError("invalid_ood_report_input")
    shifts: dict[str, float] = {}
    for dimension in P120_SHIFT_DIMENSIONS:
        baseline, current = reference.get(dimension), observed.get(dimension)
        if not isinstance(baseline, int | float) or not isinstance(current, int | float):
            shifts[dimension] = 1.0
        else:
            shifts[dimension] = min(1.0, abs(float(current) - float(baseline)))
    score = max(shifts.values())
    authority_novel = shifts["authority_novelty"] > 0
    if authority_novel:
        effect, label = "aborted_fail_closed", "abstain"
    elif score >= threshold:
        effect, label = "abstain", "abstain"
    elif score >= threshold * 0.7:
        effect, label = "investigate_more", "investigate_more"
    else:
        effect, label = "continue_with_penalty", "continue"
    report: dict[str, Any] = {
        "schema_version": "p120.ood_report.v1",
        "system_id": system_id,
        "dataset_id": dataset_id,
        "shift_dimensions": shifts,
        "ood_score": score,
        "threshold": threshold,
        "decision_effect": effect,
        "recommended_label": label,
        "calibration_effect": "invalidate" if score >= threshold else "penalize" if score > 0 else "none",
        "affected_denominator": affected_denominator,
        "evidence_refs": sorted(evidence_refs),
        "authority_counter_snapshot": zero_authority_counters(),
    }
    report["report_hash"] = stable_hash(report)
    return report


__all__ = ["P120_SHIFT_DIMENSIONS", "build_ood_report"]
