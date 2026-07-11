"""Freshness-bound release evidence for P120 cross-system evaluation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p120_evaluator import P120_EVALUATION_SCHEMA_VERSION
from app.services.p120_governance import AUTHORITY_COUNTER_KEYS

P120_RELEASE_SCHEMA_VERSION = "p120.release_evidence.v1"
_ROOT = Path(__file__).resolve().parents[2]
_FILES = tuple(f"app/services/p120_{name}.py" for name in ("governance", "splits", "normalization", "ontology", "ood", "calibration", "evaluator", "release_evidence")) + (
    "scripts/run_p120_frozen_evaluation.py",
    "scripts/build_p120_release_evidence.py",
    "scripts/validate_p120_release_evidence.py",
    "evals/p120/frozen-cross-system-manifest.json",
)


def empty_p120_release_authority_counters() -> dict[str, int]:
    return {key: 0 for key in AUTHORITY_COUNTER_KEYS}


def produce_p120_release_evidence(
    *, frozen_evaluation_report: Mapping[str, Any], reviewer_identity: Mapping[str, Any], builder_identity: Mapping[str, Any], authority_counters: Mapping[str, int]
) -> dict[str, Any]:
    reviewer, builder = str(reviewer_identity.get("id", "")), str(builder_identity.get("id", ""))
    report_current = frozen_evaluation_report.get("schema_version") == P120_EVALUATION_SCHEMA_VERSION and frozen_evaluation_report.get("evaluation_hash") == stable_hash(
        {k: v for k, v in frozen_evaluation_report.items() if k != "evaluation_hash"}
    )
    exact_zero = set(authority_counters) == set(AUTHORITY_COUNTER_KEYS) and all(authority_counters.get(k) == 0 for k in AUTHORITY_COUNTER_KEYS)
    gates = {
        "distinct_reviewer": bool(reviewer and builder and reviewer != builder),
        "frozen_report_current": report_current,
        "at_least_three_systems": int(frozen_evaluation_report.get("system_count", 0)) >= 3,
        "at_least_five_source_classes": int(frozen_evaluation_report.get("source_class_count", 0)) >= 5,
        "at_least_twenty_families": int(frozen_evaluation_report.get("scenario_family_count", 0)) >= 20,
        "bounded_cross_system_degradation": float(frozen_evaluation_report.get("max_degradation", 1.0)) <= 0.15,
        "ood_reports_complete": len(frozen_evaluation_report.get("ood_reports", [])) == int(frozen_evaluation_report.get("system_count", 0)),
        "identical_baseline_denominators": bool(_mapping(frozen_evaluation_report.get("score_report")).get("identical_denominators")),
        "exact_nonlocal_authority_zero": exact_zero,
        "source_manifest_complete": len(_hashes()) == len(_FILES),
    }
    ready = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P120_RELEASE_SCHEMA_VERSION,
        "release_id": "P120-008",
        "release_status": "p120_cross_system_benchmark_ready" if ready else "p120_blocked",
        "product_claim": "cross-system benchmark generalization readiness",
        "scope_limit": "Not production autonomy, operator replacement, auth, or credentialed execution.",
        "gates": gates,
        "frozen_evaluation_hash": frozen_evaluation_report.get("evaluation_hash"),
        "frozen_evaluation_report": dict(frozen_evaluation_report),
        "source_hashes": _hashes(),
        "authority": {"counters": dict(authority_counters), "exact_nonlocal_authority_zero": exact_zero},
        "review": {"reviewer": dict(reviewer_identity), "builder": dict(builder_identity)},
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if not passed],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p120_release_evidence(evidence: Mapping[str, Any], *, repo_root: Path = _ROOT) -> dict[str, Any]:
    report = _mapping(evidence.get("frozen_evaluation_report"))
    recorded = {str(k): str(v) for k, v in _mapping(evidence.get("source_hashes")).items()}
    current = _hashes(repo_root)
    authority = _mapping(evidence.get("authority"))
    counters = _mapping(authority.get("counters"))
    review = _mapping(evidence.get("review"))
    checks = {
        "schema_current": evidence.get("schema_version") == P120_RELEASE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({k: v for k, v in evidence.items() if k != "release_evidence_hash"}),
        "report_hash_current": report.get("evaluation_hash") == stable_hash({k: v for k, v in report.items() if k != "evaluation_hash"}),
        "report_bound": evidence.get("frozen_evaluation_hash") == report.get("evaluation_hash"),
        "source_hashes_current": recorded == current,
        "source_manifest_complete": set(recorded) == set(current),
        "distinct_reviewer": bool(
            _mapping(review.get("reviewer")).get("id") and _mapping(review.get("builder")).get("id") and _mapping(review.get("reviewer")).get("id") != _mapping(review.get("builder")).get("id")
        ),
        "exact_zero_authority": set(counters) == set(AUTHORITY_COUNTER_KEYS) and all(counters.get(k) == 0 for k in AUTHORITY_COUNTER_KEYS),
        "release_qualified": evidence.get("release_status") == "p120_cross_system_benchmark_ready",
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _hashes(root: Path = _ROOT) -> dict[str, str]:
    return {name: "sha256:" + hashlib.sha256((root / name).read_bytes()).hexdigest() for name in _FILES if (root / name).exists()}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["empty_p120_release_authority_counters", "produce_p120_release_evidence", "validate_p120_release_evidence"]
