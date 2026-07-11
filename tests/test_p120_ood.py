from __future__ import annotations

from app.services.p120_ood import P120_SHIFT_DIMENSIONS, build_ood_report


def test_ood_report_penalizes_shift_and_aborts_authority_novelty() -> None:
    zero = {dimension: 0.0 for dimension in P120_SHIFT_DIMENSIONS}
    shifted = dict(zero)
    shifted["source_origin"] = 0.6
    report = build_ood_report(system_id="holdout", dataset_id="d1", reference=zero, observed=shifted, threshold=0.8, evidence_refs=["sha256:e"], affected_denominator=4)
    assert report["decision_effect"] == "investigate_more"
    shifted["authority_novelty"] = 0.1
    report = build_ood_report(system_id="holdout", dataset_id="d1", reference=zero, observed=shifted, threshold=0.8, evidence_refs=["sha256:e"], affected_denominator=4)
    assert report["decision_effect"] == "aborted_fail_closed"
    assert all(value == 0 for value in report["authority_counter_snapshot"].values())


def test_ood_report_fails_closed_for_missing_dimensions() -> None:
    report = build_ood_report(system_id="x", dataset_id="d", reference={}, observed={}, threshold=0.8, evidence_refs=["e"], affected_denominator=1)
    assert report["ood_score"] == 1.0
    assert report["recommended_label"] == "abstain"
