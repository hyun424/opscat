"""P7 confidence calibration over replay/eval outputs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CalibrationBucket:
    name: str
    lower: float
    upper: float
    count: int
    accuracy: float
    average_confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "accuracy": self.accuracy,
            "average_confidence": self.average_confidence,
        }


@dataclass(frozen=True)
class CalibrationReport:
    buckets: list[CalibrationBucket]
    overconfidence_count: int
    underconfidence_count: int
    recommended_auto_threshold: float
    min_evidence_for_auto: int = 3

    def fail_closed(self, sample: Mapping[str, Any]) -> bool:
        confidence = float(sample.get("confidence", 0.0) or 0.0)
        evidence_count = int(sample.get("evidence_count", 0) or 0)
        conflicts = int(sample.get("conflicting_signals", 0) or 0)
        ambiguous = bool(sample.get("ambiguous", False))
        return confidence < self.recommended_auto_threshold or evidence_count < self.min_evidence_for_auto or conflicts > 0 or ambiguous

    def to_dict(self) -> dict[str, object]:
        return {
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "overconfidence_count": self.overconfidence_count,
            "underconfidence_count": self.underconfidence_count,
            "recommended_auto_threshold": self.recommended_auto_threshold,
            "min_evidence_for_auto": self.min_evidence_for_auto,
        }


class ConfidenceCalibrator:
    ranges: tuple[tuple[str, float, float], ...] = (
        ("0.00-0.49", 0.0, 0.49),
        ("0.50-0.69", 0.5, 0.69),
        ("0.70-0.84", 0.7, 0.84),
        ("0.85-1.00", 0.85, 1.0),
    )

    def calibrate(self, samples: Iterable[Mapping[str, Any]]) -> CalibrationReport:
        materialized = list(samples)
        buckets: list[CalibrationBucket] = []
        over = 0
        under = 0
        for name, lower, upper in self.ranges:
            members = [sample for sample in materialized if lower <= float(sample.get("confidence", 0.0) or 0.0) <= upper]
            correct = [sample for sample in members if bool(sample.get("correct", False))]
            count = len(members)
            avg_conf = round(sum(float(sample.get("confidence", 0.0) or 0.0) for sample in members) / count, 3) if count else 0.0
            accuracy = round(len(correct) / count, 3) if count else 0.0
            buckets.append(CalibrationBucket(name, lower, upper, count, accuracy, avg_conf))
            over += sum(1 for sample in members if float(sample.get("confidence", 0.0) or 0.0) >= 0.85 and not bool(sample.get("correct", False)))
            under += sum(1 for sample in members if float(sample.get("confidence", 0.0) or 0.0) < 0.7 and bool(sample.get("correct", False)))
        high_bucket = next((bucket for bucket in buckets if bucket.lower >= 0.85), None)
        threshold = 0.85 if high_bucket and high_bucket.accuracy >= 0.8 else 0.9
        return CalibrationReport(buckets=buckets, overconfidence_count=over, underconfidence_count=under, recommended_auto_threshold=threshold)
