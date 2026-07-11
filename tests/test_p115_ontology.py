from __future__ import annotations

import copy

import pytest

from app.services.p115_ontology import (
    P115OntologyError,
    build_action_label,
    build_action_pack,
    build_incident_case,
    sign_action_pack_payload,
)


def _pack_payload() -> dict[str, object]:
    return {
        "action_id": "restart_connection_pool",
        "action_family": "database_pool",
        "description": "Recycle a disposable lab connection pool.",
        "prerequisites": ["pool_exhaustion_confirmed", "lab_target_confirmed"],
        "contraindications": ["active_schema_migration"],
        "reversibility": "reversible",
        "blast_radius": {"scope": "single_lab_service", "max_services": 1},
        "expected_effect": {"signal": "pool_waiters", "direction": "decrease"},
        "expected_evidence": ["pool_waiters", "request_latency"],
        "validation_query": {"query_id": "pool_waiters_recovered", "read_only": True},
        "rollback_plan": {"rollback_id": "restore_previous_pool", "declarative_only": True},
        "executor_disabled": True,
        "target_scope": "local_lab",
    }


def _signed_pack() -> dict[str, object]:
    payload = _pack_payload()
    signature = sign_action_pack_payload(payload, key_id="fixture-key", key=b"offline-test-key")
    return {**payload, "signer_key_id": "fixture-key", "signature": signature}


def test_build_action_pack_verifies_signature_and_preserves_zero_authority() -> None:
    pack = build_action_pack(_signed_pack(), keyring={"fixture-key": b"offline-test-key"}).to_dict()

    assert pack["schema_version"] == "p115.action_pack.v1"
    assert pack["action_id"] == "restart_connection_pool"
    assert pack["executor_disabled"] is True
    assert pack["authority_level"] == "L1"
    assert pack["executable_body"] is None
    assert pack["pack_hash"].startswith("sha256:")


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"signature": "sha256:" + "0" * 64}, "action_pack_signature_mismatch"),
        ({"executor_disabled": False}, "executor_must_be_disabled"),
        ({"target_scope": "production"}, "production_target_selector"),
        ({"validation_query": {"command": "kubectl rollout restart"}}, "executable_command"),
        ({"rollback_plan": {}}, "missing_rollback"),
        ({"groundTruth": "restart_connection_pool"}, "truth_bearing_field"),
    ],
)
def test_action_pack_fails_closed(mutation: dict[str, object], error: str) -> None:
    pack = {**_signed_pack(), **mutation}
    if "signature" not in mutation and not ({"groundTruth", "validation_query"} & set(mutation)):
        pack["signature"] = sign_action_pack_payload(pack, key_id="fixture-key", key=b"offline-test-key")
    with pytest.raises(P115OntologyError, match=error):
        build_action_pack(pack, keyring={"fixture-key": b"offline-test-key"})


def test_signature_detects_payload_tampering() -> None:
    pack = _signed_pack()
    pack["expected_effect"] = {"signal": "pool_waiters", "direction": "increase"}
    with pytest.raises(P115OntologyError, match="action_pack_signature_mismatch"):
        build_action_pack(pack, keyring={"fixture-key": b"offline-test-key"})


def test_incident_case_and_first_class_abstention_labels_are_validated() -> None:
    incident = build_incident_case(
        {
            "case_id": "case-001",
            "source_family": "controlled_lab",
            "scenario_family": "database_pool_exhaustion",
            "topology_handle": "topology:shop-v1",
            "time_window": {"start": "2026-07-12T00:00:00Z", "end": "2026-07-12T00:05:00Z"},
            "visible_evidence_handle": "evidence:case-001",
            "diagnosis_handle": "lattice:case-001",
            "eligible_action_pack_ids": ["restart_connection_pool"],
            "required_evidence_classes": ["metric", "log"],
            "partition_group": "shop-dbpool-2026w28",
            "release_role": "development",
        }
    ).to_dict()
    label = build_action_label(
        {
            "case_id": "case-001",
            "decision": "investigate_more",
            "action_pack_ids": [],
            "evidence_ids": ["ev-pool-waiters"],
            "prerequisite_checks": {},
            "contraindication_checks": {},
            "expected_benefit": 0.0,
            "expected_harm": 0.0,
            "validation_plan": {"query_id": "collect_pool_metrics"},
            "rollback_plan": {"required": False},
            "abstention_reason": "missing_trace_evidence",
        },
        eligible_action_pack_ids=incident["eligible_action_pack_ids"],
    ).to_dict()

    assert incident["schema_version"] == "p115.incident_case.v1"
    assert label["decision"] == "investigate_more"
    assert label["action_pack_ids"] == []
    assert label["artifact_hash"].startswith("sha256:")


def test_action_label_rejects_unknown_action_and_action_without_pack() -> None:
    base = {
        "case_id": "case-001",
        "decision": "act",
        "action_pack_ids": ["unknown"],
        "evidence_ids": ["ev-1"],
        "prerequisite_checks": {"ready": True},
        "contraindication_checks": {"unsafe": False},
        "expected_benefit": 0.8,
        "expected_harm": 0.1,
        "validation_plan": {"query_id": "validate"},
        "rollback_plan": {"rollback_id": "rollback"},
        "abstention_reason": None,
    }
    with pytest.raises(P115OntologyError, match="unknown_action_pack"):
        build_action_label(base, eligible_action_pack_ids=["known"])

    no_pack = copy.deepcopy(base)
    no_pack["action_pack_ids"] = []
    with pytest.raises(P115OntologyError, match="act_requires_action_pack"):
        build_action_label(no_pack, eligible_action_pack_ids=["known"])
