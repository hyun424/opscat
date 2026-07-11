from __future__ import annotations

from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p115_ontology import build_action_pack, sign_action_pack_payload
from app.services.p118_action_pack_verifier import verify_signed_action_pack
from app.services.p118_approval import decide_p118_approval, empty_p118_policy_counters, validate_p118_approval_decision_receipt
from app.services.p118_operation_contract import P118_AUTHORITY_COUNTER_KEYS, build_operation_envelope, exact_zero_authority_counters


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64


def _receipt(payload: dict[str, object], *, field: str = "receipt_hash") -> dict[str, object]:
    result = dict(payload)
    result[field] = stable_hash(result)
    return result


def _verification():  # type: ignore[no-untyped-def]
    pack: dict[str, object] = {
        "action_id": "pack-local-005",
        "action_family": "fixture_restart",
        "description": "reset isolated checkout fixture",
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
    pack["signature"] = sign_action_pack_payload(pack, key_id="fixture-key", key=b"fixture-secret")
    canonical = build_action_pack(pack, keyring={"fixture-key": b"fixture-secret"}).to_dict()
    ref = {"action_pack_id": canonical["action_id"], "pack_hash": canonical["pack_hash"], "signature": canonical["signature"], "signer_key_id": canonical["signer_key_id"]}
    output: dict[str, object] = {
        "schema_version": "p117.decision_output.v1",
        "decision_episode_id": "episode-approval-005",
        "episode_hash": _hash("8"),
        "selected_label": "act",
        "selected_action_pack_id": "pack-local-005",
        "ranked_action_pack_ids": ["pack-local-005"],
        "requested_evidence_classes": [],
        "cited_evidence_ids": ["evidence-approval-005"],
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
            "counters": exact_zero_authority_counters(),
        },
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }
    output["output_hash"] = stable_hash(output)
    return verify_signed_action_pack(
        pack, p117_decision_output=output, p117_action_pack_ref=ref, signer_secrets={"fixture-key": "fixture-secret"}, revoked_digests=set(), now=1000, verification_expires_at=1100
    )


def _operation():  # type: ignore[no-untyped-def]
    verification = _verification()
    lease = _receipt({"operation_id": "op-approval-005", "owner_id": "worker-a", "expires_at": 1050, "cas_version": 0})
    return build_operation_envelope(
        {
            "operation_id": "op-approval-005",
            "schema_version": "p118.operation_envelope.v1",
            "p117_decision_episode_id": "episode-approval-005",
            "p117_selected_action_pack_id": "pack-local-005",
            "p115_action_pack_digest": verification.pack_digest,
            "fixture_target_id": "local:fixture:checkout-api",
            "action_level": "L3",
            "precondition_refs": ["precondition:ready"],
            "validation_plan_ref": "validation:mock",
            "rollback_plan_ref": "rollback:mock",
            "approval_receipt": {"receipt_id": "approval-request", "policy_hash": _hash("2"), "verification_hash": verification.verification_hash},
            "lease_receipt": lease,
            "wal_position": 0,
            "cas_version": 0,
            "idempotency_key": "idem:approval-005",
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }
    )


def _lease() -> dict[str, object]:
    return _receipt({"operation_id": "op-approval-005", "owner_id": "worker-a", "expires_at": 1050, "cas_version": 0})


def _wal() -> dict[str, object]:
    return _receipt({"operation_id": "op-approval-005", "cas_version": 0, "wal_position": 1})


def test_approval_accepts_only_fresh_bound_receipts() -> None:
    decision = decide_p118_approval(operation=_operation(), verification=_verification(), policy_hash=_hash("9"), now=1001, lease_receipt=_lease(), wal_receipt=_wal(), cas_version=0)
    assert decision.approved is True
    assert decision.reason == "approved"
    assert decision.nonlocal_authority_zero is True


