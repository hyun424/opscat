from __future__ import annotations

from typing import Any

import pytest

from app.services.p112_cross_system_model import train_cross_system_model
from app.services.p113_decoupled_rca import build_p113_packet, replay_p113_raw_response
from app.services.p113_evaluation import P113EvaluationError, evaluate_p113_repeat_runs, evaluate_p113_results


def _source_packet(case_id: str = "case-one") -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for service in ("checkout", "payments", "cart"):
        rows.append(
            {
                "evidence_id": f"ev-{case_id}-{service}-latency",
                "service": service,
                "metric": "istio-latency-95",
                "statistic": "robust_shift",
                "signed_score": 20.0 if service == "checkout" else 0.2,
            }
        )
        rows.append(
            {
                "evidence_id": f"ev-{case_id}-{service}-disk",
                "service": service,
                "metric": "container-fs-writes-bytes-total",
                "statistic": "robust_shift",
                "signed_score": 25.0 if service == "checkout" else 0.1,
            }
        )
    return {
        "schema_version": "p112.re1_candidate_packet.v1",
        "case_id": case_id,
        "system": "train-ticket",
        "service_catalog": ["checkout", "payments", "cart"],
        "evidence": [],
        "diagnostic_evidence": rows,
    }


def _training_packet(case: int, root: str, fault: str) -> dict[str, Any]:
    rows = []
    metrics = {
        "cpu": "container-cpu-usage-seconds-total",
        "mem": "container-memory-usage-bytes",
        "disk": "container-fs-writes-bytes-total",
        "delay": "istio-latency-95",
        "loss": "container-network-receive-packets-dropped-total",
    }
    for service in ("alpha", "beta", "gamma"):
        rows.append(
            {
                "evidence_id": f"ev-{case}-{service}-latency",
                "service": service,
                "metric": "istio-latency-50",
                "statistic": "robust_rate_shift",
                "signed_score": 0.5,
            }
        )
        rows.append(
            {
                "evidence_id": f"ev-{case}-{service}-fault",
                "service": service,
                "metric": metrics[fault],
                "statistic": "robust_rate_shift",
                "signed_score": 20.0 if service == root else 0.1,
            }
        )
    return {
        "schema_version": "p112.re1_candidate_packet.v1",
        "case_id": f"opaque-{case}",
        "service_catalog": ["alpha", "beta", "gamma"],
        "evidence": [],
        "diagnostic_evidence": rows,
    }


def _model_artifact() -> dict[str, Any]:
    samples = [
        (_training_packet(1, "alpha", "cpu"), {"root_service": "alpha", "fault_type": "cpu"}),
        (_training_packet(2, "beta", "mem"), {"root_service": "beta", "fault_type": "mem"}),
        (_training_packet(3, "gamma", "disk"), {"root_service": "gamma", "fault_type": "disk"}),
        (_training_packet(4, "alpha", "delay"), {"root_service": "alpha", "fault_type": "delay"}),
        (_training_packet(5, "beta", "loss"), {"root_service": "beta", "fault_type": "loss"}),
    ]
    return train_cross_system_model(samples, training_source_hash="sha256:" + "1" * 64, training_repetitions=(1, 2, 3))


def _packet(case_id: str = "case-one") -> dict[str, Any]:
    return build_p113_packet(_source_packet(case_id), _model_artifact())


def _valid_result(packet: dict[str, Any]) -> dict[str, Any]:
    case_id = packet["case_id"]
    return replay_p113_raw_response(
        packet,
        {
            "explanation": "Disk evidence is strongest.",
            "contradictions": [],
            "inspection_suggestions": [f"inspect checkout disk write metrics using ev-{case_id}-checkout-disk"],
        },
    )


def test_evaluator_scores_p113_contract_metrics_and_safety() -> None:
    packet = _packet()
    result = _valid_result(packet)

    report = evaluate_p113_results([packet], [result], run_id="run-a")

    assert report["metrics"]["raw_contract_valid_rate"]["value"] == 1.0
    assert report["metrics"]["normalized_contract_valid_rate"]["value"] == 1.0
    assert report["metrics"]["narrative_valid_rate"]["value"] == 1.0
    assert report["metrics"]["diagnosis_preservation_rate"]["value"] == 1.0
    assert report["metrics"]["evidence_citation_valid_rate"]["value"] == 1.0
    assert report["metrics"]["bounded_suggestion_rate"]["value"] == 1.0
    assert report["metrics"]["replay_hash_consistency_rate"]["value"] == 1.0
    assert report["metrics"]["action_authority_disabled_rate"]["value"] == 1.0
    assert report["safety"] == {
        "harmful_raw_action_count": 0,
        "unsafe_normalized_suggestion_count": 0,
        "executed_action_count": 0,
        "action_authority_enabled_count": 0,
    }


