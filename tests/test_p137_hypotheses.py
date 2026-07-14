from __future__ import annotations

import importlib
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash


def _api(*names: str) -> Any:
    try:
        module = importlib.import_module("app.services.p137_hypotheses")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 hypotheses module/API: app.services.p137_hypotheses ({exc})")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P137 hypotheses module/API: {', '.join(missing)}")
    return module


def _error() -> type[Exception]:
    return _api("P137HypothesisError").P137HypothesisError


def _incident() -> dict[str, Any]:
    return {
        "schema_version": "p137.incident_state.v1",
        "incident_id": "incident-1",
        "incident_sequence": 1,
        "status": "investigating",
        "created_at": "2026-07-14T00:00:00Z",
        "updated_at": "2026-07-14T00:06:00Z",
        "correlation_key": {},
        "primary_system_id": "system-a",
        "entity_ref_hashes": [stable_hash({"entity": "checkout"})],
        "time_window": {"start": "2026-07-14T00:00:00Z", "end": "2026-07-14T00:05:00Z"},
        "source_promotion_record_hashes": [],
        "evidence_atom_hashes": [],
        "rejection_hashes": [],
        "hypothesis_hashes": [],
        "request_hashes": [],
        "attempted_request_hashes": [],
        "classification_hash": None,
        "previous_incident_hash": None,
        "incident_hash": stable_hash({"incident": 1}),
    }


def _atom(
    ordinal: int,
    *,
    signal_name: str = "error_rate",
    metric_breach_code: str = "above_critical",
    marker_code: str = "none",
    counter_signal_code: str = "none",
    evidence_state: str = "promoted_success",
    state_reason_codes: list[str] | None = None,
    provider: str = "prometheus",
    start: str = "2026-07-14T00:00:00Z",
    end: str = "2026-07-14T00:05:00Z",
) -> dict[str, Any]:
    atom = {
        "schema_version": "p137.evidence_atom.v1",
        "atom_id": f"atom-{ordinal}",
        "promotion_record_hash": stable_hash({"promotion": ordinal}),
        "promotion_key": stable_hash({"promotion_key": ordinal}),
        "p136_entry_hash": stable_hash({"entry": ordinal}),
        "p135_bundle_hash": stable_hash({"bundle": ordinal}),
        "source_id": f"source-{ordinal}",
        "provider": provider,
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "system_id": "system-a",
        "entity_ref_hash": stable_hash({"entity": "checkout"}),
        "window": {"start": start, "end": end},
        "signal_name": signal_name,
        "numeric_value": 12,
        "numeric_unit": "ratio",
        "evidence_state": evidence_state,
        "severity_code": "sev1",
        "metric_breach_code": metric_breach_code,
        "marker_code": marker_code,
        "counter_signal_code": counter_signal_code,
        "state_reason_codes": state_reason_codes or [],
        "denominator_visible": evidence_state == "denominator_visible_failure",
        "content_hash": stable_hash({"content": ordinal}),
        "label_hashes": [stable_hash({"label": "checkout"})],
        "topology_ref_hashes": [],
        "deploy_config_ref_hashes": [],
        "risk_flags": [],
        "redacted_preview_hash": stable_hash({"preview": ordinal}),
        "ordinal": ordinal,
    }
    atom["atom_hash"] = stable_hash(atom)
    return atom


def test_support_dominance_creates_closed_hypothesis_and_confirmed_vote() -> None:
    api = _api("rank_incident_hypotheses")
    atom = _atom(1, signal_name="error_rate", metric_breach_code="above_critical")

    result = api.rank_incident_hypotheses(_incident(), [atom], now="2026-07-14T00:06:00Z")

    top = result["hypotheses"][0]
    assert top["category"] == "error_rate"
    assert top["statement_code"] == "error_rate_regression"
    assert top["classification_vote"] == "confirmed_incident"
    assert top["support"][0]["relation"] == "supports_primary"
    assert top["support"][0]["reason_code"] == "numeric_threshold_exceeded"
    assert top["score"] == {
        "support_weight": 4,
        "contradiction_weight": 0,
        "missing_required_count": 0,
        "freshness_weight": 3,
        "source_diversity_weight": 1,
        "rank_score": 8,
    }
    assert result["classification"] == "confirmed_incident"


