from __future__ import annotations

from app.services.p120_evaluator import run_p120_frozen_evaluation
from app.services.p120_release_evidence import empty_p120_release_authority_counters, produce_p120_release_evidence, validate_p120_release_evidence


def test_frozen_cross_system_evaluation_has_declared_coverage() -> None:
    report = run_p120_frozen_evaluation(seed=12001)
    assert report["case_count"] == 360
    assert report["system_count"] >= 3
    assert report["source_class_count"] >= 5
    assert report["scenario_family_count"] >= 20
    assert report["max_degradation"] <= 0.15
    assert report["authority"]["exact_nonlocal_authority_zero"] is True


def test_release_evidence_is_fresh_distinct_and_honestly_scoped() -> None:
    report = run_p120_frozen_evaluation(seed=12001)
    evidence = produce_p120_release_evidence(
        frozen_evaluation_report=report, reviewer_identity={"id": "reviewer-p120"}, builder_identity={"id": "builder-p120"}, authority_counters=empty_p120_release_authority_counters()
    )
    assert evidence["release_status"] == "p120_cross_system_benchmark_ready"
    assert "Not production autonomy" in evidence["scope_limit"]
    assert validate_p120_release_evidence(evidence)["valid"] is True


def test_release_fails_closed_for_self_review_or_authority() -> None:
    report = run_p120_frozen_evaluation(seed=12001)
    counters = empty_p120_release_authority_counters()
    counters[next(iter(counters))] = 1
    evidence = produce_p120_release_evidence(frozen_evaluation_report=report, reviewer_identity={"id": "same"}, builder_identity={"id": "same"}, authority_counters=counters)
    assert evidence["release_status"] == "p120_blocked"
