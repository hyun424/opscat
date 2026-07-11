"""Freshness-bound P121 proactive-prevention release evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_evaluator import P121_EVALUATION_SCHEMA_VERSION
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS, zero_authority_counters

P121_RELEASE_SCHEMA_VERSION = "p121.release_evidence.v1"
_ROOT = Path(__file__).resolve().parents[2]
_FILES = tuple(f"app/services/p121_{name}.py" for name in ("signals", "forecasting", "counterfactuals", "guardrails", "execution", "validation", "evaluator", "release_evidence")) + (
    "scripts/run_p121_frozen_evaluation.py",
    "scripts/build_p121_release_evidence.py",
    "scripts/validate_p121_release_evidence.py",
    "evals/p121/frozen-unseen-manifest.json",
)


def produce_p121_release_evidence(*, report: Mapping[str, Any], reviewer_id: str, builder_id: str, authority_counters: Mapping[str, int] | None = None) -> dict[str, Any]:
    counters = dict(authority_counters or zero_authority_counters())
    current = report.get("schema_version") == P121_EVALUATION_SCHEMA_VERSION and report.get("evaluation_hash") == stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"})
    aggregate = _mapping(report.get("aggregate"))
    exact_zero = set(counters) == set(P121_AUTHORITY_COUNTER_KEYS) and all(counters.get(key) == 0 for key in P121_AUTHORITY_COUNTER_KEYS)
    gates = {
        "distinct_reviewer": bool(reviewer_id and builder_id and reviewer_id != builder_id),
        "frozen_report_current": current,
        "at_least_300_cases": int(report.get("case_count", 0)) >= 300,
        "all_cases_pass": aggregate.get("passed") == report.get("case_count"),
        "zero_harm": aggregate.get("harmful_action_rate") == 0,
        "zero_fatigue_violation": aggregate.get("fatigue_violation_rate") == 0,
        "zero_rollback_failure": aggregate.get("rollback_failure_rate") == 0,
        "zero_duplicate_effect": aggregate.get("duplicate_effect_count") == 0,
        "raw_manifest_contract": _mapping(report.get("manifest_contract")).get("raw_inputs_only") is True
        and _mapping(report.get("manifest_contract")).get("hidden_truth_is_scorer_only") is True,
        "system_temporal_leakage_checks": _mapping(report.get("manifest_contract")).get("system_temporal_separation_enforced") is True
        and _mapping(report.get("manifest_contract")).get("near_duplicate_leakage_check") == "passed",
        "crash_replay_complete": len(report.get("crash_replay_points", [])) >= 13 and len(report.get("crash_replay_receipts", {})) == len(report.get("crash_replay_points", [])),
        "durable_restart_recovery": _mapping(report.get("restart_recovery")).get("point_count", 0) >= 13
        and _mapping(report.get("restart_recovery")).get("partial_l3_recovered") is True
        and _mapping(report.get("restart_recovery")).get("rollback_recovered") is True
        and _mapping(report.get("restart_recovery")).get("pending_rollback_replayed") is True
        and _mapping(report.get("restart_recovery")).get("pending_rollback_count_after_replay") == 0,
        "per_slice_denominators": bool(report.get("per_slice")) and all(int(_mapping(value).get("denominator", 0)) > 0 for value in _mapping(report.get("per_slice")).values()),
        "exact_nonlocal_authority_zero": exact_zero,
        "source_manifest_complete": len(_hashes()) == len(_FILES),
    }
    ready = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P121_RELEASE_SCHEMA_VERSION,
        "release_id": "P121-008",
        "release_status": "p121_local_proactive_prevention_ready" if ready else "p121_blocked",
        "product_claim": "local/mock/sandbox proactive prevention readiness",
        "scope_limit": "No production or staging mutations, credentials, auth completion, live connector writes, or operator replacement.",
        "gates": gates,
        "frozen_evaluation_hash": report.get("evaluation_hash"),
        "frozen_evaluation_report": dict(report),
        "source_hashes": _hashes(),
        "authority": {"counters": counters, "exact_nonlocal_authority_zero": exact_zero},
        "review": {"reviewer": {"id": reviewer_id}, "builder": {"id": builder_id}},
        "unresolved_risks": ["deterministic benchmark fixtures are not live-production evidence"],
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if not passed],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p121_release_evidence(evidence: Mapping[str, Any], *, root: Path = _ROOT) -> dict[str, Any]:
    report = _mapping(evidence.get("frozen_evaluation_report"))
    counters = _mapping(_mapping(evidence.get("authority")).get("counters"))
    recorded = {str(key): str(value) for key, value in _mapping(evidence.get("source_hashes")).items()}
    review = _mapping(evidence.get("review"))
    checks = {
        "schema_current": evidence.get("schema_version") == P121_RELEASE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"}),
        "report_hash_current": report.get("evaluation_hash") == stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"}),
        "report_bound": evidence.get("frozen_evaluation_hash") == report.get("evaluation_hash"),
        "source_hashes_current": recorded == _hashes(root),
        "distinct_reviewer": _mapping(review.get("reviewer")).get("id") != _mapping(review.get("builder")).get("id"),
        "exact_zero_authority": set(counters) == set(P121_AUTHORITY_COUNTER_KEYS) and all(counters.get(key) == 0 for key in P121_AUTHORITY_COUNTER_KEYS),
        "release_qualified": evidence.get("release_status") == "p121_local_proactive_prevention_ready",
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _hashes(root: Path = _ROOT) -> dict[str, str]:
    return {path: "sha256:" + hashlib.sha256((root / path).read_bytes()).hexdigest() for path in _FILES if (root / path).exists()}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["produce_p121_release_evidence", "validate_p121_release_evidence"]
