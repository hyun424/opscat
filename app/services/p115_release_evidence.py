"""Frozen P115 release-evidence bundle assembly.

The bundle is intentionally offline-only: it recomputes local P115 matrix and
leakage evidence, verifies supplied sealed reports, and never executes actions
or reaches production systems.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p115_leakage_guard import scan_candidate_visible_artifact
from app.services.p115_scenario_matrix import (
    REQUIRED_EVALUATOR_LABELS,
    ROADMAP_FAMILIES,
    build_p115_scenario_matrix,
    validate_p115_scenario_matrix,
)
from app.services.p116_release_evidence import validate_p116_release_evidence

P115_RELEASE_EVIDENCE_SCHEMA_VERSION = "p115.release_evidence.v1"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_FILES = (
    "app/services/p115_action_contract.py",
    "app/services/p115_baselines.py",
    "app/services/p115_evaluator.py",
    "app/services/p115_leakage_guard.py",
    "app/services/p115_ontology.py",
    "app/services/p115_outcome_benchmark.py",
    "app/services/p115_p116_benchmark_adapter.py",
    "app/services/p115_scenario_matrix.py",
    "app/services/p115_release_evidence.py",
    "scripts/run_p115_outcome_benchmark.py",
    "scripts/build_p115_release_evidence.py",
)
_ZERO_COUNTER_KEYS = (
    "action_execution_count",
    "production_mutation_count",
    "credential_access_count",
    "subprocess_execution_count",
    "external_network_count",
    "auth_grant_count",
)
_THRESHOLDS = {
    "optimal_action_top1": 0.80,
    "optimal_action_top3": 0.90,
    "harmful_action_selection_rate": 0.01,
    "unnecessary_action_selection_rate": 0.05,
    "prerequisite_compliance": 1.0,
    "contraindication_avoidance": 1.0,
    "validation_completeness": 1.0,
    "rollback_completeness": 1.0,
    "evidence_citation_validity": 0.98,
    "correct_investigate_more_rate": 0.90,
}


class P115ReleaseEvidenceError(ValueError):
    """Raised when P115 release evidence cannot be assembled safely."""


def build_p115_release_evidence(
    *,
    safe_null_baseline: Mapping[str, Any],
    deterministic_baseline: Mapping[str, Any],
    evaluator_report: Mapping[str, Any],
    reviewer_identity: Mapping[str, Any],
    builder_identity: Mapping[str, Any],
    p116_release_evidence: Mapping[str, Any] | None = None,
    expected_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a frozen P115-008 release bundle from sealed local artifacts."""

    matrix = build_p115_scenario_matrix()
    matrix_payload = matrix.to_dict()
    validation = validate_p115_scenario_matrix(matrix.cases, matrix.evaluator_labels, matrix.partition_manifest)
    leakage_report = scan_candidate_visible_artifact(
        {"cases": matrix.candidate_visible_cases(), "partition_manifest": matrix.partition_manifest},
        artifact_path="p115-candidate-visible-release-bundle.json",
    ).to_dict()
    return produce_p115_release_evidence(
        scenario_matrix=matrix_payload,
        matrix_validation=validation,
        leakage_report=leakage_report,
        safe_null_baseline=safe_null_baseline,
        deterministic_baseline=deterministic_baseline,
        evaluator_report=evaluator_report,
        reviewer_identity=reviewer_identity,
        builder_identity=builder_identity,
        p116_release_evidence=p116_release_evidence,
        expected_hashes=expected_hashes,
    )


