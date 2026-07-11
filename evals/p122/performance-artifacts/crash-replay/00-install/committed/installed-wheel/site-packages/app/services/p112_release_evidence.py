"""Fail-closed P112 cross-system accuracy release decision."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.p110_evaluation import stable_hash

SCHEMA_VERSION = "p112.release_evidence.v1"


def produce_p112_release_evidence(
    *,
    comparison: Mapping[str, Any],
    repeat_agreement: Mapping[str, Any],
    freeze_verified: bool,
    replay_integrity: Mapping[str, Any],
    cryptographic_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = comparison.get("candidate_metrics", {})
    by_fault = comparison.get("candidate_by_fault", {})
    deltas = comparison.get("metric_deltas", {})
    service_delta = float(deltas.get("service_top1", -1.0))
    fault_delta = float(deltas.get("fault_accuracy", -1.0))
    gates = {
        "blind_role": comparison.get("benchmark_role") == "blind",
        "freeze_verified": freeze_verified,
        "service_top1": _metric(metrics, "service_top1") >= 0.84,
        "service_top3": _metric(metrics, "service_top3") >= 0.92,
        "fault_accuracy": _metric(metrics, "fault_accuracy") >= 0.84,
        "loss_floor": _fault_metric(by_fault, "loss", "fault_accuracy") >= 0.60,
        "delay_floor": _fault_metric(by_fault, "delay", "fault_accuracy") >= 0.60,
        "evidence_precision": _metric(metrics, "evidence_precision") >= 0.95,
        "nonnegative_service_delta": service_delta >= 0.0,
        "nonnegative_fault_delta": fault_delta >= 0.0,
        "positive_primary_delta": service_delta > 0.0 or fault_delta > 0.0,
        "zero_safety_counters": comparison.get("zero_safety_counters") is True,
        "repeat_joint_agreement": float(repeat_agreement.get("joint_agreement", 0.0)) >= 0.90,
        "baseline_request_complete": replay_integrity.get("baseline_request_complete") is True,
        "candidate_request_complete": replay_integrity.get("candidate_request_complete") is True,
        "baseline_raw_replay": replay_integrity.get("baseline_raw_replay") is True,
        "candidate_raw_replay": replay_integrity.get("candidate_raw_replay") is True,
        "candidate_repeat_raw_replay": replay_integrity.get("candidate_repeat_raw_replay") is True,
        "cryptographic_review": _crypto_review_valid(cryptographic_review),
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release_qualified": all(gates.values()),
        "gates": gates,
        "comparison_hash": comparison.get("comparison_hash"),
        "repeat_agreement": dict(repeat_agreement),
        "replay_integrity": dict(replay_integrity),
        "reasons": [f"{name} failed closed" for name, passed in gates.items() if not passed],
        "action_execution_enabled": False,
    }
    result["release_evidence_hash"] = stable_hash(result)
    return result


def request_envelope_complete(value: Any) -> bool:
    required = {
        "model",
        "provider_endpoint",
        "provider_api",
        "system_prompt_sha256",
        "prompt_schema_version",
        "decoding_config",
    }
    return isinstance(value, Mapping) and required <= set(str(key) for key in value)


def _metric(metrics: Any, name: str) -> float:
    item = metrics.get(name, {}) if isinstance(metrics, Mapping) else {}
    value = item.get("value", 0.0) if isinstance(item, Mapping) else 0.0
    return float(value) if value is not None else 0.0


def _fault_metric(by_fault: Any, fault: str, metric: str) -> float:
    item = by_fault.get(fault, {}) if isinstance(by_fault, Mapping) else {}
    values = item.get("metrics", {}) if isinstance(item, Mapping) else {}
    return _metric(values, metric)


def _crypto_review_valid(review: Mapping[str, Any] | None) -> bool:
    return bool(
        review
        and review.get("schema_version") == "p112.cryptographic_review.v1"
        and review.get("signature_verified") is True
        and review.get("provider_receipts_verified") is True
    )
