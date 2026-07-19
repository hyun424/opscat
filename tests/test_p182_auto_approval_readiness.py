from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.p147_p152_contracts import canonical_json_bytes, stable_hash
from app.services.p182_auto_approval import (
    REQUIRED_APPROVAL_RECEIPT_CLASSES,
    P182ReadinessError,
    build_p182_readiness_artifact,
    evaluate_auto_approval_request,
    validate_campaign_readiness,
    validate_p182_readiness_artifact,
)

ROOT = Path(__file__).resolve().parents[1]


def _signed_release_evidence(*, schema_version: str, claim: str, receipt_key: str = "independent_reviewer_receipt") -> dict[str, object]:
    phase = schema_version[:4]
    evidence: dict[str, object] = {
        "schema_version": schema_version,
        "qualified": True,
        "claim": claim,
        "artifact_path": f"evals/{phase}/output/release-evidence.json",
        "artifact_file_hash": stable_hash({"artifact": schema_version}),
        "report_hash": stable_hash({"report": schema_version}),
        "freeze_hash": stable_hash({"freeze": schema_version}),
        "final_review_hash": stable_hash({"review": schema_version}),
    }
    evidence["evidence_hash"] = hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()
    evidence[receipt_key] = {
        "schema_version": "independent.receipt.v1",
        "signer_id": "independent-reviewer",
        "payload_hash": evidence["evidence_hash"],
        "signature_hash": stable_hash({"payload_hash": evidence["evidence_hash"], "signer_id": "independent-reviewer"}),
    }
    return evidence


def _policy() -> dict[str, object]:
    return {
        "schema_version": "p182.auto_approval_policy.v1",
        "enabled": True,
        "explicit_operator_policy": True,
        "allowed_action_families": ["restart_staging_worker", "rotate_staging_canary"],
        "allowed_targets": ["staging-a", "staging-b"],
        "allowed_providers": ["local-staging"],
        "allowed_accounts": ["acct-staging"],
        "allowed_projects": ["project-staging"],
        "min_confidence": 0.9,
        "max_blast_radius": "single_staging_target",
        "kill_switch_active": False,
        "max_concurrent_auto_actions": 1,
        "required_source_classes": ["metrics", "trace"],
        "freshness_seconds": 300,
        "required_freeze_hashes": {"policy": stable_hash({"policy": "p182"}), "targets": stable_hash({"targets": ["staging-a", "staging-b"]})},
    }


def _request() -> dict[str, object]:
    return {
        "action_family": "restart_staging_worker",
        "target": "staging-a",
        "provider": "local-staging",
        "account": "acct-staging",
        "project": "project-staging",
        "environment": "staging",
        "confidence": 0.95,
        "blast_radius": "single_staging_target",
        "source_classes": ["metrics", "trace"],
        "evidence_age_seconds": 120,
        "lease_valid": True,
        "rollback_plan_bound": True,
        "idempotency_key": "idem-001",
        "currently_running_auto_actions": 0,
    }


def _manifest(request: dict[str, object], policy: dict[str, object]) -> dict[str, object]:
    payload = {
        "action_family": request["action_family"],
        "target": request["target"],
        "provider": request["provider"],
        "account": request["account"],
        "project": request["project"],
        "environment": request["environment"],
        "freeze_hashes": policy["required_freeze_hashes"],
    }
    manifest: dict[str, object] = {
        "schema_version": "p182.staging_custody_manifest.v1",
        "signer_id": "staging-custodian",
        "payload": payload,
        "payload_hash": stable_hash(payload),
    }
    manifest["signature_hash"] = stable_hash({key: value for key, value in manifest.items() if key != "signature_hash"})
    return manifest


def _approval_subject_hash(request: dict[str, object], policy: dict[str, object]) -> str:
    return stable_hash(
        {
            "schema_version": "p182.approval_subject.v1",
            "policy_hash": stable_hash(dict(policy)),
            "action_family": request.get("action_family"),
            "target": request.get("target"),
            "provider": request.get("provider"),
            "account": request.get("account"),
            "project": request.get("project"),
            "environment": request.get("environment"),
            "confidence": request.get("confidence"),
            "blast_radius": request.get("blast_radius"),
            "source_classes": request.get("source_classes"),
            "evidence_age_seconds": request.get("evidence_age_seconds"),
            "lease_valid": request.get("lease_valid"),
            "rollback_plan_bound": request.get("rollback_plan_bound"),
            "idempotency_key": request.get("idempotency_key"),
            "currently_running_auto_actions": request.get("currently_running_auto_actions"),
            "staging_custody_manifest_hash": stable_hash(dict(request["staging_custody_manifest"])),
        }
    )


