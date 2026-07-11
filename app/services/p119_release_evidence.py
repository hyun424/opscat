"""Freshness-bound release evidence for P119 closed-loop local readiness."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p119_contract import P119_AUTHORITY_COUNTER_KEYS
from app.services.p119_evaluator import P119_EVALUATION_SCHEMA_VERSION

P119_RELEASE_SCHEMA_VERSION = "p119.release_evidence.v1"
_ROOT = Path(__file__).resolve().parents[2]
_FILES = tuple(
    [
        f"app/services/p119_{name}.py"
        for name in ("contract", "ledger", "scheduler", "evidence_loop", "selection", "execution_loop", "war_room", "attribution", "recovery", "evaluator", "release_evidence")
    ]
) + (
    "scripts/run_p119_frozen_evaluation.py",
    "scripts/build_p119_release_evidence.py",
    "scripts/validate_p119_release_evidence.py",
    "evals/p119/frozen-case-manifest.json",
)
_P118_DEPENDENCY_FILES = (
    "app/services/p118_operation_contract.py",
    "app/services/p118_action_pack_verifier.py",
    "app/services/p118_approval.py",
    "app/services/p118_ledger.py",
    "app/services/p118_validation_cycle.py",
    "app/services/p118_worker.py",
)


def empty_p119_release_authority_counters() -> dict[str, int]:
    return {key: 0 for key in P119_AUTHORITY_COUNTER_KEYS}


def produce_p119_release_evidence(
    *, frozen_evaluation_report: Mapping[str, Any], reviewer_identity: Mapping[str, Any], builder_identity: Mapping[str, Any], authority_counters: Mapping[str, int]
) -> dict[str, Any]:
    reviewer, builder = str(reviewer_identity.get("id", "")), str(builder_identity.get("id", ""))
    report_current = frozen_evaluation_report.get("schema_version") == P119_EVALUATION_SCHEMA_VERSION and frozen_evaluation_report.get("evaluation_hash") == stable_hash(
        {k: v for k, v in frozen_evaluation_report.items() if k != "evaluation_hash"}
    )
    metrics = frozen_evaluation_report.get("per_family_metrics")
    exact_zero = _exact_zero(authority_counters)
    p118_dependencies = _hashes_for(_P118_DEPENDENCY_FILES)
    gates = {
        "distinct_reviewer": bool(reviewer and builder and reviewer != builder),
        "frozen_report_current": report_current,
        "at_least_300_cases": int(frozen_evaluation_report.get("case_count", 0)) >= 300,
        "all_family_gates": isinstance(metrics, Mapping) and bool(metrics) and all(isinstance(v, Mapping) and v.get("numerator") == v.get("denominator") for v in metrics.values()),
        "zero_false_recovery": _mapping(frozen_evaluation_report.get("aggregate")).get("false_recovery_count") == 0,
        "zero_duplicate_action": _mapping(frozen_evaluation_report.get("aggregate")).get("duplicate_local_action_count") == 0,
        "exact_nonlocal_authority_zero": exact_zero,
        "source_manifest_complete": len(_hashes()) == len(_FILES),
        "p118_dependency_manifest_complete": len(p118_dependencies) == len(_P118_DEPENDENCY_FILES),
    }
    ready = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P119_RELEASE_SCHEMA_VERSION,
        "release_id": "P119-008",
        "release_status": "p119_local_closed_loop_ready" if ready else "p119_blocked",
        "product_claim": "local/mock/sandbox closed-loop incident-response readiness",
        "scope_limit": "Not production autonomy, operator replacement, auth, or credentialed execution.",
        "gates": gates,
        "frozen_evaluation_hash": frozen_evaluation_report.get("evaluation_hash"),
        "frozen_evaluation_report": dict(frozen_evaluation_report),
        "source_hashes": _hashes(),
        "p118_dependency_source_hashes": p118_dependencies,
        "authority": {"counters": dict(authority_counters), "exact_nonlocal_authority_zero": exact_zero},
        "review": {"reviewer": dict(reviewer_identity), "builder": dict(builder_identity)},
        "reasons": [f"{k} failed closed" for k, v in gates.items() if not v],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p119_release_evidence(evidence: Mapping[str, Any], *, repo_root: Path = _ROOT) -> dict[str, Any]:
    report = _mapping(evidence.get("frozen_evaluation_report"))
    recorded = {str(k): str(v) for k, v in _mapping(evidence.get("source_hashes")).items()}
    current = _hashes(repo_root)
    recorded_p118 = {str(k): str(v) for k, v in _mapping(evidence.get("p118_dependency_source_hashes")).items()}
    current_p118 = _hashes_for(_P118_DEPENDENCY_FILES, repo_root)
    authority = _mapping(evidence.get("authority"))
    counters = _mapping(authority.get("counters"))
    review = _mapping(evidence.get("review"))
    reviewer = _mapping(review.get("reviewer"))
    builder = _mapping(review.get("builder"))
    checks = {
        "schema_current": evidence.get("schema_version") == P119_RELEASE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({k: v for k, v in evidence.items() if k != "release_evidence_hash"}),
        "report_hash_current": report.get("evaluation_hash") == stable_hash({k: v for k, v in report.items() if k != "evaluation_hash"}),
        "report_bound": evidence.get("frozen_evaluation_hash") == report.get("evaluation_hash"),
        "source_hashes_current": recorded == current,
        "source_manifest_complete": set(recorded) == set(current),
        "p118_dependency_source_hashes_current": recorded_p118 == current_p118,
        "p118_dependency_manifest_complete": set(recorded_p118) == set(current_p118) == set(_P118_DEPENDENCY_FILES),
        "distinct_reviewer": bool(reviewer.get("id") and builder.get("id") and reviewer.get("id") != builder.get("id")),
        "exact_zero_authority": _exact_zero(counters),
        "release_qualified": evidence.get("release_status") == "p119_local_closed_loop_ready",
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{k} failed closed" for k, v in checks.items() if not v]}


def _hashes(root: Path = _ROOT) -> dict[str, str]:
    return _hashes_for(_FILES, root)


def _hashes_for(files: tuple[str, ...], root: Path = _ROOT) -> dict[str, str]:
    return {name: "sha256:" + hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files if (root / name).exists()}


def _exact_zero(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P119_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters[key] == 0 for key in P119_AUTHORITY_COUNTER_KEYS
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["empty_p119_release_authority_counters", "produce_p119_release_evidence", "validate_p119_release_evidence"]
