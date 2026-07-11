from __future__ import annotations

from typing import Any

from app.services.p110_evaluation import evaluate_p110_predictions, stable_hash
from app.services.p110_release_evidence import (
    PINNED_OFFICIAL_RE1_OB_HASH,
    produce_p110_release_evidence,
    validate_p110_independent_review,
)


def _case(index: int) -> dict[str, Any]:
    services = ("adservice", "cartservice", "checkoutservice", "currencyservice", "productcatalogservice")
    faults = ("cpu", "delay", "disk", "loss", "mem")
    service = services[index % len(services)]
    fault = faults[(index // len(services)) % len(faults)]
    repetition = 1
    case_id = f"{service}-{fault}-{index:02d}"
    return {
        "schema_version": "p110.rcaeval_scorer_truth.v1",
        "case_id": case_id,
        "root_service": service,
        "fault_type": fault,
        "scorer_only_truth": {"root_service": service, "fault_type": fault, "repetition": repetition},
        "evidence_ids": [f"{case_id}:e1"],
        "official_source_hash": PINNED_OFFICIAL_RE1_OB_HASH,
        "source_path": f"{service}_{fault}/{repetition}",
        "raw_hashes": {"data.csv": f"{index:064x}"[-64:], "inject_time": f"{index + 1:064x}"[-64:]},
        "source_hash_verified": True,
    }


def _prediction(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "run_id": "run-a",
        "ranked_services": [case["root_service"], "shadow", "fallback"],
        "fault_type": case["fault_type"],
        "evidence_ids": list(case["evidence_ids"]),
        "abstained": False,
        "harmful_actions": [],
        "latency_ms": 100,
    }


def _evaluation_report() -> dict[str, Any]:
    cases = [_case(index) for index in range(25)]
    report = evaluate_p110_predictions(cases, [_prediction(case) for case in cases], bootstrap_iterations=24, bootstrap_seed=110)
    return report


def _artifacts(evaluation_report: dict[str, Any]) -> dict[str, str]:
    return {
        "official_source": PINNED_OFFICIAL_RE1_OB_HASH,
        "labeled_cases": "sha256:" + "3" * 64,
        "scorer_truth": evaluation_report["scorer_truth_hash"],
        "candidate_outputs": "sha256:" + "4" * 64,
        "evaluation_report": evaluation_report["evaluation_hash"],
        "implementation_revision": "sha256:" + "5" * 64,
    }


def _review(release_hash: str, artifacts: dict[str, str]) -> dict[str, Any]:
    review = {
        "schema_version": "p110.independent_review.v1",
        "review_id": "p110-review-001",
        "producer_id": "p110-producer",
        "reviewer": {"role": "verifier", "id": "p110-reviewer"},
        "verdict": "pass",
        "reviewed_at": "2026-07-11T00:20:00Z",
        "freshness": {"evidence_generated_at": "2026-07-11T00:10:00Z", "max_age_seconds": 3600, "fresh": True},
        "reviewed_artifact_hashes": {**artifacts, "release_evidence": release_hash},
        "reviewer_evidence": {
            "verifier_identity": {"id": "p110-reviewer", "attestation": "pure-local-reviewer-evidence"},
            "identity_scope": "not-cryptographic-authentication",
            "commands": [
                {
                    "command": "pytest -q tests/test_p110_release_evidence.py tests/test_p110_evaluation.py",
                    "exit_code": 0,
                    "observed_at": "2026-07-11T00:20:00Z",
                }
            ],
            "checks": [
                {"name": "official source pinned", "passed": True, "evidence": "official_source matches RE1-OB SHA-256"},
                {"name": "scorer truth bound", "passed": True, "evidence": "scorer_truth hash came from evaluation report"},
            ],
        },
    }
    review["review_tamper_evident_hash"] = stable_hash(review)
    return review


def _produce(report: dict[str, Any] | None = None, review: dict[str, Any] | None = None) -> dict[str, Any]:
    evaluation_report = report or _evaluation_report()
    artifacts = _artifacts(evaluation_report)
    unsigned = produce_p110_release_evidence(
        producer_id="p110-producer",
        evaluation_report=evaluation_report,
        official_source_hash_verified=True,
        bound_artifact_hashes=artifacts,
        independent_review=None,
        trusted_now="2026-07-11T00:30:00Z",
    )
    return produce_p110_release_evidence(
        producer_id="p110-producer",
        evaluation_report=evaluation_report,
        official_source_hash_verified=True,
        bound_artifact_hashes=artifacts,
        independent_review=review or _review(unsigned["release_evidence_hash"], artifacts),
        trusted_now="2026-07-11T00:30:00Z",
    )


def test_p110_release_gate_stays_closed_for_noncryptographic_local_review() -> None:
    evidence = _produce()

    assert evidence["schema_version"] == "p110.release_evidence.v1"
    assert evidence["release_qualified"] is False
    assert evidence["release_gates"] == {
        "official_re1_ob_source_pinned": True,
        "official_source_hash_verified": True,
        "minimum_case_count": True,
        "official_fault_set": True,
        "official_service_set": True,
        "all_cells_nonzero": True,
        "quality_thresholds": True,
        "zero_safety_counters": True,
        "artifact_hash_binding": True,
        "independent_review_ready": False,
    }
    assert evidence["independent_review"]["locally_consistent"] is True
    assert any("cryptographically authenticated" in reason for reason in evidence["reasons"] + evidence["independent_review"]["reasons"])


def test_p110_release_binding_hash_is_stable_across_review_time() -> None:
    report = _evaluation_report()
    artifacts = _artifacts(report)
    first = produce_p110_release_evidence(
        producer_id="p110-producer",
        evaluation_report=report,
        official_source_hash_verified=True,
        bound_artifact_hashes=artifacts,
        independent_review=None,
        trusted_now="2026-07-11T00:10:00Z",
    )
    later = produce_p110_release_evidence(
        producer_id="p110-producer",
        evaluation_report=report,
        official_source_hash_verified=True,
        bound_artifact_hashes=artifacts,
        independent_review=None,
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert first["trusted_now"] != later["trusted_now"]
    assert first["release_evidence_hash"] == later["release_evidence_hash"]


def test_p110_release_gate_fails_closed_without_independent_review_and_binding() -> None:
    report = _evaluation_report()
    evidence = produce_p110_release_evidence(
        producer_id="p110-producer",
        evaluation_report=report,
        official_source_hash_verified=True,
        bound_artifact_hashes={"evaluation_report": report["evaluation_hash"]},
        independent_review=None,
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert evidence["release_qualified"] is False
    assert evidence["release_gates"]["artifact_hash_binding"] is False
    assert evidence["release_gates"]["independent_review_ready"] is False
    assert "missing independent review" in evidence["independent_review"]["reasons"]


def test_p110_release_gate_rejects_tiny_or_unsafe_evaluation_reports() -> None:
    report = _evaluation_report()
    report["summary"]["case_count"] = 24
    report["safety"]["truth_leak_count"] = 1
    report["safety"]["invalid_citation_count"] = 1
    report["safety"]["harmful_action_count"] = 1
    report["safety"]["provider_error_count"] = 1
    report["safety"]["duplicate_output_count"] = 1
    report["safety"]["missing_output_count"] = 1
    report["safety"]["unknown_output_count"] = 1
    report["metrics"]["service_top1"]["value"] = 0.59
    report["evaluation_hash"] = stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"})

    evidence = _produce(report)

    assert evidence["release_qualified"] is False
    assert evidence["release_gates"]["minimum_case_count"] is False
    assert evidence["release_gates"]["quality_thresholds"] is False
    assert evidence["release_gates"]["zero_safety_counters"] is False


def test_p110_release_gate_rejects_unofficial_source_or_unbound_scorer_truth() -> None:
    report = _evaluation_report()
    artifacts = _artifacts(report)
    artifacts["official_source"] = "sha256:" + "2" * 64
    artifacts["scorer_truth"] = "sha256:" + "6" * 64

    evidence = produce_p110_release_evidence(
        producer_id="p110-producer",
        evaluation_report=report,
        official_source_hash_verified=True,
        bound_artifact_hashes=artifacts,
        independent_review=None,
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert evidence["release_qualified"] is False
    assert evidence["release_gates"]["official_re1_ob_source_pinned"] is False
    assert evidence["release_gates"]["artifact_hash_binding"] is False


def test_p110_release_gate_rejects_report_with_mutated_official_source_hash() -> None:
    report = _evaluation_report()
    report["official_source_hash"] = "sha256:" + "0" * 64
    report["summary"]["official_source_hash"] = "sha256:" + "0" * 64
    report["evaluation_hash"] = stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"})

    evidence = _produce(report)

    assert evidence["release_qualified"] is False
    assert evidence["release_gates"]["official_re1_ob_source_pinned"] is False
    assert evidence["release_gates"]["artifact_hash_binding"] is False


def test_p110_release_gate_fails_closed_when_new_safety_counters_are_missing() -> None:
    report = _evaluation_report()
    for key in ("duplicate_output_count", "missing_output_count", "unknown_output_count"):
        report["safety"].pop(key)
    report["evaluation_hash"] = stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"})

    evidence = _produce(report)

    assert evidence["release_qualified"] is False
    assert evidence["release_gates"]["zero_safety_counters"] is False


def test_p110_independent_review_rejects_self_review_and_hash_mismatch() -> None:
    report = _evaluation_report()
    artifacts = _artifacts(report)
    release_hash = stable_hash({"release": "p110"})
    review = _review(release_hash, artifacts)
    review["reviewer"]["id"] = "p110-producer"
    review["reviewed_artifact_hashes"]["candidate_outputs"] = "sha256:" + "9" * 64
    review["reviewer_evidence"]["verifier_identity"]["id"] = "p110-producer"
    review["review_tamper_evident_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_tamper_evident_hash"})

    result = validate_p110_independent_review(
        review,
        expected_hashes={**artifacts, "release_evidence": release_hash},
        producer_id="p110-producer",
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert result["accepted"] is False
    assert result["reviewed_artifact_hashes_match"] is False
    assert any("self-review" in reason or "must match" in reason for reason in result["reasons"])


def test_p110_independent_review_tamper_evident_hash_must_bind_content() -> None:
    report = _evaluation_report()
    artifacts = _artifacts(report)
    release_hash = stable_hash({"release": "p110"})
    review = _review(release_hash, artifacts)
    review["verdict"] = "pass "

    result = validate_p110_independent_review(
        review,
        expected_hashes={**artifacts, "release_evidence": release_hash},
        producer_id="p110-producer",
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert result["accepted"] is False
    assert result["review_tamper_evident_hash_match"] is False


def test_p110_independent_review_requires_concrete_reviewer_evidence() -> None:
    report = _evaluation_report()
    artifacts = _artifacts(report)
    release_hash = stable_hash({"release": "p110"})
    review = _review(release_hash, artifacts)
    review["reviewer_evidence"]["commands"] = []
    review["reviewer_evidence"]["identity_scope"] = "cryptographic-authentication"
    review["review_tamper_evident_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_tamper_evident_hash"})

    result = validate_p110_independent_review(
        review,
        expected_hashes={**artifacts, "release_evidence": release_hash},
        producer_id="p110-producer",
        trusted_now="2026-07-11T00:30:00Z",
    )

    assert result["accepted"] is False
    assert result["reviewer_evidence_complete"] is False
    assert any("cryptographic identity is outside" in reason or "commands" in reason for reason in result["reasons"])
