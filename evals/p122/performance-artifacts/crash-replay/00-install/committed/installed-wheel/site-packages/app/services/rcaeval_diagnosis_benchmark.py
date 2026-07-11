"""P109 RCAEval diagnosis benchmark metrics."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.rcaeval_adapter import RCAEvalCase, read_normalized_jsonl


@dataclass(frozen=True)
class DiagnosisPrediction:
    case_id: str
    ranked_services: tuple[str, ...]
    fault_type: str | None = None
    evidence_refs: tuple[str, ...] = ()
    abstain: bool = False
    latency_ms: int = 0
    tool_call_count: int = 0
    candidate_context: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DiagnosisBenchmarkReport:
    cases: tuple[Mapping[str, Any], ...]
    predictions: Mapping[str, DiagnosisPrediction]
    metrics: Mapping[str, Mapping[str, Any]]
    by_cell: tuple[Mapping[str, Any], ...]
    safety: Mapping[str, int]
    notes: tuple[str, ...]

    @property
    def truth_eligible_case_count(self) -> int:
        return sum(1 for case in self.cases if _truth(case) is not None)

    @property
    def real_telemetry_smoke_only(self) -> bool:
        return any(bool(case.get("real_telemetry_smoke_only")) for case in self.cases)

    @property
    def release_qualified(self) -> bool:
        return (
            bool(self.cases)
            and self.truth_eligible_case_count == len(self.cases)
            and all(bool(case.get("release_qualifying_truth")) for case in self.cases)
            and not self.safety.get("candidate_context_truth_leak_count", 0)
            and not self.notes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "p109.rcaeval_diagnosis_report.v1",
            "summary": {
                "case_count": len(self.cases),
                "truth_eligible_case_count": self.truth_eligible_case_count,
                "real_telemetry_smoke_only": self.real_telemetry_smoke_only,
                "release_qualified": self.release_qualified,
            },
            "metrics": {key: dict(value) for key, value in self.metrics.items()},
            "by_cell": [_stable(cell) for cell in self.by_cell],
            "safety": dict(self.safety),
            "notes": list(self.notes),
            "release_qualified": self.release_qualified,
            "status": "real_telemetry_smoke_only" if self.real_telemetry_smoke_only and self.truth_eligible_case_count == 0 else ("release_qualified" if self.release_qualified else "unevaluable"),
            "overall": _legacy_overall(self.metrics),
            "by_fault_family": _group_to_mapping(self.by_cell, "fault_family"),
            "by_system": _group_to_mapping(self.by_cell, "system_id"),
        }


def evaluate_diagnosis_predictions(cases: Sequence[RCAEvalCase | Mapping[str, Any]], predictions: Sequence[DiagnosisPrediction]) -> DiagnosisBenchmarkReport:
    case_maps = tuple(_case_to_mapping(case) for case in cases)
    prediction_by_id = {prediction.case_id: prediction for prediction in predictions}
    safety_leaks = sum(1 for prediction in predictions if _contains_truth_leak(prediction.candidate_context))
    blocked = safety_leaks > 0

    truth_cases = [case for case in case_maps if _truth(case) is not None]
    if blocked:
        scored_cases: list[Mapping[str, Any]] = []
    else:
        scored_cases = truth_cases
    metrics = dict(_score_cases(scored_cases, prediction_by_id))
    if not blocked:
        metrics["abstention_accuracy"] = _score_abstention(case_maps, prediction_by_id)

    by_cell = tuple(_build_cells(case_maps, prediction_by_id, blocked=blocked))
    notes: list[str] = []
    if any(bool(case.get("real_telemetry_smoke_only")) for case in case_maps) and not truth_cases:
        notes.append("official_simple_data_has_no_official_truth")
    return DiagnosisBenchmarkReport(
        cases=case_maps,
        predictions=prediction_by_id,
        metrics=metrics,
        by_cell=by_cell,
        safety={"candidate_context_truth_leak_count": safety_leaks},
        notes=tuple(notes),
    )


def evaluate_rcaeval_diagnosis(
    normalized_jsonl: str | Path,
    candidate_outputs_jsonl: str | Path,
    *,
    required_fault_families: Sequence[str] = (),
) -> DiagnosisBenchmarkReport:
    cases = read_normalized_jsonl(normalized_jsonl)
    predictions = tuple(_prediction_from_mapping(row) for row in _read_jsonl(candidate_outputs_jsonl))
    report = evaluate_diagnosis_predictions(cases, predictions)
    if not required_fault_families:
        return report
    by_family = _group_to_mapping(report.by_cell, "fault_family")
    notes = list(report.notes)
    extra_cells = list(report.by_cell)
    for family in sorted(required_fault_families):
        cell = by_family.get(family)
        if cell is None or int(cell.get("case_count", 0)) == 0:
            notes.append(f"missing_or_zero_denominator:{family}")
            extra_cells.append(_empty_cell(family=family))
    return DiagnosisBenchmarkReport(
        cases=report.cases,
        predictions=report.predictions,
        metrics=report.metrics,
        by_cell=tuple(extra_cells),
        safety=report.safety,
        notes=tuple(notes),
    )


def _score_cases(cases: Sequence[Mapping[str, Any]], predictions: Mapping[str, DiagnosisPrediction]) -> Mapping[str, Mapping[str, Any]]:
    service_top1_num = 0
    service_top3_num = 0
    fault_type_num = 0
    evidence_num = 0
    evidence_den = 0
    unsupported_num = 0
    abstention_num = 0
    latency_num = 0
    tool_num = 0
    for case in cases:
        truth = _truth(case)
        if truth is None:
            continue
        prediction = predictions.get(str(case.get("case_id", "")))
        root_service = str(truth.get("root_service", ""))
        aliases = {root_service, *(str(item) for item in truth.get("acceptable_service_aliases", []))}
        expected_evidence = set(str(item) for item in truth.get("evidence_references", truth.get("evidence_refs", [])))
        if prediction is None:
            prediction = DiagnosisPrediction(case_id=str(case.get("case_id", "")), ranked_services=(), abstain=True)
        service_top1_num += int(bool(prediction.ranked_services) and prediction.ranked_services[0] in aliases)
        service_top3_num += int(any(service in aliases for service in prediction.ranked_services[:3]))
        fault_type_num += int(str(prediction.fault_type or "") == str(truth.get("fault_type", "")))
        evidence_num += sum(1 for ref in prediction.evidence_refs if ref in expected_evidence)
        evidence_den += len(prediction.evidence_refs)
        unsupported_num += sum(1 for ref in prediction.evidence_refs if ref not in expected_evidence)
        abstention_num += int(not prediction.abstain)
        latency_num += int(prediction.latency_ms)
        tool_num += int(prediction.tool_call_count)
    den = len(cases)
    return {
        "service_top1": _rate(service_top1_num, den),
        "service_top3": _rate(service_top3_num, den),
        "fault_type_accuracy": _rate(fault_type_num, den),
        "evidence_precision": _rate(evidence_num, evidence_den),
        "unsupported_claim_rate": _rate(unsupported_num, evidence_den),
        "abstention_accuracy": _rate(abstention_num, den),
        "mean_latency_ms": _mean(latency_num, den),
        "mean_tool_call_count": _mean(tool_num, den),
    }


def _score_abstention(cases: Sequence[Mapping[str, Any]], predictions: Mapping[str, DiagnosisPrediction]) -> Mapping[str, Any]:
    numerator = 0
    for case in cases:
        prediction = predictions.get(str(case.get("case_id", "")))
        truth_missing = _truth(case) is None
        abstained = True if prediction is None else prediction.abstain
        numerator += int(abstained == truth_missing or (not truth_missing and not abstained))
    return _rate(numerator, len(cases))


def _build_cells(cases: Sequence[Mapping[str, Any]], predictions: Mapping[str, DiagnosisPrediction], *, blocked: bool) -> list[Mapping[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        dataset = str(case.get("dataset_id", "rcaeval"))
        system_id = str(case.get("system_id", case.get("case_id", "unknown")))
        fault_family = str(case.get("fault_family", "truth_unavailable"))
        grouped[(dataset, system_id, fault_family)].append(case)
    cells: list[Mapping[str, Any]] = []
    for (dataset, system_id, fault_family), cell_cases in sorted(grouped.items()):
        truth_cases = [case for case in cell_cases if _truth(case) is not None]
        metrics = _score_cases([] if blocked else truth_cases, predictions)
        cells.append(
            {
                "dataset": dataset,
                "system_id": system_id,
                "fault_family": fault_family,
                "case_count": len(cell_cases),
                "truth_eligible_case_count": len(truth_cases),
                "status": "scored" if truth_cases and not blocked else "unevaluable",
                "metrics": metrics,
                **metrics,
            }
        )
    return cells


def _empty_cell(*, family: str) -> Mapping[str, Any]:
    metrics = _score_cases([], {})
    return {
        "dataset": "rcaeval",
        "system_id": "missing",
        "fault_family": family,
        "case_count": 0,
        "truth_eligible_case_count": 0,
        "status": "unevaluable",
        "metrics": metrics,
        **metrics,
    }


def _prediction_from_mapping(data: Mapping[str, Any]) -> DiagnosisPrediction:
    tool_calls = data.get("tool_calls", [])
    tool_count = len(tool_calls) if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes, bytearray)) else int(data.get("tool_call_count", 0) or 0)
    return DiagnosisPrediction(
        case_id=str(data.get("case_id", "")),
        ranked_services=tuple(str(item) for item in _sequence(data.get("ranked_root_services", data.get("ranked_services", [])))),
        fault_type=str(data.get("fault_type", "")),
        evidence_refs=tuple(str(item) for item in _sequence(data.get("evidence_references", data.get("evidence_refs", [])))),
        abstain=bool(data.get("abstained", data.get("abstain", False))),
        latency_ms=int(data.get("latency_ms", 0) or 0),
        tool_call_count=tool_count,
        candidate_context=data.get("candidate_context") if isinstance(data.get("candidate_context"), Mapping) else None,
    )


def _case_to_mapping(case: RCAEvalCase | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(case, RCAEvalCase):
        return case.to_normalized_dict()
    return case


def _truth(case: Mapping[str, Any]) -> Mapping[str, Any] | None:
    truth = case.get("scorer_only_truth")
    return truth if isinstance(truth, Mapping) else None


def _contains_truth_leak(value: Any) -> bool:
    if value is None:
        return False
    text = json.dumps(value, sort_keys=True).lower()
    return any(token in text for token in ("scorer_only", "root_service", "fault_type", "truth"))


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "value": (numerator / denominator if denominator else None)}


def _mean(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "value": (float(numerator) / denominator if denominator else None)}


def _read_jsonl(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            data = json.loads(line)
            if isinstance(data, Mapping):
                rows.append(data)
    return tuple(rows)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _legacy_overall(metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {
        "top1_service_accuracy": metrics["service_top1"],
        "top3_service_accuracy": metrics["service_top3"],
        "fault_type_accuracy": metrics["fault_type_accuracy"],
        "evidence_precision": metrics["evidence_precision"],
        "unsupported_claim_rate": metrics["unsupported_claim_rate"],
        "abstention_rate": _rate(
            metrics["abstention_accuracy"]["denominator"] - metrics["abstention_accuracy"]["numerator"],
            metrics["abstention_accuracy"]["denominator"],
        ),
        "mean_latency_ms": metrics["mean_latency_ms"],
        "mean_tool_calls": metrics["mean_tool_call_count"],
    }


def _group_to_mapping(cells: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[str(cell.get(key, "unknown"))].append(cell)
    result: dict[str, Mapping[str, Any]] = {}
    for group_key, group_cells in grouped.items():
        if len(group_cells) == 1:
            result[group_key] = group_cells[0]
            continue
        metrics = _merge_metrics([_mapping(cell.get("metrics")) for cell in group_cells])
        result[group_key] = {
            key: group_key,
            "case_count": sum(int(cell.get("case_count", 0)) for cell in group_cells),
            "truth_eligible_case_count": sum(int(cell.get("truth_eligible_case_count", 0)) for cell in group_cells),
            "status": "scored" if any(cell.get("status") == "scored" for cell in group_cells) else "unevaluable",
            "metrics": metrics,
            **metrics,
        }
    return result


def _merge_metrics(metrics_items: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    keys = ("service_top1", "service_top3", "fault_type_accuracy", "evidence_precision", "unsupported_claim_rate", "abstention_accuracy", "mean_latency_ms", "mean_tool_call_count")
    merged: dict[str, Mapping[str, Any]] = {}
    for key in keys:
        numerator = sum(int(_mapping(item.get(key)).get("numerator", 0)) for item in metrics_items)
        denominator = sum(int(_mapping(item.get(key)).get("denominator", 0)) for item in metrics_items)
        merged[key] = _mean(numerator, denominator) if key.startswith("mean_") else _rate(numerator, denominator)
    merged.update(_legacy_names(merged))
    return merged


def _legacy_names(metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {
        "top1_service_accuracy": metrics["service_top1"],
        "top3_service_accuracy": metrics["service_top3"],
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_stable(item) for item in value]
    return value
