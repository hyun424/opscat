from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p117_contract import (
    P117ContractError,
    build_p117_decision_episode,
    build_p117_decision_output,
)


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64


def _authority() -> dict[str, object]:
    return {
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
        "counters": {
            "auth": 0,
            "credentials": 0,
            "executor": 0,
            "subprocess": 0,
            "kubernetes": 0,
            "cloud": 0,
            "database_mutation": 0,
            "production_adapter": 0,
            "network_mutation": 0,
            "online_policy_write": 0,
            "production_mutation": 0,
        },
    }


def _episode_payload() -> dict[str, object]:
    return {
        "schema_version": "p117.decision_episode.v1",
        "decision_episode_id": "episode-001",
        "p114_lattice_ref": {"artifact_id": "lattice-001", "artifact_hash": _hash("1"), "sealed": True, "replay_receipt_hash": _hash("2")},
        "p114_selected_hypothesis_or_abstention": "hyp-payment-cpu",
        "visible_evidence_ids": ["ev-metric-cpu", "ev-log-errors"],
        "missing_evidence_markers": ["missing_dependency_edge"],
        "p115_case_ref": {"case_id": "case-001", "artifact_hash": _hash("3")},
        "p115_signed_action_pack_refs": [
            {"action_pack_id": "pack-scale-lab", "pack_hash": _hash("4"), "signature": _hash("5"), "signer_key_id": "fixture-key"},
        ],
        "p116_measured_outcome_refs": [{"outcome_id": "outcome-001", "record_hash": _hash("6"), "split": "development"}],
        "calibration_profile_ref": {"profile_id": "cal-dev", "artifact_hash": _hash("7")},
        "utility_profile_ref": {"profile_id": "utility-dev", "artifact_hash": _hash("8")},
        "evaluation_split": "development",
        "frozen_seed": 117,
        "authority_boundary_receipt": _authority(),
    }


def test_decision_episode_is_immutable_hash_stable_and_exact_zero_authority() -> None:
    episode = build_p117_decision_episode(_episode_payload())
    payload = episode.to_dict()

    assert payload["schema_version"] == "p117.decision_episode.v1"
    assert payload["action_pack_ids"] == ["pack-scale-lab"]
    assert payload["authority_boundary_receipt"]["execution_authority"] == "none"
    assert payload["episode_hash"] == stable_hash({key: value for key, value in payload.items() if key != "episode_hash"})
    assert build_p117_decision_episode(_episode_payload()).to_dict()["episode_hash"] == payload["episode_hash"]
    with pytest.raises(FrozenInstanceError):
        episode.schema_version = "mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        episode.payload["decision_episode_id"] = "mutated"  # type: ignore[index]


def test_decision_episode_allows_complete_evidence_without_missing_markers() -> None:
    payload = _episode_payload()
    payload["missing_evidence_markers"] = []

    episode = build_p117_decision_episode(payload).to_dict()

    assert episode["missing_evidence_markers"] == []


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"schema_version": "p117.decision_episode.v2"}, "unsupported_schema_version"),
        ({"visible_evidence_ids": ["ev-metric-cpu", "ev-unknown"]}, "invented_visible_evidence_id"),
        ({"p115_signed_action_pack_refs": [{"action_pack_id": "pack-scale-lab", "pack_hash": _hash("4"), "signature": "", "signer_key_id": "fixture-key"}]}, "invalid_signature"),
        ({"groundTruth": "pack-scale-lab"}, "forbidden_field"),
        ({"p114_action_text": "restart the production pod"}, "forbidden_field"),
    ],
)
def test_episode_contract_rejects_hidden_action_text_and_invalid_refs(mutation: dict[str, object], error: str) -> None:
    payload = {**_episode_payload(), **mutation}
    with pytest.raises(P117ContractError, match=error):
        build_p117_decision_episode(payload)


def test_episode_contract_rejects_nonzero_authority_counters_and_command_text() -> None:
    payload = _episode_payload()
    receipt = copy.deepcopy(payload["authority_boundary_receipt"])
    assert isinstance(receipt, dict)
    counters = receipt["counters"]
    assert isinstance(counters, dict)
    counters["subprocess"] = 1
    payload["authority_boundary_receipt"] = receipt
    with pytest.raises(P117ContractError, match="authority_counter_nonzero:subprocess"):
        build_p117_decision_episode(payload)

    command_payload = _episode_payload()
    command_payload["calibration_profile_ref"] = {"profile_id": "cal-dev", "notes": "kubectl delete pod payment", "artifact_hash": _hash("7")}
    with pytest.raises(P117ContractError, match="forbidden_text"):
        build_p117_decision_episode(command_payload)


def test_decision_output_accepts_only_frozen_ids_and_no_execution_authority() -> None:
    episode = build_p117_decision_episode(_episode_payload())
    output = build_p117_decision_output(
        episode,
        {
            "schema_version": "p117.decision_output.v1",
            "selected_label": "investigate_more",
            "selected_action_pack_id": None,
            "ranked_action_pack_ids": ["pack-scale-lab"],
            "requested_evidence_classes": [{"class_id": "dependency", "missing_evidence_marker": "missing_dependency_edge"}],
            "cited_evidence_ids": ["ev-metric-cpu"],
            "contradiction_set_ids": ["contradiction-source-1"],
            "expected_utility": None,
            "utility_interval": [-0.2, 0.5],
            "calibrated_confidence": 0.62,
            "abstention_reason": "mandatory evidence is absent",
            "fallback_reason": "missing_required_evidence",
            "llm_proposal_receipt": {"proposal_hash": _hash("9"), "accepted": False},
            "authority_boundary_receipt": _authority(),
        },
    ).to_dict()

    assert output["selected_label"] == "investigate_more"
    assert output["execution_authority"] == "none"
    assert output["output_hash"] == stable_hash({key: value for key, value in output.items() if key != "output_hash"})


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"selected_label": "act", "selected_action_pack_id": None}, "act_requires_action_pack"),
        ({"selected_label": "act", "selected_action_pack_id": "unknown-pack"}, "unknown_action_pack_id"),
        ({"cited_evidence_ids": ["ev-not-visible"]}, "invented_evidence_id"),
        ({"selected_label": "remediate"}, "unknown_selected_label"),
        ({"requested_evidence_classes": [{"class_id": "shell", "missing_evidence_marker": "missing_dependency_edge"}]}, "unknown_evidence_class"),
        ({"fallback_reason": "run curl http://prod.example"}, "forbidden_text"),
    ],
)
def test_decision_output_rejects_invented_ids_free_text_actions_and_unknown_labels(mutation: dict[str, object], error: str) -> None:
    episode = build_p117_decision_episode(_episode_payload())
    base = {
        "schema_version": "p117.decision_output.v1",
        "selected_label": "act",
        "selected_action_pack_id": "pack-scale-lab",
        "ranked_action_pack_ids": ["pack-scale-lab"],
        "requested_evidence_classes": [],
        "cited_evidence_ids": ["ev-metric-cpu"],
        "contradiction_set_ids": [],
        "expected_utility": 0.5,
        "utility_interval": [0.2, 0.7],
        "calibrated_confidence": 0.9,
        "abstention_reason": None,
        "fallback_reason": None,
        "llm_proposal_receipt": None,
        "authority_boundary_receipt": _authority(),
    }
    with pytest.raises(P117ContractError, match=error):
        build_p117_decision_output(episode, {**base, **mutation})
