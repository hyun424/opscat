from __future__ import annotations

import copy

import pytest

from app.services.p120_ontology import (
    P120OntologyError,
    build_mapping_record,
    mapping_quality_metrics,
    normalize_entity_identity,
    validate_mapping_record,
)


def _mapping() -> dict[str, object]:
    return {
        "mapping_id": "map-1",
        "source_label": "HTTP latency symptom",
        "source_context": {"field": "alert.title", "source": "src-1"},
        "canonical_label": "evidence.latency.http",
        "mapping_confidence": 0.82,
        "ambiguity_set": [],
        "human_review_required": False,
        "evidence_refs": ["telemetry:rec-1"],
        "ontology_version": "p120-ontology-v1",
        "split": "development",
        "system_id": "sys-1",
        "source_hash": "sha256:" + "a" * 64,
        "source_id": "src-1",
        "incident_family": "latency",
        "action_family": "investigate",
        "outcome_label": None,
    }


def test_normalizes_entity_identity_and_builds_mapping_metrics() -> None:
    identity = normalize_entity_identity(system_id="sys-1", source_entity_id="Checkout API", entity_kind="service", service_id="checkout", topology_refs=["edge:a:b"])
    assert identity["canonical_entity_ref"] == "opscat://sys-1/service/checkout/checkout-api"

    record = build_mapping_record(_mapping())
    validate_mapping_record(record)
    metrics = mapping_quality_metrics([record])
    assert metrics["metrics"][0]["denominator"] == 1
    assert metrics["metrics"][0]["mean_confidence"] == pytest.approx(0.82)


def test_ambiguous_mapping_must_not_be_forced_into_confident_action_path() -> None:
    ambiguous = {
        **_mapping(),
        "mapping_confidence": 0.95,
        "ambiguity_set": ["evidence.latency.http", "evidence.saturation.queue"],
        "human_review_required": True,
    }
    with pytest.raises(P120OntologyError, match="ambiguous_mapping_forced"):
        build_mapping_record(ambiguous)

    routed = {
        **_mapping(),
        "mapping_confidence": 0.55,
        "ambiguity_set": ["evidence.latency.http", "evidence.saturation.queue"],
        "human_review_required": True,
        "decision_effect": "investigate_more",
    }
    assert build_mapping_record(routed)["decision_effect"] == "investigate_more"


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"source_label": "ground_truth root cause database"}, "source_label_hidden_answer_leak"),
        ({"canonical_label": "fixture.safe.production-cluster target"}, "production_like_target_normalized_as_fixture"),
        ({"evidence_refs": []}, "missing_evidence_refs|missing_mapping_evidence_refs"),
        ({"source_hash": "not-a-hash"}, "invalid_source_hash"),
    ],
)
def test_mapping_rejects_hidden_answer_authority_and_missing_evidence_refs(patch: dict[str, object], expected: str) -> None:
    with pytest.raises(P120OntologyError, match=expected):
        build_mapping_record({**_mapping(), **patch})


def test_mapping_tamper_detection() -> None:
    record = build_mapping_record(_mapping())
    tampered = copy.deepcopy(record)
    tampered["canonical_label"] = "evidence.other"
    with pytest.raises(P120OntologyError, match="mapping_record_tampered"):
        validate_mapping_record(tampered)