def _approval_receipt_set(request: dict[str, object], policy: dict[str, object]) -> dict[str, object]:
    subject_hash = _approval_subject_hash(request, policy)
    receipts = []
    for receipt_class in REQUIRED_APPROVAL_RECEIPT_CLASSES:
        payload = {
            "receipt_class": receipt_class,
            "subject_hash": subject_hash,
            "status": "not_triggered" if receipt_class == "conditional_safety_event" else "verified",
        }
        receipt: dict[str, object] = {
            "schema_version": "p182.approval_receipt.v1",
            "receipt_class": receipt_class,
            "subject_hash": subject_hash,
            "signer_id": f"p182-{receipt_class}-reviewer",
            "payload": payload,
            "payload_hash": stable_hash(payload),
        }
        receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
        receipts.append(receipt)
    receipt_set: dict[str, object] = {
        "schema_version": "p182.approval_receipt_set.v1",
        "subject_hash": subject_hash,
        "receipts": receipts,
    }
    receipt_set["receipt_set_hash"] = stable_hash(
        {
            "schema_version": "p182.approval_receipt_set.v1",
            "subject_hash": subject_hash,
            "receipts": [
                {"receipt_class": receipt["receipt_class"], "receipt_hash": receipt["receipt_hash"]}
                for receipt in receipts
            ],
        }
    )
    return receipt_set


def test_auto_approval_policy_allows_only_explicit_staging_allowlist_requests() -> None:
    policy = _policy()
    old_minimal_request = _request()
    old_minimal_request["staging_custody_manifest"] = _manifest(old_minimal_request, policy)
    old_minimal_denied = evaluate_auto_approval_request(old_minimal_request, policy)
    assert old_minimal_denied["approved"] is False
    assert "approval_receipt_set_required" in old_minimal_denied["reasons"]

    request = _request()
    request["staging_custody_manifest"] = _manifest(request, policy)
    request["approval_receipt_set"] = _approval_receipt_set(request, policy)
    decision = evaluate_auto_approval_request(request, policy)
    assert decision["approved"] is True
    assert decision["production_mutation_structurally_impossible"] is True

    production = _request()
    production["environment"] = "production"
    production["staging_custody_manifest"] = _manifest(production, policy)
    production["approval_receipt_set"] = _approval_receipt_set(production, policy)
    denied = evaluate_auto_approval_request(production, policy)
    assert denied["approved"] is False
    assert "production_environment_forbidden" in denied["reasons"]

    prod_like = _request()
    prod_like["target"] = "prod-a"
    prod_like["staging_custody_manifest"] = _manifest(prod_like, policy)
    prod_like["approval_receipt_set"] = _approval_receipt_set(prod_like, policy)
    prod_like_denied = evaluate_auto_approval_request(prod_like, policy)
    assert prod_like_denied["approved"] is False
    assert "prod_like_target_forbidden" in prod_like_denied["reasons"]

    missing_manifest = evaluate_auto_approval_request(_request(), policy)
    assert missing_manifest["approved"] is False
    assert "staging_custody_manifest_required" in missing_manifest["reasons"]
    assert missing_manifest["production_mutation_structurally_impossible"] is False


def test_auto_approval_denies_missing_tampered_or_wrong_bound_receipts() -> None:
    policy = _policy()
    request = _request()
    request["staging_custody_manifest"] = _manifest(request, policy)
    request["approval_receipt_set"] = _approval_receipt_set(request, policy)
    assert evaluate_auto_approval_request(request, policy)["approved"] is True

    missing = deepcopy(request)
    missing_set = deepcopy(request["approval_receipt_set"])
    missing_set["receipts"] = missing_set["receipts"][:-1]
    missing["approval_receipt_set"] = missing_set
    missing_denied = evaluate_auto_approval_request(missing, policy)
    assert missing_denied["approved"] is False
    assert "missing_required_approval_receipt" in missing_denied["reasons"]

    tampered = deepcopy(request)
    tampered["approval_receipt_set"]["receipts"][0]["payload"]["status"] = "forged_verified"
    tampered_denied = evaluate_auto_approval_request(tampered, policy)
    assert tampered_denied["approved"] is False
    assert "invalid_approval_receipt" in tampered_denied["reasons"]

    wrong_bound_source = _request()
    wrong_bound_source["target"] = "staging-b"
    wrong_bound_source["staging_custody_manifest"] = _manifest(wrong_bound_source, policy)
    wrong_bound = deepcopy(request)
    wrong_bound["approval_receipt_set"] = _approval_receipt_set(wrong_bound_source, policy)
    wrong_bound_denied = evaluate_auto_approval_request(wrong_bound, policy)
    assert wrong_bound_denied["approved"] is False
    assert "approval_receipt_set_binding_mismatch" in wrong_bound_denied["reasons"]