def test_decision_hash_binds_every_execution_context_input() -> None:
    operation = _operation()
    verification = _verification()
    lease = _lease()
    wal = _wal()
    baseline = decide_p118_approval(
        operation=operation,
        verification=verification,
        policy_hash=_hash("9"),
        now=1001,
        lease_receipt=lease,
        wal_receipt=wal,
        cas_version=0,
    )
    contexts: list[dict[str, Any]] = [
        {"now": 1002},
        {"lease_receipt": _receipt({**{k: v for k, v in lease.items() if k != "receipt_hash"}, "expires_at": 1060})},
        {"wal_receipt": _receipt({**{k: v for k, v in wal.items() if k != "receipt_hash"}, "wal_position": 2})},
    ]
    varied_hashes = {
        decide_p118_approval(
            operation=operation,
            verification=verification,
            policy_hash=_hash("9"),
            now=int(context.get("now", 1001)),
            lease_receipt=context.get("lease_receipt", lease),
            wal_receipt=context.get("wal_receipt", wal),
            cas_version=0,
        ).decision_hash
        for context in contexts
    }
    assert baseline.decision_hash not in varied_hashes
    assert len(varied_hashes) == len(contexts)
    receipt = baseline.to_dict()
    assert receipt["verification_expires_at"] == verification.expires_at
    assert receipt["lease_expires_at"] == lease["expires_at"]
    assert receipt["lease_receipt_hash"] == lease["receipt_hash"]
    assert receipt["wal_receipt_hash"] == wal["receipt_hash"]
    assert receipt["wal_position"] == wal["wal_position"]
    assert receipt["cas_version"] == 0
    assert receipt["operation_context_hash"].startswith("sha256:")
    assert receipt["approval_context_hash"].startswith("sha256:")


def test_consumed_approval_receipt_requires_exact_integer_zero_p118_authority_keys() -> None:
    valid = decide_p118_approval(
        operation=_operation(),
        verification=_verification(),
        policy_hash=_hash("9"),
        now=1001,
        lease_receipt=_lease(),
        wal_receipt=_wal(),
        cas_version=0,
    ).to_dict()
    assert validate_p118_approval_decision_receipt(valid) is True
    assert valid["counters"] == exact_zero_authority_counters()

    mutations: list[dict[str, object]] = [
        {},
        {key: 0 for key in P118_AUTHORITY_COUNTER_KEYS[:-1]},
        {**exact_zero_authority_counters(), "unexpected": 0},
        {**exact_zero_authority_counters(), P118_AUTHORITY_COUNTER_KEYS[0]: 1},
        {**exact_zero_authority_counters(), P118_AUTHORITY_COUNTER_KEYS[0]: False},
    ]
    for counters in mutations:
        forged = {**valid, "counters": counters}
        forged["approval_context_hash"] = stable_hash(
            {
                "operation_context_hash": forged["operation_context_hash"],
                "verification_hash": forged["verification_hash"],
                "verification_expires_at": forged["verification_expires_at"],
                "policy_hash": forged["policy_hash"],
                "lease_expires_at": forged["lease_expires_at"],
                "lease_receipt_hash": forged["lease_receipt_hash"],
                "wal_receipt_hash": forged["wal_receipt_hash"],
                "wal_position": forged["wal_position"],
                "cas_version": forged["cas_version"],
                "decided_at": forged["decided_at"],
                "counters": counters,
                "policy_counters": forged["policy_counters"],
            }
        )
        forged["decision_hash"] = stable_hash({key: value for key, value in forged.items() if key != "decision_hash"})
        assert validate_p118_approval_decision_receipt(forged) is False


def test_approval_fails_closed_for_missing_policy_nonzero_authority_and_unrelated_receipt() -> None:
    operation = _operation()
    missing = decide_p118_approval(operation=operation, verification=_verification(), policy_hash="", now=1001, lease_receipt=_lease(), wal_receipt=_wal(), cas_version=0)
    counters = empty_p118_policy_counters()
    counters["shell"] = 1
    shell = decide_p118_approval(
        operation=operation, verification=_verification(), policy_hash=_hash("9"), now=1001, lease_receipt=_lease(), wal_receipt=_wal(), cas_version=0, observed_counters=counters
    )
    unrelated = {**_wal(), "operation_id": "other"}
    wrong_wal = decide_p118_approval(operation=operation, verification=_verification(), policy_hash=_hash("9"), now=1001, lease_receipt=_lease(), wal_receipt=unrelated, cas_version=0)
    forged = {**_wal(), "receipt_hash": _hash("4")}
    forged_wal = decide_p118_approval(operation=operation, verification=_verification(), policy_hash=_hash("9"), now=1001, lease_receipt=_lease(), wal_receipt=forged, cas_version=0)
    assert missing.reason == "missing_policy_hash"
    assert shell.reason == "authority_counter_nonzero:shell"
    assert wrong_wal.reason == "invalid_wal_receipt"
    assert forged_wal.reason == "invalid_wal_receipt"
