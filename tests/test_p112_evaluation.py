from __future__ import annotations

import pytest

from app.services.p112_comparison import compare_p112_predictions
from app.services.p112_evaluation import P112EvaluationError, evaluate_p112_predictions

SOURCE = "sha256:" + "a" * 64


def _truth(case_id: str, service: str, fault: str) -> dict:
    return {
        "schema_version": "p112.re1_scorer_truth.v1",
        "case_id": case_id,
        "scorer_only_truth": {"root_service": service, "fault_type": fault, "repetition": 4},
        "official_source_hash": SOURCE,
        "evidence_ids": [f"ev-{case_id}"],
        "source_path": f"{service}_{fault}/4",
        "raw_hashes": {"data.csv": "1" * 64, "inject_time": "2" * 64},
    }


def _prediction(case_id: str, service: str, fault: str, *, confidence: float = 0.8) -> dict:
    return {
        "case_id": case_id,
        "ranked_services": [service, "svc-b" if service == "svc-a" else "svc-a"],
        "fault_type": fault,
        "evidence_refs": [f"ev-{case_id}"],
        "confidence": confidence,
        "abstain": False,
        "advisory_actions": ["inspect evidence"],
        "executed_actions": [],
        "validation_errors": [],
    }


def test_evaluator_recomputes_metrics_and_safety() -> None:
    truth = [_truth("one", "svc-a", "loss"), _truth("two", "svc-b", "delay")]
    predictions = [_prediction("one", "svc-a", "loss"), _prediction("two", "svc-a", "loss")]
    report = evaluate_p112_predictions(truth, predictions, expected_source_hash=SOURCE, allowed_root_services=("svc-a", "svc-b"))
    assert report["metrics"]["service_top1"]["value"] == 0.5
    assert report["metrics"]["fault_accuracy"]["value"] == 0.5
    assert report["metrics"]["evidence_precision"]["value"] == 1.0
    assert all(value == 0 for value in report["safety"].values())


def test_comparison_requires_same_truth_and_reports_paired_delta() -> None:
    truth = [_truth("one", "svc-a", "loss"), _truth("two", "svc-b", "delay")]
    baseline = [_prediction("one", "svc-b", "delay"), _prediction("two", "svc-b", "delay")]
    candidate = [_prediction("one", "svc-a", "loss"), _prediction("two", "svc-b", "delay")]
    report = compare_p112_predictions(
        truth,
        baseline,
        candidate,
        expected_source_hash=SOURCE,
        allowed_root_services=("svc-a", "svc-b"),
        benchmark_role="blind",
    )
    assert report["metric_deltas"]["service_top1"] == 0.5
    assert report["metric_deltas"]["fault_accuracy"] == 0.5
    assert report["paired"]["service_top1"]["improved"] == 1


def test_evaluator_rejects_case_set_or_source_mismatch() -> None:
    with pytest.raises(P112EvaluationError, match="prediction_case_set_mismatch"):
        evaluate_p112_predictions(
            [_truth("one", "svc-a", "loss")], [], expected_source_hash=SOURCE, allowed_root_services=("svc-a",)
        )
    wrong = _truth("one", "svc-a", "loss")
    wrong["official_source_hash"] = "sha256:" + "b" * 64
    with pytest.raises(P112EvaluationError, match="source_hash_mismatch"):
        evaluate_p112_predictions(
            [wrong], [_prediction("one", "svc-a", "loss")], expected_source_hash=SOURCE, allowed_root_services=("svc-a",)
        )
