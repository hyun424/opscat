"""Closed P137 hypothesis generation and deterministic integer ranking."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_contracts import HYPOTHESIS_SCHEMA_VERSION as CONTRACT_HYPOTHESIS_SCHEMA_VERSION

HYPOTHESIS_SCHEMA_VERSION = CONTRACT_HYPOTHESIS_SCHEMA_VERSION
SCORE_FORMULA_ID = "p137_integer_semantic_score_v1"
TIE_POLICY = "semantic_tuple_tie_yields_insufficient_evidence"

_ATOM_FIELDS = frozenset(
    {
        "schema_version",
        "atom_id",
        "promotion_record_hash",
        "promotion_key",
        "p136_entry_hash",
        "p135_bundle_hash",
        "source_id",
        "provider",
        "format",
        "signal_family",
        "system_id",
        "entity_ref_hash",
        "window",
        "signal_name",
        "numeric_value",
        "numeric_unit",
        "evidence_state",
        "severity_code",
        "metric_breach_code",
        "marker_code",
        "counter_signal_code",
        "state_reason_codes",
        "denominator_visible",
        "content_hash",
        "label_hashes",
        "topology_ref_hashes",
        "deploy_config_ref_hashes",
        "risk_flags",
        "redacted_preview_hash",
        "ordinal",
        "atom_hash",
    }
)
_EVIDENCE_STATES = frozenset({"promoted_success", "denominator_visible_failure", "context_only"})
_SEVERITIES = frozenset({"sev0", "sev1", "sev2", "sev3", "sev4", "unknown"})
_BREACH_CODES = frozenset({"none", "above_warning", "above_critical", "below_warning", "below_critical", "baseline_delta_warning", "baseline_delta_critical"})
_MARKER_CODES = frozenset({"none", "known_benign_schedule", "topology_noise", "deployment_marker", "topology_marker", "security_marker", "data_quality_marker"})
_COUNTER_CODES = frozenset({"none", "weak_counter_signal", "decisive_counter_signal"})
_STATE_REASONS = frozenset(
    {
        "parser_failure",
        "redaction_failure",
        "provenance_failure",
        "local_catalog_selectable",
        "p135_adapter_failure",
        "provider_authority_required",
        "network_authority_required",
        "credential_authority_required",
        "operator_authority_required",
        "action_authority_required",
    }
)
_EXTERNAL_REASONS = frozenset(
    {
        "provider_authority_required",
        "network_authority_required",
        "credential_authority_required",
        "operator_authority_required",
        "action_authority_required",
    }
)
_DEFAULT_LIMITS = {
    "max_hypotheses": 64,
    "max_support_edges_per_hypothesis": 64,
    "max_contradiction_edges_per_hypothesis": 64,
    "max_missing_evidence_items_per_hypothesis": 64,
    "correlation_window_seconds": 900,
}


class P137HypothesisError(ValueError):
    """Raised when P137 hypothesis construction must fail closed."""


def rank_incident_hypotheses(
    incident: Mapping[str, Any],
    atoms: Sequence[Mapping[str, Any]],
    *,
    now: str = "1970-01-01T00:00:00Z",
    limits: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    effective_limits = _limits(limits)
    validated_atoms = [_validate_atom(atom) for atom in atoms]
    if len(validated_atoms) > effective_limits["max_hypotheses"]:
        raise P137HypothesisError("hypothesis_budget_exceeded")

    hypotheses = [
        _build_hypothesis(
            incident,
            atom,
            sequence=index,
            now=now,
            correlation_window_seconds=effective_limits["correlation_window_seconds"],
        )
        for index, atom in enumerate(sorted(validated_atoms, key=lambda item: str(item["atom_hash"])), start=1)
    ]
    for hypothesis in hypotheses:
        if len(hypothesis["support"]) > effective_limits["max_support_edges_per_hypothesis"]:
            raise P137HypothesisError("support_edge_budget_exceeded")
        if len(hypothesis["contradictions"]) > effective_limits["max_contradiction_edges_per_hypothesis"]:
            raise P137HypothesisError("contradiction_edge_budget_exceeded")
        if len(hypothesis["missing_evidence"]) > effective_limits["max_missing_evidence_items_per_hypothesis"]:
            raise P137HypothesisError("missing_evidence_budget_exceeded")
    hypotheses.sort(key=lambda item: (_semantic_tuple(item), str(item["hypothesis_hash"])), reverse=True)
    for rank, hypothesis in enumerate(hypotheses, start=1):
        hypothesis["rank"] = rank
        hypothesis["hypothesis_hash"] = _hash_hypothesis(hypothesis)

    top_ties = _top_semantic_ties(hypotheses)
    classification = _classification(hypotheses, top_ties)
    return {
        "schema_version": "p137.hypothesis_ranking.v1",
        "score_formula_id": SCORE_FORMULA_ID,
        "tie_policy": TIE_POLICY,
        "hypotheses": hypotheses,
        "classification": classification,
        "top_tie_hypothesis_hashes": sorted(str(hypothesis["hypothesis_hash"]) for hypothesis in top_ties),
        "planned_requests": [],
    }


def _limits(overrides: Mapping[str, int] | None) -> dict[str, int]:
    values = dict(_DEFAULT_LIMITS)
    for key, value in (overrides or {}).items():
        if key not in values:
            raise P137HypothesisError("unknown_budget_key")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise P137HypothesisError("invalid_budget_value")
        if key == "correlation_window_seconds" and value == 0:
            raise P137HypothesisError("invalid_budget_value")
        values[key] = value
    return values


def _validate_atom(atom: Mapping[str, Any]) -> dict[str, Any]:
    if set(atom) != _ATOM_FIELDS:
        raise P137HypothesisError("unexpected_atom_keys")
    if atom.get("schema_version") != "p137.evidence_atom.v1":
        raise P137HypothesisError("invalid_atom_schema")
    if atom.get("evidence_state") not in _EVIDENCE_STATES:
        raise P137HypothesisError("invalid_evidence_state")
    if atom.get("severity_code") not in _SEVERITIES or atom.get("metric_breach_code") not in _BREACH_CODES:
        raise P137HypothesisError("invalid_atom_classifier_enum")
    if atom.get("marker_code") not in _MARKER_CODES or atom.get("counter_signal_code") not in _COUNTER_CODES:
        raise P137HypothesisError("invalid_atom_classifier_enum")
    numeric_value = atom.get("numeric_value")
    if isinstance(numeric_value, bool):
        raise P137HypothesisError("bool_numeric_value_forbidden")
    reasons = atom.get("state_reason_codes")
    if not isinstance(reasons, list) or any(reason not in _STATE_REASONS for reason in reasons):
        raise P137HypothesisError("invalid_state_reason_code")
    window = atom.get("window")
    if not isinstance(window, Mapping) or set(window) != {"start", "end"}:
        raise P137HypothesisError("invalid_atom_window")
    return dict(atom)


def _build_hypothesis(
    incident: Mapping[str, Any],
    atom: Mapping[str, Any],
    *,
    sequence: int,
    now: str,
    correlation_window_seconds: int,
) -> dict[str, Any]:
    statement_code, category = _statement(atom)
    support, contradictions, missing = _edges(atom)
    score = _score(support, contradictions, missing, now=now, correlation_window_seconds=correlation_window_seconds)
    hypothesis: dict[str, Any] = {
        "schema_version": HYPOTHESIS_SCHEMA_VERSION,
        "hypothesis_id": _hypothesis_id(str(incident["incident_id"]), statement_code, str(atom["atom_hash"])),
        "incident_id": str(incident["incident_id"]),
        "hypothesis_sequence": sequence,
        "category": category,
        "statement_code": statement_code,
        "scope": {
            "system_id": str(atom["system_id"]),
            "entity_ref_hash": str(atom["entity_ref_hash"]),
            "window": dict(atom["window"]),
            "evidence_atom_hashes": [str(atom["atom_hash"])],
        },
        "support": support,
        "contradictions": contradictions,
        "missing_evidence": missing,
        "score": score,
        "rank": 0,
        "classification_vote": _vote(category, support, contradictions, missing),
        "previous_hypothesis_hash": None,
    }
    hypothesis["hypothesis_hash"] = _hash_hypothesis(hypothesis)
    return hypothesis


def _statement(atom: Mapping[str, Any]) -> tuple[str, str]:
    if atom["evidence_state"] == "promoted_success" and atom["signal_name"] == "error_rate" and atom["metric_breach_code"] in {"above_warning", "above_critical"}:
        return "error_rate_regression", "error_rate"
    if atom["evidence_state"] == "promoted_success" and atom["signal_name"] == "latency" and atom["metric_breach_code"] in {"above_warning", "above_critical"}:
        return "latency_regression", "latency"
    if atom["evidence_state"] == "promoted_success" and atom["signal_name"] in {"cpu", "memory", "disk", "queue_depth"} and atom["metric_breach_code"] != "none":
        return "resource_saturation_signal", "resource_saturation"
    if atom["evidence_state"] == "promoted_success" and atom["signal_name"] == "data_quality" and atom["metric_breach_code"] != "none":
        return "data_quality_drop", "data_quality"
    if atom["evidence_state"] == "promoted_success" and atom["marker_code"] == "security_marker":
        return "security_signal_cluster", "security_signal"
    if atom["evidence_state"] == "promoted_success" and atom["marker_code"] == "deployment_marker":
        return "deployment_correlated_change", "deployment_change"
    if atom["evidence_state"] == "promoted_success" and atom["marker_code"] == "topology_marker":
        return "topology_correlated_change", "topology_change"
    if atom["evidence_state"] == "promoted_success" and atom["marker_code"] in {"known_benign_schedule", "topology_noise"}:
        return "scheduled_or_known_benign_noise", "benign_pattern"
    if atom["evidence_state"] == "promoted_success" and atom["metric_breach_code"] in {"baseline_delta_warning", "baseline_delta_critical"} and (
        bool(atom["label_hashes"]) or bool(atom["content_hash"]) or bool(atom["redacted_preview_hash"])
    ):
        return "metric_spike_with_correlated_logs", "availability"
    if atom["evidence_state"] == "denominator_visible_failure":
        _request_need_class(atom)
        return "telemetry_gap_only", "telemetry_gap"
    return "unknown_insufficient_context", "unknown"


def _edges(atom: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    support: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    if atom["evidence_state"] == "promoted_success":
        if atom["metric_breach_code"] in {"above_warning", "above_critical", "below_warning", "below_critical"}:
            support.append(_edge(atom, "supports_primary", 4, "numeric_threshold_exceeded"))
        if atom["metric_breach_code"] in {"baseline_delta_warning", "baseline_delta_critical"}:
            support.append(_edge(atom, "supports_primary", 4, "promoted_baseline_delta"))
        if atom["marker_code"] == "known_benign_schedule":
            support.append(_edge(atom, "supports_benign", 3, "known_benign_schedule"))
        if atom["marker_code"] == "topology_marker":
            support.append(_edge(atom, "supports_secondary", 2, "topology_change_detected"))
        if atom["counter_signal_code"] == "decisive_counter_signal":
            contradictions.append(_edge(atom, "contradicts_decisive", -5, "decisive_counter_signal"))
        if atom["counter_signal_code"] == "weak_counter_signal":
            contradictions.append(_edge(atom, "contradicts_soft", -2, "weak_counter_signal"))
    if atom["evidence_state"] == "denominator_visible_failure":
        request_need_class = _request_need_class(atom)
        reason = "external_authority_unavailable" if request_need_class == "EXTERNAL_UNAVAILABLE" else "required_local_selection_missing"
        relation = "missing_external_unavailable" if request_need_class == "EXTERNAL_UNAVAILABLE" else "missing_required_local"
        missing.append(_missing(atom, request_need_class, reason, relation))
    if not support and not contradictions and atom["evidence_state"] == "context_only":
        support.append(_edge(atom, "neutral_context", 0, "provider_signal_overlap"))
    return support, contradictions, missing


def _edge(atom: Mapping[str, Any], relation: str, weight: int, reason_code: str) -> dict[str, Any]:
    edge = {
        "edge_id": _edge_id(str(atom["atom_hash"]), relation, reason_code),
        "evidence_atom_hash": str(atom["atom_hash"]),
        "relation": relation,
        "weight": weight,
        "window": dict(atom["window"]),
        "reason_code": reason_code,
    }
    edge["edge_hash"] = stable_hash(edge)
    return edge


def _missing(atom: Mapping[str, Any], request_need_class: str, why_needed_code: str, relation: str) -> dict[str, Any]:
    item = {
        "missing_id": _edge_id(str(atom["atom_hash"]), relation, why_needed_code),
        "request_kind": "closed_catalog_selection" if request_need_class == "LOCAL_SELECTION" else "unavailable_external_authority",
        "request_need_class": request_need_class,
        "expected_value_code": "validated_follow_up_evidence",
        "why_needed_code": why_needed_code,
        "blocking": True,
        "unavailable_need_hash": stable_hash({"atom_hash": atom["atom_hash"], "request_need_class": request_need_class}),
    }
    item["item_hash"] = stable_hash(item)
    return item


def _request_need_class(atom: Mapping[str, Any]) -> str:
    reasons = set(atom["state_reason_codes"])
    if reasons & _EXTERNAL_REASONS:
        return "EXTERNAL_UNAVAILABLE"
    if "local_catalog_selectable" in reasons:
        return "LOCAL_SELECTION"
    raise P137HypothesisError("denominator_failure_reason_unmapped")


def _score(
    support: Sequence[Mapping[str, Any]],
    contradictions: Sequence[Mapping[str, Any]],
    missing: Sequence[Mapping[str, Any]],
    *,
    now: str,
    correlation_window_seconds: int,
) -> dict[str, int]:
    support_weight = sum(_int(edge["weight"]) for edge in support)
    contradiction_weight = sum(abs(_int(edge["weight"])) for edge in contradictions)
    missing_required_count = sum(1 for item in missing if item["blocking"])
    freshness_weight = _freshness_weight(support, now, correlation_window_seconds)
    source_diversity_weight = 1 if support else 0
    rank_score = support_weight - contradiction_weight - (4 * missing_required_count) + freshness_weight + source_diversity_weight
    return {
        "support_weight": support_weight,
        "contradiction_weight": contradiction_weight,
        "missing_required_count": missing_required_count,
        "freshness_weight": freshness_weight,
        "source_diversity_weight": source_diversity_weight,
        "rank_score": rank_score,
    }


def _vote(category: str, support: Sequence[Mapping[str, Any]], contradictions: Sequence[Mapping[str, Any]], missing: Sequence[Mapping[str, Any]]) -> str:
    blocking_missing = any(item["blocking"] for item in missing)
    decisive_counter = any(edge["relation"] == "contradicts_decisive" for edge in contradictions)
    primary_support = any(edge["relation"] == "supports_primary" for edge in support)
    benign_support = any(edge["relation"] == "supports_benign" for edge in support)
    if category == "benign_pattern" and benign_support and not blocking_missing:
        return "benign_anomaly"
    if category != "benign_pattern" and primary_support and not decisive_counter and not blocking_missing:
        return "confirmed_incident"
    return "insufficient_evidence"


def _classification(hypotheses: Sequence[Mapping[str, Any]], top_ties: Sequence[Mapping[str, Any]]) -> str:
    if not hypotheses:
        return "insufficient_evidence"
    if len(top_ties) > 1 and len({str(item["statement_code"]) for item in top_ties}) > 1:
        return "insufficient_evidence"
    return str(hypotheses[0]["classification_vote"])


def _top_semantic_ties(hypotheses: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not hypotheses:
        return []
    top_tuple = _semantic_tuple(hypotheses[0])
    return [hypothesis for hypothesis in hypotheses if _semantic_tuple(hypothesis) == top_tuple]


def _semantic_tuple(hypothesis: Mapping[str, Any]) -> tuple[int, int, int, int, int, int]:
    score = hypothesis["score"]
    return (
        _int(score["rank_score"]),
        _int(score["support_weight"]),
        -_int(score["contradiction_weight"]),
        -_int(score["missing_required_count"]),
        _int(score["freshness_weight"]),
        _int(score["source_diversity_weight"]),
    )


def _freshness_weight(support: Sequence[Mapping[str, Any]], now: str, correlation_window_seconds: int) -> int:
    if not support:
        return 0
    newest = max(_parse_time(str(edge["window"]["end"])) for edge in support)
    age_bucket = int((_parse_time(now) - newest).total_seconds() // correlation_window_seconds)
    return max(0, 3 - age_bucket)


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise P137HypothesisError("score_integer_required")
    return value


def _hypothesis_id(incident_id: str, statement_code: str, atom_hash: str) -> str:
    return f"p137-hyp-{stable_hash({'incident_id': incident_id, 'statement_code': statement_code, 'atom_hash': atom_hash}).removeprefix('sha256:')[:40]}"


def _edge_id(atom_hash: str, relation: str, reason_code: str) -> str:
    return f"p137-edge-{stable_hash({'atom_hash': atom_hash, 'relation': relation, 'reason_code': reason_code}).removeprefix('sha256:')[:40]}"


def _hash_hypothesis(hypothesis: Mapping[str, Any]) -> str:
    return stable_hash({key: value for key, value in hypothesis.items() if key != "hypothesis_hash"})


def _parse_time(value: str) -> datetime:
    if not value.endswith("Z"):
        raise P137HypothesisError("timestamp_must_be_utc_z")
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(UTC)
