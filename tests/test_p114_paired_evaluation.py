from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, cast

import pytest

from app.services.p114_adjudicator import build_p114_adjudication_packet, replay_p114_adjudication
from app.services.p114_hypothesis_lattice import build_p114_hypothesis_lattice
from app.services.p114_paired_evaluation import (
    P114PairedEvaluationError,
    evaluate_p114_paired_results,
    evaluate_p114_repeat_agreement,
    p114_adjudicator_development_gate,
)


def _artifacts() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    candidate: dict[str, object] = {
        "schema_version": "p114.re2_candidate_packet.v1",
        "case_id": "case-a",
        "system": "test",
        "injection_timestamp": 1.0,
        "evidence_graph": {
            "nodes": [
                {
                    "node_id": "ev-a",
                    "modality": "metric",
                    "subject": "payment",
                    "signal": "cpu",
                    "pre_value": 1.0,
                    "post_value": 9.0,
                    "delta": 8.0,
                    "support": [],
                    "contradiction": [],
                    "missing": [],
                }
            ],
            "edges": [],
        },
        "source_integrity": {},
    }
    lattice = build_p114_hypothesis_lattice(candidate)
    packet = build_p114_adjudication_packet(candidate, lattice)
    hypotheses = cast(tuple[Mapping[str, Any], ...], packet["hypotheses"])
    top = next(
        item
        for item in hypotheses
        if item["service"] == "payment" and item["fault"] == "cpu"
    )
    result = replay_p114_adjudication(
        packet,
        {
            "hypothesis_id": top["hypothesis_id"],
            "abstain": False,
        },
    )
    truth = {
        "schema_version": "p114.re2_scorer_truth.v1",
        "case_id": "case-a",
        "scorer_only_truth": {"root_service": "payment", "fault_type": "cpu"},
        "official_source_hash": "sha256:" + "a" * 64,
        "source_path": "hidden",
        "evidence_node_ids": ["ev-a"],
    }
    return cast(dict[str, object], truth), cast(dict[str, object], lattice), cast(dict[str, object], result)


def test_paired_evaluation_reports_exact_metrics_contract_and_zero_actions() -> None:
    truth, lattice, result = _artifacts()

    report = evaluate_p114_paired_results([truth], [lattice], [result])

    assert report["deterministic"]["joint_top1"] == {"value": 1.0, "numerator": 1, "denominator": 1}
    assert report["adjudicated"]["joint_top1"]["value"] == 1.0
    assert report["delta"]["joint_top1"] == 0.0
    assert report["contract"]["raw_contract_rate"]["value"] == 1.0
    assert report["safety"]["executed_action_count"] == 0
    assert "root_service" not in str(report)


def test_fallback_preservation_and_repeat_agreement_are_measured() -> None:
    truth, lattice, valid = _artifacts()
    packet = build_p114_adjudication_packet(
        {
            "schema_version": "p114.re2_candidate_packet.v1",
            "case_id": "case-a",
            "system": "test",
            "injection_timestamp": 1.0,
            "evidence_graph": {
                "nodes": [
                    {
                        "node_id": "ev-a",
                        "modality": "metric",
                        "subject": "payment",
                        "signal": "cpu",
                        "pre_value": 1.0,
                        "post_value": 9.0,
                        "delta": 8.0,
                        "support": [],
                        "contradiction": [],
                        "missing": [],
                    }
                ],
                "edges": [],
            },
            "source_integrity": {},
        },
        lattice,
    )
    fallback = replay_p114_adjudication(packet, "bad-json")

    report = evaluate_p114_paired_results([truth], [lattice], [fallback])
    agreement = evaluate_p114_repeat_agreement([valid], [fallback])

    assert report["contract"]["fallback_rate"]["value"] == 1.0
    assert report["contract"]["diagnosis_preservation_rate"]["value"] == 1.0
    assert agreement["agreement"]["value"] == 1.0


def test_paired_evaluator_rejects_hash_drift_and_case_mismatch() -> None:
    truth, lattice, result = _artifacts()
    forged = copy.deepcopy(result)
    forged["selected_fault"] = "mem"

    with pytest.raises(P114PairedEvaluationError, match="artifact_hash_mismatch"):
        evaluate_p114_paired_results([truth], [lattice], [forged])
    other_truth = dict(truth)
    other_truth["case_id"] = "other"
    with pytest.raises(P114PairedEvaluationError, match="case_set_mismatch"):
        evaluate_p114_paired_results([other_truth], [lattice], [result])


def test_adjudicator_development_gate_requires_nonnegative_delta_and_repeatability() -> None:
    from app.services.p110_evaluation import stable_hash

    truth, lattice, result = _artifacts()
    paired = evaluate_p114_paired_results([truth], [lattice], [result])
    agreement = evaluate_p114_repeat_agreement([result], [result])

    assert p114_adjudicator_development_gate([paired, paired], agreement)["passed"] is True

    degraded = copy.deepcopy(paired)
    degraded["delta"]["joint_top1"] = -0.1
    degraded["evaluation_hash"] = stable_hash({key: value for key, value in degraded.items() if key != "evaluation_hash"})
    gate = p114_adjudicator_development_gate([paired, degraded], agreement)
    assert gate["passed"] is False
    assert gate["checks"]["run_2_nonnegative_joint_delta"] is False
