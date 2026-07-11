from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.p114_re2_loader import P114EvidenceNode, P114RE2Case
from scripts.run_p114_adjudication_development import (
    run_adjudication_development,
    stratified_development_cases,
)


@dataclass
class SelectingProvider:
    name: str = "fake"
    model_calls_enabled: bool = False

    def diagnose(self, packet: dict[str, Any], prompt: str) -> dict[str, Any]:
        hypothesis = next(item for item in packet["hypotheses"] if item["hypothesis_id"] == packet["deterministic_fallback_hypothesis_id"])
        return {
            "hypothesis_id": hypothesis["hypothesis_id"],
            "abstain": False,
        }


def _case(index: int, fault: str) -> P114RE2Case:
    node = P114EvidenceNode(
        node_id=f"ev-{index}",
        modality="metric",
        subject="svc",
        signal=fault,
        statistic="delta",
        pre_value=1.0,
        post_value=2.0,
        delta=1.0,
        support=(),
        contradiction=(),
        missing=(),
        source={},
    )
    return P114RE2Case(
        case_id=f"case-{index:02d}",
        system="test",
        inject_time=1.0,
        official_source_hash="sha256:" + "a" * 64,
        raw_hashes={
            "inject_time.txt": "a",
            "simple_metrics.csv": "b",
            "logts.csv": "c",
            "cluster_info.json": "d",
        },
        scorer_only_truth={"root_service": "svc", "fault_type": fault, "repetition": 1},
        nodes=(node,),
        edges=(),
        source_path=f"hidden/{index}",
    )


def test_stratified_selection_and_two_run_evaluation(tmp_path: Any) -> None:
    faults = ("cpu", "mem", "disk", "delay", "loss", "socket")
    cases = tuple(_case(index, fault) for index, fault in enumerate((*faults, *faults)))
    selected = stratified_development_cases(cases, per_fault=1)

    summary = run_adjudication_development(
        selected,
        provider=SelectingProvider(),  # type: ignore[arg-type]
        model="fake/model",
        runs=2,
        output_dir=tmp_path,
    )

    assert len(selected) == 6
    assert summary["case_count"] == 6
    assert summary["repeat_agreement"] == 1.0
    assert summary["raw_contract_rates"] == [1.0, 1.0]
    assert summary["executed_action_count"] == 0
    assert summary["development_gates_passed"] is True
    assert (tmp_path / "run-1-results.json").exists()
    assert (tmp_path / "run-2-paired-evaluation.json").exists()
