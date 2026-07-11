"""Offline verification of real P115 packs selected by real P117 outputs."""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p115_ontology import P115OntologyError, build_action_pack
from app.services.p118_operation_contract import P118ContractError, exact_zero_authority_counters, reject_authority_boundary


class P118ActionPackVerificationError(ValueError):
    """Raised when the P117/P115 chain fails closed before execution."""


@dataclass(frozen=True)
class P118ActionPackVerificationResult:
    accepted: bool
    action_pack_id: str
    pack_digest: str
    signer_id: str
    signer_key_id: str
    p117_decision_episode_id: str
    p117_output_hash: str
    revocation_manifest_hash: str
    expiration_checked_at: int
    expires_at: int
    authority_counter_snapshot: dict[str, int]
    verification_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "action_pack_id": self.action_pack_id,
            "pack_digest": self.pack_digest,
            "signer_id": self.signer_id,
            "signer_key_id": self.signer_key_id,
            "p117_decision_episode_id": self.p117_decision_episode_id,
            "p117_output_hash": self.p117_output_hash,
            "revocation_manifest_hash": self.revocation_manifest_hash,
            "expiration_checked_at": self.expiration_checked_at,
            "expires_at": self.expires_at,
            "authority_counter_snapshot": self.authority_counter_snapshot,
            "verification_hash": self.verification_hash,
        }


def verify_signed_action_pack(
    pack: Mapping[str, Any],
    *,
    p117_decision_output: Mapping[str, Any],
    p117_action_pack_ref: Mapping[str, Any],
    signer_secrets: Mapping[str, str],
    revoked_digests: Set[str],
    now: int,
    verification_expires_at: int,
) -> P118ActionPackVerificationResult:
    try:
        reject_authority_boundary(pack)
        schema = p117_decision_output.get("schema_version")
        if schema not in {"p117.decision_output.v1", "p117.deterministic_decision.v1"}:
            raise P118ActionPackVerificationError("invalid_p117_output_schema")
        hash_field = "output_hash" if schema == "p117.decision_output.v1" else "decision_hash"
        decision_hash = _self_hash(p117_decision_output, hash_field, "invalid_p117_output_hash")
        if p117_decision_output.get("selected_label") != "act":
            raise P118ActionPackVerificationError("p117_non_act_decision")
        decision_episode_id = _required_text(p117_decision_output, "decision_episode_id")
        selected_id = _required_text(p117_decision_output, "selected_action_pack_id")
        ref_id = _required_text(p117_action_pack_ref, "action_pack_id")
        if selected_id != ref_id:
            raise P118ActionPackVerificationError("p117_p115_id_mismatch")
        _validate_p117_decision_contract(p117_decision_output, schema=schema)
        if verification_expires_at <= now:
            raise P118ActionPackVerificationError("stale_action_pack")
        signer_key_id = _required_text(pack, "signer_key_id")
        secret = signer_secrets.get(signer_key_id)
        if not secret:
            raise P118ActionPackVerificationError("unknown_signer_key")
        canonical = build_action_pack(pack, keyring={signer_key_id: secret.encode()}).to_dict()
        action_id = str(canonical["action_id"])
        digest = str(canonical["pack_hash"])
        if action_id != selected_id:
            raise P118ActionPackVerificationError("p117_p115_id_mismatch")
        if digest != p117_action_pack_ref.get("pack_hash"):
            raise P118ActionPackVerificationError("pack_digest_mismatch")
        if canonical.get("signature") != p117_action_pack_ref.get("signature"):
            raise P118ActionPackVerificationError("p117_signature_ref_mismatch")
        if signer_key_id != p117_action_pack_ref.get("signer_key_id"):
            raise P118ActionPackVerificationError("p117_signer_ref_mismatch")
        if digest in revoked_digests:
            raise P118ActionPackVerificationError("revoked_action_pack")
        if canonical.get("executor_disabled") is not True:
            raise P118ActionPackVerificationError("executor_must_be_disabled")
        counters = exact_zero_authority_counters()
    except (P115OntologyError, P118ContractError) as exc:
        raise P118ActionPackVerificationError(str(exc)) from exc
    base = {
        "accepted": True,
        "action_pack_id": action_id,
        "pack_digest": digest,
        "signer_id": signer_key_id,
        "signer_key_id": signer_key_id,
        "p117_decision_episode_id": decision_episode_id,
        "p117_output_hash": decision_hash,
        "revocation_manifest_hash": stable_hash(sorted(revoked_digests)),
        "expiration_checked_at": now,
        "expires_at": verification_expires_at,
        "authority_counter_snapshot": counters,
    }
    return P118ActionPackVerificationResult(
        accepted=True,
        action_pack_id=action_id,
        pack_digest=digest,
        signer_id=signer_key_id,
        signer_key_id=signer_key_id,
        p117_decision_episode_id=decision_episode_id,
        p117_output_hash=decision_hash,
        revocation_manifest_hash=str(base["revocation_manifest_hash"]),
        expiration_checked_at=now,
        expires_at=verification_expires_at,
        authority_counter_snapshot=counters,
        verification_hash=stable_hash(base),
    )


