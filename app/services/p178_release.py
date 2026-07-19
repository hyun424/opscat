"""P178 offline readiness artifact assembly.

This module cannot qualify P178. It records the local prevention substrate and
blocks promotion until a separate qualified P177 release-evidence artifact is
supplied.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import canonical_json_bytes, file_hash, stable_hash, write_canonical_json

READINESS_SCHEMA_VERSION = "p178.readiness_offline_substrate.v1"
NOT_QUALIFIED_STATUS = "p178_readiness_offline_substrate_only"
REQUIRED_P177_SCHEMA = "p177.release_evidence.v1"
REQUIRED_P177_CLAIM = "evidence_seeking_diagnosis_qualified"
FORBIDDEN_CLAIMS = (
    "bounded_prevention_shadow_qualified",
    "ha_self_monitoring_staging_qualified",
    "real_shadow_operator_ready",
    "limited_staging_auto_approval_qualified",
    "production_autonomy_qualified",
)
SOURCE_PATHS = (
    "app/services/p178_policy.py",
    "app/services/p178_release.py",
    "scripts/build_p178_readiness.py",
    "tests/test_p178_policy_release.py",
    "docs/tickets/p178/README.md",
    "docs/tickets/p178/PRD.md",
    "docs/tickets/p178/test-spec.md",
    "docs/operations/p176-p182-roadmap.md",
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class P178ReleaseError(ValueError):
    """Raised when P178 readiness evidence overclaims or is inconsistent."""


def build_readiness_artifact(*, project_root: Path, p177_release_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    p177_status = _p177_status(p177_release_evidence)
    artifact: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "phase": "p178",
        "status": NOT_QUALIFIED_STATUS,
        "qualified": False,
        "maximum_claim": "readiness_only_not_qualification",
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "stop_reasons": [
            "missing_qualified_p177_release_evidence",
            "missing_600_window_independent_scorer_report",
            "missing_false_prevention_exact_upper_bound_gate",
            "offline_substrate_only",
        ],
        "p177_release_evidence": p177_status,
        "release_artifact_status": {"status": "absent", "blocking": True, "reason": "offline_readiness_only_no_release_artifact"},
        "substrate_capabilities": [
            "precursor_window_taxonomy",
            "prevention_decision_schema_act_no_act_seek_evidence",
            "evidence_citations_and_confidence",
            "fail_closed_prevention_eligibility",
            "false_prevention_one_sided_exact_upper_confidence_bound",
            "fatigue_and_operator_interruption_metrics",
            "counterfactual_outcome_scoring",
            "action_safety_and_blast_radius",
            "shadow_only_no_auto_approval",
        ],
        "safety_counters": {
            "production_mutation_count": 0,
            "staging_mutation_count": 0,
            "credential_read_count": 0,
            "external_network_count": 0,
            "auto_approval_count": 0,
            "unsupported_prevention_proposal_count": 0,
            "unsafe_action_advice_count": 0,
            "fake_qualification_count": 0,
        },
        "source_hashes": _source_hashes(project_root),
    }
    artifact["readiness_hash"] = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    return artifact


def validate_readiness_artifact(artifact: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    if artifact.get("schema_version") != READINESS_SCHEMA_VERSION or artifact.get("phase") != "p178":
        raise P178ReleaseError("invalid_readiness_schema")
    if artifact.get("qualified") is not False or artifact.get("maximum_claim") != "readiness_only_not_qualification":
        raise P178ReleaseError("qualification_forbidden")
    if "bounded_prevention_shadow_qualified" not in artifact.get("forbidden_claims", []):
        raise P178ReleaseError("forbidden_claim_missing")
    p177_status = artifact.get("p177_release_evidence")
    if not isinstance(p177_status, Mapping):
        raise P178ReleaseError("missing_p177_status")
    if p177_status.get("valid") is True:
        raise P178ReleaseError("fabricated_or_unqualified_p177_evidence")
    counters = artifact.get("safety_counters")
    if not isinstance(counters, Mapping):
        raise P178ReleaseError("missing_safety_counters")
    if any(int(counters.get(key, 1)) != 0 for key in counters):
        raise P178ReleaseError("safety_counter_nonzero")
    if artifact.get("source_hashes") != _source_hashes(project_root):
        raise P178ReleaseError("source_hash_mismatch")
    expected_hash = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    if artifact.get("readiness_hash") != expected_hash:
        raise P178ReleaseError("readiness_hash_invalid")
    return dict(artifact)


def write_readiness_artifact(*, project_root: Path, output_path: Path, p177_release_evidence: Mapping[str, Any] | None = None) -> Path:
    artifact = build_readiness_artifact(project_root=project_root, p177_release_evidence=p177_release_evidence)
    validate_readiness_artifact(artifact, project_root=project_root)
    return write_canonical_json(output_path, artifact)


def _p177_status(p177_release_evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    if p177_release_evidence is None:
        return {"valid": False, "reason": "not_supplied", "evidence_hash": None}
    evidence_hash = p177_release_evidence.get("evidence_hash")
    expected_hash = _release_payload_digest(p177_release_evidence)
    valid = (
        p177_release_evidence.get("schema_version") == REQUIRED_P177_SCHEMA
        and p177_release_evidence.get("qualified") is True
        and p177_release_evidence.get("claim") == REQUIRED_P177_CLAIM
        and isinstance(evidence_hash, str)
        and _HEX64_RE.fullmatch(evidence_hash) is not None
        and evidence_hash == expected_hash
        and _has_release_bindings(p177_release_evidence)
    )
    return {
        "valid": False,
        "reason": "qualified_p177_evidence_not_accepted_by_readiness_substrate" if valid else "invalid_or_unqualified_p177_evidence",
        "evidence_hash": evidence_hash if valid else None,
    }


def _source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = project_root / relative
        if not path.exists():
            raise P178ReleaseError(f"missing_source_path:{relative}")
        result[relative] = file_hash(path)
    return result


def _has_release_bindings(evidence: Mapping[str, Any]) -> bool:
    receipt = evidence.get("independent_reviewer_receipt")
    return (
        isinstance(evidence.get("artifact_path"), str)
        and isinstance(evidence.get("artifact_file_hash"), str)
        and isinstance(evidence.get("report_hash"), str)
        and isinstance(evidence.get("freeze_hash"), str)
        and isinstance(evidence.get("final_review_hash"), str)
        and isinstance(receipt, Mapping)
        and receipt.get("payload_hash") == evidence.get("evidence_hash")
        and isinstance(receipt.get("signer_id"), str)
        and isinstance(receipt.get("signature_hash"), str)
    )


def _release_payload_digest(evidence: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in evidence.items() if key not in {"evidence_hash", "independent_reviewer_receipt", "independent_scorer_receipt"}}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
