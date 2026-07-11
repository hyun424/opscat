from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from inspect import signature
from typing import Any, cast

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p114_acceptance import (
    ACCEPTANCE_GATES,
    P114_REQUIRED_SAFETY_COUNTERS,
    P114_RUNTIME_SAFETY_COUNTERS,
    P114AcceptanceError,
    _acceptance_gate,
    build_p114_acceptance_freeze,
    build_p114_acceptance_lattices,
    evaluate_p114_re2_ob_blind,
    validate_p114_acceptance_freeze,
)
from app.services.p114_fault_knn import train_p114_fault_knn
from app.services.p114_hypothesis_lattice import FAULTS
from app.services.p114_re2_loader import P114EvidenceNode, P114RE2Case

FROZEN_AT = "2026-07-11T00:00:00Z"
SCORED_AT = "2026-07-11T00:00:01Z"
RUNTIME_SAFETY = {counter: 0 for counter in P114_RUNTIME_SAFETY_COUNTERS}


def test_p114_acceptance_freeze_roundtrip_rejects_drift() -> None:
    bundle = _synthetic_acceptance_bundle()

    freeze = build_p114_acceptance_freeze(**bundle.freeze_inputs)

    assert freeze["case_count"] == 90
    assert freeze["acceptance_gates"] == ACCEPTANCE_GATES
    assert freeze["llm_adjudication_enabled"] is False
    assert freeze["action_contract_status"] == "disabled"
    validate_p114_acceptance_freeze(freeze, **bundle.validation_inputs)

    drifted = dict(freeze)
    drifted["case_ids"] = list(freeze["case_ids"])
    drifted["case_ids"][0] = "case_drift"
    drifted["freeze_hash"] = stable_hash({key: value for key, value in drifted.items() if key != "freeze_hash"})

    with pytest.raises(P114AcceptanceError, match="freeze_drift"):
        validate_p114_acceptance_freeze(drifted, **bundle.validation_inputs)


def test_p114_acceptance_rejects_scoring_before_freeze_time() -> None:
    bundle = _synthetic_acceptance_bundle()
    freeze = build_p114_acceptance_freeze(**bundle.freeze_inputs)

    with pytest.raises(P114AcceptanceError, match="scoring_before_freeze"):
        evaluate_p114_re2_ob_blind(
            bundle.cases,
            bundle.lattices,
            bundle.lattices,
            freeze,
            scored_at="2026-07-10T23:59:59Z",
            source_sha256_after="sha256:" + "a" * 64,
            runtime_safety=RUNTIME_SAFETY,
        )


def test_p114_acceptance_aggregates_passing_metrics_and_preserves_no_action_contract() -> None:
    bundle = _synthetic_acceptance_bundle()
    freeze = build_p114_acceptance_freeze(**bundle.freeze_inputs)

    report, gate = evaluate_p114_re2_ob_blind(
        bundle.cases,
        bundle.lattices,
        bundle.lattices,
        freeze,
        scored_at=SCORED_AT,
        source_sha256_after="sha256:" + "a" * 64,
        runtime_safety=RUNTIME_SAFETY,
    )

    assert report["benchmark_role"] == "fresh_case_multimodal_acceptance_consumed_after_score"
    assert report["freeze_hash"] == freeze["freeze_hash"]
    assert report["metrics"]["case_count"] == 90
    assert report["metrics"]["service_top1"] == {"value": 1.0, "numerator": 90, "denominator": 90}
    assert report["metrics"]["service_top3"] == {"value": 1.0, "numerator": 90, "denominator": 90}
    assert report["metrics"]["fault_accuracy"] == {"value": 1.0, "numerator": 90, "denominator": 90}
    assert report["metrics"]["joint_top1"] == {"value": 1.0, "numerator": 90, "denominator": 90}
    assert report["metrics"]["joint_candidate_recall"] == {"value": 1.0, "numerator": 90, "denominator": 90}
    assert report["metrics"]["evidence_precision"]["value"] == 1.0
    assert report["metrics"]["replay_consistency"] == {"value": 1.0, "numerator": 90, "denominator": 90}
    assert report["metrics"]["diagnosis_preservation"] == {"value": 1.0, "numerator": 1, "denominator": 1}
    assert report["safety"]
    assert all(value == 0 for value in report["safety"].values())

    for fault in FAULTS:
        assert report["by_fault"][fault]["case_count"] == 15
        assert report["by_fault"][fault]["fault_accuracy"] == {
            "value": 1.0,
            "numerator": 15,
            "denominator": 15,
        }

    assert gate["passed"] is True
    assert all(gate["checks"].values())
    assert gate["evaluation_hash"] == report["evaluation_hash"]
    assert all(lattice["action_contract_status"] == "disabled" for lattice in bundle.lattices)
    assert all(lattice["executed_actions"] == [] for lattice in bundle.lattices)


def test_freeze_api_does_not_accept_external_truth_derived_lattices() -> None:
    assert "lattices" not in signature(build_p114_acceptance_freeze).parameters


