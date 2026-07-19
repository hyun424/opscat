"""P177 offline readiness artifact assembly.

This module deliberately cannot qualify P177. It only records local readiness
and blocks promotion until independent scoring plus valid P176 G002 live evidence
are supplied by later, separate work.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import canonical_json_bytes, file_hash, stable_hash, write_canonical_json

READINESS_SCHEMA_VERSION = "p177.readiness_offline_substrate.v1"
NOT_QUALIFIED_STATUS = "p177_readiness_offline_substrate_only"
FORBIDDEN_CLAIMS = (
    "evidence_seeking_diagnosis_qualified",
    "multi_service_staging_fault_qualified",
    "production_autonomy_qualified",
)
SOURCE_PATHS = (
    "app/services/p177_tools.py",
    "app/services/p177_trace.py",
    "app/services/p177_policy.py",
    "app/services/p177_scorer.py",
    "app/services/p177_release.py",
    "scripts/build_p177_readiness.py",
    "tests/test_p177_trace_policy.py",
    "tests/test_p177_scorer_release.py",
    "docs/tickets/p177/README.md",
    "docs/tickets/p177/PRD.md",
    "docs/tickets/p177/test-spec.md",
    "docs/operations/p176-p182-roadmap.md",
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

PREDECESSOR_RELEASE_SOURCE_PATHS: Mapping[str, tuple[str, ...]] = {
    "p178": (
        "app/services/p178_policy.py",
        "app/services/p178_release.py",
        "scripts/build_p178_readiness.py",
        "tests/test_p178_policy_release.py",
        "docs/tickets/p178/README.md",
        "docs/tickets/p178/PRD.md",
        "docs/tickets/p178/test-spec.md",
        "docs/operations/p176-p182-roadmap.md",
    ),
    "p179": (
        "app/services/p179_readiness.py",
        "scripts/build_p179_readiness.py",
        "tests/test_p179_readiness.py",
        "docs/tickets/p179/README.md",
        "docs/tickets/p179/PRD.md",
        "docs/tickets/p179/test-spec.md",
        "docs/operations/p176-p182-roadmap.md",
        "evals/p179/input/manifest.json",
    ),
    "p180": (
        "app/services/p180_hidden_eval.py",
        "scripts/build_p180_readiness.py",
        "tests/test_p180_hidden_eval_readiness.py",
        "docs/tickets/p180/README.md",
        "docs/tickets/p180/PRD.md",
        "docs/tickets/p180/test-spec.md",
        "docs/operations/p176-p182-roadmap.md",
    ),
    "p181": (
        "app/services/p181_shadow_readiness.py",
        "scripts/build_p181_readiness.py",
        "tests/test_p181_shadow_readiness.py",
        "docs/tickets/p181/README.md",
        "docs/tickets/p181/PRD.md",
        "docs/tickets/p181/test-spec.md",
        "docs/operations/p176-p182-roadmap.md",
    ),
}


class P177ReleaseError(ValueError):
    """Raised when P177 readiness evidence overclaims or is inconsistent."""


def build_readiness_artifact(*, project_root: Path, p176_live_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    p176_status = _p176_g002_status(p176_live_evidence)
    artifact: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "phase": "p177",
        "status": NOT_QUALIFIED_STATUS,
        "qualified": False,
        "maximum_claim": "readiness_only_not_qualification",
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "stop_reasons": [
            "missing_valid_p176_g002_live_evidence",
            "missing_600_episode_independent_scorer_report",
            "offline_substrate_only",
        ],
        "p176_g002_live_evidence": p176_status,
        "release_artifact_status": {"status": "absent", "blocking": True, "reason": "offline_readiness_only_no_release_artifact"},
        "substrate_capabilities": [
            "evidence_seeking_trace_schema",
            "bounded_read_only_tool_registry",
            "fail_closed_query_tool_time_token_budgets",
            "citation_and_evidence_validation",
            "contradiction_representation",
            "hash_chain_trace_integrity",
            "explicit_stop_reasons",
            "isolated_scorer_api",
            "strongest_baseline_comparison",
            "paired_family_stratified_bootstrap_ci",
            "strict_label_leak_prevention",
        ],
        "safety_counters": {
            "production_mutation_count": 0,
            "staging_mutation_count": 0,
            "credential_read_count": 0,
            "external_network_count": 0,
            "unsafe_action_advice_count": 0,
            "fake_live_evidence_count": 0,
        },
        "source_hashes": _source_hashes(project_root),
    }
    artifact["readiness_hash"] = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    return artifact


def validate_readiness_artifact(artifact: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    if artifact.get("schema_version") != READINESS_SCHEMA_VERSION or artifact.get("phase") != "p177":
        raise P177ReleaseError("invalid_readiness_schema")
    if artifact.get("qualified") is not False or artifact.get("maximum_claim") != "readiness_only_not_qualification":
        raise P177ReleaseError("qualification_forbidden")
    if "evidence_seeking_diagnosis_qualified" not in artifact.get("forbidden_claims", []):
        raise P177ReleaseError("forbidden_claim_missing")
    counters = artifact.get("safety_counters")
    if not isinstance(counters, Mapping):
        raise P177ReleaseError("missing_safety_counters")
    if any(int(counters.get(key, 1)) != 0 for key in counters):
        raise P177ReleaseError("safety_counter_nonzero")
    p176_status = artifact.get("p176_g002_live_evidence")
    if not isinstance(p176_status, Mapping):
        raise P177ReleaseError("missing_p176_g002_status")
    if p176_status.get("valid") is True and not p176_status.get("evidence_hash"):
        raise P177ReleaseError("p176_g002_hash_missing")
    if artifact.get("source_hashes") != _source_hashes(project_root):
        raise P177ReleaseError("source_hash_mismatch")
    expected_hash = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    if artifact.get("readiness_hash") != expected_hash:
        raise P177ReleaseError("readiness_hash_invalid")
    return dict(artifact)


def write_readiness_artifact(*, project_root: Path, output_path: Path, p176_live_evidence: Mapping[str, Any] | None = None) -> Path:
    artifact = build_readiness_artifact(project_root=project_root, p176_live_evidence=p176_live_evidence)
    validate_readiness_artifact(artifact, project_root=project_root)
    return write_canonical_json(output_path, artifact)


def _p176_g002_status(p176_live_evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    if p176_live_evidence is None:
        return {"valid": False, "reason": "not_supplied", "evidence_hash": None}
    evidence_hash = p176_live_evidence.get("evidence_hash")
    expected_hash = hashlib.sha256(canonical_json_bytes({key: value for key, value in p176_live_evidence.items() if key != "evidence_hash"})).hexdigest()
    valid = (
        p176_live_evidence.get("schema_version") == "p176.g002.live_evidence.v1"
        and p176_live_evidence.get("valid") is True
        and isinstance(evidence_hash, str)
        and _HEX64_RE.fullmatch(evidence_hash) is not None
        and evidence_hash == expected_hash
    )
    return {
        "valid": bool(valid),
        "reason": "valid" if valid else "invalid_or_not_g002",
        "evidence_hash": evidence_hash if valid else None,
    }


def _source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = project_root / relative
        if not path.exists():
            raise P177ReleaseError(f"missing_source_path:{relative}")
        result[relative] = file_hash(path)
    return result


def validate_predecessor_release_on_disk(
    evidence: Mapping[str, Any],
    *,
    project_root: Path,
    phase: str,
    schema_version: str,
    claim: str,
    receipt_key: str,
) -> bool:
    """Validate a predecessor release against canonical files, not strings."""

    try:
        _validate_predecessor_release_on_disk(
            evidence,
            project_root=project_root,
            phase=phase,
            schema_version=schema_version,
            claim=claim,
            receipt_key=receipt_key,
        )
    except (OSError, P177ReleaseError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return True


def _validate_predecessor_release_on_disk(
    evidence: Mapping[str, Any],
    *,
    project_root: Path,
    phase: str,
    schema_version: str,
    claim: str,
    receipt_key: str,
) -> None:
    if evidence.get("schema_version") != schema_version or evidence.get("phase") not in {None, phase}:
        raise P177ReleaseError("predecessor_schema_invalid")
    if evidence.get("qualified") is not True or evidence.get("claim") != claim:
        raise P177ReleaseError("predecessor_claim_invalid")
    evidence_hash = evidence.get("evidence_hash")
    if not isinstance(evidence_hash, str) or _HEX64_RE.fullmatch(evidence_hash) is None:
        raise P177ReleaseError("predecessor_evidence_hash_invalid")
    expected_hash = hashlib.sha256(canonical_json_bytes(_release_payload(evidence))).hexdigest()
    if evidence_hash != expected_hash:
        raise P177ReleaseError("predecessor_evidence_hash_mismatch")

    release_root = _repo_relative_regular_dir(project_root, Path(f"evals/{phase}/output"))
    artifact_path = _bound_file_under_root(
        project_root=project_root,
        release_root=release_root,
        relative_value=evidence.get("artifact_path"),
        hash_value=evidence.get("artifact_file_hash"),
        hash_field="artifact_file_hash",
    )
    if artifact_path.name != "release-evidence.json":
        raise P177ReleaseError("predecessor_release_artifact_name_invalid")
    release = _load_json(artifact_path)
    if dict(release) != dict(evidence):
        raise P177ReleaseError("predecessor_release_artifact_payload_mismatch")

    report = _load_bound_companion(
        project_root=project_root,
        release_root=release_root,
        path_value=evidence.get("report_path"),
        expected_hash=evidence.get("report_hash"),
        hash_field="report_hash",
    )
    freeze = _load_bound_companion(
        project_root=project_root,
        release_root=release_root,
        path_value=evidence.get("freeze_path"),
        expected_hash=evidence.get("freeze_hash"),
        hash_field="freeze_hash",
    )
    final_review = _load_bound_companion(
        project_root=project_root,
        release_root=release_root.parent,
        path_value=evidence.get("final_review_path"),
        expected_hash=evidence.get("final_review_hash"),
        hash_field="final_review_hash",
    )
    _validate_companion_bindings(evidence=evidence, report=report, freeze=freeze, final_review=final_review)
    _validate_predecessor_source_hashes(evidence.get("source_hashes"), project_root=project_root, phase=phase)
    _validate_independent_receipt(evidence.get(receipt_key), evidence_hash=evidence_hash)


def _release_payload(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in evidence.items()
        if key not in {"evidence_hash", "independent_reviewer_receipt", "independent_scorer_receipt"}
    }


def _repo_relative_regular_dir(project_root: Path, relative: Path) -> Path:
    root = project_root.resolve()
    candidate = root / relative
    resolved = candidate.resolve()
    if candidate.is_symlink() or root not in resolved.parents or not resolved.is_dir():
        raise P177ReleaseError("predecessor_release_root_invalid")
    return resolved


def _bound_file_under_root(
    *,
    project_root: Path,
    release_root: Path,
    relative_value: Any,
    hash_value: Any,
    hash_field: str,
) -> Path:
    resolved = _resolve_file_under_root(project_root=project_root, release_root=release_root, relative_value=relative_value)
    if file_hash(resolved) != _hash_text(hash_value, hash_field):
        raise P177ReleaseError(f"{hash_field}_mismatch")
    return resolved


def _resolve_file_under_root(*, project_root: Path, release_root: Path, relative_value: Any) -> Path:
    if not isinstance(relative_value, str) or not relative_value:
        raise P177ReleaseError("predecessor_artifact_path_invalid")
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise P177ReleaseError("predecessor_artifact_path_invalid")
    project = project_root.resolve()
    candidate = project / relative
    resolved = candidate.resolve()
    if candidate.is_symlink() or release_root not in resolved.parents or not resolved.is_file() or resolved.is_symlink():
        raise P177ReleaseError("predecessor_artifact_path_unsafe")
    return resolved


def _load_bound_companion(
    *,
    project_root: Path,
    release_root: Path,
    path_value: Any,
    expected_hash: Any,
    hash_field: str,
) -> dict[str, Any]:
    path = _resolve_file_under_root(project_root=project_root, release_root=release_root, relative_value=path_value)
    payload = _load_json(path)
    actual = payload.get(hash_field)
    if hash_field == "freeze_hash":
        actual = payload.get("manifest_hash", payload.get("freeze_hash"))
    if hash_field == "final_review_hash":
        actual = payload.get("review_hash", payload.get("final_review_hash"))
    if actual != _hash_text(expected_hash, hash_field):
        raise P177ReleaseError(f"{hash_field}_mismatch")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise P177ReleaseError("predecessor_json_invalid")
    return payload


def _validate_companion_bindings(
    *,
    evidence: Mapping[str, Any],
    report: Mapping[str, Any],
    freeze: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> None:
    if report.get("report_hash") != evidence.get("report_hash"):
        raise P177ReleaseError("report_hash_mismatch")
    freeze_hash = freeze.get("manifest_hash", freeze.get("freeze_hash"))
    if freeze_hash != evidence.get("freeze_hash") or freeze.get("report_hash") != evidence.get("report_hash"):
        raise P177ReleaseError("freeze_hash_mismatch")
    review_hash = final_review.get("review_hash", final_review.get("final_review_hash"))
    if review_hash != evidence.get("final_review_hash"):
        raise P177ReleaseError("final_review_hash_mismatch")
    if final_review.get("reviewed_report_hash") not in {None, evidence.get("report_hash")}:
        raise P177ReleaseError("final_review_report_hash_mismatch")
    if final_review.get("reviewed_manifest_hash", final_review.get("reviewed_freeze_manifest_hash")) not in {None, evidence.get("freeze_hash")}:
        raise P177ReleaseError("final_review_freeze_hash_mismatch")


def _validate_predecessor_source_hashes(value: Any, *, project_root: Path, phase: str) -> None:
    expected_paths = PREDECESSOR_RELEASE_SOURCE_PATHS.get(phase)
    if expected_paths is None:
        raise P177ReleaseError("predecessor_source_paths_unknown")
    if not isinstance(value, Mapping) or set(value) != set(expected_paths) or list(value) != sorted(value):
        raise P177ReleaseError("predecessor_source_hashes_invalid")
    project = project_root.resolve()
    for relative_value, expected_hash in value.items():
        relative = Path(str(relative_value))
        if relative.is_absolute() or ".." in relative.parts:
            raise P177ReleaseError("predecessor_source_path_invalid")
        path = project / relative
        resolved = path.resolve()
        if path.is_symlink() or project not in resolved.parents or not resolved.is_file() or resolved.is_symlink():
            raise P177ReleaseError("predecessor_source_path_unsafe")
        if file_hash(resolved) != _hash_text(expected_hash, "source_hash"):
            raise P177ReleaseError("predecessor_source_hash_mismatch")


def _validate_independent_receipt(value: Any, *, evidence_hash: str) -> None:
    if not isinstance(value, Mapping):
        raise P177ReleaseError("independent_receipt_missing")
    if value.get("payload_hash") != evidence_hash:
        raise P177ReleaseError("independent_receipt_payload_mismatch")
    if not isinstance(value.get("signer_id"), str) or "independent" not in value["signer_id"]:
        raise P177ReleaseError("independent_receipt_signer_invalid")
    signature_hash = value.get("signature_hash")
    if not isinstance(signature_hash, str) or not _HASH_RE.fullmatch(signature_hash):
        raise P177ReleaseError("independent_receipt_signature_invalid")
    expected_signature = stable_hash({key: item for key, item in value.items() if key != "signature_hash"})
    if signature_hash != expected_signature:
        raise P177ReleaseError("independent_receipt_signature_invalid")
    if "receipt_hash" in value:
        if value.get("receipt_hash") != stable_hash({key: item for key, item in value.items() if key != "receipt_hash"}):
            raise P177ReleaseError("independent_receipt_hash_invalid")


def _hash_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise P177ReleaseError(f"{field}_invalid")
    return value
