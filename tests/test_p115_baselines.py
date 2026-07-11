from __future__ import annotations

import copy

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p115_baselines import P115BaselineError, deterministic_rule_baseline, safe_null_baseline
from app.services.p115_ontology import build_action_pack, build_incident_case, sign_action_pack_payload


def _pack_payload() -> dict[str, object]:
    return {
        "action_id": "restart_connection_pool",
        "action_family": "database_pool",
        "description": "Recycle a disposable lab connection pool.",
        "prerequisites": ["pool_exhaustion_confirmed", "lab_target_confirmed"],
        "contraindications": ["active_schema_migration"],
        "reversibility": "reversible",
        "blast_radius": {"scope": "single_lab_service", "max_services": 1, "expected_harm": 0.02},
        "expected_effect": {"signal": "pool_waiters", "direction": "decrease", "benefit": 0.8},
        "expected_evidence": ["pool_waiters", "request_latency"],
        "validation_query": {"query_id": "pool_waiters_recovered", "read_only": True},
        "rollback_plan": {"rollback_id": "restore_previous_pool", "declarative_only": True},
        "executor_disabled": True,
        "target_scope": "local_lab",
    }


def _signed_pack_payload(overrides: dict[str, object] | None = None) -> dict[str, object]:
    payload = {**_pack_payload(), **(overrides or {})}
    signature = sign_action_pack_payload(payload, key_id="fixture-key", key=b"offline-test-key")
    return {**payload, "signer_key_id": "fixture-key", "signature": signature}


def _pack(overrides: dict[str, object] | None = None) -> dict[str, object]:
    return build_action_pack(_signed_pack_payload(overrides), keyring={"fixture-key": b"offline-test-key"}).to_dict()


def _incident(eligible_action_pack_ids: list[str] | None = None, required_evidence_classes: list[str] | None = None) -> dict[str, object]:
    return build_incident_case(
        {
            "case_id": "case-001",
            "source_family": "controlled_lab",
            "scenario_family": "database_pool_exhaustion",
            "topology_handle": "topology:shop-v1",
            "time_window": {"start": "2026-07-12T00:00:00Z", "end": "2026-07-12T00:05:00Z"},
            "visible_evidence_handle": "evidence:case-001",
            "diagnosis_handle": "lattice:case-001",
            "eligible_action_pack_ids": eligible_action_pack_ids or ["restart_connection_pool"],
            "required_evidence_classes": required_evidence_classes or ["metric", "log"],
            "partition_group": "shop-dbpool-2026w28",
            "release_role": "development",
        }
    ).to_dict()


def _evidence() -> dict[str, list[dict[str, object]]]:
    return {
        "case-001": [
            {"evidence_id": "pool_waiters", "evidence_class": "metric", "complete": True},
            {"evidence_id": "request_latency", "evidence_class": "log", "complete": True},
        ]
    }


def test_deterministic_rule_baseline_selects_only_frozen_safe_eligible_pack_and_hashes_bytes() -> None:
    report = deterministic_rule_baseline(
        [_incident()],
        [_pack()],
        _evidence(),
        {"case-001": {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True}},
        {"case-001": {"active_schema_migration": False}},
    ).to_dict()
    repeat = deterministic_rule_baseline(
        [_incident()],
        [_pack()],
        _evidence(),
        {"case-001": {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True}},
        {"case-001": {"active_schema_migration": False}},
    ).to_dict()

    label = report["labels"][0]
    assert label["decision"] == "act"
    assert label["action_pack_ids"] == ["restart_connection_pool"]
    assert label["evidence_ids"] == ["pool_waiters", "request_latency"]
    assert label["authority_level"] == "L1"
    assert label["executed_actions"] == []
    assert report["counters"]["action_execution_count"] == 0
    assert report["counters"]["llm_call_count"] == 0
    assert report == repeat
    assert report["report_hash"] == stable_hash({key: value for key, value in report.items() if key != "report_hash"})


def test_safe_null_baseline_never_selects_action_pack_and_is_evidence_aware() -> None:
    complete = safe_null_baseline([_incident()], _evidence()).to_dict()
    missing = safe_null_baseline([_incident()], {"case-001": [{"evidence_id": "pool_waiters", "evidence_class": "metric"}]}).to_dict()

    assert complete["labels"][0]["decision"] == "no_action"
    assert complete["labels"][0]["action_pack_ids"] == []
    assert missing["labels"][0]["decision"] == "investigate_more"
    assert missing["labels"][0]["abstention_reason"] == "missing_required_evidence:log"
    assert complete["counters"]["action_execution_count"] == 0
    assert complete["counters"]["llm_call_count"] == 0


