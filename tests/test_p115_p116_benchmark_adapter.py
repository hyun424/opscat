from __future__ import annotations

from collections import Counter

from app.services.p115_p116_benchmark_adapter import build_p115_p116_benchmark_cases
from app.services.p115_scenario_matrix import REQUIRED_EVALUATOR_LABELS, ROADMAP_FAMILIES, build_p115_scenario_matrix


def test_adapter_covers_all_600_cases_and_15_families_deterministically() -> None:
    first = build_p115_p116_benchmark_cases()
    second = build_p115_p116_benchmark_cases()
    assert len(first) == 600
    assert {item.scenario.family for item in first} == set(ROADMAP_FAMILIES)
    assert [item.adapter_hash for item in first] == [item.adapter_hash for item in second]
    assert Counter(item.scenario.split for item in first) == {"development": 300, "holdout": 300}


def test_candidate_packets_do_not_encode_hidden_label_or_execution_authority() -> None:
    matrix = build_p115_scenario_matrix()
    labels = {str(item["case_id"]): str(item["evaluator_label"]) for item in matrix.evaluator_labels}
    adapted = build_p115_p116_benchmark_cases(matrix)
    forbidden = set(REQUIRED_EVALUATOR_LABELS) | {value.replace("_", "-") for value in REQUIRED_EVALUATOR_LABELS}

    for item in adapted:
        packet = item.candidate_packet
        serialized = str(packet).lower()
        assert labels[item.scenario.case_id] not in item.scenario.case_id
        assert not any(token in item.scenario.case_id for token in forbidden)
        assert packet["authority_level"] == "L1"
        assert packet["executed_actions"] == []
        assert "evaluator_label" not in serialized
        assert item.scenario.variant.startswith("variant_")


def test_hidden_semantics_are_operationally_observable_but_not_named() -> None:
    matrix = build_p115_scenario_matrix()
    labels = {str(item["case_id"]): str(item["evaluator_label"]) for item in matrix.evaluator_labels}
    adapted = {item.scenario.case_id: item for item in build_p115_p116_benchmark_cases(matrix)}

    for case_id, label in labels.items():
        item = adapted[case_id]
        evidence = set(item.scenario.visible_evidence)
        if label == "no_action":
            assert item.scenario.spontaneous_recovery is True
            assert "transient_recovery_pattern" in evidence
        elif label == "investigate_more":
            assert item.scenario.telemetry_coverage < 0.6
            assert item.outcome_contract_skeleton["evidence_sufficient"] is False
        elif label == "contraindicated":
            assert item.scenario.human_required is True
            assert item.outcome_contract_skeleton["human_authorized_only"] is True
        elif label == "harmful_or_ineffective":
            assert "first_mitigation_did_not_change_slo" in evidence
            assert item.scenario.required_actions != item.scenario.runbook_actions[:1]
