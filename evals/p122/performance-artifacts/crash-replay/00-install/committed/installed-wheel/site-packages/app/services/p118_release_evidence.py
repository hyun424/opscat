"""Freshness-bound P118 local execution release evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_evaluator import P118_EVALUATION_SCHEMA_VERSION
from app.services.p118_operation_contract import P118_AUTHORITY_COUNTER_KEYS

P118_RELEASE_EVIDENCE_SCHEMA_VERSION = "p118.release_evidence.v1"
_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_FILES = (
    "app/services/p118_operation_contract.py",
    "app/services/p118_action_pack_verifier.py",
    "app/services/p118_approval.py",
    "app/services/p118_ledger.py",
    "app/services/p118_validation_cycle.py",
    "app/services/p118_crash_recovery.py",
    "app/services/p118_evaluator.py",
    "app/services/p118_release_evidence.py",
    "scripts/run_p118_frozen_evaluation.py",
    "scripts/build_p118_release_evidence.py",
    "scripts/validate_p118_release_evidence.py",
    "evals/p118/frozen-case-manifest.json",
)


def empty_p118_release_authority_counters() -> dict[str, int]:
    return {key: 0 for key in P118_AUTHORITY_COUNTER_KEYS}


def produce_p118_release_evidence(
    *,
    frozen_evaluation_report: Mapping[str, Any],
    reviewer_identity: Mapping[str, Any],
    builder_identity: Mapping[str, Any],
    authority_counters: Mapping[str, int],
) -> dict[str, Any]:
    reviewer_id = str(reviewer_identity.get("id", ""))
    builder_id = str(builder_identity.get("id", ""))
    exact_zero = _exact_zero_authority(authority_counters)
    evaluation_current = frozen_evaluation_report.get("schema_version") == P118_EVALUATION_SCHEMA_VERSION and frozen_evaluation_report.get("evaluation_hash") == stable_hash(
        {key: value for key, value in frozen_evaluation_report.items() if key != "evaluation_hash"}
    )
    metrics = frozen_evaluation_report.get("per_family_metrics")
    all_cases_pass = isinstance(metrics, Mapping) and bool(metrics) and all(isinstance(value, Mapping) and value.get("numerator") == value.get("denominator") for value in metrics.values())
    gates = {
        "distinct_reviewer": bool(reviewer_id and builder_id and reviewer_id != builder_id),
        "frozen_evaluation_current": evaluation_current,
        "at_least_300_cases": int(frozen_evaluation_report.get("case_count", 0)) >= 300,
        "all_family_gates_passed": all_cases_pass,
        "no_duplicate_actions": _mapping(frozen_evaluation_report.get("aggregate")).get("duplicate_action_count") == 0,
        "exact_nonlocal_authority_zero": exact_zero,
        "source_hashes_present": len(_source_hashes()) == len(_SOURCE_FILES),
    }
    qualified = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P118_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "release_id": "P118-008",
        "release_status": "p118_local_mock_sandbox_ready" if qualified else "p118_blocked",
        "product_claim": "local/mock/sandbox reactive execution substrate readiness",
        "scope_limit": "No production mutation, external authority, credentials, or auth implementation.",
        "gates": gates,
        "frozen_evaluation_hash": frozen_evaluation_report.get("evaluation_hash"),
        "frozen_evaluation_report": dict(frozen_evaluation_report),
        "source_hashes": _source_hashes(),
        "authority": {"counters": dict(authority_counters), "exact_nonlocal_authority_zero": exact_zero},
        "review": {"reviewer": dict(reviewer_identity), "builder": dict(builder_identity)},
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if passed is not True],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p118_release_evidence(evidence: Mapping[str, Any], *, repo_root: Path = _ROOT) -> dict[str, Any]:
    report = _mapping(evidence.get("frozen_evaluation_report"))
    current_sources = _source_hashes(repo_root)
    recorded_sources = {str(key): str(value) for key, value in _mapping(evidence.get("source_hashes")).items()}
    authority = _mapping(evidence.get("authority"))
    counters = _mapping(authority.get("counters"))
    review = _mapping(evidence.get("review"))
    reviewer = _mapping(review.get("reviewer"))
    builder = _mapping(review.get("builder"))
    checks = {
        "schema_current": evidence.get("schema_version") == P118_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"}),
        "frozen_evaluation_self_hash_current": report.get("evaluation_hash") == stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"}),
        "frozen_evaluation_hash_bound": evidence.get("frozen_evaluation_hash") == report.get("evaluation_hash"),
        "source_manifest_complete": set(recorded_sources) == set(current_sources),
        "source_hashes_current": recorded_sources == current_sources,
        "distinct_reviewer": bool(reviewer.get("id") and builder.get("id") and reviewer.get("id") != builder.get("id")),
        "exact_nonlocal_authority_zero": _exact_zero_authority(counters),
        "release_qualified": evidence.get("release_status") == "p118_local_mock_sandbox_ready",
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _source_hashes(repo_root: Path = _ROOT) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in _SOURCE_FILES:
        path = repo_root / relative
        if path.exists():
            result[relative] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _exact_zero_authority(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P118_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters[key] == 0 for key in P118_AUTHORITY_COUNTER_KEYS
    )


__all__ = [
    "P118_RELEASE_EVIDENCE_SCHEMA_VERSION",
    "empty_p118_release_authority_counters",
    "produce_p118_release_evidence",
    "validate_p118_release_evidence",
]
