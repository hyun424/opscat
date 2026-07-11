from __future__ import annotations

import pytest

from app.services.p120_calibration import score_cross_system_predictions


def _record(case_id: str, system_id: str, *, correct: bool = True) -> dict[str, object]:
    return {"case_id": case_id, "system_id": system_id, "correct": correct, "confidence": 0.9, "label": "act", "harmful": False, "unnecessary": False}


def test_cross_system_score_uses_identical_denominators() -> None:
    records = [_record("a", "dev"), _record("b", "holdout")]
    report = score_cross_system_predictions(records, {"safe_null": records, "nearest": records})
    assert report["denominator"] == 2
    assert report["identical_denominators"] is True
    assert report["overall"]["accuracy"] == 1.0


def test_cross_system_score_rejects_baseline_denominator_mismatch() -> None:
    records = [_record("a", "dev"), _record("b", "holdout")]
    with pytest.raises(ValueError, match="baseline_denominator_mismatch"):
        score_cross_system_predictions(records, {"broken": records[:1]})
