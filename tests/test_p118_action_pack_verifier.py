from __future__ import annotations

import copy
from typing import cast

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p115_ontology import build_action_pack, sign_action_pack_payload
from app.services.p118_action_pack_verifier import P118ActionPackVerificationError, P118ActionPackVerificationResult, verify_signed_action_pack


def _pack(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "action_id": "pack-local-001",
        "action_family": "fixture_restart",
        "description": "reset the isolated checkout fixture",
        "prerequisites": ["precondition:ready"],
        "contraindications": ["contraindication:unsafe"],
        "reversibility": "full",
        "blast_radius": {"scope": "single_fixture"},
        "expected_effect": {"healthy": True},
        "expected_evidence": ["fixture_health"],
        "validation_query": {"plan_id": "validation:mock"},
        "rollback_plan": {"plan_id": "rollback:mock"},
        "executor_disabled": True,
        "target_scope": "offline_fixture",
        "signer_key_id": "fixture-key",
    }
    payload.update(overrides)
    payload["signature"] = sign_action_pack_payload(payload, key_id="fixture-key", key=b"fixture-secret")
    return payload


def _chain(pack: dict[str, object] | None = None) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    source = pack or _pack()
    canonical = build_action_pack(source, keyring={"fixture-key": b"fixture-secret"}).to_dict()
    ref = {
        "action_pack_id": canonical["action_id"],
        "pack_hash": canonical["pack_hash"],
        "signature": canonical["signature"],
        "signer_key_id": canonical["signer_key_id"],
    }
    decision: dict[str, object] = {
        "schema_version": "p117.decision_output.v1",
        "decision_episode_id": "episode-001",
        "episode_hash": "sha256:" + "2" * 64,
        "selected_label": "act",
        "selected_action_pack_id": canonical["action_id"],
        "ranked_action_pack_ids": [canonical["action_id"]],
        "requested_evidence_classes": [],
        "cited_evidence_ids": ["evidence-001"],
        "contradiction_set_ids": [],
        "expected_utility": 1.0,
        "utility_interval": [0.5, 1.0],
        "calibrated_confidence": 0.9,
        "abstention_reason": None,
        "fallback_reason": None,
        "llm_proposal_receipt": None,
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
    decision["output_hash"] = stable_hash(decision)
    return source, ref, decision


def _verify(
    pack: dict[str, object],
    ref: dict[str, object],
    decision: dict[str, object],
    *,
    revoked_digests: set[str] | None = None,
    verification_expires_at: int = 1100,
) -> P118ActionPackVerificationResult:
    return verify_signed_action_pack(
        pack,
        p117_decision_output=decision,
        p117_action_pack_ref=ref,
        signer_secrets={"fixture-key": "fixture-secret"},
        revoked_digests=revoked_digests or set(),
        now=1000,
        verification_expires_at=verification_expires_at,
    )


def test_real_p115_pack_verifies_with_exact_p117_output_binding() -> None:
    pack, ref, decision = _chain()
    result = _verify(pack, ref, decision)
    assert result.accepted is True
    assert result.action_pack_id == "pack-local-001"
    assert result.p117_decision_episode_id == "episode-001"
    assert result.authority_counter_snapshot["production_mutation"] == 0
    assert result.verification_hash == stable_hash({key: value for key, value in result.to_dict().items() if key != "verification_hash"})


@pytest.mark.parametrize(
    "mutation,error",
    [
        ({"selected_label": "investigate_more"}, "p117_non_act_decision"),
        ({"selected_action_pack_id": "other"}, "p117_p115_id_mismatch"),
    ],
)
def test_p117_decision_must_be_current_act_and_match_pack(mutation: dict[str, object], error: str) -> None:
    pack, ref, decision = _chain()
    decision.update(mutation)
    decision["output_hash"] = stable_hash({key: value for key, value in decision.items() if key != "output_hash"})
    with pytest.raises(P118ActionPackVerificationError, match=error):
        _verify(pack, ref, decision)


def test_verifier_rejects_tampering_revocation_staleness_and_nonzero_authority() -> None:
    pack, ref, decision = _chain()
    tampered_ref = {**ref, "pack_hash": "sha256:" + "0" * 64}
    with pytest.raises(P118ActionPackVerificationError, match="pack_digest_mismatch"):
        _verify(pack, tampered_ref, decision)
    with pytest.raises(P118ActionPackVerificationError, match="revoked_action_pack"):
        _verify(pack, ref, decision, revoked_digests={cast(str, ref["pack_hash"])})
    with pytest.raises(P118ActionPackVerificationError, match="stale_action_pack"):
        _verify(pack, ref, decision, verification_expires_at=1000)
    unsafe = copy.deepcopy(pack)
    unsafe["target_scope"] = "production"
    unsafe["signature"] = sign_action_pack_payload(unsafe, key_id="fixture-key", key=b"fixture-secret")
    with pytest.raises(P118ActionPackVerificationError, match="forbidden_authority_text|production_target_selector"):
        _verify(unsafe, ref, decision)


def test_verifier_rejects_invalid_p115_signature_and_forged_p117_hash() -> None:
    pack, ref, decision = _chain()
    pack["description"] = "tampered after signing"
    with pytest.raises(P118ActionPackVerificationError, match="action_pack_signature_mismatch"):
        _verify(pack, ref, decision)
    valid_pack, valid_ref, forged = _chain()
    forged["output_hash"] = "sha256:" + "0" * 64
    with pytest.raises(P118ActionPackVerificationError, match="invalid_p117_output_hash"):
        _verify(valid_pack, valid_ref, forged)