@pytest.mark.parametrize(
    ("pack_overrides", "prerequisites", "contraindications", "evidence", "expected_decision", "expected_reason"),
    [
        (
            {},
            {"pool_exhaustion_confirmed": True},
            {"active_schema_migration": False},
            _evidence(),
            "investigate_more",
            "missing_prerequisite:lab_target_confirmed",
        ),
        (
            {},
            {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True},
            {"active_schema_migration": True},
            _evidence(),
            "escalate",
            "active_or_unknown_contraindication:active_schema_migration",
        ),
        (
            {"reversibility": "irreversible"},
            {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True},
            {"active_schema_migration": False},
            _evidence(),
            "escalate",
            "risky_irreversible_action",
        ),
        (
            {"blast_radius": {"scope": "single_lab_service", "max_services": 1, "requires_human_authorization": True}},
            {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True},
            {"active_schema_migration": False},
            _evidence(),
            "escalate",
            "human_authorized_operation",
        ),
        (
            {},
            {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True},
            {"active_schema_migration": False},
            {"case-001": []},
            "investigate_more",
            "missing_required_evidence:metric",
        ),
        (
            {},
            {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True},
            {"active_schema_migration": False},
            {"case-001": [{"evidence_id": "pool_waiters", "evidence_class": "metric"}]},
            "investigate_more",
            "missing_required_evidence:log",
        ),
    ],
)
def test_deterministic_rule_baseline_fails_closed_for_incomplete_or_unsafe_inputs(
    pack_overrides: dict[str, object],
    prerequisites: dict[str, bool],
    contraindications: dict[str, bool],
    evidence: dict[str, list[dict[str, object]]],
    expected_decision: str,
    expected_reason: str,
) -> None:
    report = deterministic_rule_baseline([_incident()], [_pack(pack_overrides)], evidence, {"case-001": prerequisites}, {"case-001": contraindications}).to_dict()

    label = report["labels"][0]
    assert label["decision"] == expected_decision
    assert label["action_pack_ids"] == []
    assert label["abstention_reason"] == expected_reason
    assert report["counters"]["action_execution_count"] == 0


def test_deterministic_rule_baseline_fails_closed_for_unknown_or_unfrozen_packs() -> None:
    unknown = deterministic_rule_baseline([_incident(["missing_pack"])], [_pack()], _evidence(), {"case-001": {}}, {"case-001": {}}).to_dict()
    assert unknown["labels"][0]["decision"] == "investigate_more"
    assert unknown["labels"][0]["abstention_reason"] == "unknown_action_pack:missing_pack"

    tampered = copy.deepcopy(_pack())
    tampered["expected_evidence"] = ["pool_waiters"]
    with pytest.raises(P115BaselineError, match="unfrozen_action_pack"):
        deterministic_rule_baseline([_incident()], [tampered], _evidence(), {"case-001": {}}, {"case-001": {}})


@pytest.mark.parametrize(
    ("extra_evidence", "expected_decision"),
    [
        ([{"evidence_id": "privileged_scope_required", "evidence_class": "privileged_scope_required"}], "escalate"),
        (
            [
                {"evidence_id": "transient_recovery_pattern", "evidence_class": "transient_recovery_pattern"},
                {"evidence_id": "error_slope_negative", "evidence_class": "error_slope_negative"},
            ],
            "no_action",
        ),
    ],
)
def test_rule_baseline_treats_human_scope_and_natural_recovery_as_first_class_decisions(
    extra_evidence: list[dict[str, object]], expected_decision: str
) -> None:
    evidence = _evidence()
    evidence["case-001"].extend(extra_evidence)
    report = deterministic_rule_baseline(
        [_incident()],
        [_pack()],
        evidence,
        {"case-001": {"pool_exhaustion_confirmed": True, "lab_target_confirmed": True}},
        {"case-001": {"active_schema_migration": False}},
    ).to_dict()
    assert report["labels"][0]["decision"] == expected_decision
    assert report["labels"][0]["action_pack_ids"] == []