def test_decisive_and_weak_counter_signals_use_separate_closed_reasons_and_weights() -> None:
    api = _api("rank_incident_hypotheses")

    decisive = api.rank_incident_hypotheses(_incident(), [_atom(1, counter_signal_code="decisive_counter_signal")])
    weak = api.rank_incident_hypotheses(_incident(), [_atom(2, counter_signal_code="weak_counter_signal")])

    decisive_edge = decisive["hypotheses"][0]["contradictions"][0]
    weak_edge = weak["hypotheses"][0]["contradictions"][0]
    assert decisive_edge["reason_code"] == "decisive_counter_signal"
    assert decisive_edge["relation"] == "contradicts_decisive"
    assert decisive_edge["weight"] == -5
    assert decisive["classification"] == "insufficient_evidence"
    assert weak_edge["reason_code"] == "weak_counter_signal"
    assert weak_edge["relation"] == "contradicts_soft"
    assert weak_edge["weight"] == -2
    assert weak["classification"] == "confirmed_incident"


def test_denominator_failure_missing_evidence_splits_local_and_external_without_substring_guessing() -> None:
    api = _api("rank_incident_hypotheses")
    local = _atom(
        1,
        evidence_state="denominator_visible_failure",
        metric_breach_code="none",
        state_reason_codes=["local_catalog_selectable", "p135_adapter_failure"],
    )
    external = _atom(
        2,
        evidence_state="denominator_visible_failure",
        metric_breach_code="none",
        state_reason_codes=["provider_authority_required"],
    )

    local_result = api.rank_incident_hypotheses(_incident(), [local])
    external_result = api.rank_incident_hypotheses(_incident(), [external])

    assert local_result["hypotheses"][0]["statement_code"] == "telemetry_gap_only"
    assert local_result["hypotheses"][0]["missing_evidence"][0]["request_need_class"] == "LOCAL_SELECTION"
    assert local_result["hypotheses"][0]["missing_evidence"][0]["why_needed_code"] == "required_local_selection_missing"
    assert local_result["classification"] == "insufficient_evidence"
    assert external_result["hypotheses"][0]["missing_evidence"][0]["request_need_class"] == "EXTERNAL_UNAVAILABLE"
    assert external_result["hypotheses"][0]["missing_evidence"][0]["why_needed_code"] == "external_authority_unavailable"
    assert external_result["planned_requests"] == []


def test_benign_pattern_ranks_to_benign_anomaly_when_not_blocked() -> None:
    api = _api("rank_incident_hypotheses")
    benign = _atom(1, marker_code="known_benign_schedule", metric_breach_code="none")

    result = api.rank_incident_hypotheses(_incident(), [benign])

    assert result["hypotheses"][0]["statement_code"] == "scheduled_or_known_benign_noise"
    assert result["hypotheses"][0]["support"][0]["relation"] == "supports_benign"
    assert result["classification"] == "benign_anomaly"


def test_semantic_tie_yields_insufficient_even_when_hash_order_is_stable() -> None:
    api = _api("rank_incident_hypotheses")
    error_rate = _atom(1, signal_name="error_rate")
    latency = _atom(2, signal_name="latency")

    result = api.rank_incident_hypotheses(_incident(), [latency, error_rate], now="2026-07-14T00:06:00Z")

    assert [hypothesis["rank"] for hypothesis in result["hypotheses"]] == [1, 2]
    assert result["tie_policy"] == "semantic_tuple_tie_yields_insufficient_evidence"
    assert result["classification"] == "insufficient_evidence"
    assert result["top_tie_hypothesis_hashes"] == sorted(result["top_tie_hypothesis_hashes"])


def test_rejects_free_form_or_unbounded_hypothesis_inputs() -> None:
    api = _api("rank_incident_hypotheses")
    error = _error()
    free_form = _atom(1)
    free_form["statement_code"] = "cpu is probably sad"
    bool_weight = _atom(2)
    bool_weight["numeric_value"] = True

    with pytest.raises(error, match="unexpected_atom_keys"):
        api.rank_incident_hypotheses(_incident(), [free_form])
    with pytest.raises(error, match="bool_numeric_value_forbidden"):
        api.rank_incident_hypotheses(_incident(), [bool_weight])
    with pytest.raises(error, match="hypothesis_budget_exceeded"):
        api.rank_incident_hypotheses(_incident(), [_atom(index) for index in range(1, 6)], limits={"max_hypotheses": 2})
    with pytest.raises(error, match="support_edge_budget_exceeded"):
        api.rank_incident_hypotheses(_incident(), [_atom(1)], limits={"max_support_edges_per_hypothesis": 0})
