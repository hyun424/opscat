from __future__ import annotations

import copy

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p115_ontology import build_action_pack, sign_action_pack_payload
from app.services.p118_approval import validate_p118_approval_decision_receipt
from app.services.p119_contract import exact_zero_authority_counters
from app.services.p119_selection import P119SelectionError, approve_p119_selection


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def _decision(label: str = "act", selected_id: str | None = "pack-local-1") -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "p117.deterministic_decision.v1",
        "decision_episode_id": "episode-p119-1",
        "selected_label": label,
        "selected_action_pack_id": selected_id,
        "ranked_action_pack_ids": ["pack-local-1"],
        "requested_evidence_classes": [],
        "cited_evidence_ids": ["evidence-p119-1"],
        "contradiction_set_ids": [],
        "expected_utility": 1.0,
        "utility_interval": [0.5, 1.0],
        "calibrated_confidence": 0.9,
        "authority_boundary_receipt": {
            "execution_authority": "none",
            "llm_authority": "proposal_only",
            "production_authority": False,
            "credential_scope": False,
            "p118_required_for_execution": True,
            "counters": {"production_mutation": 0},
        },
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }
    value["decision_hash"] = stable_hash(value)
    return value


def _binding() -> dict[str, object]:
    pack: dict[str, object] = {
        "action_id": "pack-local-1",
        "action_family": "fixture_restart",
        "description": "reset isolated checkout fixture",
        "prerequisites": ["precondition:ready"],
        "contraindications": ["contraindication:unsafe"],
        "reversibility": "full",
        "blast_radius": {"scope": "single_fixture"},
        "expected_effect": {"healthy": True},
        "expected_evidence": ["fixture_health"],
        "validation_query": {"plan_id": "validation:local"},
        "rollback_plan": {"plan_id": "rollback:local"},
        "executor_disabled": True,
        "target_scope": "offline_fixture",
        "signer_key_id": "fixture-key",
    }
    pack["signature"] = sign_action_pack_payload(pack, key_id="fixture-key", key=b"fixture-secret")
    canonical = build_action_pack(pack, keyring={"fixture-key": b"fixture-secret"}).to_dict()
    return {
        "schema_version": "p119.frozen_action_binding.v1",
        "p115_pack": pack,
        "p117_action_pack_ref": {"action_pack_id": canonical["action_id"], "pack_hash": canonical["pack_hash"], "signature": canonical["signature"], "signer_key_id": canonical["signer_key_id"]},
        "verification_expires_at": 1000,
        "revoked": False,
        "allowed_level": "L2",
        "fixture_target_id": "local:fixture:checkout-api",
        "policy_hash": _hash("9"),
        "prerequisite_receipts": ["precondition:ready"],
        "contraindications_resolved": True,
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }


def _approve(decision=None, binding=None, policy=None):  # type: ignore[no-untyped-def]
    return approve_p119_selection(
        p117_decision=decision or _decision(),
        frozen_action_manifest={"pack-local-1": binding or _binding()},
        policy_hash=policy or _hash("9"),
        target_fixture_id="local:fixture:checkout-api",
        budget_snapshot={"approval_wait_remaining": 3},
        timeline_refs=["timeline:decision"],
        now=100,
        signer_secrets={"fixture-key": "fixture-secret"},
    )


def test_selection_approves_only_real_p117_p115_p118_bound_local_operation() -> None:
    outcome = _approve()
    assert outcome.outcome == "approved"
    assert outcome.operation_envelope is not None
    assert outcome.operation_envelope["fixture_target_id"] == "local:fixture:checkout-api"
    assert str(outcome.operation_envelope["p115_action_pack_digest"]).startswith("sha256:")
    assert outcome.approval_receipt == outcome.operation_envelope["approval_receipt"]
    assert outcome.approval_receipt is not None
    assert validate_p118_approval_decision_receipt(outcome.approval_receipt) is True
    assert outcome.approval_receipt["schema_version"] == "p118.approval_decision.v1"
    assert outcome.approval_receipt["authority_counter_snapshot"] == {
        key: 0 for key in outcome.operation_envelope["authority_counter_snapshot"]
    }


def test_selection_keeps_non_action_labels_first_class() -> None:
    decision = _decision(label="investigate_more", selected_id=None)
    decision["requested_evidence_classes"] = ["trace_span"]
    decision["decision_hash"] = stable_hash({key: value for key, value in decision.items() if key != "decision_hash"})
    outcome = _approve(decision=decision)
    assert outcome.outcome == "investigate_more"
    assert outcome.operation_envelope is None


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("revoked", "revoked_action_pack"),
        ("expired", "stale_action_pack"),
        ("l4", "action_level_above_l3"),
        ("validation", "missing_validation_plan"),
        ("rollback", "missing_rollback_plan"),
        ("production", "forbidden_authority_text|fixture_target_mismatch"),
        ("authority", "authority_counter_nonzero:production_mutation_count"),
    ],
)
def test_selection_red_bindings_fail_closed(mutation: str, error: str) -> None:
    binding = copy.deepcopy(_binding())
    if mutation == "revoked":
        binding["revoked"] = True
    elif mutation == "expired":
        binding["verification_expires_at"] = 1
    elif mutation == "l4":
        binding["allowed_level"] = "L4"
    elif mutation == "production":
        binding["fixture_target_id"] = "production:checkout"
    elif mutation == "authority":
        binding["authority_counter_snapshot"]["production_mutation_count"] = 1  # type: ignore[index]
    else:
        pack = binding["p115_pack"]
        assert isinstance(pack, dict)
        pack["validation_query" if mutation == "validation" else "rollback_plan"] = {}
    with pytest.raises(P119SelectionError, match=error):
        _approve(binding=binding)


def test_selection_rejects_forged_signature_invented_id_and_escalates_policy() -> None:
    binding = copy.deepcopy(_binding())
    pack = binding["p115_pack"]
    assert isinstance(pack, dict)
    pack["description"] = "tampered"
    with pytest.raises(P119SelectionError, match="action_pack_signature_mismatch"):
        _approve(binding=binding)
    with pytest.raises(P119SelectionError, match="invented_action_id"):
        _approve(decision=_decision(selected_id="invented"))
    assert _approve(policy=_hash("8")).reason == "policy_hash_mismatch"
