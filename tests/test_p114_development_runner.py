from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from scripts.run_p114_development_eval import _packet_for_modality, run_development_evaluation


def _packet() -> dict[str, object]:
    nodes = [
        {
            "node_id": "metric-a",
            "modality": "metric",
            "subject": "svc",
            "signal": "cpu",
            "pre_value": 1.0,
            "post_value": 3.0,
            "delta": 2.0,
        },
        {
            "node_id": "log-a",
            "modality": "log_template",
            "subject": "svc",
            "signal": "template-1",
            "pre_value": 1.0,
            "post_value": 2.0,
            "delta": 1.0,
        },
    ]
    return {
        "schema_version": "p114.re2_candidate_packet.v1",
        "case_id": "case-a",
        "system": "test",
        "injection_timestamp": 1.0,
        "evidence_graph": {
            "nodes": nodes,
            "edges": [
                {
                    "edge_id": "cross",
                    "source_node_id": "metric-a",
                    "target_node_id": "log-a",
                    "relation": "cochange",
                }
            ],
        },
        "source_integrity": {},
    }


def test_modality_ablation_removes_cross_modality_nodes_and_edges() -> None:
    metric = _packet_for_modality(_packet(), "metric")
    log = _packet_for_modality(_packet(), "log_template")

    assert [node["node_id"] for node in metric["evidence_graph"]["nodes"]] == ["metric-a"]
    assert metric["evidence_graph"]["edges"] == []
    assert [node["node_id"] for node in log["evidence_graph"]["nodes"]] == ["log-a"]
    assert log["evidence_graph"]["edges"] == []


def test_runner_writes_aggregate_reports_without_scorer_truth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Case:
        def to_candidate_packet(self) -> dict[str, object]:
            return _packet()

        def to_scorer_truth(self) -> dict[str, object]:
            return {
                "schema_version": "p114.re2_scorer_truth.v1",
                "case_id": "case-a",
                "scorer_only_truth": {"root_service": "svc", "fault_type": "cpu"},
                "official_source_hash": "sha256:" + "a" * 64,
                "source_path": "hidden",
                "evidence_node_ids": ["metric-a", "log-a"],
            }

    def load_cases_stub(*args: Any, **kwargs: Any) -> tuple[Case, ...]:
        return (Case(),)

    monkeypatch.setattr(
        "scripts.run_p114_development_eval.load_pinned_re2_cases",
        load_cases_stub,
    )

    summary = run_development_evaluation(
        "archive.zip",
        "manifest.json",
        hmac_key=b"secret",
        output_dir=tmp_path,
    )

    assert summary["case_count"] == 1
    assert summary["action_authority"] == "disabled"
    report = json.loads((tmp_path / "fused-evaluation.json").read_text())
    assert "root_service" not in json.dumps(report)
    lattices = json.loads((tmp_path / "fused-lattices.json").read_text())
    assert lattices["lattices"][0]["lattice_hash"] == stable_hash({key: value for key, value in lattices["lattices"][0].items() if key != "lattice_hash"})