def test_kill_switch_overrides_otherwise_valid_auto_approval_request() -> None:
    policy = _policy()
    policy["kill_switch_active"] = True
    request = _request()
    request["staging_custody_manifest"] = _manifest(request, _policy())
    request["approval_receipt_set"] = _approval_receipt_set(request, policy)
    decision = evaluate_auto_approval_request(request, policy)
    assert decision["approved"] is False
    assert decision["mode"] == "shadow_human_required"
    assert "kill_switch_active" in decision["reasons"]


def test_campaign_readiness_requires_three_separate_dates_receipts_and_p100_safety_clocks() -> None:
    report = validate_campaign_readiness(
        {
            "campaigns": [
                {"campaign_id": "c1", "utc_date": "2026-03-01", "safely_closed_auto_approved_actions": 20},
                {"campaign_id": "c2", "utc_date": "2026-03-02", "safely_closed_auto_approved_actions": 20},
                {"campaign_id": "c3", "utc_date": "2026-03-03", "safely_closed_auto_approved_actions": 20},
            ],
            "reviewed_action_family_count": 2,
            "staging_target_count": 2,
            "global_kill_switch_drill_count": 3,
            "target_local_kill_switch_drill_count": 3,
            "active_operation_cancel_or_isolate_drill_count": 3,
            "auto_demotion_drill_count": 9,
            "distinct_auto_demotion_anomaly_class_count_per_campaign": 3,
            "rollback_drill_count": 6,
            "human_takeover_drill_count": 6,
            "required_receipt_completeness": 1.0,
            "missing_malformed_unbound_receipt_count": 0,
            "conditional_event_without_trigger_or_not_triggered_receipt_count": 0,
            "kill_switch_dispatch_block_lease_revoke_p100_seconds": 5,
            "active_operation_cancel_or_isolate_p100_seconds": 10,
            "auto_demotion_p100_seconds": 30,
            "post_demotion_action_dispatch_count": 0,
            "max_concurrent_auto_actions": 1,
            "production_mutation_count": 0,
            "target_escape_count": 0,
            "unsafe_action_count": 0,
            "duplicate_side_effect_count": 0,
            "unresolved_effect_count": 0,
            "failed_rollback_closure_count": 0,
            "failed_human_takeover_count": 0,
            "credential_leak_count": 0,
            "failed_kill_switch_drill_count": 0,
            "failed_auto_demotion_count": 0,
            "release_evidence_contains_not_general_operator_replacement": True,
            "forbidden_production_or_general_autonomy_claim_count": 0,
        }
    )
    assert report["total_safely_closed_auto_approved_action_count"] == 60
    assert report["campaign_distinct_utc_date_count"] == 3

    slow = deepcopy(report)
    slow["auto_demotion_p100_seconds"] = 31
    with pytest.raises(P182ReadinessError, match="auto_demotion_p100_seconds"):
        validate_campaign_readiness(slow)


def test_p182_readiness_is_blocked_until_p181_and_explicit_policy_exist() -> None:
    artifact = build_p182_readiness_artifact(project_root=ROOT, p181_release_evidence=None, explicit_policy=None)
    assert artifact["qualified"] is False
    assert artifact["maximum_claim"] == "readiness_offline_substrate_only"
    assert "limited_staging_auto_approval_qualified" in artifact["forbidden_claims"]
    assert "missing_qualified_p181_release_evidence" in artifact["stop_reasons"]
    assert "missing_explicit_p182_operator_policy" in artifact["stop_reasons"]
    assert validate_p182_readiness_artifact(artifact, project_root=ROOT)["qualified"] is False

    forged = deepcopy(artifact)
    forged["qualified"] = True
    forged["maximum_claim"] = "limited_staging_auto_approval_qualified"
    forged["readiness_hash"] = stable_hash({key: value for key, value in forged.items() if key != "readiness_hash"})
    with pytest.raises(P182ReadinessError, match="qualification_forbidden"):
        validate_p182_readiness_artifact(forged, project_root=ROOT)

    fabricated_predecessor = {
        "schema_version": "p181.release_evidence.v1",
        "qualified": True,
        "claim": "real_shadow_operator_ready",
        "evidence_hash": "sha256:" + "1" * 64,
    }
    still_blocked = build_p182_readiness_artifact(project_root=ROOT, p181_release_evidence=fabricated_predecessor, explicit_policy=_policy())
    assert still_blocked["p181_release_evidence"]["valid"] is False

    nonexistent_predecessor = _signed_release_evidence(schema_version="p181.release_evidence.v1", claim="real_shadow_operator_ready")
    still_blocked = build_p182_readiness_artifact(project_root=ROOT, p181_release_evidence=nonexistent_predecessor, explicit_policy=_policy())
    assert still_blocked["p181_release_evidence"]["valid"] is False
    assert "missing_qualified_p181_release_evidence" in still_blocked["stop_reasons"]
