from __future__ import annotations

import copy

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p115_evaluator import P115EvaluationError, evaluate_p115_decisions


def _record(case_id: str, *, lift: float, qualified: bool, harmful: bool = False, natural: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "p116.paired_outcome_record.v1",
        "case_id": case_id,
        "family": "database_pool_exhaustion",
        "variant": "obvious",
        "split": "holdout",
        "seed": 11,
        "causal_attribution": {
            "selected_effective": qualified,
            "selected_utility_lift_over_no_action": lift,
            "natural_recovery_observed": natural,
            "wrong_action_harm_observed": True,
            "rollback_restored_safe_state": True,
            "qualified": qualified,
        },
        "collateral_harm": {"selected_action": {"harmful": harmful}},
        "reset_verification": {"same_scenario": True, "same_seed": True, "same_initial_state": True, "required_arms_present": True},
        "authority": {"production_mutation_enabled": False},
    }
    payload["record_hash"] = stable_hash(payload)
    return payload


def _label(case_id: str, decision: str, packs: list[str]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "p115.action_label.v1",
        "case_id": case_id,
        "decision": decision,
        "action_pack_ids": packs,
        "evidence_ids": ["ev-1"],
        "prerequisite_checks": {"ready": True},
        "contraindication_checks": {"blocked": False},
        "validation_plan": {"query_id": "validate"},
        "rollback_plan": {"rollback_id": "rollback"},
        "submitted_success": True,
    }
    payload["artifact_hash"] = stable_hash(payload)
    return payload


def test_scores_from_measured_outcome_not_submitted_success() -> None:
    good = _record("case-1", lift=0.4, qualified=True)
    harmful = _record("case-2", lift=-0.3, qualified=False, harmful=True)
    contracts = [
        {
            "case_id": "case-1",
            "family": "database_pool_exhaustion",
            "partition": "holdout",
            "evidence_sufficient": True,
            "human_authorized_only": False,
            "visible_evidence_ids": ["ev-1"],
            "action_records": {"restart_pool": good["record_hash"]},
        },
        {
            "case_id": "case-2",
            "family": "database_pool_exhaustion",
            "partition": "holdout",
            "evidence_sufficient": True,
            "human_authorized_only": False,
            "visible_evidence_ids": ["ev-1"],
            "action_records": {"restart_pool": harmful["record_hash"]},
        },
    ]
    labels = [_label("case-1", "act", ["restart_pool"]), _label("case-2", "act", ["restart_pool"])]

    report = evaluate_p115_decisions(labels, outcome_contracts=contracts, p116_records=[good, harmful])

    assert report["release_status"] == "p115_outcome_qualified"
    assert report["metrics"]["optimal_action_top1"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert report["metrics"]["harmful_action_selection_rate"]["numerator"] == 1
    assert report["metrics"]["outcome_weighted_utility"]["value"] == pytest.approx(0.05)


def test_natural_recovery_requires_no_action_and_missing_evidence_requires_investigation() -> None:
    natural = _record("case-natural", lift=0.2, qualified=False, natural=True)
    contracts = [
        {
            "case_id": "case-natural",
            "family": "network_delay",
            "partition": "holdout",
            "evidence_sufficient": True,
            "human_authorized_only": False,
            "visible_evidence_ids": ["ev-1"],
            "action_records": {"restart": natural["record_hash"]},
        },
        {
            "case_id": "case-missing",
            "family": "dns_failure",
            "partition": "holdout",
            "evidence_sufficient": False,
            "human_authorized_only": False,
            "visible_evidence_ids": ["ev-1"],
            "action_records": {},
        },
    ]
    labels = [_label("case-natural", "no_action", []), _label("case-missing", "investigate_more", [])]

    report = evaluate_p115_decisions(labels, outcome_contracts=contracts, p116_records=[natural])

    assert report["metrics"]["correct_no_action_rate"]["value"] == 1.0
    assert report["metrics"]["correct_investigate_more_rate"]["value"] == 1.0
    assert report["metrics"]["unnecessary_action_selection_rate"]["value"] == 0.0


def test_missing_p116_record_is_contract_ready_only_and_null_denominator_stays_null() -> None:
    contracts = [
        {
            "case_id": "case-1",
            "family": "queue_backlog",
            "partition": "development",
            "evidence_sufficient": True,
            "human_authorized_only": False,
            "visible_evidence_ids": ["ev-1"],
            "action_records": {"scale": "sha256:" + "a" * 64},
        }
    ]
    report = evaluate_p115_decisions([_label("case-1", "act", ["scale"])], outcome_contracts=contracts, p116_records=[])

    assert report["release_status"] == "p115_contract_ready"
    assert report["outcome_qualified"] is False
    assert report["metrics"]["correct_escalation_rate"]["denominator"] == 0
    assert report["metrics"]["correct_escalation_rate"]["value"] is None


def test_rejects_forged_record_hash_and_duplicate_case_contract() -> None:
    record = _record("case-1", lift=0.4, qualified=True)
    forged = copy.deepcopy(record)
    forged["causal_attribution"]["qualified"] = False  # type: ignore[index]
    contract = {
        "case_id": "case-1",
        "family": "database",
        "partition": "holdout",
        "evidence_sufficient": True,
        "human_authorized_only": False,
        "visible_evidence_ids": ["ev-1"],
        "action_records": {"restart": record["record_hash"]},
    }
    with pytest.raises(P115EvaluationError, match="p116_record_hash_mismatch"):
        evaluate_p115_decisions([_label("case-1", "act", ["restart"])], outcome_contracts=[contract], p116_records=[forged])

    with pytest.raises(P115EvaluationError, match="duplicate_outcome_contract"):
        evaluate_p115_decisions([_label("case-1", "act", ["restart"])], outcome_contracts=[contract, contract], p116_records=[record])
