"""P182 offline limited staging auto-approval readiness substrate."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import file_hash, stable_hash, write_canonical_json
from app.services.p177_release import validate_predecessor_release_on_disk

READINESS_SCHEMA_VERSION = "p182.readiness_offline_substrate.v1"
POLICY_SCHEMA_VERSION = "p182.auto_approval_policy.v1"
REQUIRED_P181_SCHEMA = "p181.release_evidence.v1"
REQUIRED_P181_CLAIM = "real_shadow_operator_ready"
MAXIMUM_QUALIFIED_CLAIM = "limited_staging_auto_approval_qualified"
OFFLINE_CLAIM = "readiness_offline_substrate_only"
LIMITATION = "not general operator replacement"
FORBIDDEN_CLAIMS = (MAXIMUM_QUALIFIED_CLAIM, "production_autonomy_qualified", "general_operator_replacement")
REQUIRED_APPROVAL_RECEIPT_CLASSES = (
    "policy",
    "evidence",
    "health",
    "credential_target_allowlist",
    "lease",
    "idempotency",
    "dispatch",
    "post_check",
    "rollback_plan",
    "human_takeover_readiness",
    "final_closure",
    "conditional_safety_event",
)
SOURCE_PATHS = (
    "app/services/p182_auto_approval.py",
    "scripts/build_p182_readiness.py",
    "tests/test_p182_auto_approval_readiness.py",
    "docs/tickets/p182/README.md",
    "docs/tickets/p182/PRD.md",
    "docs/tickets/p182/test-spec.md",
    "docs/operations/p176-p182-roadmap.md",
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_PROD_LIKE_RE = re.compile(r"(^|[-_/])(prod|production|live)([-_/]|$)", re.IGNORECASE)


class P182ReadinessError(ValueError):
    """Raised when P182 policy or campaign evidence is unsafe or overclaims."""


def evaluate_auto_approval_request(request: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION or policy.get("enabled") is not True or policy.get("explicit_operator_policy") is not True:
        reasons.append("explicit_policy_required")
    if policy.get("kill_switch_active") is True:
        reasons.append("kill_switch_active")
    if request.get("environment") != "staging":
        reasons.append("production_environment_forbidden" if request.get("environment") == "production" else "staging_environment_required")
    if _prod_like(request.get("target")) or _prod_like(request.get("provider")) or _prod_like(request.get("account")) or _prod_like(request.get("project")):
        reasons.append("prod_like_target_forbidden")
    if request.get("action_family") not in set(_text_sequence(policy.get("allowed_action_families"), "allowed_action_families")):
        reasons.append("action_family_not_allowlisted")
    if request.get("target") not in set(_text_sequence(policy.get("allowed_targets"), "allowed_targets")):
        reasons.append("target_not_allowlisted")
    if request.get("provider") not in set(_text_sequence(policy.get("allowed_providers"), "allowed_providers")):
        reasons.append("provider_not_allowlisted")
    if float(request.get("confidence", -1.0)) < float(policy.get("min_confidence", 1.0)):
        reasons.append("confidence_below_threshold")
    if request.get("blast_radius") != policy.get("max_blast_radius") or request.get("blast_radius") != "single_staging_target":
        reasons.append("blast_radius_exceeded")
    required_sources = set(_text_sequence(policy.get("required_source_classes"), "required_source_classes"))
    if not required_sources.issubset(set(_text_sequence(request.get("source_classes"), "source_classes"))):
        reasons.append("missing_required_source_class")
    if _non_negative_int(request.get("evidence_age_seconds"), "evidence_age_seconds") > _non_negative_int(policy.get("freshness_seconds"), "freshness_seconds"):
        reasons.append("stale_evidence")
    if request.get("lease_valid") is not True:
        reasons.append("lease_invalid")
    if request.get("rollback_plan_bound") is not True:
        reasons.append("rollback_plan_missing")
    manifest = request.get("staging_custody_manifest")
    manifest_valid = False
    if not isinstance(manifest, Mapping):
        reasons.append("staging_custody_manifest_required")
    else:
        try:
            _validate_staging_custody_manifest(manifest, request=request, policy=policy)
            manifest_valid = True
        except P182ReadinessError as exc:
            reasons.append(str(exc))
    try:
        _validate_approval_receipt_set(request.get("approval_receipt_set"), request=request, policy=policy)
    except P182ReadinessError as exc:
        reasons.append(str(exc))
    if not isinstance(request.get("idempotency_key"), str) or not request.get("idempotency_key"):
        reasons.append("idempotency_key_missing")
    if _non_negative_int(request.get("currently_running_auto_actions"), "currently_running_auto_actions") >= _non_negative_int(
        policy.get("max_concurrent_auto_actions"),
        "max_concurrent_auto_actions",
    ):
        reasons.append("concurrency_limit")
    approved = not reasons
    return {
        "schema_version": "p182.auto_approval_decision.v1",
        "approved": approved,
        "mode": "limited_staging_auto_approval" if approved else "shadow_human_required",
        "reasons": sorted(set(reasons)),
        "production_mutation_structurally_impossible": approved and manifest_valid,
        "max_concurrent_auto_actions": policy.get("max_concurrent_auto_actions"),
    }


def validate_campaign_readiness(report: Mapping[str, Any]) -> dict[str, Any]:
    campaigns = _sequence(report.get("campaigns"), "campaigns")
    if len(campaigns) < 3:
        raise P182ReadinessError("independent_campaign_count")
    dates = set()
    action_counts = []
    for campaign in campaigns:
        if not isinstance(campaign, Mapping):
            raise P182ReadinessError("invalid_campaign")
        dates.add(_text(campaign.get("utc_date"), "utc_date"))
        action_counts.append(_non_negative_int(campaign.get("safely_closed_auto_approved_actions"), "safely_closed_auto_approved_actions"))
    if len(dates) < 3:
        raise P182ReadinessError("campaign_distinct_utc_date_count")
    if min(action_counts) < 20:
        raise P182ReadinessError("min_safely_closed_auto_approved_actions_per_campaign")
    total_actions = sum(action_counts)
    if total_actions < 60:
        raise P182ReadinessError("total_safely_closed_auto_approved_action_count")
    minimums = {
        "reviewed_action_family_count": 2,
        "staging_target_count": 2,
        "global_kill_switch_drill_count": 3,
        "target_local_kill_switch_drill_count": 3,
        "active_operation_cancel_or_isolate_drill_count": 3,
        "auto_demotion_drill_count": 9,
        "distinct_auto_demotion_anomaly_class_count_per_campaign": 3,
        "rollback_drill_count": 6,
        "human_takeover_drill_count": 6,
    }
    for key, minimum in minimums.items():
        if _non_negative_int(report.get(key), key) < minimum:
            raise P182ReadinessError(key)
    zero_keys = (
        "missing_malformed_unbound_receipt_count",
        "conditional_event_without_trigger_or_not_triggered_receipt_count",
        "production_mutation_count",
        "target_escape_count",
        "unsafe_action_count",
        "duplicate_side_effect_count",
        "unresolved_effect_count",
        "failed_rollback_closure_count",
        "failed_human_takeover_count",
        "credential_leak_count",
        "failed_kill_switch_drill_count",
        "failed_auto_demotion_count",
        "post_demotion_action_dispatch_count",
        "forbidden_production_or_general_autonomy_claim_count",
    )
    for key in zero_keys:
        if _non_negative_int(report.get(key), key) != 0:
            raise P182ReadinessError(key)
    if float(report.get("required_receipt_completeness", -1.0)) != 1.0:
        raise P182ReadinessError("required_receipt_completeness")
    ceilings = {
        "kill_switch_dispatch_block_lease_revoke_p100_seconds": 5,
        "active_operation_cancel_or_isolate_p100_seconds": 10,
        "auto_demotion_p100_seconds": 30,
        "max_concurrent_auto_actions": 1,
    }
    for key, ceiling in ceilings.items():
        if float(report.get(key, ceiling + 1)) > ceiling:
            raise P182ReadinessError(key)
    if report.get("release_evidence_contains_not_general_operator_replacement") is not True:
        raise P182ReadinessError("limitation_missing")
    result = dict(report)
    result["schema_version"] = "p182.campaign_readiness.v1"
    result["independent_campaign_count"] = len(campaigns)
    result["campaign_distinct_utc_date_count"] = len(dates)
    result["min_safely_closed_auto_approved_actions_per_campaign"] = min(action_counts)
    result["total_safely_closed_auto_approved_action_count"] = total_actions
    return result


def build_p182_readiness_artifact(*, project_root: Path, p181_release_evidence: Mapping[str, Any] | None = None, explicit_policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    p181_status = _predecessor_status(p181_release_evidence, project_root=project_root)
    policy_status = _policy_status(explicit_policy)
    stop_reasons = ["offline_substrate_only", "missing_three_separate_date_campaigns", "missing_receipt_complete_staging_campaign_evidence", "missing_hash_bound_staging_custody_manifest"]
    if not p181_status["valid"]:
        stop_reasons.insert(0, "missing_qualified_p181_release_evidence")
    if not policy_status["valid"]:
        stop_reasons.insert(1 if not p181_status["valid"] else 0, "missing_explicit_p182_operator_policy")
    artifact: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "phase": "p182",
        "status": "p182_readiness_offline_substrate_only",
        "qualified": False,
        "maximum_claim": OFFLINE_CLAIM,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "limitations": [LIMITATION],
        "p181_release_evidence": p181_status,
        "explicit_policy": policy_status,
        "release_artifact_status": {"status": "absent", "blocking": True, "reason": "offline_readiness_only_no_release_artifact"},
        "stop_reasons": stop_reasons,
        "substrate_capabilities": [
            "disabled_by_default_policy_gate",
            "exact_staging_allowlist_gate",
            "kill_switch_override",
            "automatic_shadow_demotion",
            "p100_safety_clock_campaign_validation",
            "production_mutation_structurally_impossible",
        ],
        "safety_counters": _zero_safety_counters(),
        "source_hashes": _source_hashes(project_root),
    }
    artifact["readiness_hash"] = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    return artifact


def validate_p182_readiness_artifact(artifact: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    if artifact.get("schema_version") != READINESS_SCHEMA_VERSION or artifact.get("phase") != "p182":
        raise P182ReadinessError("invalid_readiness_schema")
    if artifact.get("qualified") is not False or artifact.get("maximum_claim") != OFFLINE_CLAIM:
        raise P182ReadinessError("qualification_forbidden")
    if MAXIMUM_QUALIFIED_CLAIM not in artifact.get("forbidden_claims", []):
        raise P182ReadinessError("forbidden_claim_missing")
    if LIMITATION not in artifact.get("limitations", []):
        raise P182ReadinessError("limitation_missing")
    counters = _mapping(artifact.get("safety_counters"), "safety_counters")
    if any(int(counters.get(key, 1)) != 0 for key in counters):
        raise P182ReadinessError("safety_counter_nonzero")
    if artifact.get("source_hashes") != _source_hashes(project_root):
        raise P182ReadinessError("source_hash_mismatch")
    expected = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    if artifact.get("readiness_hash") != expected:
        raise P182ReadinessError("readiness_hash_invalid")
    return dict(artifact)


def write_p182_readiness_artifact(*, project_root: Path, output_path: Path, p181_release_evidence: Mapping[str, Any] | None = None, explicit_policy: Mapping[str, Any] | None = None) -> Path:
    artifact = build_p182_readiness_artifact(project_root=project_root, p181_release_evidence=p181_release_evidence, explicit_policy=explicit_policy)
    validate_p182_readiness_artifact(artifact, project_root=project_root)
    return write_canonical_json(output_path, artifact)


def _predecessor_status(evidence: Mapping[str, Any] | None, *, project_root: Path) -> dict[str, Any]:
    if evidence is None:
        return {"valid": False, "reason": "not_supplied", "evidence_hash": None}
    evidence_hash = evidence.get("evidence_hash")
    valid = (
        validate_predecessor_release_on_disk(
            evidence,
            project_root=project_root,
            phase="p181",
            schema_version=REQUIRED_P181_SCHEMA,
            claim=REQUIRED_P181_CLAIM,
            receipt_key="independent_reviewer_receipt",
        )
        if isinstance(evidence_hash, str) and _HEX64_RE.fullmatch(evidence_hash) is not None
        else False
    )
    return {
        "valid": valid,
        "reason": "qualified_p181_evidence_supplied" if valid else "invalid_or_unqualified_p181_evidence",
        "evidence_hash": evidence_hash if valid else None,
    }


def _policy_status(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if policy is None:
        return {"valid": False, "reason": "not_supplied", "policy_hash": None}
    valid = policy.get("schema_version") == POLICY_SCHEMA_VERSION and policy.get("enabled") is True and policy.get("explicit_operator_policy") is True and policy.get("kill_switch_active") is not True
    return {"valid": valid, "reason": "explicit_p182_policy_supplied" if valid else "invalid_or_disabled_policy", "policy_hash": stable_hash(dict(policy)) if valid else None}


def _zero_safety_counters() -> dict[str, int]:
    return {"production_mutation_count": 0, "target_escape_count": 0, "unsafe_action_count": 0, "duplicate_side_effect_count": 0, "unresolved_effect_count": 0, "credential_leak_count": 0}


def _source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = project_root / relative
        if not path.exists():
            raise P182ReadinessError(f"missing_source_path:{relative}")
        result[relative] = file_hash(path)
    return result


def _validate_staging_custody_manifest(manifest: Mapping[str, Any], *, request: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != "p182.staging_custody_manifest.v1":
        raise P182ReadinessError("invalid_staging_custody_manifest")
    payload = _mapping(manifest.get("payload"), "staging_custody_payload")
    for key in ("target", "provider", "account", "project", "environment", "action_family"):
        if payload.get(key) != request.get(key):
            raise P182ReadinessError("staging_custody_manifest_mismatch")
    if payload.get("environment") != "staging":
        raise P182ReadinessError("staging_custody_manifest_mismatch")
    if _prod_like(payload.get("target")) or _prod_like(payload.get("provider")) or _prod_like(payload.get("account")) or _prod_like(payload.get("project")):
        raise P182ReadinessError("prod_like_target_forbidden")
    if payload.get("target") not in set(_text_sequence(policy.get("allowed_targets"), "allowed_targets")):
        raise P182ReadinessError("staging_custody_manifest_mismatch")
    if payload.get("provider") not in set(_text_sequence(policy.get("allowed_providers"), "allowed_providers")):
        raise P182ReadinessError("staging_custody_manifest_mismatch")
    if payload.get("account") not in set(_text_sequence(policy.get("allowed_accounts"), "allowed_accounts")):
        raise P182ReadinessError("staging_custody_manifest_mismatch")
    if payload.get("project") not in set(_text_sequence(policy.get("allowed_projects"), "allowed_projects")):
        raise P182ReadinessError("staging_custody_manifest_mismatch")
    freeze_hashes = _mapping(payload.get("freeze_hashes"), "freeze_hashes")
    required_freeze_hashes = _mapping(policy.get("required_freeze_hashes"), "required_freeze_hashes")
    if freeze_hashes != required_freeze_hashes:
        raise P182ReadinessError("staging_custody_manifest_mismatch")
    if not isinstance(manifest.get("signer_id"), str) or not manifest.get("signer_id"):
        raise P182ReadinessError("invalid_staging_custody_manifest")
    if manifest.get("payload_hash") != stable_hash(dict(payload)):
        raise P182ReadinessError("staging_custody_manifest_hash_invalid")
    expected_signature = stable_hash({key: value for key, value in manifest.items() if key != "signature_hash"})
    if manifest.get("signature_hash") != expected_signature:
        raise P182ReadinessError("staging_custody_manifest_hash_invalid")


def _validate_approval_receipt_set(value: Any, *, request: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise P182ReadinessError("approval_receipt_set_required")
    if value.get("schema_version") != "p182.approval_receipt_set.v1":
        raise P182ReadinessError("invalid_approval_receipt_set")
    subject_hash = _approval_subject_hash(request, policy)
    if value.get("subject_hash") != subject_hash:
        raise P182ReadinessError("approval_receipt_set_binding_mismatch")
    receipts = _sequence(value.get("receipts"), "approval_receipts")
    receipts_by_class: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            raise P182ReadinessError("invalid_approval_receipt")
        receipt_class = receipt.get("receipt_class")
        if receipt_class not in REQUIRED_APPROVAL_RECEIPT_CLASSES:
            raise P182ReadinessError("unexpected_approval_receipt_class")
        if receipt_class in receipts_by_class:
            raise P182ReadinessError("duplicate_approval_receipt_class")
        _validate_approval_receipt(receipt, receipt_class=receipt_class, subject_hash=subject_hash)
        receipts_by_class[receipt_class] = receipt
    missing = set(REQUIRED_APPROVAL_RECEIPT_CLASSES) - set(receipts_by_class)
    if missing:
        raise P182ReadinessError("missing_required_approval_receipt")
    expected_hash = stable_hash(
        {
            "schema_version": "p182.approval_receipt_set.v1",
            "subject_hash": subject_hash,
            "receipts": [
                {"receipt_class": receipt_class, "receipt_hash": receipts_by_class[receipt_class]["receipt_hash"]}
                for receipt_class in REQUIRED_APPROVAL_RECEIPT_CLASSES
            ],
        }
    )
    if value.get("receipt_set_hash") != expected_hash:
        raise P182ReadinessError("approval_receipt_set_hash_invalid")


def _validate_approval_receipt(receipt: Mapping[str, Any], *, receipt_class: str, subject_hash: str) -> None:
    if receipt.get("schema_version") != "p182.approval_receipt.v1":
        raise P182ReadinessError("invalid_approval_receipt")
    if receipt.get("subject_hash") != subject_hash:
        raise P182ReadinessError("approval_receipt_binding_mismatch")
    if not isinstance(receipt.get("signer_id"), str) or not receipt.get("signer_id"):
        raise P182ReadinessError("invalid_approval_receipt")
    payload = _mapping(receipt.get("payload"), "approval_receipt_payload")
    if payload.get("receipt_class") != receipt_class or payload.get("subject_hash") != subject_hash:
        raise P182ReadinessError("approval_receipt_binding_mismatch")
    status = payload.get("status")
    if receipt_class == "conditional_safety_event":
        if status not in ("triggered_verified", "not_triggered"):
            raise P182ReadinessError("invalid_approval_receipt")
    elif status != "verified":
        raise P182ReadinessError("invalid_approval_receipt")
    if receipt.get("payload_hash") != stable_hash(dict(payload)):
        raise P182ReadinessError("approval_receipt_hash_invalid")
    expected_hash = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    if receipt.get("receipt_hash") != expected_hash:
        raise P182ReadinessError("approval_receipt_hash_invalid")


def _approval_subject_hash(request: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
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
            "staging_custody_manifest_hash": stable_hash(dict(_mapping(request.get("staging_custody_manifest"), "staging_custody_manifest")))
            if isinstance(request.get("staging_custody_manifest"), Mapping)
            else None,
        }
    )


def _prod_like(value: Any) -> bool:
    return isinstance(value, str) and _PROD_LIKE_RE.search(value) is not None


def _text_sequence(value: Any, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise P182ReadinessError(f"invalid_{field}")
    result = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise P182ReadinessError(f"invalid_{field}")
        result.append(item)
    return result


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P182ReadinessError(f"invalid_{field}")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise P182ReadinessError(f"invalid_{field}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P182ReadinessError(f"invalid_{field}")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise P182ReadinessError(f"invalid_{field}")
    return value
