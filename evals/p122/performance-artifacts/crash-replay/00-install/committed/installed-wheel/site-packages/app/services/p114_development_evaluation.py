"""Aggregate-only consumed-development evaluation for P114 hypothesis lattices."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p114_hypothesis_lattice import FAULTS, LATTICE_SCHEMA_VERSION
from app.services.p114_re2_loader import TRUTH_SCHEMA_VERSION

REPORT_SCHEMA_VERSION = "p114.development_evaluation.v1"
GATE_SCHEMA_VERSION = "p114.candidate_gate_report.v1"
DEVELOPMENT_GATES = {
    "service_top5_recall_min": 0.85,
    "joint_candidate_recall_min": 0.70,
    "evidence_precision_min": 0.95,
    "per_fault_candidate_recall_min": 0.60,
    "zero_action_authority": True,
}


class P114DevelopmentEvaluationError(ValueError):
    """Raised when development evidence is incomplete or internally inconsistent."""


def evaluate_p114_development_lattices(
    truths: Sequence[Mapping[str, Any]],
    lattices: Sequence[Mapping[str, Any]],
    *,
    modality: str,
) -> dict[str, Any]:
    if modality not in {"fused", "metric", "log_template"}:
        raise P114DevelopmentEvaluationError("invalid_modality")
    truth_by_id = _index(truths, schema=TRUTH_SCHEMA_VERSION, label="truth")
    lattice_by_id = _index(lattices, schema=LATTICE_SCHEMA_VERSION, label="lattice")
    if set(truth_by_id) != set(lattice_by_id):
        raise P114DevelopmentEvaluationError("case_set_mismatch")
    rows = [_score_case(truth_by_id[case_id], lattice_by_id[case_id]) for case_id in sorted(truth_by_id)]
    aggregate = _aggregate(rows)
    by_fault = {fault: _aggregate([row for row in rows if row["fault"] == fault]) for fault in FAULTS}
    payload: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "benchmark_role": "consumed_development",
        "modality": modality,
        "summary": {"case_count": aggregate["case_count"]},
        "metrics": aggregate["metrics"],
        "by_fault": by_fault,
        "safety": {
            "truth_leak_count": 0,
            "executed_action_count": sum(int(row["executed_action_count"]) for row in rows),
            "action_authority_enabled_count": sum(int(row["action_authority_enabled_count"]) for row in rows),
            "invalid_evidence_reference_count": sum(int(row["invalid_evidence_count"]) for row in rows),
        },
    }
    payload["evaluation_hash"] = stable_hash(payload)
    return payload


def p114_candidate_gate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != REPORT_SCHEMA_VERSION or not _stable_hash_matches(report, "evaluation_hash"):
        raise P114DevelopmentEvaluationError("invalid_development_report")
    metrics = _mapping(report.get("metrics"))
    by_fault = _mapping(report.get("by_fault"))
    safety = _mapping(report.get("safety"))
    checks = {
        "service_top5_recall": _metric(metrics, "service_top5_recall") >= DEVELOPMENT_GATES["service_top5_recall_min"],
        "joint_candidate_recall": _metric(metrics, "joint_candidate_recall") >= DEVELOPMENT_GATES["joint_candidate_recall_min"],
        "evidence_precision": _metric(metrics, "evidence_precision") >= DEVELOPMENT_GATES["evidence_precision_min"],
        "zero_action_authority": int(safety.get("executed_action_count", -1)) == 0 and int(safety.get("action_authority_enabled_count", -1)) == 0,
        "zero_invalid_evidence": int(safety.get("invalid_evidence_reference_count", -1)) == 0,
    }
    for fault in FAULTS:
        fault_metrics = _mapping(_mapping(by_fault.get(fault)).get("metrics"))
        checks[f"{fault}_candidate_recall"] = _metric(fault_metrics, "joint_candidate_recall") >= DEVELOPMENT_GATES["per_fault_candidate_recall_min"]
    payload: dict[str, Any] = {
        "schema_version": GATE_SCHEMA_VERSION,
        "evaluation_hash": str(report.get("evaluation_hash", "")),
        "checks": checks,
        "passed": all(checks.values()),
    }
    payload["gate_report_hash"] = stable_hash(payload)
    return payload


def _score_case(truth: Mapping[str, Any], lattice: Mapping[str, Any]) -> dict[str, Any]:
    if not _stable_hash_matches(lattice, "lattice_hash"):
        raise P114DevelopmentEvaluationError("lattice_hash_mismatch")
    hidden = _mapping(truth.get("scorer_only_truth"))
    service = str(hidden.get("root_service", ""))
    fault = str(hidden.get("fault_type", ""))
    if not service or fault not in FAULTS:
        raise P114DevelopmentEvaluationError("invalid_scorer_truth")
    ranked_services = [str(item) for item in _sequence(lattice.get("ranked_services"))]
    ranked_faults = [str(item) for item in _sequence(lattice.get("ranked_faults"))]
    hypotheses = [_mapping(item) for item in _sequence(lattice.get("hypotheses"))]
    evidence_ids = set(str(item) for item in _sequence(lattice.get("evidence_node_ids")))
    cited = [str(evidence_id) for hypothesis in hypotheses for field in ("supporting_evidence_ids", "contradicting_evidence_ids") for evidence_id in _sequence(hypothesis.get(field))]
    invalid = sum(1 for evidence_id in cited if evidence_id not in evidence_ids)
    joint_candidate = any(str(item.get("service", "")) == service and str(item.get("fault", "")) == fault for item in hypotheses)
    return {
        "fault": fault,
        "service_top1_num": int(bool(ranked_services) and ranked_services[0] == service),
        "service_top3_num": int(service in ranked_services[:3]),
        "service_top5_num": int(service in ranked_services[:5]),
        "fault_accuracy_num": int(bool(ranked_faults) and ranked_faults[0] == fault),
        "joint_candidate_num": int(joint_candidate),
        "valid_evidence_num": len(cited) - invalid,
        "evidence_den": len(cited),
        "invalid_evidence_count": invalid,
        "executed_action_count": len(_sequence(lattice.get("executed_actions"))),
        "action_authority_enabled_count": int(lattice.get("action_contract_status") != "disabled"),
    }


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    return {
        "case_count": count,
        "metrics": {
            "service_top1": _rate(sum(int(row["service_top1_num"]) for row in rows), count),
            "service_top3": _rate(sum(int(row["service_top3_num"]) for row in rows), count),
            "service_top5_recall": _rate(sum(int(row["service_top5_num"]) for row in rows), count),
            "fault_accuracy": _rate(sum(int(row["fault_accuracy_num"]) for row in rows), count),
            "joint_candidate_recall": _rate(sum(int(row["joint_candidate_num"]) for row in rows), count),
            "evidence_precision": _rate(
                sum(int(row["valid_evidence_num"]) for row in rows),
                sum(int(row["evidence_den"]) for row in rows),
            ),
        },
    }


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "value": round(numerator / denominator, 6) if denominator else 0.0,
        "numerator": numerator,
        "denominator": denominator,
    }


def _index(items: Sequence[Mapping[str, Any]], *, schema: str, label: str) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if item.get("schema_version") != schema:
            raise P114DevelopmentEvaluationError(f"invalid_{label}_schema")
        case_id = str(item.get("case_id", ""))
        if not case_id:
            raise P114DevelopmentEvaluationError(f"missing_{label}_case")
        if case_id in indexed:
            raise P114DevelopmentEvaluationError(f"duplicate_{label}_case")
        indexed[case_id] = item
    if not indexed:
        raise P114DevelopmentEvaluationError(f"empty_{label}_set")
    return indexed


def _metric(metrics: Mapping[str, Any], key: str) -> float:
    value = _mapping(metrics.get(key)).get("value")
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise P114DevelopmentEvaluationError(f"missing_metric:{key}")
    return float(value)


def _stable_hash_matches(value: Mapping[str, Any], field: str) -> bool:
    submitted = str(value.get(field, ""))
    return bool(submitted) and submitted == stable_hash({key: item for key, item in value.items() if key != field})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()