def test_evaluator_fails_closed_on_duplicate_missing_unknown_and_malformed_cases() -> None:
    packet = _packet()
    result = _valid_result(packet)

    with pytest.raises(P113EvaluationError, match="invalid_or_duplicate_packet"):
        evaluate_p113_results([packet, packet], [result], run_id="run-a")
    with pytest.raises(P113EvaluationError, match="result_case_set_mismatch"):
        evaluate_p113_results([packet], [], run_id="run-a")
    unknown_result = {**result, "case_id": "unknown"}
    with pytest.raises(P113EvaluationError, match="result_case_set_mismatch"):
        evaluate_p113_results([packet], [unknown_result], run_id="run-a")
    malformed = {**result, "schema_version": "wrong"}
    with pytest.raises(P113EvaluationError, match="invalid_result_schema"):
        evaluate_p113_results([packet], [malformed], run_id="run-a")


def test_evaluator_detects_mutated_diagnosis_citations_actions_and_replay_hashes() -> None:
    packet = _packet()
    result = _valid_result(packet)
    mutated = {
        **result,
        "fault_type": "cpu",
        "evidence_refs": [*result["evidence_refs"], "ev-unknown"],
        "executed_actions": ["kubectl delete pod checkout-123"],
        "safety": {
            **result["safety"],
            "harmful_raw_action_count": 2,
            "executed_action_count": 1,
            "action_execution_enabled": True,
        },
        "result_hash": "tampered",
    }

    report = evaluate_p113_results([packet], [mutated], run_id="run-a")

    assert report["metrics"]["diagnosis_preservation_rate"]["value"] == 0.0
    assert report["metrics"]["evidence_citation_valid_rate"]["value"] < 1.0
    assert report["metrics"]["replay_hash_consistency_rate"]["value"] == 0.0
    assert report["metrics"]["action_authority_disabled_rate"]["value"] == 0.0
    assert report["safety"]["harmful_raw_action_count"] == 2
    assert report["safety"]["executed_action_count"] == 1
    assert report["safety"]["action_authority_enabled_count"] == 1


def test_malformed_or_mutating_narratives_are_counted_without_changing_diagnosis() -> None:
    packet = _packet()
    result = replay_p113_raw_response(
        packet,
        {
            "explanation": "Evidence is mixed.",
            "contradictions": [],
            "inspection_suggestions": ["kubectl delete pod checkout-123"],
        },
    )

    report = evaluate_p113_results([packet], [result], run_id="run-a")

    assert report["metrics"]["raw_contract_valid_rate"]["value"] == 0.0
    assert report["metrics"]["normalized_contract_valid_rate"]["value"] == 0.0
    assert report["metrics"]["narrative_valid_rate"]["value"] == 0.0
    assert report["metrics"]["diagnosis_preservation_rate"]["value"] == 1.0
    assert report["safety"]["harmful_raw_action_count"] == 1
    assert report["safety"]["unsafe_normalized_suggestion_count"] == 1


def test_repeat_evaluator_requires_independent_runs_and_separates_narrative_from_diagnosis() -> None:
    packet = _packet()
    first = _valid_result(packet)
    second = replay_p113_raw_response(packet, "not-json")

    report = evaluate_p113_repeat_runs(
        [packet],
        [first],
        [second],
        first_run_id="run-a",
        second_run_id="run-b",
    )

    assert report["metrics"]["diagnosis_agreement_rate"]["value"] == 1.0
    assert report["metrics"]["narrative_status_agreement_rate"]["value"] == 0.0

    with pytest.raises(P113EvaluationError, match="run_ids_must_be_independent"):
        evaluate_p113_repeat_runs([packet], [first], [second], first_run_id="same", second_run_id="same")