def _self_hash(value: Mapping[str, Any], field: str, error: str) -> str:
    claimed = value.get(field)
    if claimed != stable_hash({key: item for key, item in value.items() if key != field}):
        raise P118ActionPackVerificationError(error)
    return str(claimed)


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P118ActionPackVerificationError(f"missing_{key}")
    return value.strip()


def _validate_p117_decision_contract(value: Mapping[str, Any], *, schema: Any) -> None:
    required = {
        "decision_episode_id",
        "selected_label",
        "selected_action_pack_id",
        "ranked_action_pack_ids",
        "requested_evidence_classes",
        "cited_evidence_ids",
        "contradiction_set_ids",
        "expected_utility",
        "utility_interval",
        "calibrated_confidence",
        "authority_boundary_receipt",
        "execution_authority",
        "llm_authority",
        "production_authority",
        "credential_scope",
        "p118_required_for_execution",
    }
    if schema == "p117.decision_output.v1":
        required.add("episode_hash")
    missing = sorted(required - set(value))
    if missing:
        raise P118ActionPackVerificationError(f"incomplete_p117_output:{missing[0]}")
    selected = _required_text(value, "selected_action_pack_id")
    ranked = value.get("ranked_action_pack_ids")
    cited = value.get("cited_evidence_ids")
    interval = value.get("utility_interval")
    confidence = value.get("calibrated_confidence")
    if not isinstance(ranked, list | tuple) or selected not in {str(item) for item in ranked}:
        raise P118ActionPackVerificationError("p117_selected_pack_not_ranked")
    if not isinstance(cited, list | tuple) or not cited or any(not isinstance(item, str) or not item for item in cited):
        raise P118ActionPackVerificationError("p117_missing_cited_evidence")
    if not isinstance(interval, list | tuple) or len(interval) != 2 or any(not isinstance(item, int | float) or isinstance(item, bool) for item in interval) or float(interval[0]) > float(interval[1]):
        raise P118ActionPackVerificationError("p117_invalid_utility_interval")
    if not isinstance(confidence, int | float) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
        raise P118ActionPackVerificationError("p117_invalid_confidence")
    receipt = value.get("authority_boundary_receipt")
    if not isinstance(receipt, Mapping):
        raise P118ActionPackVerificationError("p117_missing_authority_receipt")
    if (
        value.get("execution_authority") != "none"
        or value.get("llm_authority") != "proposal_only"
        or value.get("production_authority") is not False
        or value.get("credential_scope") is not False
        or value.get("p118_required_for_execution") is not True
    ):
        raise P118ActionPackVerificationError("p117_authority_contract_mismatch")
    counters = receipt.get("counters")
    if (
        receipt.get("execution_authority") != "none"
        or receipt.get("production_authority") is not False
        or not isinstance(counters, Mapping)
        or not counters
        or any(not isinstance(item, int) or isinstance(item, bool) or item != 0 for item in counters.values())
    ):
        raise P118ActionPackVerificationError("p117_authority_receipt_invalid")


__all__ = ["P118ActionPackVerificationError", "P118ActionPackVerificationResult", "verify_signed_action_pack"]
