"""Deterministic confidence calibration helpers for P7 replay outcomes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0.00-0.49", 0.0, 0.5),
    ("0.50-0.69", 0.5, 0.7),
    ("0.70-0.84", 0.7, 0.85),
    ("0.85-1.00", 0.85, 1.01),
)


def calibrate_confidence(outcomes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in outcomes]
    bucket_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    overconfidence = 0
    underconfidence = 0
    unsupported_high = 0
    for row in rows:
        confidence = float(row.get("confidence", 0.0) or 0.0)
        correct = bool(row.get("correct", row.get("passed", False)))
        bucket_rows[_bucket(confidence)].append(row)
        if confidence >= 0.85 and not correct:
            overconfidence += 1
        if confidence < 0.5 and correct:
            underconfidence += 1
        if confidence >= 0.85 and (int(row.get("evidence_count", 0) or 0) < 2 or bool(row.get("conflicting_signals", False)) or bool(row.get("known_ambiguity", False))):
            unsupported_high += 1
    bucket_accuracy = {}
    for label, _, _ in BUCKETS:
        items = bucket_rows.get(label, [])
        bucket_accuracy[label] = {
            "total": len(items),
            "correct": sum(1 for item in items if bool(item.get("correct", item.get("passed", False)))),
            "accuracy": (sum(1 for item in items if bool(item.get("correct", item.get("passed", False)))) / len(items)) if items else 0.0,
        }
    threshold = 0.9 if overconfidence or unsupported_high else 0.82
    return {
        "total": len(rows),
        "bucket_accuracy": bucket_accuracy,
        "overconfidence_count": overconfidence,
        "underconfidence_count": underconfidence,
        "unsupported_high_confidence_count": unsupported_high,
        "recommended_thresholds": {
            "auto_action_min_confidence": threshold,
            "min_supporting_evidence": 2,
            "fail_closed_on_conflicting_signals": True,
        },
    }


def is_auto_action_eligible(*, confidence: float | None, evidence_count: int, conflicting_signals: bool, known_ambiguity: bool, threshold: float = 0.82) -> bool:
    return bool(confidence is not None and confidence >= threshold and evidence_count >= 2 and not conflicting_signals and not known_ambiguity)


def _bucket(confidence: float) -> str:
    for label, start, end in BUCKETS:
        if start <= confidence < end:
            return label
    return "0.85-1.00" if confidence >= 1 else "0.00-0.49"



@dataclass(frozen=True)
class CalibrationReport:
    total: int
    bucket_accuracy: dict[str, Any]
    overconfidence_count: int
    underconfidence_count: int
    unsupported_high_confidence_count: int
    recommended_auto_action_threshold: float
    fail_closed_rejections: int

    @property
    def buckets(self) -> dict[str, Any]:
        return self.bucket_accuracy

    @property
    def recommended_auto_threshold(self) -> float:
        return self.recommended_auto_action_threshold

    def fail_closed(self, sample: Mapping[str, Any]) -> bool:
        confidence = float(sample.get("confidence", 0.0) or 0.0)
        evidence_count = int(sample.get("evidence_count", 0) or 0)
        conflicting = bool(sample.get("conflicting_signals", False))
        ambiguous = bool(sample.get("ambiguous", sample.get("known_ambiguity", False)))
        return not is_auto_action_eligible(
            confidence=confidence,
            evidence_count=evidence_count,
            conflicting_signals=conflicting,
            known_ambiguity=ambiguous,
            threshold=self.recommended_auto_action_threshold,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "bucket_accuracy": self.bucket_accuracy,
            "overconfidence_count": self.overconfidence_count,
            "underconfidence_count": self.underconfidence_count,
            "unsupported_high_confidence_count": self.unsupported_high_confidence_count,
            "recommended_auto_action_threshold": self.recommended_auto_action_threshold,
            "fail_closed_rejections": self.fail_closed_rejections,
        }


class ConfidenceCalibrator:
    def calibrate(self, outcomes: Iterable[Mapping[str, Any]]) -> CalibrationReport:
        return calibrate_replay_results(outcomes)


def calibrate_replay_results(outcomes: Iterable[Mapping[str, Any]]) -> CalibrationReport:
    rows = [dict(item) for item in outcomes]
    raw = calibrate_confidence(rows)
    threshold = float(raw["recommended_thresholds"]["auto_action_min_confidence"])
    report = CalibrationReport(
        total=int(raw["total"]),
        bucket_accuracy=dict(raw["bucket_accuracy"]),
        overconfidence_count=int(raw["overconfidence_count"]),
        underconfidence_count=int(raw["underconfidence_count"]),
        unsupported_high_confidence_count=int(raw["unsupported_high_confidence_count"]),
        recommended_auto_action_threshold=threshold,
        fail_closed_rejections=0,
    )
    rejected = sum(1 for row in rows if report.fail_closed(row))
    return CalibrationReport(
        total=report.total,
        bucket_accuracy=report.bucket_accuracy,
        overconfidence_count=report.overconfidence_count,
        underconfidence_count=report.underconfidence_count,
        unsupported_high_confidence_count=report.unsupported_high_confidence_count,
        recommended_auto_action_threshold=report.recommended_auto_action_threshold,
        fail_closed_rejections=rejected,
    )