def test_acceptance_gate_measures_action_artifact_violations() -> None:
    bundle = _synthetic_acceptance_bundle()
    freeze = build_p114_acceptance_freeze(**bundle.freeze_inputs)
    unsafe = [cast(dict[str, Any], copy.deepcopy(lattice)) for lattice in bundle.lattices]
    unsafe[0]["action_contract_status"] = "enabled"
    unsafe[0]["executed_actions"] = [{"kind": "forbidden-test-action"}]
    unsafe[0]["lattice_hash"] = stable_hash({key: value for key, value in unsafe[0].items() if key != "lattice_hash"})

    report, gate = evaluate_p114_re2_ob_blind(
        bundle.cases,
        unsafe,
        unsafe,
        freeze,
        scored_at=SCORED_AT,
        source_sha256_after="sha256:" + "a" * 64,
        runtime_safety=RUNTIME_SAFETY,
    )

    assert report["safety"]["executed_action_count"] == 1
    assert report["safety"]["artifact_authority_violation_count"] == 1
    assert gate["checks"]["complete_zero_safety_counters"] is False
    assert gate["passed"] is False


@pytest.mark.parametrize("counter", P114_REQUIRED_SAFETY_COUNTERS)
def test_acceptance_gate_fails_closed_when_safety_counter_is_missing(counter: str) -> None:
    bundle = _synthetic_acceptance_bundle()
    freeze = build_p114_acceptance_freeze(**bundle.freeze_inputs)
    report, _gate = evaluate_p114_re2_ob_blind(
        bundle.cases,
        bundle.lattices,
        bundle.lattices,
        freeze,
        scored_at=SCORED_AT,
        source_sha256_after="sha256:" + "a" * 64,
        runtime_safety=RUNTIME_SAFETY,
    )
    del report["safety"][counter]
    report["evaluation_hash"] = stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"})

    gate = _acceptance_gate(report)

    assert gate["checks"]["complete_zero_safety_counters"] is False
    assert gate["passed"] is False


class _Bundle:
    def __init__(
        self,
        *,
        cases: tuple[P114RE2Case, ...],
        packets: tuple[Mapping[str, Any], ...],
        lattices: tuple[Mapping[str, Any], ...],
        source_verification: Mapping[str, Any],
        model: Mapping[str, Any],
        development_gate: Mapping[str, Any],
        implementation_hash: str,
    ) -> None:
        self.cases = cases
        self.packets = packets
        self.lattices = lattices
        self.freeze_inputs: dict[str, Any] = {
            "source_verification": source_verification,
            "model": model,
            "packets": packets,
            "development_gate": development_gate,
            "implementation_hash": implementation_hash,
            "frozen_at": FROZEN_AT,
        }
        self.validation_inputs: dict[str, Any] = {
            "source_verification": source_verification,
            "model": model,
            "packets": packets,
            "development_gate": development_gate,
            "implementation_hash": implementation_hash,
        }


def _synthetic_acceptance_bundle() -> _Bundle:
    cases = tuple(_case(index, fault) for index, fault in enumerate(_fault_sequence()))
    packets = tuple(case.to_candidate_packet() for case in cases)
    model = train_p114_fault_knn(cases)
    lattices = build_p114_acceptance_lattices(packets, model)
    return _Bundle(
        cases=cases,
        packets=packets,
        lattices=lattices,
        source_verification={
            "verified": True,
            "source_id": "rcaeval-re2-ob",
            "sha256": "a" * 64,
            "bytes": 90_000,
            "case_count": 90,
        },
        model=model,
        development_gate=_development_gate(),
        implementation_hash="sha256:" + "b" * 64,
    )


def _fault_sequence() -> tuple[str, ...]:
    return tuple(fault for fault in FAULTS for _ in range(15))


def _case(index: int, fault: str) -> P114RE2Case:
    service = f"service-{index % 15:02d}"
    node_ids = (f"node-{index:03d}-primary", f"node-{index:03d}-log")
    return P114RE2Case(
        case_id=f"case-{index:03d}",
        system="synthetic-re2-ob",
        inject_time=1000.0 + index,
        official_source_hash="sha256:" + "a" * 64,
        raw_hashes={
            "inject_time.txt": "1" * 64,
            "simple_metrics.csv": "2" * 64,
            "logts.csv": "3" * 64,
            "cluster_info.json": "4" * 64,
        },
        scorer_only_truth={"root_service": service, "fault_type": fault},
        nodes=(
            _node(node_ids[0], service, _signal_for_fault(fault), 10.0, 30.0),
            _node(node_ids[1], service, "template-burst", 1.0, 3.0, modality="log_template"),
        ),
        edges=(),
        source_path=f"heldout/{index:03d}",
    )


def _node(
    node_id: str,
    service: str,
    signal: str,
    pre_value: float,
    post_value: float,
    *,
    modality: str = "metric",
) -> P114EvidenceNode:
    return P114EvidenceNode(
        node_id=node_id,
        modality=modality,
        subject=service,
        signal=signal,
        statistic="median",
        pre_value=pre_value,
        post_value=post_value,
        delta=post_value - pre_value,
        support=("synthetic-support",),
        contradiction=(),
        missing=(),
        source={"binding": node_id},
    )


def _signal_for_fault(fault: str) -> str:
    return {
        "cpu": "cpu",
        "mem": "mem",
        "disk": "diskio",
        "delay": "latency-90",
        "loss": "error",
        "socket": "socket",
    }[fault]


def _nodes(packet: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    graph = packet["evidence_graph"]
    return graph["nodes"]


def _development_gate() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "p114.synthetic_development_gate.v1",
        "passed": True,
        "checks": {"synthetic_acceptance_fixture": True},
    }
    payload["gate_hash"] = stable_hash(payload)
    return payload
