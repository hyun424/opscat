from __future__ import annotations

import copy

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p114_development_evaluation import (
    P114DevelopmentEvaluationError,
    evaluate_p114_development_lattices,
    p114_candidate_gate_report,
)


def _lattice(case_id: str, service: str, fault: str, *, include_truth: bool = True) -> dict[str, object]:
    hypotheses = [
        {
            "schema_version": "p114.hypothesis.v1",
            "hypothesis_id": f"hyp-{case_id}-right",
            "service": service if include_truth else "wrong",
            "fault": fault if include_truth else "cpu",
            "score": 2.0,
            "supporting_evidence_ids": [f"ev-{case_id}"],
            "contradicting_evidence_ids": [],
            "missing_evidence": [],
            "action_contract_status": "disabled",
        },
        {
            "schema_version": "p114.hypothesis.v1",
            "hypothesis_id": f"hyp-{case_id}-wrong",
            "service": "wrong",
            "fault": "cpu",
            "score": 1.0,
            "supporting_evidence_ids": [f"ev-{case_id}"],
            "contradicting_evidence_ids": [],
            "missing_evidence": [],
            "action_contract_status": "disabled",
        },
    ]
    payload: dict[str, object] = {
        "schema_version": "p114.hypothesis_lattice.v1",
        "case_id": case_id,
        "source_packet_hash": stable_hash(case_id),
        "ranked_services": [service if include_truth else "wrong", "wrong"],
        "ranked_faults": [fault if include_truth else "cpu", "cpu"],
        "hypotheses": hypotheses,
        "candidate_counts": {"services": 2, "faults": 6, "generated": 12, "retained": 2},
        "evidence_node_ids": [f"ev-{case_id}"],
        "action_contract_status": "disabled",
        "executed_actions": [],
    }
    payload["lattice_hash"] = stable_hash(payload)
    return payload


def _truth(case_id: str, service: str, fault: str) -> dict[str, object]:
    return {
        "schema_version": "p114.re2_scorer_truth.v1",
        "case_id": case_id,
        "scorer_only_truth": {"root_service": service, "fault_type": fault, "repetition": 1},
        "official_source_hash": "sha256:" + "a" * 64,
        "source_path": "hidden",
        "evidence_node_ids": [f"ev-{case_id}"],
    }


def test_development_evaluator_scores_candidate_recall_and_aggregate_fault_cells() -> None:
    truths = [_truth(f"case-{index}", "svc", fault) for index, fault in enumerate(("cpu", "mem", "disk", "delay", "loss", "socket"))]
    lattices = [_lattice(str(item["case_id"]), "svc", str(item["scorer_only_truth"]["fault_type"])) for item in truths]  # type: ignore[index]

    report = evaluate_p114_development_lattices(truths, lattices, modality="fused")

    assert report["metrics"]["service_top5_recall"]["value"] == 1.0
    assert report["metrics"]["joint_candidate_recall"]["value"] == 1.0
    assert report["metrics"]["fault_accuracy"]["value"] == 1.0
    assert report["metrics"]["evidence_precision"]["value"] == 1.0
    assert set(report["by_fault"]) == {"cpu", "mem", "disk", "delay", "loss", "socket"}
    assert "root_service" not in str(report)


def test_candidate_gate_fails_when_joint_candidate_or_fault_floor_is_missing() -> None:
    truths = [_truth("case-a", "svc", "mem"), _truth("case-b", "svc", "cpu")]
    lattices = [_lattice("case-a", "svc", "mem", include_truth=False), _lattice("case-b", "svc", "cpu")]
    report = evaluate_p114_development_lattices(truths, lattices, modality="fused")

    gate = p114_candidate_gate_report(report)

    assert gate["passed"] is False
    assert gate["checks"]["joint_candidate_recall"] is False
    assert gate["checks"]["mem_candidate_recall"] is False


def test_evaluator_rejects_case_mismatch_duplicate_and_forged_lattice_hash() -> None:
    truth = _truth("case-a", "svc", "cpu")
    lattice = _lattice("case-a", "svc", "cpu")
    forged = copy.deepcopy(lattice)
    forged["ranked_services"] = ["forged"]

    with pytest.raises(P114DevelopmentEvaluationError, match="lattice_hash_mismatch"):
        evaluate_p114_development_lattices([truth], [forged], modality="fused")
    with pytest.raises(P114DevelopmentEvaluationError, match="case_set_mismatch"):
        evaluate_p114_development_lattices([truth], [_lattice("case-b", "svc", "cpu")], modality="fused")
    with pytest.raises(P114DevelopmentEvaluationError, match="duplicate_truth_case"):
        evaluate_p114_development_lattices([truth, truth], [lattice], modality="fused")
