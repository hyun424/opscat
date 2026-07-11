from __future__ import annotations

import copy

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p114_hypothesis_lattice import build_p114_hypothesis_lattice
from app.services.p115_action_contract import P115ActionContractError, build_p115_action_proposal


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


def _lattice() -> dict[str, object]:
    return build_p114_hypothesis_lattice(
        {
            "schema_version": "p114.re2_candidate_packet.v1",
            "case_id": "p115_case",
            "system": "sock_shop",
            "injection_timestamp": 10.0,
            "evidence_graph": {
                "nodes": [
                    _node("ev-payment-cpu", "payment", "cpu", 9.0),
                    _node("ev-payment-cpu-drop", "payment", "cpu", -0.5),
                    _node("ev-payment-log", "payment", "template_1", 8.0, modality="log_template"),
                    _node("ev-orders-latency", "orders", "latency-90", 2.0),
                ],
                "edges": [],
            },
            "source_integrity": {"metric_series": "a" * 64, "log_template_series": "b" * 64},
        }
    )


def _proposal(lattice: dict[str, object]) -> dict[str, object]:
    hypothesis = lattice["hypotheses"][0]  # type: ignore[index]
    return {
        "hypothesis_id": hypothesis["hypothesis_id"],
        "evidence_ids": ["ev-payment-cpu", "ev-payment-log"],
        "target": {"service": "payment", "environment": "lab"},
        "action_pack_hash": "sha256:" + "b" * 64,
        "expected_utility_inputs": {
            "recovery_benefit": 0.72,
            "harm_risk": 0.04,
            "uncertainty": 0.12,
            "rollback_cost": 0.02,
        },
        "prerequisites": ["operator review", "read-only evidence remains current"],
        "contraindications": ["suspected credential compromise"],
        "validation_plan": {"checks": ["primary_slo_recovers"], "window_seconds": 300},
        "rollback_plan": {"steps": ["do not execute in P115", "restore previous recommendation state"]},
        "reversibility": "reversible",
        "blast_radius": {"scope": "single_service", "max_affected_services": 1},
    }


def test_action_proposal_is_immutable_label_free_and_hash_bound_to_lattice_hypothesis_and_evidence() -> None:
    lattice = _lattice()
    contract = build_p115_action_proposal(lattice, _proposal(lattice))
    payload = contract.to_dict()

    assert payload["schema_version"] == "p115.action_proposal.v1"
    assert payload["lattice_hash"] == lattice["lattice_hash"]
    assert payload["hypothesis_id"] == lattice["hypotheses"][0]["hypothesis_id"]  # type: ignore[index]
    assert payload["evidence_ids"] == ["ev-payment-cpu", "ev-payment-log"]
    assert payload["authority_level"] == "L1"
    assert payload["executed_actions"] == []
    assert payload["proposal_hash"] == stable_hash({key: value for key, value in payload.items() if key != "proposal_hash"})

    with pytest.raises(AttributeError):
        contract.authority_level = "L2"  # type: ignore[misc]
    with pytest.raises(TypeError):
        contract.evidence_ids[0] = "ev-other"  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"action_pack_hash": "not-a-hash"}, "invalid_action_pack_hash"),
        ({"evidence_ids": ["ev-not-in-lattice"]}, "unknown_evidence_id"),
        ({"hypothesis_id": "hyp_unknown"}, "unknown_hypothesis"),
        ({"validation_plan": {}}, "missing_validation_plan"),
        ({"rollback_plan": {}}, "missing_rollback_plan"),
        ({"authority_level": "L2"}, "action_authority_above_l1"),
        ({"executed_actions": ["kubectl delete pod payment"]}, "executed_actions_not_empty"),
        ({"root_service": "payment"}, "truth_bearing_field"),
    ],
)
def test_action_proposal_rejects_invalid_or_truth_bearing_fields(mutation: dict[str, object], error: str) -> None:
    lattice = _lattice()
    proposal = {**_proposal(lattice), **mutation}

    with pytest.raises(P115ActionContractError, match=error):
        build_p115_action_proposal(lattice, proposal)


def test_action_proposal_rejects_forged_lattice_hash_and_nested_truth_fields() -> None:
    lattice = _lattice()
    forged = copy.deepcopy(lattice)
    forged["lattice_hash"] = "sha256:" + "c" * 64
    with pytest.raises(P115ActionContractError, match="lattice_hash_mismatch"):
        build_p115_action_proposal(forged, _proposal(lattice))

    proposal = _proposal(lattice)
    proposal["expected_utility_inputs"] = {"benefit": 1.0, "scorer_only_truth": {"fault": "cpu"}}
    with pytest.raises(P115ActionContractError, match="truth_bearing_field"):
        build_p115_action_proposal(lattice, proposal)


def test_action_proposal_rejects_lattice_evidence_not_bound_to_selected_hypothesis() -> None:
    lattice = _lattice()
    proposal = _proposal(lattice)
    proposal["evidence_ids"] = ["ev-payment-cpu", "ev-orders-latency"]

    with pytest.raises(P115ActionContractError, match="evidence_not_bound_to_hypothesis:ev-orders-latency"):
        build_p115_action_proposal(lattice, proposal)


def test_action_proposal_accepts_selected_hypothesis_contradicting_evidence_binding() -> None:
    lattice = _lattice()
    proposal = _proposal(lattice)
    proposal["evidence_ids"] = ["ev-payment-cpu", "ev-payment-cpu-drop"]

    contract = build_p115_action_proposal(lattice, proposal)

    assert contract.to_dict()["evidence_ids"] == ["ev-payment-cpu", "ev-payment-cpu-drop"]


@pytest.mark.parametrize(
    "truth_key",
    ["Ground Truth", "GROUND-TRUTH", "ground.truth", "groundTruth", "groundtruth", "Scorer Only Truth", "SCORER-ONLY-TRUTH"],
)
def test_action_proposal_rejects_truth_fields_case_insensitive_with_separator_variants(truth_key: str) -> None:
    lattice = _lattice()
    proposal = _proposal(lattice)
    proposal["expected_utility_inputs"] = {"benefit": 1.0, truth_key: {"fault": "cpu"}}

    with pytest.raises(P115ActionContractError, match="truth_bearing_field"):
        build_p115_action_proposal(lattice, proposal)
