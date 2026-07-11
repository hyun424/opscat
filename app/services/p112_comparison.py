"""Paired metrics, calibration, and repeat agreement for P112."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p111_comparison import measure_repeat_agreement
from app.services.p112_evaluation import evaluate_p112_predictions

SCHEMA_VERSION = "p112.paired_comparison.v1"


def compare_p112_predictions(
    scorer_truth: Sequence[Mapping[str, Any]],
    baseline_predictions: Sequence[Mapping[str, Any]],
    candidate_predictions: Sequence[Mapping[str, Any]],
    *,
    expected_source_hash: str,
    allowed_root_services: Sequence[str],
    benchmark_role: str,
) -> dict[str, Any]:
    baseline = evaluate_p112_predictions(
        scorer_truth, baseline_predictions, expected_source_hash=expected_source_hash, allowed_root_services=allowed_root_services
    )
    candidate = evaluate_p112_predictions(
        scorer_truth, candidate_predictions, expected_source_hash=expected_source_hash, allowed_root_services=allowed_root_services
    )
    truth = {str(item["case_id"]): item["scorer_only_truth"] for item in scorer_truth}
    base = {str(item["case_id"]): item for item in baseline_predictions}
    cand = {str(item["case_id"]): item for item in candidate_predictions}
    paired = {metric: _paired(truth, base, cand, metric) for metric in ("service_top1", "service_top3", "fault_accuracy")}
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_role": benchmark_role,
        "case_count": len(truth),
        "official_source_hash": expected_source_hash,
        "baseline_evaluation_hash": baseline["evaluation_hash"],
        "candidate_evaluation_hash": candidate["evaluation_hash"],
        "baseline_metrics": baseline["metrics"],
        "candidate_metrics": candidate["metrics"],
        "metric_deltas": {
            name: round(float(candidate["metrics"][name]["value"]) - float(baseline["metrics"][name]["value"]), 6)
            for name in ("service_top1", "service_top3", "fault_accuracy", "evidence_precision")
        },
        "paired": paired,
        "calibration": {"baseline": _calibration(truth, base), "candidate": _calibration(truth, cand)},
        "candidate_by_fault": candidate["by_fault"],
        "safety": candidate["safety"],
        "zero_safety_counters": all(int(value) == 0 for value in candidate["safety"].values()),
    }
    result["comparison_hash"] = stable_hash(result)
    return result


def _paired(
    truth: Mapping[str, Mapping[str, Any]], baseline: Mapping[str, Mapping[str, Any]], candidate: Mapping[str, Mapping[str, Any]], metric: str
) -> dict[str, int]:
    counts = {"improved": 0, "regressed": 0, "both_correct": 0, "both_wrong": 0}
    for case_id in sorted(truth):
        before = _correct(truth[case_id], baseline[case_id], metric)
        after = _correct(truth[case_id], candidate[case_id], metric)
        key = "improved" if after and not before else "regressed" if before and not after else "both_correct" if after else "both_wrong"
        counts[key] += 1
    return counts


def _correct(truth: Mapping[str, Any], prediction: Mapping[str, Any], metric: str) -> bool:
    ranked = [str(item) for item in prediction.get("ranked_services", [])]
    if metric == "service_top1":
        return bool(ranked) and ranked[0] == str(truth["root_service"])
    if metric == "service_top3":
        return str(truth["root_service"]) in ranked[:3]
    return str(prediction.get("fault_type")) == str(truth["fault_type"])


def _calibration(truth: Mapping[str, Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    values = []
    for case_id in sorted(truth):
        confidence = min(1.0, max(0.0, float(predictions[case_id].get("confidence", 0.0))))
        correct = int(_correct(truth[case_id], predictions[case_id], "service_top1") and _correct(truth[case_id], predictions[case_id], "fault_accuracy"))
        values.append((confidence, correct))
    brier = sum((confidence - correct) ** 2 for confidence, correct in values) / len(values)
    return {"brier_score": round(brier, 6), "sample_count": len(values)}


__all__ = ["compare_p112_predictions", "measure_repeat_agreement"]
