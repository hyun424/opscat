from __future__ import annotations

from typing import Any

from app.services import p111_comparison


def _truth() -> list[dict[str, object]]:
    return [
        {
            "schema_version": "p110.rcaeval_scorer_truth.v1",
            "case_id": "case-1",
            "scorer_only_truth": {"root_service": "svc", "fault_type": "disk", "repetition": 3},
            "official_source_hash": "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4",
            "evidence_ids": ["ev-1"],
            "source_path": "svc_disk/3",
            "raw_hashes": {"data.csv": "a", "inject_time": "b"},
        }
    ]


def _prediction(service: str, fault: str, confidence: float) -> dict[str, object]:
    return {
        "case_id": "case-1",
        "ranked_services": [service],
        "fault_type": fault,
        "evidence_refs": ["ev-1"],
        "confidence": confidence,
        "abstain": False,
        "validation_status": "valid",
        "validation_errors": [],
        "advisory_actions": [],
        "advisory_action_risk": [],
        "executed_actions": [],
        "latency_ms": 1,
    }


def test_comparison_reports_paired_gain_and_calibration(monkeypatch: Any) -> None:
    def fake_evaluate(_truth: object, predictions: list[dict[str, object]]) -> dict[str, object]:
        correct = predictions[0]["ranked_services"] == ["svc"]
        fault_correct = predictions[0]["fault_type"] == "disk"
        return {
            "evaluation_hash": f"sha256:{correct}:{fault_correct}",
            "metrics": {
                "service_top1": {"value": float(correct)},
                "service_top3": {"value": float(correct)},
                "fault_accuracy": {"value": float(fault_correct)},
                "evidence_precision": {"value": 1.0},
            },
            "by_fault": {},
            "safety": {"truth_leak_count": 0, "executed_action_count": 0},
        }

    monkeypatch.setattr(p111_comparison, "evaluate_p110_predictions", fake_evaluate)
    report = p111_comparison.compare_p111_predictions(
        _truth(), [_prediction("other", "cpu", 0.9)], [_prediction("svc", "disk", 0.8)], benchmark_role="blind"
    )
    assert report["metric_deltas"]["service_top1"] == 1.0
    assert report["metric_deltas"]["fault_accuracy"] == 1.0
    assert report["paired"]["fault_accuracy"]["improved"] == 1
    assert report["calibration"]["candidate"]["brier_score"] == 0.04
    assert report["zero_safety_counters"] is True


def test_repeat_agreement_is_exact_and_case_bound() -> None:
    first = [_prediction("svc", "disk", 0.8)]
    second = [_prediction("svc", "disk", 0.7)]
    assert p111_comparison.measure_repeat_agreement(first, second)["joint_agreement"] == 1.0
