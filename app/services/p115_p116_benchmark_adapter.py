"""Bridge the frozen P115 matrix into disposable P116 lab scenarios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.causal_remediation_benchmark import CausalScenario
from app.services.p110_evaluation import stable_hash
from app.services.p115_leakage_guard import require_leakage_free
from app.services.p115_scenario_matrix import P115ScenarioMatrix, build_p115_scenario_matrix

ADAPTER_SCHEMA_VERSION = "p115.p116_benchmark_adapter.v1"
_FAMILY_ACTIONS: dict[str, tuple[str, str, str, str]] = {
    "cpu": ("cpu_throttled_seconds_high", "scale_service", "tune_cpu_limit", "evict_bad_cache_key"),
    "memory": ("oom_kills_rising", "increase_memory_limit", "restart_service", "evict_bad_cache_key"),
    "disk": ("disk_free_bytes_low", "prune_safe_temp_files", "expand_storage", "restart_service"),
    "network_delay": ("dependency_timeout_rate_high", "enable_dependency_fallback", "shed_load", "restart_service"),
    "network_loss": ("packet_loss_high", "reroute_traffic", "shed_load", "restart_service"),
    "socket": ("open_file_descriptors_near_limit", "restart_service", "raise_fd_limit", "evict_bad_cache_key"),
    "deploy": ("deployment_revision_changed", "rollback_deploy", "restart_service", "evict_bad_cache_key"),
    "dependency": ("dependency_timeout_rate_high", "enable_dependency_fallback", "shed_load", "restart_service"),
    "database_pool": ("db_pool_wait_high", "recycle_connection_pool", "shed_load", "restart_service"),
    "queue": ("queue_lag_growing", "restart_consumer", "scale_consumer", "restart_service"),
    "dns": ("dns_resolution_failures", "switch_dns_resolver", "refresh_service_discovery", "restart_service"),
    "certificate": ("tls_certificate_expiring", "renew_certificate", "reroute_traffic", "restart_service"),
    "quota": ("provider_quota_remaining_low", "reduce_request_rate", "request_quota_review", "restart_service"),
    "cache": ("cache_miss_fanout_spike", "enable_request_coalescing", "disable_aggressive_retries", "restart_service"),
    "traffic": ("request_rate_above_capacity", "scale_service", "shed_load", "evict_bad_cache_key"),
}


class P115P116AdapterError(ValueError):
    """Raised when a matrix case cannot be safely represented in the lab."""


@dataclass(frozen=True)
class P115P116BenchmarkCase:
    scenario: CausalScenario
    candidate_packet: Mapping[str, Any]
    outcome_contract_skeleton: Mapping[str, Any]
    adapter_hash: str


def build_p115_p116_benchmark_cases(matrix: P115ScenarioMatrix | None = None) -> tuple[P115P116BenchmarkCase, ...]:
    source = matrix or build_p115_scenario_matrix()
    labels = {str(item["case_id"]): str(item["evaluator_label"]) for item in source.evaluator_labels}
    if len(labels) != len(source.cases):
        raise P115P116AdapterError("label_case_set_mismatch")
    results = [_adapt_case(case, labels[str(case["case_id"])]) for case in source.cases]
    results.sort(key=lambda item: item.scenario.case_id)
    return tuple(results)


def p115_family_action_spec(family: str) -> tuple[str, str, str, str]:
    try:
        return _FAMILY_ACTIONS[family]
    except KeyError as exc:
        raise P115P116AdapterError(f"unknown_family:{family}") from exc


def _adapt_case(case: Mapping[str, Any], evaluator_label: str) -> P115P116BenchmarkCase:
    family = str(case.get("scenario_family", ""))
    if family not in _FAMILY_ACTIONS:
        raise P115P116AdapterError(f"unknown_family:{family}")
    marker, primary, secondary, harmful = _FAMILY_ACTIONS[family]
    evidence = [marker, f"{family}_slo_regression"]
    required = [primary]
    runbook = [primary]
    spontaneous = False
    human_required = False
    telemetry = 0.95
    if evaluator_label == "no_action":
        evidence = ["transient_recovery_pattern", "error_slope_negative", f"{family}_slo_regression"]
        required = []
        runbook = ["observe_only"]
        spontaneous = True
    elif evaluator_label == "investigate_more":
        evidence.extend(("telemetry_gap_detected", "required_trace_missing"))
        telemetry = 0.35
    elif evaluator_label == "contraindicated":
        evidence.append("privileged_scope_required")
        human_required = True
    elif evaluator_label == "harmful_or_ineffective":
        evidence.append("first_mitigation_did_not_change_slo")
        required = [secondary]
        runbook = [primary, secondary]
    elif evaluator_label != "action":
        raise P115P116AdapterError(f"unknown_evaluator_label:{evaluator_label}")

    case_id = str(case["case_id"])
    action_pack_id = str(_required_sequence(case.get("eligible_action_pack_ids"))[0])
    scenario = CausalScenario(
        case_id=case_id,
        family=family,
        variant=_opaque_variant(case_id),
        split=str(case["release_role"]),
        symptom=f"{family} service-level objective regression",
        visible_evidence=tuple(evidence),
        runbook_actions=tuple(runbook),
        required_actions=tuple(required),
        harmful_actions=(harmful,),
        spontaneous_recovery=spontaneous,
        human_required=human_required,
        telemetry_coverage=telemetry,
        initial_availability=0.58,
        initial_latency_ms=850.0,
        initial_backlog=170.0,
        initial_correctness=0.92,
    )
    candidate_packet = {
        "schema_version": "p115.p116_candidate_packet.v1",
        "case_id": case_id,
        "scenario_family": family,
        "partition": str(case["release_role"]),
        "visible_evidence_ids": evidence,
        "eligible_action_pack_ids": [action_pack_id],
        "authority_level": "L1",
        "executed_actions": [],
    }
    require_leakage_free(candidate_packet, artifact_path="p115-p116-candidate.json")
    outcome_contract = {
        "schema_version": "p115.outcome_contract_skeleton.v1",
        "case_id": case_id,
        "family": family,
        "partition": str(case["release_role"]),
        "evidence_sufficient": evaluator_label != "investigate_more",
        "human_authorized_only": evaluator_label == "contraindicated",
        "visible_evidence_ids": evidence,
        "eligible_action_pack_ids": [action_pack_id],
        "action_records": {},
    }
    payload = {"scenario": _scenario_payload(scenario), "candidate_packet": candidate_packet, "outcome_contract_skeleton": outcome_contract}
    return P115P116BenchmarkCase(scenario, candidate_packet, outcome_contract, stable_hash(payload))


def _scenario_payload(scenario: CausalScenario) -> dict[str, Any]:
    return {
        "case_id": scenario.case_id,
        "family": scenario.family,
        "variant": scenario.variant,
        "split": scenario.split,
        "visible_evidence": list(scenario.visible_evidence),
        "runbook_actions": list(scenario.runbook_actions),
        "required_actions": list(scenario.required_actions),
        "harmful_actions": list(scenario.harmful_actions),
        "spontaneous_recovery": scenario.spontaneous_recovery,
        "human_required": scenario.human_required,
        "telemetry_coverage": scenario.telemetry_coverage,
    }


def _opaque_variant(case_id: str) -> str:
    return "variant_" + stable_hash({"case_id": case_id})[7:19]


def _required_sequence(value: Any) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P115P116AdapterError("missing_action_pack")
    return value


__all__ = [
    "ADAPTER_SCHEMA_VERSION",
    "P115P116AdapterError",
    "P115P116BenchmarkCase",
    "build_p115_p116_benchmark_cases",
    "p115_family_action_spec",
]
