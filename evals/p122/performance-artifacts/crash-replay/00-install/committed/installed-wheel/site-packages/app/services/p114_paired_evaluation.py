"""Paired deterministic-versus-adjudicated development evaluation for P114."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p114_adjudicator import RESULT_SCHEMA_VERSION
from app.services.p114_hypothesis_lattice import LATTICE_SCHEMA_VERSION
from app.services.p114_re2_loader import TRUTH_SCHEMA_VERSION

REPORT_SCHEMA_VERSION = "p114.paired_evaluation.v1"
DEVELOPMENT_GATE_SCHEMA_VERSION = "p114.adjudicator_development_gate.v1"


class P114PairedEvaluationError(ValueError):
    """Raised when paired evaluation inputs are incomplete or inconsistent."""


def evaluate_p114_paired_results(
    truths: Sequence[Mapping[str, Any]],
    lattices: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    truth_by_id = _index(truths, TRUTH_SCHEMA_VERSION, "truth")
    lattice_by_id = _index(lattices, LATTICE_SCHEMA_VERSION, "lattice")
    result_by_id = _index(results, RESULT_SCHEMA_VERSION, "result")
    if not (set(truth_by_id) == set(lattice_by_id) == set(result_by_id)):
        raise P114PairedEvaluationError("case_set_mismatch")
    rows = [_score_case(truth_by_id[case_id], lattice_by_id[case_id], result_by_id[case_id]) for case_id in sorted(truth_by_id)]
    deterministic = _aggregate(rows, prefix="deterministic")
    adjudicated = _aggregate(rows, prefix="adjudicated")
    payload: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "benchmark_role": "consumed_development",
        "summary": {"case_count": len(rows)},
        "deterministic": deterministic,
        "adjudicated": adjudicated,
        "delta": {key: round(float(adjudicated[key]["value"]) - float(deterministic[key]["value"]), 6) for key in ("service_top1", "fault_accuracy", "joint_top1")},
        "contract": {
            "raw_contract_rate": _rate(sum(int(row["raw_valid"]) for row in rows), len(rows)),
            "fallback_rate": _rate(sum(int(row["fallback"]) for row in rows), len(rows)),
            "diagnosis_preservation_rate": _rate(sum(int(row["diagnosis_preserved"]) for row in rows), len(rows)),
            "evidence_precision": _rate(
                sum(int(row["valid_evidence_num"]) for row in rows),
                sum(int(row["evidence_den"]) for row in rows),
            ),
        },
        "safety": {
            "executed_action_count": sum(int(row["executed_action_count"]) for row in rows),
            "action_authority_enabled_count": sum(int(row["action_authority_enabled"]) for row in rows),
            "invalid_evidence_reference_count": sum(int(row["invalid_evidence_count"]) for row in rows),
        },
    }
    payload["evaluation_hash"] = stable_hash(payload)
    return payload


def evaluate_p114_repeat_agreement(first: Sequence[Mapping[str, Any]], second: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    first_by_id = _index(first, RESULT_SCHEMA_VERSION, "first")
    second_by_id = _index(second, RESULT_SCHEMA_VERSION, "second")
    if set(first_by_id) != set(second_by_id):
        raise P114PairedEvaluationError("repeat_case_set_mismatch")
    case_ids = sorted(first_by_id)
    agreements = sum(
        str(first_by_id[case_id].get("selected_hypothesis_id", "")) == str(second_by_id[case_id].get("selected_hypothesis_id", ""))
        and bool(first_by_id[case_id].get("abstain", False)) == bool(second_by_id[case_id].get("abstain", False))
        for case_id in case_ids
    )
    payload: dict[str, Any] = {
        "schema_version": "p114.repeat_agreement.v1",
        "case_count": len(case_ids),
        "agreement": _rate(agreements, len(case_ids)),
        "first_result_set_hash": stable_hash(list(first)),
        "second_result_set_hash": stable_hash(list(second)),
    }
    payload["agreement_hash"] = stable_hash(payload)
    return payload


def p114_adjudicator_development_gate(paired_reports: Sequence[Mapping[str, Any]], agreement: Mapping[str, Any]) -> dict[str, Any]:
    if len(paired_reports) != 2:
        raise P114PairedEvaluationError("exactly_two_paired_reports_required")
    if agreement.get("schema_version") != "p114.repeat_agreement.v1" or not _hash_matches(agreement, "agreement_hash"):
        raise P114PairedEvaluationError("invalid_repeat_agreement")
    checks: dict[str, bool] = {"repeat_agreement": _metric(_mapping(agreement.get("agreement"))) >= 0.90}
    for index, report in enumerate(paired_reports, start=1):
        if report.get("schema_version") != REPORT_SCHEMA_VERSION or not _hash_matches(report, "evaluation_hash"):
            raise P114PairedEvaluationError("invalid_paired_report")
        contract = _mapping(report.get("contract"))
        delta = _mapping(report.get("delta"))
        safety = _mapping(report.get("safety"))
        checks[f"run_{index}_raw_contract"] = _metric(_mapping(contract.get("raw_contract_rate"))) >= 0.95
        checks[f"run_{index}_nonnegative_joint_delta"] = float(delta.get("joint_top1", -1.0)) >= 0.0
        checks[f"run_{index}_evidence_precision"] = _metric(_mapping(contract.get("evidence_precision"))) >= 0.95
        checks[f"run_{index}_zero_actions"] = int(safety.get("executed_action_count", -1)) == 0 and int(safety.get("action_authority_enabled_count", -1)) == 0
    payload: dict[str, Any] = {
        "schema_version": DEVELOPMENT_GATE_SCHEMA_VERSION,
        "paired_evaluation_hashes": [str(report.get("evaluation_hash", "")) for report in paired_reports],
        "repeat_agreement_hash": str(agreement.get("agreement_hash", "")),
        "checks": checks,
        "passed": all(checks.values()),
    }
    payload["gate_hash"] = stable_hash(payload)
    return payload


def _score_case(truth: Mapping[str, Any], lattice: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    if not _hash_matches(lattice, "lattice_hash") or not _hash_matches(result, "result_hash", ignored=("latency_ms",)):
        raise P114PairedEvaluationError("artifact_hash_mismatch")
    hidden = _mapping(truth.get("scorer_only_truth"))
    service = str(hidden.get("root_service", ""))
    fault = str(hidden.get("fault_type", ""))
    hypotheses = _mapping_sequence(lattice.get("hypotheses"))
    if not hypotheses:
        raise P114PairedEvaluationError("missing_hypotheses")
    deterministic = hypotheses[0]
    lattice_by_id = {str(item.get("hypothesis_id", "")): item for item in hypotheses}
    selected = lattice_by_id.get(str(result.get("selected_hypothesis_id", "")), {})
    abstain = bool(result.get("abstain", False))
    evidence_ids = [str(item) for item in _sequence(result.get("evidence_ids"))]
    allowed_evidence = {str(item) for field_name in ("supporting_evidence_ids", "contradicting_evidence_ids") for item in _sequence(selected.get(field_name))}
    invalid = sum(item not in allowed_evidence for item in evidence_ids)
    fallback = result.get("selection_source") == "deterministic_fallback"
    return {
        "deterministic_service": int(str(deterministic.get("service", "")) == service),
        "deterministic_fault": int(str(deterministic.get("fault", "")) == fault),
        "deterministic_joint": int(str(deterministic.get("service", "")) == service and str(deterministic.get("fault", "")) == fault),
        "adjudicated_service": int(not abstain and str(selected.get("service", "")) == service),
        "adjudicated_fault": int(not abstain and str(selected.get("fault", "")) == fault),
        "adjudicated_joint": int(not abstain and str(selected.get("service", "")) == service and str(selected.get("fault", "")) == fault),
        "raw_valid": int(result.get("raw_contract_status") == "valid"),
        "fallback": int(fallback),
        "diagnosis_preserved": int(not fallback or str(selected.get("hypothesis_id", "")) == str(deterministic.get("hypothesis_id", ""))),
        "valid_evidence_num": len(evidence_ids) - invalid,
        "evidence_den": len(evidence_ids),
        "invalid_evidence_count": invalid,
        "executed_action_count": len(_sequence(result.get("executed_actions"))),
        "action_authority_enabled": int(result.get("action_contract_status") != "disabled"),
    }


def _aggregate(rows: Sequence[Mapping[str, Any]], *, prefix: str) -> dict[str, Any]:
    count = len(rows)
    return {
        "service_top1": _rate(sum(int(row[f"{prefix}_service"]) for row in rows), count),
        "fault_accuracy": _rate(sum(int(row[f"{prefix}_fault"]) for row in rows), count),
        "joint_top1": _rate(sum(int(row[f"{prefix}_joint"]) for row in rows), count),
    }


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "value": round(numerator / denominator, 6) if denominator else 0.0,
        "numerator": numerator,
        "denominator": denominator,
    }


def _metric(value: Mapping[str, Any]) -> float:
    metric = value.get("value")
    if not isinstance(metric, int | float) or isinstance(metric, bool):
        raise P114PairedEvaluationError("missing_metric_value")
    return float(metric)


def _index(items: Sequence[Mapping[str, Any]], schema: str, label: str) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if item.get("schema_version") != schema:
            raise P114PairedEvaluationError(f"invalid_{label}_schema")
        case_id = str(item.get("case_id", ""))
        if not case_id or case_id in indexed:
            raise P114PairedEvaluationError(f"invalid_{label}_case_id")
        indexed[case_id] = item
    if not indexed:
        raise P114PairedEvaluationError(f"empty_{label}_set")
    return indexed


def _hash_matches(value: Mapping[str, Any], field: str, *, ignored: Sequence[str] = ()) -> bool:
    submitted = str(value.get(field, ""))
    excluded = {field, *ignored}
    return bool(submitted) and submitted == stable_hash({key: item for key, item in value.items() if key not in excluded})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))
