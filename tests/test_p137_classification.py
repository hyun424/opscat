from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p137_classification import (
    P137ClassificationError,
    build_classification_record,
    derive_classification,
    validate_classification_record,
)


def _edge(relation: str) -> dict[str, object]:
    edge: dict[str, object] = {"relation": relation, "edge_id": stable_hash({"relation": relation})}
    edge["edge_hash"] = stable_hash(edge)
    return edge


def _hypothesis(category: str, relations: list[str], *, blocking: bool = False) -> dict[str, object]:
    support = [_edge(relation) for relation in relations if relation.startswith("supports")]
    contradictions = [_edge(relation) for relation in relations if relation.startswith("contradicts")]
    missing: list[dict[str, object]] = []
    if blocking:
        item = {"blocking": True, "missing_id": "missing-a"}
        item["item_hash"] = stable_hash(item)
        missing.append(item)
    hypothesis: dict[str, object] = {
        "category": category,
        "support": support,
        "contradictions": contradictions,
        "missing_evidence": missing,
        "score": {
            "rank_score": 5,
            "support_weight": 4,
            "contradiction_weight": 0,
            "missing_required_count": int(blocking),
            "freshness_weight": 1,
            "source_diversity_weight": 1,
        },
    }
    hypothesis["hypothesis_hash"] = stable_hash(hypothesis)
    return hypothesis


def test_four_classification_semantics_and_fail_closed_commit_boundary() -> None:
    confirmed = _hypothesis("error_rate", ["supports_primary"])
    benign = _hypothesis("benign_pattern", ["supports_benign"])
    blocked = _hypothesis("error_rate", ["supports_primary"], blocking=True)
    assert derive_classification([confirmed], accepted_incident=True) == "confirmed_incident"
    assert derive_classification([benign], accepted_incident=True) == "benign_anomaly"
    assert derive_classification([blocked], accepted_incident=True) == "insufficient_evidence"
    assert derive_classification([confirmed], accepted_incident=True, semantic_tie=True) == "insufficient_evidence"
    assert derive_classification([confirmed], accepted_incident=True, failure_code="budget", classification_write_succeeded=True, ledger_cas_succeeded=False) is None
    assert derive_classification([confirmed], accepted_incident=True, failure_code="budget", classification_write_succeeded=True, ledger_cas_succeeded=True) == "aborted_fail_closed"


def test_classification_record_binds_hypothesis_summaries_and_hash() -> None:
    hypothesis = _hypothesis("error_rate", ["supports_primary"])
    record = build_classification_record(
        incident_id="incident-a",
        classification_sequence=1,
        classification="confirmed_incident",
        decided_at="2026-01-01T00:00:00Z",
        top_hypothesis=hypothesis,
        authority_counters={"network_call_count": 0},
        runtime_activity={"classification_write_count": 1},
        resource_usage={"wall_time_ms": 1},
        decision_reasons=["numeric_threshold_exceeded"],
    )
    validate_classification_record(record, top_hypothesis=hypothesis)
    forged = deepcopy(record)
    forged["support_summary_hashes"] = []
    forged["classification_hash"] = stable_hash({key: value for key, value in forged.items() if key != "classification_hash"})
    with pytest.raises(P137ClassificationError, match="forged_support_summary"):
        validate_classification_record(forged, top_hypothesis=hypothesis)


def test_nonzero_authority_is_rejected() -> None:
    with pytest.raises(P137ClassificationError, match="nonzero_authority_counters"):
        build_classification_record(
            incident_id="incident-a",
            classification_sequence=1,
            classification="aborted_fail_closed",
            decided_at="2026-01-01T00:00:00Z",
            top_hypothesis=None,
            authority_counters={"network_call_count": 1},
            runtime_activity={},
            resource_usage={},
        )