def produce_p115_release_evidence(
    *,
    scenario_matrix: Mapping[str, Any],
    matrix_validation: Mapping[str, Any],
    leakage_report: Mapping[str, Any],
    safe_null_baseline: Mapping[str, Any],
    deterministic_baseline: Mapping[str, Any],
    evaluator_report: Mapping[str, Any],
    reviewer_identity: Mapping[str, Any],
    builder_identity: Mapping[str, Any],
    p116_release_evidence: Mapping[str, Any] | None = None,
    expected_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble and gate a hash-bound P115 release-evidence object."""

    _require_distinct_reviewer(reviewer_identity, builder_identity)
    _verify_scenario_matrix_hash(scenario_matrix)
    partition_manifest = _mapping(scenario_matrix.get("partition_manifest"))
    _verify_hash_field("partition_manifest", partition_manifest, "manifest_hash")
    _verify_hash_field("leakage_report", leakage_report, "report_hash")
    _verify_hash_field("safe_null_baseline", safe_null_baseline, "report_hash")
    _verify_hash_field("deterministic_baseline", deterministic_baseline, "report_hash")
    _verify_hash_field("evaluator_report", evaluator_report, "report_hash")
    if p116_release_evidence is not None:
        _verify_hash_field("p116_release_evidence", p116_release_evidence, "release_evidence_hash")

    denominators = _denominator_summary(scenario_matrix, matrix_validation, evaluator_report)
    authority = _authority_summary(safe_null_baseline, deterministic_baseline, evaluator_report, p116_release_evidence)
    p116_import = _p116_import_summary(p116_release_evidence)
    evaluator_thresholds = _threshold_summary(evaluator_report)
    artifact_hashes = {
        "source_modules": stable_hash(_source_hashes()),
        "scenario_matrix": str(scenario_matrix["matrix_hash"]),
        "partition_manifest": str(partition_manifest["manifest_hash"]),
        "matrix_validation": stable_hash(matrix_validation),
        "leakage_report": str(leakage_report["report_hash"]),
        "safe_null_baseline": str(safe_null_baseline["report_hash"]),
        "deterministic_baseline": str(deterministic_baseline["report_hash"]),
        "evaluator_report": str(evaluator_report["report_hash"]),
        "p116_release_evidence": str(p116_release_evidence.get("release_evidence_hash", "")) if p116_release_evidence else "",
        "p116_record_hashes": stable_hash(p116_import["record_hashes"]),
    }
    _verify_expected_hashes(artifact_hashes, expected_hashes or {})

    gates = {
        "source_hashes_present": all(value.startswith("sha256:") for value in _source_hashes().values()),
        "matrix_600_cases": int(denominators["case_count"]) == 600,
        "partition_manifest_bound": partition_manifest.get("matrix_hash") == scenario_matrix.get("matrix_hash"),
        "matrix_denominators_complete": denominators["matrix_denominators_complete"],
        "evaluator_denominators_complete": denominators["evaluator_denominators_complete"],
        "no_aggregate_masking": denominators["no_aggregate_masking"],
        "leakage_report_clean": leakage_report.get("clean") is True and int(leakage_report.get("finding_count", -1)) == 0,
        "authority_counters_present": authority["authority_counters_present"],
        "exact_zero_authority": authority["exact_zero_authority"],
        "distinct_reviewer_identity": True,
        "sealed_hashes_current": True,
        "p116_import_contract": p116_import["contract_ready"],
    }
    contract_ready = all(gates.values())
    outcome_qualified = (
        contract_ready
        and p116_import["outcome_qualified"]
        and evaluator_report.get("outcome_qualified") is True
        and evaluator_thresholds["thresholds_passed"]
    )
    evidence: dict[str, Any] = {
        "schema_version": P115_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "release_id": "P115-008",
        "release_status": "p115_outcome_qualified" if outcome_qualified else "p115_contract_ready" if contract_ready else "p115_blocked",
        "contract_ready": contract_ready,
        "outcome_qualified": outcome_qualified,
        "gates": gates,
        "thresholds": evaluator_thresholds,
        "source_hashes": _source_hashes(),
        "artifact_hashes": artifact_hashes,
        "scenario_matrix": {
            "schema_version": scenario_matrix.get("schema_version"),
            "matrix_hash": scenario_matrix.get("matrix_hash"),
            "partition_manifest_hash": partition_manifest.get("manifest_hash"),
        },
        "denominators": denominators,
        "baseline_reports": {
            "safe_null": {"report_hash": safe_null_baseline.get("report_hash"), "counters": dict(_mapping(safe_null_baseline.get("counters")))},
            "deterministic_rule": {
                "report_hash": deterministic_baseline.get("report_hash"),
                "counters": dict(_mapping(deterministic_baseline.get("counters"))),
            },
        },
        "leakage_report": {
            "report_hash": leakage_report.get("report_hash"),
            "clean": leakage_report.get("clean"),
            "finding_count": leakage_report.get("finding_count"),
        },
        "evaluator_report": {
            "report_hash": evaluator_report.get("report_hash"),
            "release_status": evaluator_report.get("release_status"),
            "outcome_qualified": evaluator_report.get("outcome_qualified"),
            "missing_p116_record_count": evaluator_report.get("missing_p116_record_count"),
        },
        "p116_import": p116_import,
        "authority": authority,
        "review": {"reviewer": dict(reviewer_identity), "builder": dict(builder_identity)},
        "reasons": [f"{name} failed closed" for name, passed in gates.items() if passed is not True]
        + ([] if evaluator_thresholds["thresholds_passed"] else ["evaluator thresholds failed closed"])
        + ([] if outcome_qualified or p116_import["present"] else ["P116 absent: contract_ready only"]),
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def render_p115_release_markdown(evidence: Mapping[str, Any]) -> str:
    """Render a concise operations summary without hidden outcome contents."""

    failed = [name for name, passed in _mapping(evidence.get("gates")).items() if passed is not True]
    return (
        "# P115 final release summary\n\n"
        f"- Release: {evidence.get('release_id', 'P115-008')}\n"
        f"- Status: {evidence.get('release_status')}\n"
        f"- Contract ready: {evidence.get('contract_ready')}\n"
        f"- Outcome qualified: {evidence.get('outcome_qualified')}\n"
        f"- Release evidence hash: {evidence.get('release_evidence_hash')}\n"
        f"- Scenario matrix hash: {_mapping(evidence.get('scenario_matrix')).get('matrix_hash')}\n"
        f"- Partition manifest hash: {_mapping(evidence.get('scenario_matrix')).get('partition_manifest_hash')}\n"
        f"- P116 release hash: {_mapping(evidence.get('p116_import')).get('release_evidence_hash', '')}\n"
        f"- Failed gates: {', '.join(failed) if failed else 'none'}\n"
    )


def validate_p115_release_evidence(
    evidence: Mapping[str, Any],
    *,
    imported_p116_evidence: Mapping[str, Any],
    repo_root: Path = _REPO_ROOT,
) -> dict[str, Any]:
    """Validate persisted P115 evidence and its transitive P116 dependency."""

    claimed_hash = str(evidence.get("release_evidence_hash", ""))
    unhashed = {key: value for key, value in evidence.items() if key != "release_evidence_hash"}
    current_sources = _source_hashes(repo_root=repo_root)
    recorded_sources = {str(k): str(v) for k, v in _mapping(evidence.get("source_hashes")).items()}
    p116_report = validate_p116_release_evidence(imported_p116_evidence, repo_root=repo_root)
    imported_hash = str(imported_p116_evidence.get("release_evidence_hash", ""))
    checks = {
        "schema_current": evidence.get("schema_version") == P115_RELEASE_EVIDENCE_SCHEMA_VERSION,
        "self_hash_current": bool(claimed_hash) and claimed_hash == stable_hash(unhashed),
        "source_manifest_complete": set(recorded_sources) == set(current_sources),
        "source_hashes_current": recorded_sources == current_sources,
        "contract_ready": evidence.get("contract_ready") is True,
        "outcome_qualified": evidence.get("outcome_qualified") is True,
        "p116_import_hash_current": _mapping(evidence.get("p116_import")).get("release_evidence_hash") == imported_hash,
        "p116_artifact_current": p116_report.get("valid") is True,
        "exact_zero_authority": _mapping(evidence.get("authority")).get("exact_zero_authority") is True,
    }
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "claimed_release_evidence_hash": claimed_hash,
        "current_source_hashes": current_sources,
        "recorded_source_hashes": recorded_sources,
        "p116_validation": p116_report,
        "reasons": [f"{name} failed closed" for name, passed in checks.items() if passed is not True],
    }


def _denominator_summary(
    scenario_matrix: Mapping[str, Any],
    matrix_validation: Mapping[str, Any],
    evaluator_report: Mapping[str, Any],
) -> dict[str, Any]:
    validation_denominators = _mapping(matrix_validation.get("denominators"))
    by_family = _mapping(validation_denominators.get("by_family"))
    by_family_label = _mapping(validation_denominators.get("by_family_label"))
    partitions = [_mapping(item) for item in _sequence(evaluator_report.get("partitions"))]
    metrics = _mapping(evaluator_report.get("metrics"))
    case_count = len(_sequence(scenario_matrix.get("cases")))
    evaluator_case_count = _int(evaluator_report.get("case_count"))
    matrix_complete = (
        case_count == 600
        and set(by_family) == set(ROADMAP_FAMILIES)
        and all(_int(_mapping(by_family.get(family)).get(role)) > 0 for family in ROADMAP_FAMILIES for role in ("development", "holdout"))
        and all(
            _int(_mapping(_mapping(by_family_label.get(family)).get(label)).get(role)) > 0
            for family in ROADMAP_FAMILIES
            for label in REQUIRED_EVALUATOR_LABELS
            for role in ("development", "holdout")
        )
    )
    evaluator_complete = bool(partitions) and evaluator_case_count > 0 and all(_int(row.get("denominator")) > 0 for row in partitions)
    no_aggregate_masking = evaluator_complete and {str(row.get("family", "")) for row in partitions} >= set(ROADMAP_FAMILIES)
    metric_denominators = {
        name: _int(_mapping(metric).get("denominator"))
        for name, metric in metrics.items()
        if isinstance(metric, Mapping) and name in _THRESHOLDS
    }
    return {
        "case_count": case_count,
        "matrix_validation_case_count": _int(matrix_validation.get("case_count")),
        "matrix_family_count": _int(matrix_validation.get("family_count")),
        "matrix_denominators_complete": matrix_complete,
        "evaluator_case_count": evaluator_case_count,
        "evaluator_partition_count": len(partitions),
        "evaluator_denominators_complete": evaluator_complete and all(value > 0 for value in metric_denominators.values()),
        "no_aggregate_masking": no_aggregate_masking,
        "metric_denominators": metric_denominators,
        "matrix_denominators": validation_denominators,
    }


def _authority_summary(
    safe_null_baseline: Mapping[str, Any],
    deterministic_baseline: Mapping[str, Any],
    evaluator_report: Mapping[str, Any],
    p116_release_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    counters = {key: 0 for key in _ZERO_COUNTER_KEYS}
    present = True
    for report in (safe_null_baseline, deterministic_baseline, evaluator_report):
        report_counters = _mapping(report.get("counters")) or _mapping(report.get("authority"))
        present = present and bool(report_counters)
        counters["action_execution_count"] += _int(report_counters.get("action_execution_count"))
        counters["production_mutation_count"] += _int(report_counters.get("production_mutation_count"))
        counters["credential_access_count"] += _int(report_counters.get("credential_access_count"))
        counters["subprocess_execution_count"] += _int(report_counters.get("subprocess_execution_count"))
        counters["external_network_count"] += _int(report_counters.get("external_network_count"))
        counters["auth_grant_count"] += _int(report_counters.get("auth_grant_count"))
    if p116_release_evidence is not None:
        p116_counters = _mapping(_mapping(p116_release_evidence.get("authority")).get("production_authority_counters"))
        present = present and bool(p116_counters)
        counters["production_mutation_count"] += sum(_int(value) for value in p116_counters.values())
    return {
        "authority_counters_present": present,
        "production_authority_counters": counters,
        "exact_zero_authority": all(value == 0 for value in counters.values()),
        "production_execution_forbidden": True,
    }


def _p116_import_summary(p116_release_evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    if p116_release_evidence is None:
        return {
            "present": False,
            "contract_ready": True,
            "outcome_qualified": False,
            "release_evidence_hash": "",
            "record_hashes": [],
            "record_count": 0,
        }
    record_hashes = [str(item) for item in _sequence(p116_release_evidence.get("record_hashes"))]
    return {
        "present": True,
        "contract_ready": p116_release_evidence.get("contract_ready") is True,
        "outcome_qualified": p116_release_evidence.get("outcome_qualified") is True,
        "release_evidence_hash": str(p116_release_evidence.get("release_evidence_hash", "")),
        "record_hashes": record_hashes,
        "record_count": len(record_hashes),
    }


def _threshold_summary(evaluator_report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _mapping(evaluator_report.get("metrics"))
    checks: dict[str, dict[str, Any]] = {}
    for name, threshold in _THRESHOLDS.items():
        metric = _mapping(metrics.get(name))
        value = metric.get("value")
        denominator = _int(metric.get("denominator"))
        if not isinstance(value, int | float) or isinstance(value, bool) or denominator <= 0:
            passed = False
        elif name.endswith("_rate") and name in {"harmful_action_selection_rate", "unnecessary_action_selection_rate"}:
            passed = float(value) <= threshold
        else:
            passed = float(value) >= threshold
        checks[name] = {"value": value, "denominator": denominator, "threshold": threshold, "passed": passed}
    return {"thresholds_passed": all(item["passed"] is True for item in checks.values()), "checks": checks}


def _verify_hash_field(name: str, payload: Mapping[str, Any], hash_field: str) -> None:
    expected = payload.get(hash_field)
    if not isinstance(expected, str) or not expected.startswith("sha256:"):
        raise P115ReleaseEvidenceError(f"missing_hash:{name}:{hash_field}")
    actual = stable_hash({key: value for key, value in payload.items() if key != hash_field})
    if expected != actual:
        raise P115ReleaseEvidenceError(f"stale_hash:{name}:{hash_field}")


def _verify_scenario_matrix_hash(scenario_matrix: Mapping[str, Any]) -> None:
    expected = scenario_matrix.get("matrix_hash")
    if not isinstance(expected, str) or not expected.startswith("sha256:"):
        raise P115ReleaseEvidenceError("missing_hash:scenario_matrix:matrix_hash")
    actual = stable_hash(
        {
            "schema_version": scenario_matrix.get("schema_version"),
            "cases": list(_sequence(scenario_matrix.get("cases"))),
            "evaluator_labels": list(_sequence(scenario_matrix.get("evaluator_labels"))),
        }
    )
    if expected != actual:
        raise P115ReleaseEvidenceError("stale_hash:scenario_matrix:matrix_hash")


def _verify_expected_hashes(artifact_hashes: Mapping[str, str], expected_hashes: Mapping[str, str]) -> None:
    for name, expected in expected_hashes.items():
        if artifact_hashes.get(name) != expected:
            raise P115ReleaseEvidenceError(f"expected_hash_mismatch:{name}")


def _require_distinct_reviewer(reviewer_identity: Mapping[str, Any], builder_identity: Mapping[str, Any]) -> None:
    reviewer_id = str(reviewer_identity.get("id") or reviewer_identity.get("email") or "")
    builder_id = str(builder_identity.get("id") or builder_identity.get("email") or "")
    if not reviewer_id or not builder_id:
        raise P115ReleaseEvidenceError("missing_reviewer_or_builder_identity")
    if reviewer_id == builder_id:
        raise P115ReleaseEvidenceError("self_review")


def _source_hashes(*, repo_root: Path = _REPO_ROOT) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in _SOURCE_FILES:
        hashes[relative] = "sha256:" + hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
    return hashes


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


__all__ = [
    "P115_RELEASE_EVIDENCE_SCHEMA_VERSION",
    "P115ReleaseEvidenceError",
    "build_p115_release_evidence",
    "produce_p115_release_evidence",
    "render_p115_release_markdown",
    "validate_p115_release_evidence",
]
