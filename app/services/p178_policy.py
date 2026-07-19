"""P178 shadow-only prevention policy and counterfactual scoring substrate."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p147_p152_contracts import stable_hash

PRECURSOR_WINDOW_SCHEMA_VERSION = "p178.precursor_window.v1"
PREVENTION_DECISION_SCHEMA_VERSION = "p178.prevention_decision.v1"
EVALUATED_DECISION_SCHEMA_VERSION = "p178.evaluated_prevention_decision.v1"
COUNTERFACTUAL_REPORT_SCHEMA_VERSION = "p178.counterfactual_report.v1"

ALLOWED_TAXONOMIES = frozenset({"actionable_precursor", "healthy", "noisy_non_actionable", "natural_recovery", "ood"})
ALLOWED_DECISIONS = frozenset({"act", "no-act", "seek-evidence"})
ALLOWED_BLAST_RADIUS = frozenset({"none", "single_service"})
FALSE_PREVENTION_ALPHA = 0.05
FALSE_PREVENTION_RATE_GATE = 0.01


class P178PolicyError(ValueError):
    """Raised when a P178 prevention decision cannot be safely evaluated."""


def validate_precursor_window(window: Mapping[str, Any]) -> dict[str, Any]:
    if window.get("schema_version") != PRECURSOR_WINDOW_SCHEMA_VERSION:
        raise P178PolicyError("invalid_precursor_window_schema")
    taxonomy = _text(window.get("taxonomy"), "taxonomy")
    if taxonomy not in ALLOWED_TAXONOMIES:
        raise P178PolicyError("unknown_precursor_taxonomy")
    lead_time_seconds = _non_negative_int(window.get("lead_time_seconds"), "lead_time_seconds")
    classes = _optional_text_list(window.get("expected_prevention_classes", []), "expected_prevention_classes")
    non_actionable = _bool(window.get("non_actionable_signal"), "non_actionable_signal")
    if taxonomy == "actionable_precursor":
        if non_actionable or not classes or lead_time_seconds <= 0:
            raise P178PolicyError("invalid_actionable_precursor_window")
    elif classes and not non_actionable:
        raise P178PolicyError("invalid_non_actionable_window")

    result: dict[str, Any] = {
        "schema_version": PRECURSOR_WINDOW_SCHEMA_VERSION,
        "window_id": _text(window.get("window_id"), "window_id"),
        "family": _text(window.get("family"), "family"),
        "service": _text(window.get("service"), "service"),
        "taxonomy": taxonomy,
        "lead_time_seconds": lead_time_seconds,
        "expected_prevention_classes": classes,
        "non_actionable_signal": non_actionable,
        "p177_trace_id": _text(window.get("p177_trace_id"), "p177_trace_id"),
        "p177_evidence_ids": _text_list(window.get("p177_evidence_ids"), "p177_evidence_ids"),
    }
    result["window_hash"] = stable_hash({key: value for key, value in result.items() if key != "window_hash"})
    return result


def evaluate_decision(
    decision: Mapping[str, Any],
    *,
    precursor_window: Mapping[str, Any],
    evidence_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if decision.get("schema_version") != PREVENTION_DECISION_SCHEMA_VERSION:
        raise P178PolicyError("invalid_prevention_decision_schema")
    if decision.get("window_id") != precursor_window.get("window_id"):
        raise P178PolicyError("decision_window_mismatch")
    decision_type = _text(decision.get("decision_type"), "decision_type")
    if decision_type not in ALLOWED_DECISIONS:
        raise P178PolicyError("invalid_decision_type")

    confidence = _probability(decision.get("confidence"), "confidence")
    expected_benefit = _probability(decision.get("expected_benefit"), "expected_benefit")
    possible_harm = _probability(decision.get("possible_harm"), "possible_harm")
    citations = _text_list(decision.get("cited_evidence_ids"), "cited_evidence_ids")
    cited_records = _validated_citations(citations, evidence_records)
    source_classes = {record["source_class"] for record in cited_records}
    safety = _validate_safety(decision.get("safety"))

    taxonomy = _text(precursor_window.get("taxonomy"), "taxonomy")
    expected_classes = _optional_text_list(precursor_window.get("expected_prevention_classes", []), "expected_prevention_classes")
    prevention_class = decision.get("prevention_class")
    if prevention_class is not None and not isinstance(prevention_class, str):
        raise P178PolicyError("invalid_prevention_class")

    eligible = False
    stop_reason = decision_type
    unsupported = False
    unsafe = False
    if decision_type == "act":
        if taxonomy != "actionable_precursor":
            raise P178PolicyError("unsupported_prevention_proposal")
        if prevention_class not in expected_classes:
            raise P178PolicyError("unsupported_prevention_proposal")
        if len(source_classes) < 2:
            raise P178PolicyError("source_diversity_required")
        if not safety["supported"] or not safety["reversible"] or safety["mutation_authority"] != "none" or safety["blast_radius"] not in ALLOWED_BLAST_RADIUS:
            raise P178PolicyError("unsafe_action_advice")
        eligible = True
        stop_reason = "eligible_shadow_prevention"
    elif decision_type == "no-act":
        if not _text(decision.get("abstention_reason"), "abstention_reason"):
            raise P178PolicyError("missing_abstention_reason")
        stop_reason = "non_actionable_signal" if bool(precursor_window.get("non_actionable_signal")) else "abstain"
    else:
        if not _text(decision.get("escalation_reason"), "escalation_reason"):
            raise P178PolicyError("missing_escalation_reason")
        stop_reason = "seek_more_evidence"

    result: dict[str, Any] = {
        "schema_version": EVALUATED_DECISION_SCHEMA_VERSION,
        "window_id": precursor_window["window_id"],
        "decision_type": decision_type,
        "prevention_class": prevention_class,
        "eligible": eligible,
        "stop_reason": stop_reason,
        "cited_evidence_ids": citations,
        "source_classes": sorted(source_classes),
        "citation_confidence": 1.0,
        "confidence": confidence,
        "expected_benefit": expected_benefit,
        "possible_harm": possible_harm,
        "counterfactual_action": decision.get("counterfactual_action"),
        "action_safety": safety,
        "unsupported_prevention_proposal": unsupported,
        "unsafe_action_advice": unsafe,
        "auto_approval": False,
        "production_mutation": False,
    }
    result["decision_hash"] = stable_hash({key: value for key, value in result.items() if key != "decision_hash"})
    return result


def false_prevention_one_sided_exact_95ub(*, false_prevention_count: int, negative_window_count: int) -> float:
    if false_prevention_count < 0 or negative_window_count <= 0 or false_prevention_count > negative_window_count:
        raise P178PolicyError("invalid_false_prevention_denominator")
    if false_prevention_count == negative_window_count:
        return 1.0
    if false_prevention_count == 0:
        return 1.0 - FALSE_PREVENTION_ALPHA ** (1.0 / negative_window_count)

    low = 0.0
    high = 1.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if _binomial_cdf(false_prevention_count, negative_window_count, mid) > FALSE_PREVENTION_ALPHA:
            low = mid
        else:
            high = mid
    return high


def score_counterfactual_outcomes(
    *,
    rows: Sequence[Mapping[str, Any]],
    false_prevention_count: int,
    negative_window_count: int,
) -> dict[str, Any]:
    if not rows:
        raise P178PolicyError("missing_counterfactual_rows")
    deltas: list[float] = []
    by_family: dict[str, list[float]] = {}
    operator_interruptions = 0
    for row in rows:
        family = _text(row.get("family"), "family")
        delta = _probability(row.get("candidate_utility"), "candidate_utility") - _probability(row.get("baseline_utility"), "baseline_utility")
        deltas.append(delta)
        by_family.setdefault(family, []).append(delta)
        if _bool(row.get("operator_interrupted"), "operator_interrupted"):
            operator_interruptions += 1

    point_rate = false_prevention_count / negative_window_count
    upper_bound = false_prevention_one_sided_exact_95ub(false_prevention_count=false_prevention_count, negative_window_count=negative_window_count)
    report: dict[str, Any] = {
        "schema_version": COUNTERFACTUAL_REPORT_SCHEMA_VERSION,
        "row_count": len(rows),
        "counterfactual_metrics": {
            "mean_net_prevention_utility": sum(deltas) / len(deltas),
            "by_family": {family: {"mean_net_prevention_utility": sum(values) / len(values), "window_count": len(values)} for family, values in sorted(by_family.items())},
        },
        "fatigue_metrics": {
            "operator_interruption_count": operator_interruptions,
            "operator_interruption_rate": operator_interruptions / len(rows),
            "prevention_proposal_count": sum(1 for row in rows if row.get("decision_type") == "act"),
            "seek_evidence_count": sum(1 for row in rows if row.get("decision_type") == "seek-evidence"),
        },
        "false_prevention_gate": {
            "false_prevention_count": false_prevention_count,
            "negative_window_count": negative_window_count,
            "healthy_false_prevention_rate": point_rate,
            "healthy_false_prevention_one_sided_exact_95ub": upper_bound,
            "passed": point_rate <= FALSE_PREVENTION_RATE_GATE and upper_bound <= FALSE_PREVENTION_RATE_GATE,
        },
    }
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    return report


def _validated_citations(citations: Sequence[str], evidence_records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(citations) != len(set(citations)):
        raise P178PolicyError("duplicate_citation")
    records = {_text(record.get("evidence_id"), "evidence_id"): record for record in evidence_records}
    cited: list[dict[str, Any]] = []
    for citation in citations:
        record = records.get(citation)
        if record is None:
            raise P178PolicyError("unsupported_citation")
        if record.get("fresh") is not True:
            raise P178PolicyError("stale_citation")
        if record.get("read_only") is not True:
            raise P178PolicyError("non_read_only_citation")
        source_class = _text(record.get("source_class"), "source_class")
        cited.append({"evidence_id": citation, "source_class": source_class})
    return cited


def _validate_safety(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise P178PolicyError("invalid_safety")
    safety = {
        "supported": _bool(value.get("supported"), "safety.supported"),
        "reversible": _bool(value.get("reversible"), "safety.reversible"),
        "blast_radius": _text(value.get("blast_radius"), "safety.blast_radius"),
        "mutation_authority": _text(value.get("mutation_authority"), "safety.mutation_authority"),
    }
    if safety["blast_radius"] not in {"none", "single_service", "multi_service", "global"}:
        raise P178PolicyError("invalid_blast_radius")
    if safety["mutation_authority"] not in {"none", "staging", "production"}:
        raise P178PolicyError("invalid_mutation_authority")
    return safety


def _binomial_cdf(successes: int, trials: int, probability: float) -> float:
    if probability <= 0:
        return 1.0
    if probability >= 1:
        return 0.0 if successes < trials else 1.0
    total = 0.0
    for observed in range(successes + 1):
        total += math.comb(trials, observed) * (probability**observed) * ((1.0 - probability) ** (trials - observed))
    return total


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P178PolicyError(f"invalid_{field}")
    return value


def _text_list(value: Any, field: str) -> list[str]:
    result = _optional_text_list(value, field)
    if not result:
        raise P178PolicyError(f"invalid_{field}")
    return result


def _optional_text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P178PolicyError(f"invalid_{field}")
    result = [item for item in value if isinstance(item, str) and item]
    if len(result) != len(value):
        raise P178PolicyError(f"invalid_{field}")
    return result


def _probability(value: Any, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= float(value) <= 1:
        raise P178PolicyError(f"invalid_{field}")
    return float(value)


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise P178PolicyError(f"invalid_{field}")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise P178PolicyError(f"invalid_{field}")
    return value
