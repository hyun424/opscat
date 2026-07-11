"""Fail-closed P111 accuracy release evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.p110_evaluation import stable_hash

SCHEMA_VERSION = "p111.release_evidence.v1"


def produce_p111_release_evidence(
    *, comparison: Mapping[str, Any], repeat_agreement: Mapping[str, Any], freeze_verified: bool, cryptographic_review: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    metrics = comparison.get("candidate_metrics", {})
    by_fault = comparison.get("candidate_by_fault", {})
    gates = {
        "blind_role": comparison.get("benchmark_role") == "blind",
        "freeze_verified": freeze_verified,
        "service_top1": _metric(metrics, "service_top1") >= 0.84,
        "service_top3": _metric(metrics, "service_top3") >= 0.92,
        "fault_accuracy": _metric(metrics, "fault_accuracy") >= 0.68,
        "evidence_precision": _metric(metrics, "evidence_precision") >= 0.95,
        "disk_floor": _fault_metric(by_fault, "disk", "fault_accuracy") >= 0.60,
        "loss_floor": _fault_metric(by_fault, "loss", "fault_accuracy") >= 0.60,
        "service_positive_delta": float(comparison.get("metric_deltas", {}).get("service_top1", -1.0)) > 0.0,
        "fault_positive_delta": float(comparison.get("metric_deltas", {}).get("fault_accuracy", -1.0)) > 0.0,
        "zero_safety_counters": comparison.get("zero_safety_counters") is True,
        "repeat_joint_agreement": float(repeat_agreement.get("joint_agreement", 0.0)) >= 0.80,
        "cryptographic_review": _crypto_review_valid(cryptographic_review),
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release_qualified": all(gates.values()),
        "gates": gates,
        "comparison_hash": comparison.get("comparison_hash"),
        "repeat_agreement": dict(repeat_agreement),
        "reasons": [f"{name} failed closed" for name, passed in gates.items() if not passed],
        "action_execution_enabled": False,
    }
    result["release_evidence_hash"] = stable_hash(result)
    return result


def _metric(metrics: Mapping[str, Any], name: str) -> float:
    item = metrics.get(name, {})
    return float(item.get("value", 0.0)) if isinstance(item, Mapping) else 0.0


def _fault_metric(by_fault: Mapping[str, Any], fault: str, metric: str) -> float:
    item = by_fault.get(fault, {})
    values = item.get("metrics", {}) if isinstance(item, Mapping) else {}
    return _metric(values, metric)


def _crypto_review_valid(review: Mapping[str, Any] | None) -> bool:
    return bool(
        review
        and review.get("schema_version") == "p111.cryptographic_review.v1"
        and review.get("signature_verified") is True
        and review.get("provider_receipts_verified") is True
    )
