from __future__ import annotations

import copy

import pytest

from app.services.p114_fault_knn import (
    FEATURES,
    P114FaultKNNError,
    predict_p114_fault,
    rerank_p114_lattice_with_fault_knn,
    train_p114_fault_knn,
)
from app.services.p114_hypothesis_lattice import build_p114_hypothesis_lattice
from app.services.p114_re2_loader import P114EvidenceNode, P114RE2Case


def _case(index: int, fault: str, service: str, signal: str) -> P114RE2Case:
    node = P114EvidenceNode(
        node_id=f"ev-{index}",
        modality="metric",
        subject=service,
        signal=signal,
        statistic="delta",
        pre_value=1.0,
        post_value=10.0,
        delta=9.0,
        support=(),
        contradiction=(),
        missing=(),
        source={},
    )
    return P114RE2Case(
        case_id=f"case-{index}",
        system="test",
        inject_time=1.0,
        official_source_hash="sha256:" + "a" * 64,
        raw_hashes={"inject_time.txt": "a", "simple_metrics.csv": "b", "logts.csv": "c", "cluster_info.json": "d"},
        scorer_only_truth={"root_service": service, "fault_type": fault, "repetition": 1},
        nodes=(node,),
        edges=(),
        source_path="hidden",
    )


def _training_cases() -> tuple[P114RE2Case, ...]:
    signal_by_fault = {"cpu": "cpu", "mem": "mem", "disk": "diskio", "delay": "latency-90", "loss": "workload", "socket": "socket"}
    return tuple(_case(index * 10 + repeat, fault, f"svc-{index}-{repeat}", signal_by_fault[fault]) for index, fault in enumerate(signal_by_fault) for repeat in range(3))


def test_model_contains_no_service_or_case_identity_and_reranks_lattice() -> None:
    cases = _training_cases()
    model = train_p114_fault_knn(cases)
    target = _case(999, "socket", "unseen", "socket")
    packet = target.to_candidate_packet()
    prediction = predict_p114_fault(packet, "unseen", model)
    lattice = rerank_p114_lattice_with_fault_knn(packet, build_p114_hypothesis_lattice(packet), model)

    assert tuple(model["features"]) == FEATURES
    assert model["contains_service_names"] is False
    assert model["contains_case_ids"] is False
    assert "svc-" not in str(model)
    assert "case-" not in str(model)
    assert prediction["ranked_faults"][0] == "socket"
    assert lattice["hypotheses"][0]["fault"] == "socket"
    assert lattice["fault_model_hash"] == model["model_hash"]


def test_model_and_lattice_hash_drift_fail_closed() -> None:
    cases = _training_cases()
    model = train_p114_fault_knn(cases)
    target = _case(999, "cpu", "unseen", "cpu")
    packet = target.to_candidate_packet()
    lattice = build_p114_hypothesis_lattice(packet)
    forged_model = copy.deepcopy(model)
    forged_model["k"] = 1
    forged_lattice = copy.deepcopy(lattice)
    forged_lattice["ranked_services"] = ["attacker"]

    with pytest.raises(P114FaultKNNError, match="invalid_model"):
        predict_p114_fault(packet, "unseen", forged_model)
    with pytest.raises(P114FaultKNNError, match="invalid_lattice"):
        rerank_p114_lattice_with_fault_knn(packet, forged_lattice, model)
