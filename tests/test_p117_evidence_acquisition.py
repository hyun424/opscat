from __future__ import annotations

import pytest

from app.services.p117_evidence_acquisition import (
    EVIDENCE_TAXONOMY_HASH,
    FROZEN_EVIDENCE_TAXONOMY,
    P117EvidenceAcquisitionError,
    build_evidence_request,
    compute_value_of_information,
)


def test_taxonomy_is_frozen_ordered_hash_bound_and_label_safe() -> None:
    class_ids = [item.class_id for item in FROZEN_EVIDENCE_TAXONOMY]

    assert class_ids == [
        "metric",
        "log",
        "topology",
        "deploy_config",
        "saturation",
        "dependency",
        "queue",
        "dns",
        "certificate",
        "quota",
        "validation",
        "rollback",
    ]
    assert EVIDENCE_TAXONOMY_HASH.startswith("sha256:")
    with pytest.raises(AttributeError):
        FROZEN_EVIDENCE_TAXONOMY[0].class_id = "hidden_truth"  # type: ignore[misc]


def test_voi_gate_emits_declarative_investigate_more_request_with_marker_citation() -> None:
    request = build_evidence_request(
        missing_evidence_markers={"missing_dependency_edge": "dependency", "missing_queue_depth": "queue"},
        expected_utility_delta=0.18,
        uncertainty_reduction=0.30,
        acquisition_cost=0.04,
        authority_constraints={"live_access": False, "credential_scope": False},
    ).to_dict()

    assert request["selected_label"] == "investigate_more"
    assert request["value_of_information"]["positive"] is True
    assert request["requests"] == [
        {"class_id": "dependency", "missing_evidence_marker": "missing_dependency_edge", "declarative_only": True},
        {"class_id": "queue", "missing_evidence_marker": "missing_queue_depth", "declarative_only": True},
    ]
    assert request["live_access_request_count"] == 0
    assert request["taxonomy_hash"] == EVIDENCE_TAXONOMY_HASH


def test_voi_gate_abstains_when_cost_or_authority_blocks_acquisition() -> None:
    assert compute_value_of_information(
        expected_utility_delta=0.02,
        uncertainty_reduction=0.10,
        acquisition_cost=0.20,
        authority_constraints={"live_access": False},
    )["positive"] is False

    request = build_evidence_request(
        missing_evidence_markers={"missing_metric_window": "metric"},
        expected_utility_delta=0.50,
        uncertainty_reduction=0.50,
        acquisition_cost=0.01,
        authority_constraints={"live_access": True},
    ).to_dict()

    assert request["selected_label"] == "abstain"
    assert request["value_of_information"]["authority_blocked"] is True
    assert request["requests"][0]["declarative_only"] is True


@pytest.mark.parametrize(
    ("markers", "error"),
    [
        ({"hidden_root_cause_payment_cpu": "metric"}, "leakage_probe"),
        ({"missing_shell": "shell"}, "unknown_evidence_class"),
        ({"missing_url": "https://prod.example/metrics"}, "live_access_request"),
        ({"missing_query": "metric"}, "leakage_probe"),
    ],
)
def test_evidence_requests_reject_live_access_secret_scope_and_hidden_label_leaks(markers: dict[str, str], error: str) -> None:
    with pytest.raises(P117EvidenceAcquisitionError, match=error):
        build_evidence_request(
            missing_evidence_markers=markers,
            expected_utility_delta=0.50,
            uncertainty_reduction=0.50,
            acquisition_cost=0.01,
            authority_constraints={"live_access": False, "credential_scope": False},
        )
