from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p177_release import P177ReleaseError, build_readiness_artifact, validate_readiness_artifact
from app.services.p177_scorer import (
    P177ScorerError,
    compute_paired_stratified_bootstrap_ci,
    isolated_score_report,
    selective_utility,
    validate_candidate_trace_for_label_leak,
)

ROOT = Path(__file__).resolve().parents[1]


def _labels() -> list[dict[str, object]]:
    return [
        {"episode_id": "ep-a", "family": "cpu", "root_cause": "checkout_cpu", "affected_service": "checkout", "valid_evidence_ids": ["e1", "e2"]},
        {"episode_id": "ep-b", "family": "cpu", "root_cause": "cart_cpu", "affected_service": "cart", "valid_evidence_ids": ["e3", "e4"]},
        {"episode_id": "ep-c", "family": "network", "root_cause": "network_loss", "affected_service": "frontend", "valid_evidence_ids": ["e5", "e6"]},
        {"episode_id": "ep-d", "family": "network", "root_cause": "healthy", "affected_service": "none", "valid_evidence_ids": ["e7", "e8"], "ood": True},
    ]


def _predictions(system: str, correct: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label in _labels():
        root = label["root_cause"] if correct else "wrong"
        rows.append(
            {
                "episode_id": label["episode_id"],
                "system": system,
                "decision_type": "diagnosis",
                "root_cause": root,
                "top3_root_causes": [root, "secondary", "tertiary"],
                "affected_service": label["affected_service"] if correct else "wrong",
                "cited_evidence_ids": label["valid_evidence_ids"],
                "uncertainty": 0.1 if correct else 0.9,
                "unsafe_action_advice": False,
            }
        )
    return rows


def test_selective_utility_and_stratified_bootstrap_are_deterministic() -> None:
    assert selective_utility(correct=True, abstained=False, unsafe=False, unsupported=False, uncertainty=0.1) == 0.9
    assert selective_utility(correct=False, abstained=False, unsafe=True, unsupported=False, uncertainty=0.2) == 0.0
    ci = compute_paired_stratified_bootstrap_ci(
        [
            {"episode_id": "ep-a", "family": "cpu", "candidate_utility": 0.9, "baseline_utility": 0.2},
            {"episode_id": "ep-b", "family": "cpu", "candidate_utility": 0.8, "baseline_utility": 0.1},
            {"episode_id": "ep-c", "family": "network", "candidate_utility": 0.7, "baseline_utility": 0.0},
            {"episode_id": "ep-d", "family": "network", "candidate_utility": 0.6, "baseline_utility": 0.0},
        ],
        seed=177,
        iterations=200,
    )
    assert ci["mean_lift"] > 0.5
    assert ci["lower"] == compute_paired_stratified_bootstrap_ci(
        [
            {"episode_id": "ep-a", "family": "cpu", "candidate_utility": 0.9, "baseline_utility": 0.2},
            {"episode_id": "ep-b", "family": "cpu", "candidate_utility": 0.8, "baseline_utility": 0.1},
            {"episode_id": "ep-c", "family": "network", "candidate_utility": 0.7, "baseline_utility": 0.0},
            {"episode_id": "ep-d", "family": "network", "candidate_utility": 0.6, "baseline_utility": 0.0},
        ],
        seed=177,
        iterations=200,
    )["lower"]


def test_isolated_scorer_uses_strongest_preregistered_baseline_and_blocks_label_leaks() -> None:
    labels = _labels()
    report = isolated_score_report(
        sealed_labels=labels,
        candidate_predictions=_predictions("candidate", True),
        single_pass_predictions=_predictions("single_pass", False),
        deterministic_predictions=_predictions("deterministic", False),
        bootstrap_seed=177,
        bootstrap_iterations=200,
        minimum_episode_count=4,
        minimum_family_count=2,
        minimum_healthy_ambiguous_ood_count=1,
        p176_core_family_ids=["cpu", "network"],
        p176_core_family_set_hash=stable_hash(["cpu", "network"]),
        reviewer_signature={"reviewer_id": "independent-scorer", "signed_at": "2026-07-18T00:00:00Z"},
    )
    assert report["comparison_baseline"] in {"single_pass", "deterministic"}
    assert report["sealed_label_hash"] == stable_hash(labels)
    assert report["candidate_summary"]["label_access"] == "forbidden"
    assert report["citation_validity"] == 1.0
    assert report["unsupported_final_diagnosis_count"] == 0
    assert report["report_hash"] == stable_hash({key: value for key, value in report.items() if key != "report_hash"})

    leaking_trace = {"episode_id": "ep-a", "hidden_label": "checkout_cpu"}
    with pytest.raises(P177ScorerError, match="label_leak"):
        validate_candidate_trace_for_label_leak(leaking_trace)

    bad_candidate = deepcopy(_predictions("candidate", True))
    bad_candidate[0]["cited_evidence_ids"] = ["forged"]
    with pytest.raises(P177ScorerError, match="invalid_citation"):
        isolated_score_report(
            sealed_labels=labels,
            candidate_predictions=bad_candidate,
            single_pass_predictions=_predictions("single_pass", False),
            deterministic_predictions=_predictions("deterministic", False),
            bootstrap_seed=177,
            bootstrap_iterations=50,
            minimum_episode_count=4,
            minimum_family_count=2,
            minimum_healthy_ambiguous_ood_count=1,
            p176_core_family_ids=["cpu", "network"],
            p176_core_family_set_hash=stable_hash(["cpu", "network"]),
            reviewer_signature={"reviewer_id": "independent-scorer", "signed_at": "2026-07-18T00:00:00Z"},
        )


def test_isolated_scorer_requires_frozen_complete_p176_core_family_denominator() -> None:
    labels = _labels()
    with pytest.raises(P177ScorerError, match="p176_core_family_set_mismatch"):
        isolated_score_report(
            sealed_labels=labels,
            candidate_predictions=_predictions("candidate", True),
            single_pass_predictions=_predictions("single_pass", False),
            deterministic_predictions=_predictions("deterministic", False),
            bootstrap_seed=177,
            bootstrap_iterations=50,
            minimum_episode_count=4,
            minimum_family_count=2,
            minimum_healthy_ambiguous_ood_count=1,
            p176_core_family_ids=["cpu"],
            p176_core_family_set_hash=stable_hash(["cpu"]),
            reviewer_signature={"reviewer_id": "independent-scorer", "signed_at": "2026-07-18T00:00:00Z"},
        )

    with pytest.raises(P177ScorerError, match="invalid_p176_core_family_set_hash"):
        isolated_score_report(
            sealed_labels=labels,
            candidate_predictions=_predictions("candidate", True),
            single_pass_predictions=_predictions("single_pass", False),
            deterministic_predictions=_predictions("deterministic", False),
            bootstrap_seed=177,
            bootstrap_iterations=50,
            minimum_episode_count=4,
            minimum_family_count=2,
            minimum_healthy_ambiguous_ood_count=1,
            p176_core_family_ids=["cpu", "network"],
            p176_core_family_set_hash="not-a-hash",
            reviewer_signature={"reviewer_id": "independent-scorer", "signed_at": "2026-07-18T00:00:00Z"},
        )


def test_readiness_artifact_is_not_qualified_without_valid_p176_g002_live_evidence() -> None:
    artifact = build_readiness_artifact(project_root=ROOT, p176_live_evidence=None)
    assert artifact["qualified"] is False
    assert artifact["maximum_claim"] == "readiness_only_not_qualification"
    assert artifact["p176_g002_live_evidence"]["valid"] is False
    assert "evidence_seeking_diagnosis_qualified" in artifact["forbidden_claims"]
    assert validate_readiness_artifact(artifact, project_root=ROOT)["qualified"] is False

    forged = deepcopy(artifact)
    forged["qualified"] = True
    forged["maximum_claim"] = "evidence_seeking_diagnosis_qualified"
    forged["readiness_hash"] = stable_hash({key: value for key, value in forged.items() if key != "readiness_hash"})
    with pytest.raises(P177ReleaseError, match="qualification_forbidden"):
        validate_readiness_artifact(forged, project_root=ROOT)
