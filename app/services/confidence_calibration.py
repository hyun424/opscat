"""P7 bucketed confidence calibration for replay/eval outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CalibrationBucket:
    name: str
    lower: float
    upper: float
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.total, 3) if self.total else 0.0

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "lower": self.lower, "upper": self.upper, "total": self.total, "correct": self.correct, "accuracy": self.accuracy}


@dataclass(frozen=True)
class CalibrationReport:
    total: int
    bucket_accuracy: dict[str, float]
    buckets: tuple[CalibrationBucket, ...]
    overconfidence_count: int
    underconfidence_count: int
    fail_closed_rejections: int
    recommended_auto_action_threshold: float

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "bucket_accuracy": self.bucket_accuracy,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "overconfidence_count": self.overconfidence_count,
            "underconfidence_count": self.underconfidence_count,
            "fail_closed_rejections": self.fail_closed_rejections,
            "recommended_auto_action_threshold": self.recommended_auto_action_threshold,
        }


def calibrate_replay_results(results: list[dict[str, Any]]) -> CalibrationReport:
    ranges = (("0.00-0.49", 0.0, 0.49), ("0.50-0.69", 0.5, 0.69), ("0.70-0.84", 0.7, 0.84), ("0.85-1.00", 0.85, 1.0))
    buckets: list[CalibrationBucket] = []
    over = 0
    under = 0
    fail_closed = 0
    for name, lower, upper in ranges:
        selected = [item for item in results if lower <= float(item.get("confidence", 0.0)) <= upper]
        correct = sum(1 for item in selected if item.get("passed") is True)
        buckets.append(CalibrationBucket(name, lower, upper, len(selected), correct))
    for item in results:
        confidence = float(item.get("confidence", 0.0))
        passed = item.get("passed") is True
        evidence_count = int(item.get("evidence_count", 0))
        ambiguous = bool(item.get("ambiguous", False))
        if confidence >= 0.85 and not passed:
            over += 1
        if confidence < 0.70 and passed:
            under += 1
        if confidence >= 0.80 and (evidence_count < 3 or ambiguous or item.get("policy_decision") in {"DENY", "ESCALATE"}):
            fail_closed += 1
    threshold = 0.85 if over == 0 else 0.90
    return CalibrationReport(
        total=len(results),
        bucket_accuracy={bucket.name: bucket.accuracy for bucket in buckets},
        buckets=tuple(buckets),
        overconfidence_count=over,
        underconfidence_count=under,
        fail_closed_rejections=fail_closed,
        recommended_auto_action_threshold=threshold,
    )
