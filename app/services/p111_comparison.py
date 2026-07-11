"""Paired, calibrated P111 comparison over the sealed P110 scorer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import evaluate_p110_predictions, stable_hash

SCHEMA_VERSION = "p111.paired_comparison.v1"


def measure_repeat_agreement(
    first_predictions: Sequence[Mapping[str, Any]], second_predictions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    first = {str(item["case_id"]): item for item in first_predictions}
    second = {str(item["case_id"]): item for item in second_predictions}
    if set(first) != set(second) or not first:
        raise ValueError("repeat prediction sets must match and be non-empty")
    service_matches = 0
    fault_matches = 0
    joint_matches = 0
    for case_id in sorted(first):
        first_ranked = list(first[case_id].get("ranked_services", []))
        second_ranked = list(second[case_id].get("ranked_services", []))
        service_match = bool(first_ranked and second_ranked and first_ranked[0] == second_ranked[0])
        fault_match = first[case_id].get("fault_type") == second[case_id].get("fault_type")
        service_matches += service_match
        fault_matches += fault_match
        joint_matches += service_match and fault_match
    count = len(first)
    return {
        "case_count": count,
        "service_top1_agreement": round(service_matches / count, 6),
        "fault_agreement": round(fault_matches / count, 6),
        "joint_agreement": round(joint_matches / count, 6),
    }


def compare_p111_predictions(
    scorer_truth: Sequence[Mapping[str, Any]],
    baseline_predictions: Sequence[Mapping[str, Any]],
    candidate_predictions: Sequence[Mapping[str, Any]],
    *,
    benchmark_role: str,
) -> dict[str, Any]:
    baseline = evaluate_p110_predictions(scorer_truth, baseline_predictions)
    candidate = evaluate_p110_predictions(scorer_truth, candidate_predictions)
    truth = {str(item["case_id"]): item["scorer_only_truth"] for item in scorer_truth}
    base_by_id = {str(item["case_id"]): item for item in baseline_predictions}
    cand_by_id = {str(item["case_id"]): item for item in candidate_predictions}
    case_ids = sorted(truth)
    paired = {
        metric: _paired_counts(case_ids, truth, base_by_id, cand_by_id, metric=metric)
        for metric in ("service_top1", "service_top3", "fault_accuracy")
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_role": benchmark_role,
        "case_count": len(case_ids),
        "baseline_evaluation_hash": baseline["evaluation_hash"],
        "candidate_evaluation_hash": candidate["evaluation_hash"],
        "baseline_metrics": baseline["metrics"],
        "candidate_metrics": candidate["metrics"],
        "metric_deltas": {
            metric: round(float(candidate["metrics"][metric]["value"]) - float(baseline["metrics"][metric]["value"]), 6)
            for metric in ("service_top1", "service_top3", "fault_accuracy", "evidence_precision")
        },
        "paired": paired,
        "calibration": {
            "baseline": _calibration(case_ids, truth, base_by_id),
            "candidate": _calibration(case_ids, truth, cand_by_id),
        },
        "candidate_by_fault": candidate["by_fault"],
        "safety": candidate["safety"],
        "zero_safety_counters": all(int(value) == 0 for value in candidate["safety"].values()),
    }
    result["comparison_hash"] = stable_hash(result)
    return result


def _paired_counts(
    case_ids: Sequence[str],
    truth: Mapping[str, Mapping[str, Any]],
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
    *,
    metric: str,
) -> dict[str, int]:
    counts = {"improved": 0, "regressed": 0, "both_correct": 0, "both_wrong": 0}
    for case_id in case_ids:
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
    if metric == "fault_accuracy":
        return str(prediction.get("fault_type")) == str(truth["fault_type"])
    raise ValueError(f"unsupported paired metric: {metric}")


def _calibration(
    case_ids: Sequence[str], truth: Mapping[str, Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    values: list[tuple[float, int]] = []
    for case_id in case_ids:
        prediction = predictions[case_id]
        confidence = min(1.0, max(0.0, float(prediction.get("confidence", 0.0))))
        correct = int(
            _correct(truth[case_id], prediction, "service_top1")
            and _correct(truth[case_id], prediction, "fault_accuracy")
        )
        values.append((confidence, correct))
    brier = sum((confidence - correct) ** 2 for confidence, correct in values) / len(values) if values else 0.0
    bins: list[dict[str, Any]] = []
    ece = 0.0
    for lower_index in range(5):
        lower = lower_index / 5
        upper = (lower_index + 1) / 5
        bucket = [(confidence, correct) for confidence, correct in values if lower <= confidence <= upper and (lower_index == 4 or confidence < upper)]
        if not bucket:
            continue
        mean_confidence = sum(item[0] for item in bucket) / len(bucket)
        accuracy = sum(item[1] for item in bucket) / len(bucket)
        ece += len(bucket) / len(values) * abs(mean_confidence - accuracy)
        bins.append({"lower": lower, "upper": upper, "count": len(bucket), "mean_confidence": round(mean_confidence, 6), "accuracy": round(accuracy, 6)})
    return {"brier_score": round(brier, 6), "expected_calibration_error": round(ece, 6), "bins": bins}
