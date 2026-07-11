from __future__ import annotations

from app.services.p111_release_evidence import produce_p111_release_evidence


def _comparison() -> dict[str, object]:
    metric = lambda value: {"value": value}  # noqa: E731
    return {
        "benchmark_role": "blind",
        "comparison_hash": "sha256:comparison",
        "candidate_metrics": {
            "service_top1": metric(0.88), "service_top3": metric(0.96),
            "fault_accuracy": metric(0.80), "evidence_precision": metric(1.0),
        },
        "candidate_by_fault": {
            "disk": {"metrics": {"fault_accuracy": metric(0.8)}},
            "loss": {"metrics": {"fault_accuracy": metric(0.8)}},
        },
        "metric_deltas": {"service_top1": 0.08, "fault_accuracy": 0.24},
        "zero_safety_counters": True,
    }


def test_local_evidence_remains_release_closed_without_crypto_review() -> None:
    result = produce_p111_release_evidence(
        comparison=_comparison(), repeat_agreement={"joint_agreement": 1.0}, freeze_verified=True
    )
    assert result["gates"]["cryptographic_review"] is False
    assert result["release_qualified"] is False
