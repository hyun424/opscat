"""Measured validation, rollback, attribution, and recurrence reporting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import sqrt
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import validate_exact_zero_authority, zero_authority_counters


def validate_prevention_outcome(data: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("validation_plan_hash", "rollback_plan_hash", "pre_measurement_hash", "post_measurement_hash", "control_hash"):
        if not str(data.get(key, "")).startswith("sha256:"):
            raise ValueError(f"missing_{key}")
    validate_exact_zero_authority(data.get("authority_counters"))
    validation_passed = bool(data.get("validation_passed"))
    harm = bool(data.get("harm_detected"))
    collateral = bool(data.get("collateral_regression"))
    ambiguous = bool(data.get("ambiguous_attribution"))
    natural = bool(data.get("natural_recovery"))
    rollback_required = not validation_passed or harm or collateral or ambiguous
    rollback_attempted = bool(data.get("rollback_attempted"))
    rollback_passed = bool(data.get("rollback_passed"))
    if rollback_required and not rollback_attempted:
        raise ValueError("required_rollback_missing")
    rejected = []
    if natural:
        rejected.append("natural_recovery_credit_rejected")
    if ambiguous:
        rejected.append("ambiguous_attribution")
    if rollback_attempted:
        rejected.append("rollback_recovery_not_prevention_success")
    if harm:
        rejected.append("harm_detected")
    success = validation_passed and not any((harm, collateral, ambiguous, natural, rollback_attempted))
    report: dict[str, Any] = {
        "schema_version": "p121.validation_outcome.v1",
        "operation_id": str(data.get("operation_id", "")),
        "validation_passed": validation_passed,
        "rollback_required": rollback_required,
        "rollback_attempted": rollback_attempted,
        "rollback_passed": rollback_passed if rollback_attempted else None,
        "prevention_success": success,
        "causal_confidence": float(data.get("causal_confidence", 0.0)) if success else 0.0,
        "avoided_impact": float(data.get("avoided_impact", 0.0)) if success else 0.0,
        "useful_delay": float(data.get("useful_delay", 0.0)) if success else 0.0,
        "harm_score": float(data.get("harm_score", 0.0)),
        "rejected_credit_reasons": rejected,
        "authority_counters": zero_authority_counters(),
    }
    report["report_hash"] = stable_hash(report)
    return report


def recurrence_reduction_report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("missing_recurrence_records")
    slices: list[dict[str, Any]] = []
    for record in records:
        before, after = int(record.get("before_count", -1)), int(record.get("after_count", -1))
        windows = int(record.get("matched_windows", 0))
        if min(before, after) < 0 or windows <= 0 or record.get("matched") is not True:
            raise ValueError("unmatched_recurrence_window")
        rate = (before - after) / max(1, before)
        margin = 1.96 * sqrt(max(0.0, abs(rate) * (1 - min(1.0, abs(rate))) / windows))
        slices.append(
            {
                "system_id": record.get("system_id"),
                "incident_family": record.get("incident_family"),
                "before_count": before,
                "after_count": after,
                "matched_windows": windows,
                "reduction": rate,
                "confidence_interval": [max(-1.0, rate - margin), min(1.0, rate + margin)],
            }
        )
    report: dict[str, Any] = {"schema_version": "p121.recurrence_reduction.v1", "denominator": len(slices), "slices": slices}
    report["report_hash"] = stable_hash(report)
    return report


__all__ = ["recurrence_reduction_report", "validate_prevention_outcome"]
