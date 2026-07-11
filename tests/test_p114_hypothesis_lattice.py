from __future__ import annotations

import copy

import pytest

from app.services.p114_hypothesis_lattice import P114HypothesisError, build_p114_hypothesis_lattice


def _node(node_id: str, subject: str, signal: str, delta: float, *, modality: str = "metric") -> dict[str, object]:
    return {
        "node_id": node_id,
        "modality": modality,
        "subject": subject,
        "signal": signal,
        "statistic": "post_minus_pre_mean",
        "pre_value": 1.0,
        "post_value": 1.0 + delta,
        "delta": delta,
        "support": [],
        "contradiction": [],
        "missing": [],
        "source": {"source_token": modality, "sample_count": 4},
    }


def _packet() -> dict[str, object]:
    return {
        "schema_version": "p114.re2_candidate_packet.v1",
        "case_id": "p114_case",
        "system": "sock_shop",
        "injection_timestamp": 10.0,
        "evidence_graph": {
            "nodes": [
                _node("ev-payment-cpu", "payment", "cpu", 9.0),
                _node("ev-payment-log", "payment", "template_1", 8.0, modality="log_template"),
                _node("ev-orders-latency", "orders", "latency-90", 2.0),
                _node("ev-orders-error", "orders", "error", 1.0),
            ],
            "edges": [],
        },
        "source_integrity": {"metric_series": "a" * 64, "log_template_series": "b" * 64},
    }


def test_lattice_ranks_typed_service_fault_pair_and_binds_evidence() -> None:
    lattice = build_p114_hypothesis_lattice(_packet())

    top = lattice["hypotheses"][0]
    assert top["service"] == "payment"
    assert top["fault"] == "cpu"
    assert "ev-payment-cpu" in top["supporting_evidence_ids"]
    assert lattice["ranked_services"][0] == "payment"
    assert lattice["action_contract_status"] == "disabled"
    assert lattice["executed_actions"] == []
    assert lattice["lattice_hash"].startswith("sha256:")


def test_lattice_is_order_invariant_and_supports_all_six_fault_families() -> None:
    packet = _packet()
    reversed_packet = copy.deepcopy(packet)
    reversed_packet["evidence_graph"]["nodes"].reverse()  # type: ignore[index]

    first = build_p114_hypothesis_lattice(packet, max_hypotheses=30)
    second = build_p114_hypothesis_lattice(reversed_packet, max_hypotheses=30)

    assert first == second
    assert set(first["ranked_faults"]) == {"cpu", "mem", "disk", "delay", "loss", "socket"}
    assert len({item["hypothesis_id"] for item in first["hypotheses"]}) == len(first["hypotheses"])


def test_lattice_marks_missing_typed_evidence_and_never_invents_evidence_ids() -> None:
    lattice = build_p114_hypothesis_lattice(_packet(), max_hypotheses=30)
    known = {node["node_id"] for node in _packet()["evidence_graph"]["nodes"]}  # type: ignore[index]
    memory = next(item for item in lattice["hypotheses"] if item["service"] == "payment" and item["fault"] == "mem")

    assert "typed_metric_evidence" in memory["missing_evidence"]
    for hypothesis in lattice["hypotheses"]:
        assert set(hypothesis["supporting_evidence_ids"]) <= known
        assert set(hypothesis["contradicting_evidence_ids"]) <= known


@pytest.mark.parametrize(
    "mutation,error",
    [
        ({"schema_version": "wrong"}, "invalid_candidate_schema"),
        ({"evidence_graph": {"nodes": [], "edges": []}}, "missing_evidence_nodes"),
    ],
)
def test_lattice_fails_closed_on_invalid_candidate_packet(mutation: dict[str, object], error: str) -> None:
    packet = {**_packet(), **mutation}
    with pytest.raises(P114HypothesisError, match=error):
        build_p114_hypothesis_lattice(packet)


def test_lattice_rejects_duplicate_nodes_nonfinite_values_and_invalid_budget() -> None:
    duplicate = _packet()
    duplicate["evidence_graph"]["nodes"].append(copy.deepcopy(duplicate["evidence_graph"]["nodes"][0]))  # type: ignore[index]
    nonfinite = _packet()
    nonfinite["evidence_graph"]["nodes"][0]["delta"] = float("nan")  # type: ignore[index]

    with pytest.raises(P114HypothesisError, match="duplicate_evidence_node"):
        build_p114_hypothesis_lattice(duplicate)
    with pytest.raises(P114HypothesisError, match="nonfinite_evidence_value"):
        build_p114_hypothesis_lattice(nonfinite)
    with pytest.raises(P114HypothesisError, match="invalid_hypothesis_budget"):
        build_p114_hypothesis_lattice(_packet(), max_hypotheses=0)


def test_fault_signature_normalization_prevents_cpu_dominating_socket_and_loss() -> None:
    packet = _packet()
    packet["evidence_graph"]["nodes"] = [  # type: ignore[index]
        _node("cpu", "svc", "cpu", 39.0),
        _node("socket", "svc", "socket", 2.0),
        _node("latency", "other", "latency-90", 2.0),
        _node("workload", "other", "workload", -0.5),
    ]
    packet["evidence_graph"]["edges"] = []  # type: ignore[index]

    lattice = build_p114_hypothesis_lattice(packet)
    scores = {(item["service"], item["fault"]): item["score"] for item in lattice["hypotheses"]}

    assert scores[("svc", "socket")] > scores[("svc", "cpu")]
    assert scores[("other", "loss")] > scores[("other", "delay")]
