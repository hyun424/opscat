"""End-to-end measured P115 benchmark over the disposable P116 lab."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from app.services.p115_baselines import deterministic_rule_baseline, safe_null_baseline
from app.services.p115_evaluator import evaluate_p115_decisions
from app.services.p115_ontology import build_action_pack, build_incident_case, sign_action_pack_payload
from app.services.p115_p116_benchmark_adapter import build_p115_p116_benchmark_cases, p115_family_action_spec
from app.services.p115_scenario_matrix import ROADMAP_FAMILIES, build_p115_scenario_matrix
from app.services.p116_lab_runner import P116PairedLabRunner
from app.services.p116_release_evidence import produce_p116_release_evidence


def run_p115_outcome_benchmark(*, seeds: Sequence[int] = (11501,), sample_size: int = 20) -> dict[str, Any]:
    """Run frozen matrix twice and return measured baseline/evaluator evidence."""

    matrix = build_p115_scenario_matrix()
    adapted = build_p115_p116_benchmark_cases(matrix)
    scenarios = [item.scenario for item in adapted]
    runner = P116PairedLabRunner(sample_size=sample_size)
    primary = runner.run(cases=scenarios, seeds=seeds).to_dict()
    replay = runner.run(cases=scenarios, seeds=seeds).to_dict()
    p116_release = produce_p116_release_evidence(primary_run=primary, replay_run=replay)
    records = [dict(item) for item in p116_release["paired_outcome_records"]]
    records_by_case = {str(record["case_id"]): record for record in records}

    action_packs = _action_packs()
    incidents, evidence, prerequisites, contraindications = _baseline_inputs(matrix, adapted)
    safe_null = safe_null_baseline(incidents, evidence).to_dict()
    deterministic = deterministic_rule_baseline(
        incidents,
        action_packs,
        evidence,
        prerequisites,
        contraindications,
    ).to_dict()
    contracts: list[dict[str, Any]] = []
    for item in adapted:
        record = records_by_case[item.scenario.case_id]
        contract = dict(item.outcome_contract_skeleton)
        action_pack_id = str(contract["eligible_action_pack_ids"][0])
        contract["action_records"] = {action_pack_id: record["record_hash"]}
        contracts.append(contract)
    evaluator = evaluate_p115_decisions(
        deterministic["labels"],
        outcome_contracts=contracts,
        p116_records=records,
    )
    return {
        "schema_version": "p115.outcome_benchmark_run.v1",
        "safe_null_baseline": safe_null,
        "deterministic_baseline": deterministic,
        "evaluator_report": evaluator,
        "p116_release_evidence": p116_release,
    }


def _action_packs() -> list[dict[str, Any]]:
    key = b"opscat-p115-offline-benchmark-fixture-key"
    packs: list[dict[str, Any]] = []
    for family in ROADMAP_FAMILIES:
        marker, primary, secondary, _harmful = p115_family_action_spec(family)
        payload: dict[str, Any] = {
            "action_id": f"p115_pack_{family}_candidate_response",
            "action_family": f"{family}_candidate_response_pack",
            "description": f"Evidence-bound, validation-gated local lab response for {family}.",
            "prerequisites": ["lab_target_confirmed"],
            "contraindications": ["production_target_detected"],
            "reversibility": "reversible",
            "blast_radius": {"scope": "single_lab_service", "max_services": 1, "expected_harm": 0.0},
            "expected_effect": {"signal": f"{family}_slo", "direction": "recover", "benefit": 0.8},
            "expected_evidence": [marker],
            "validation_query": {"query_id": f"validate_{family}_slo", "read_only": True},
            "rollback_plan": {
                "rollback_id": f"restore_{family}_fixture",
                "declarative_only": True,
                "followup_action_ids": [primary, secondary],
            },
            "executor_disabled": True,
            "target_scope": "local_lab",
        }
        signature = sign_action_pack_payload(payload, key_id="p115-offline-fixture", key=key)
        packs.append(
            build_action_pack(
                {**payload, "signer_key_id": "p115-offline-fixture", "signature": signature},
                keyring={"p115-offline-fixture": key},
            ).to_dict()
        )
    return packs


def _baseline_inputs(
    matrix: Any,
    adapted: Sequence[Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, dict[str, bool]], dict[str, dict[str, bool]]]:
    matrix_by_id = {str(case["case_id"]): case for case in matrix.cases}
    incidents: list[dict[str, Any]] = []
    evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prerequisites: dict[str, dict[str, bool]] = {}
    contraindications: dict[str, dict[str, bool]] = {}
    for item in adapted:
        scenario = item.scenario
        source = matrix_by_id[scenario.case_id]
        required_classes = ["metric", "trace"] if scenario.telemetry_coverage < 0.6 else ["metric"]
        incident = build_incident_case(
            {
                "case_id": scenario.case_id,
                "source_family": str(source["source_family"]),
                "scenario_family": scenario.family,
                "topology_handle": str(source["topology_handle"]),
                "time_window": dict(source["time_window"]),
                "visible_evidence_handle": str(source["visible_evidence_handle"]),
                "diagnosis_handle": str(source["diagnosis_handle"]),
                "eligible_action_pack_ids": list(item.candidate_packet["eligible_action_pack_ids"]),
                "required_evidence_classes": required_classes,
                "partition_group": str(source["partition_group"]),
                "release_role": str(source["release_role"]),
            }
        ).to_dict()
        incidents.append(incident)
        evidence[scenario.case_id] = [
            {"evidence_id": evidence_id, "evidence_class": "metric", "complete": True}
            for evidence_id in scenario.visible_evidence
        ]
        prerequisites[scenario.case_id] = {"lab_target_confirmed": True}
        contraindications[scenario.case_id] = {"production_target_detected": False}
    return incidents, dict(evidence), prerequisites, contraindications


__all__ = ["run_p115_outcome_benchmark"]
