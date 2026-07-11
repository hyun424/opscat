"""Outcome-grounded P115 scorer using hash-bound P116 paired records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash


class P115EvaluationError(ValueError):
    """Raised when final scoring cannot safely consume its sealed inputs."""


def evaluate_p115_decisions(
    labels: Sequence[Mapping[str, Any]],
    *,
    outcome_contracts: Sequence[Mapping[str, Any]],
    p116_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    contracts = _index_unique(outcome_contracts, "case_id", "duplicate_outcome_contract")
    candidates = _index_unique(labels, "case_id", "duplicate_candidate_label")
    records = _index_records(p116_records)
    metric_counts: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    rows: list[dict[str, Any]] = []
    missing_record_count = 0
    for case_id, contract in sorted(contracts.items()):
        label = candidates.get(case_id)
        if label is None:
            raise P115EvaluationError(f"missing_candidate_label:{case_id}")
        action_records = _mapping(contract.get("action_records"))
        measured: dict[str, Mapping[str, Any]] = {}
        for action_id, record_hash in action_records.items():
            record = records.get(str(record_hash))
            if record is None:
                missing_record_count += 1
            else:
                if str(record.get("case_id", "")) != case_id:
                    raise P115EvaluationError("cross_case_outcome_binding")
                measured[str(action_id)] = record

        expected_decision, optimal = _expected_decision(contract, measured)
        decision = str(label.get("decision", ""))
        selected_ids = [str(item) for item in _sequence(label.get("action_pack_ids"))]
        selected_record = measured.get(selected_ids[0]) if selected_ids else None
        selected_harmful = _is_harmful(selected_record) if selected_record else False
        selected_lift = _lift(selected_record) if selected_record else 0.0
        cited_evidence = {str(item) for item in _sequence(label.get("evidence_ids"))}
        allowed_evidence = {str(item) for item in _sequence(contract.get("visible_evidence_ids"))}
        exact = decision == expected_decision and (decision != "act" or bool(selected_ids) and selected_ids[0] in optimal)
        _add(metric_counts, "optimal_action_top1", exact)
        _add(metric_counts, "optimal_action_top3", decision == expected_decision and (decision != "act" or bool(set(selected_ids[:3]) & set(optimal))))
        _add(metric_counts, "harmful_action_selection_rate", selected_harmful)
        unnecessary = decision == "act" and expected_decision != "act"
        _add(metric_counts, "unnecessary_action_selection_rate", unnecessary)
        _add_applicable(metric_counts, "correct_no_action_rate", expected_decision == "no_action", decision == "no_action")
        _add_applicable(metric_counts, "correct_investigate_more_rate", expected_decision == "investigate_more", decision == "investigate_more")
        _add_applicable(metric_counts, "correct_escalation_rate", expected_decision == "escalate", decision == "escalate")
        _add(metric_counts, "evidence_citation_validity", bool(cited_evidence) and bool(allowed_evidence) and cited_evidence <= allowed_evidence)
        if decision == "act":
            _add(metric_counts, "prerequisite_compliance", _all_checks(label.get("prerequisite_checks"), expected=True))
            _add(metric_counts, "contraindication_avoidance", _all_checks(label.get("contraindication_checks"), expected=False))
        else:
            metric_counts["prerequisite_compliance"]
            metric_counts["contraindication_avoidance"]
        _add(metric_counts, "validation_completeness", bool(_mapping(label.get("validation_plan"))))
        _add(metric_counts, "rollback_completeness", bool(_mapping(label.get("rollback_plan"))))
        metric_counts["outcome_weighted_utility"][0] += selected_lift
        metric_counts["outcome_weighted_utility"][1] += 1.0
        rows.append(
            {
                "case_id": case_id,
                "family": str(contract.get("family", "")),
                "partition": str(contract.get("partition", "")),
                "correct": exact,
            }
        )
    outcome_qualified = missing_record_count == 0 and bool(contracts)
    report: dict[str, Any] = {
        "schema_version": "p115.paired_score.v1",
        "release_status": "p115_outcome_qualified" if outcome_qualified else "p115_contract_ready",
        "outcome_qualified": outcome_qualified,
        "missing_p116_record_count": missing_record_count,
        "metrics": {name: _metric(values) for name, values in sorted(metric_counts.items())},
        "partitions": _partition_metrics(rows),
        "case_count": len(rows),
        "authority": {"action_execution_count": 0, "production_mutation_count": 0, "credential_access_count": 0},
    }
    for required in (
        "optimal_action_top1",
        "optimal_action_top3",
        "harmful_action_selection_rate",
        "unnecessary_action_selection_rate",
        "correct_no_action_rate",
        "correct_investigate_more_rate",
        "correct_escalation_rate",
    ):
        report["metrics"].setdefault(required, _metric([0.0, 0.0]))
    report["report_hash"] = stable_hash(report)
    return report


def _expected_decision(contract: Mapping[str, Any], measured: Mapping[str, Mapping[str, Any]]) -> tuple[str, list[str]]:
    if contract.get("human_authorized_only") is True:
        return "escalate", []
    if contract.get("evidence_sufficient") is not True:
        return "investigate_more", []
    if any(bool(_mapping(record.get("causal_attribution")).get("natural_recovery_observed")) for record in measured.values()):
        return "no_action", []
    qualified = [(action_id, _lift(record)) for action_id, record in measured.items() if bool(_mapping(record.get("causal_attribution")).get("qualified")) and not _is_harmful(record)]
    if not qualified:
        return "no_action", []
    qualified.sort(key=lambda item: (-item[1], item[0]))
    return "act", [action_id for action_id, _value in qualified]


def _index_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in records:
        record_hash = str(record.get("record_hash", ""))
        if record_hash != stable_hash({key: value for key, value in record.items() if key != "record_hash"}):
            raise P115EvaluationError("p116_record_hash_mismatch")
        if record_hash in indexed:
            raise P115EvaluationError("duplicate_p116_record")
        indexed[record_hash] = record
    return indexed


def _index_unique(items: Sequence[Mapping[str, Any]], key: str, error: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        identifier = str(item.get(key, ""))
        if not identifier:
            raise P115EvaluationError(f"missing_{key}")
        if identifier in result:
            raise P115EvaluationError(f"{error}:{identifier}")
        result[identifier] = item
    return result


def _is_harmful(record: Mapping[str, Any] | None) -> bool:
    if record is None:
        return False
    return bool(_mapping(_mapping(record.get("collateral_harm")).get("selected_action")).get("harmful"))


def _lift(record: Mapping[str, Any] | None) -> float:
    if record is None:
        return 0.0
    raw = _mapping(record.get("causal_attribution")).get("selected_utility_lift_over_no_action", 0.0)
    return float(raw) if isinstance(raw, int | float) and not isinstance(raw, bool) else 0.0


def _all_checks(value: Any, *, expected: bool) -> bool:
    checks = _mapping(value)
    return bool(checks) and all(item is expected for item in checks.values())


def _add(counts: dict[str, list[float]], name: str, passed: bool) -> None:
    counts[name][0] += float(passed)
    counts[name][1] += 1.0


def _add_applicable(counts: dict[str, list[float]], name: str, applicable: bool, passed: bool) -> None:
    if applicable:
        _add(counts, name, passed)
    else:
        counts[name]


def _metric(values: Sequence[float]) -> dict[str, Any]:
    numerator, denominator = values
    return {
        "numerator": int(numerator) if numerator.is_integer() else round(numerator, 6),
        "denominator": int(denominator),
        "value": round(numerator / denominator, 6) if denominator else None,
    }


def _partition_metrics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["partition"]), str(row["family"]))].append(row)
    return [
        {
            "partition": partition,
            "family": family,
            "correct": sum(bool(row["correct"]) for row in group),
            "denominator": len(group),
            "value": round(sum(bool(row["correct"]) for row in group) / len(group), 6),
        }
        for (partition, family), group in sorted(groups.items())
    ]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


__all__ = ["P115EvaluationError", "evaluate_p115_decisions"]
