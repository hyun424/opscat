from __future__ import annotations

from app.services.p110_evaluation import stable_hash
from app.services.p119_evaluator import P119_FAMILIES, run_p119_frozen_evaluation
from app.services.p119_release_evidence import empty_p119_release_authority_counters, produce_p119_release_evidence, validate_p119_release_evidence


def test_frozen_closed_loop_evaluation_has_complete_families_and_zero_false_recovery() -> None:
    report = run_p119_frozen_evaluation(seed=11901)
    assert report["case_count"] >= 300
    assert set(report["per_family_metrics"]) == set(P119_FAMILIES)
    assert report["aggregate"]["failed"] == 0
    assert report["aggregate"]["false_recovery_count"] == 0
    assert report["aggregate"]["duplicate_local_action_count"] == 0
    assert report["authority"]["exact_nonlocal_authority_zero"] is True


def test_release_evidence_is_fresh_distinct_reviewed_and_honestly_scoped() -> None:
    report = run_p119_frozen_evaluation(seed=11901)
    evidence = produce_p119_release_evidence(
        frozen_evaluation_report=report, reviewer_identity={"id": "reviewer-p119"}, builder_identity={"id": "builder-p119"}, authority_counters=empty_p119_release_authority_counters()
    )
    assert evidence["release_status"] == "p119_local_closed_loop_ready"
    assert "Not production autonomy" in evidence["scope_limit"]
    assert validate_p119_release_evidence(evidence)["valid"] is True
    assert set(evidence["p118_dependency_source_hashes"]) == {
        "app/services/p118_approval.py",
        "app/services/p118_action_pack_verifier.py",
        "app/services/p118_ledger.py",
        "app/services/p118_operation_contract.py",
        "app/services/p118_validation_cycle.py",
        "app/services/p118_worker.py",
    }
    stale = dict(evidence)
    stale["frozen_evaluation_hash"] = "sha256:" + "0" * 64
    assert validate_p119_release_evidence(stale)["valid"] is False

    dependency_stale = dict(evidence)
    dependency_stale["p118_dependency_source_hashes"] = dict(evidence["p118_dependency_source_hashes"])
    dependency_stale["p118_dependency_source_hashes"]["app/services/p118_approval.py"] = "sha256:" + "0" * 64
    dependency_stale["release_evidence_hash"] = stable_hash({key: value for key, value in dependency_stale.items() if key != "release_evidence_hash"})
    assert validate_p119_release_evidence(dependency_stale)["valid"] is False

    ledger_stale = dict(evidence)
    ledger_stale["p118_dependency_source_hashes"] = dict(evidence["p118_dependency_source_hashes"])
    ledger_stale["p118_dependency_source_hashes"]["app/services/p118_ledger.py"] = "sha256:" + "0" * 64
    ledger_stale["release_evidence_hash"] = stable_hash({key: value for key, value in ledger_stale.items() if key != "release_evidence_hash"})
    assert validate_p119_release_evidence(ledger_stale)["valid"] is False


def test_release_fails_closed_for_self_review_or_nonzero_authority() -> None:
    report = run_p119_frozen_evaluation(seed=11901)
    counters = empty_p119_release_authority_counters()
    counters["production_mutation_count"] = 1
    evidence = produce_p119_release_evidence(frozen_evaluation_report=report, reviewer_identity={"id": "same"}, builder_identity={"id": "same"}, authority_counters=counters)
    assert evidence["release_status"] == "p119_blocked"
