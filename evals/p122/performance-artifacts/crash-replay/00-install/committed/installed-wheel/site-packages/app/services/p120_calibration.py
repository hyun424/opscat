"""Cross-system calibration, abstention, and identical-denominator baselines."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p120_governance import zero_authority_counters


def score_cross_system_predictions(records: Sequence[Mapping[str, Any]], baselines: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    if not records:
        raise ValueError("missing_predictions")
    ids = [str(r.get("case_id", "")) for r in records]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("invalid_case_ids")
    for name, values in baselines.items():
        if {str(v.get("case_id", "")) for v in values} != set(ids):
            raise ValueError(f"baseline_denominator_mismatch:{name}")
    overall = _metrics(records)
    systems = {str(r["system_id"]) for r in records}
    per_system = {system: _metrics([r for r in records if r.get("system_id") == system]) for system in sorted(systems)}
    baseline_metrics = {name: _metrics(values) for name, values in baselines.items()}
    report: dict[str, Any] = {
        "schema_version": "p120.cross_system_score.v1",
        "denominator": len(records),
        "overall": overall,
        "per_system": per_system,
        "baselines": baseline_metrics,
        "identical_denominators": True,
        "authority_counter_snapshot": zero_authority_counters(),
    }
    report["report_hash"] = stable_hash(report)
    return report


def _metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    denominator = len(records)
    correct = sum(int(r.get("correct") is True) for r in records)
    ece = sum(abs(float(r.get("confidence", 0.0)) - int(r.get("correct") is True)) for r in records) / denominator
    abstentions = [r for r in records if r.get("label") in {"abstain", "investigate_more", "escalate"}]
    actions = [r for r in records if r.get("label") == "act"]
    return {
        "denominator": denominator,
        "accuracy": correct / denominator,
        "expected_calibration_error": ece,
        "abstention_rate": len(abstentions) / denominator,
        "harmful_action_rate": sum(int(r.get("harmful") is True) for r in actions) / max(1, len(actions)),
        "unnecessary_action_rate": sum(int(r.get("unnecessary") is True) for r in actions) / max(1, len(actions)),
        "escalation_correctness": sum(int(r.get("label") == "escalate" and r.get("correct") is True) for r in records) / max(1, sum(int(r.get("label") == "escalate") for r in records)),
    }


__all__ = ["score_cross_system_predictions"]
