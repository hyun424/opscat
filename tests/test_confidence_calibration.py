from __future__ import annotations

from app.services.confidence_calibration import calibrate_confidence, is_auto_action_eligible


def test_confidence_calibration_reports_bucket_accuracy_and_thresholds() -> None:
    report = calibrate_confidence(
        [
            {"scenario": "strong", "confidence": 0.92, "correct": True, "evidence_count": 4},
            {"scenario": "over", "confidence": 0.91, "correct": False, "evidence_count": 1, "conflicting_signals": True},
            {"scenario": "under", "confidence": 0.35, "correct": True, "evidence_count": 3},
        ]
    )

    assert report["bucket_accuracy"]
    assert report["overconfidence_count"] == 1
    assert report["underconfidence_count"] == 1
    assert 0.7 <= report["recommended_thresholds"]["auto_action_min_confidence"] <= 0.95


def test_auto_action_gate_rejects_unsupported_high_confidence() -> None:
    assert is_auto_action_eligible(confidence=0.92, evidence_count=4, conflicting_signals=False, known_ambiguity=False)
    assert not is_auto_action_eligible(confidence=0.95, evidence_count=1, conflicting_signals=False, known_ambiguity=False)
    assert not is_auto_action_eligible(confidence=0.9, evidence_count=4, conflicting_signals=True, known_ambiguity=False)
