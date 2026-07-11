from __future__ import annotations

import pytest

from app.services.p121_signals import zero_authority_counters
from app.services.p121_validation import recurrence_reduction_report, validate_prevention_outcome


def _outcome(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operation_id": "op",
        "validation_plan_hash": "sha256:v",
        "rollback_plan_hash": "sha256:r",
        "pre_measurement_hash": "sha256:pre",
        "post_measurement_hash": "sha256:post",
        "control_hash": "sha256:c",
        "validation_passed": True,
        "harm_detected": False,
        "collateral_regression": False,
        "ambiguous_attribution": False,
        "natural_recovery": False,
        "rollback_attempted": False,
        "causal_confidence": 0.9,
        "avoided_impact": 2,
        "useful_delay": 1,
        "harm_score": 0,
        "authority_counters": zero_authority_counters(),
    }
    value.update(changes)
    return value


def test_measured_outcome_can_receive_prevention_credit() -> None:
    report = validate_prevention_outcome(_outcome())
    assert report["prevention_success"] is True
    assert report["avoided_impact"] == 2


def test_natural_or_rollback_recovery_never_receives_credit() -> None:
    report = validate_prevention_outcome(_outcome(validation_passed=False, natural_recovery=True, rollback_attempted=True, rollback_passed=True))
    assert report["prevention_success"] is False
    assert report["avoided_impact"] == 0
    assert "rollback_recovery_not_prevention_success" in report["rejected_credit_reasons"]


def test_required_rollback_cannot_be_hidden() -> None:
    with pytest.raises(ValueError, match="required_rollback_missing"):
        validate_prevention_outcome(_outcome(harm_detected=True))


def test_recurrence_report_requires_matched_visible_windows() -> None:
    report = recurrence_reduction_report([{"system_id": "s", "incident_family": "f", "before_count": 10, "after_count": 4, "matched_windows": 10, "matched": True}])
    assert report["denominator"] == 1
    assert report["slices"][0]["reduction"] == 0.6
