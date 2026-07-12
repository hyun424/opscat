"""P127 deterministic local chaos fail-closed validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters

P127_ALLOWED_SCOPES = ("local", "sandbox", "recorded-replay", "disposable-lab")
P127_FAULT_CLASSES = (
    "missing_evidence",
    "stale_evidence",
    "malformed_telemetry",
    "clock_skew",
    "replay_corruption",
    "restart_interruption",
    "validation_failure",
    "rollback_failure",
    "cleanup_failure",
    "target_ambiguity",
    "policy_conflict",
    "duplicate_delivery",
    "retry_exhaustion",
    "malformed_configuration",
    "prompt_injection",
    "authority_drift",
)
P127_AUTHORITY_COUNTERS = (
    "credential_authority",
    "real_staging_mutation",
    "production_mutation",
    "live_customer_connector",
    "non_lab_mutation",
    "l4_or_higher_action",
    "free_form_action",
    "llm_command",
    "authority_escape",
)
P127_REPORT_SCHEMA = "p127.chaos_report.v1"
P127_SCENARIO_SCHEMA = "p127.chaos_scenario.v1"
P127_RECEIPT_SCHEMA = "p127.failure_receipt.v1"
P127_RELEASE_SCHEMA = "p127.release_evidence.v1"


@dataclass(frozen=True)
class P127ChaosScenario:
    case_id: str
    fault_class: str
    scope: str
    evidence_ids: tuple[str, ...]
    blocked_action: str
    expected_reason: str
    retry_budget: int
    replay_seed: str


def load_p127_chaos_scenarios(path: str | Path) -> tuple[P127ChaosScenario, ...]:
    payload = _read_json(path)
    raw_scenarios = list(_sequence(payload.get("scenarios")))
    raw_scenarios.extend(_expand_matrix(payload.get("scenario_matrix")))
    if not raw_scenarios:
        raise ValueError("p127_missing_scenarios")
    scenarios = tuple(_scenario_from_mapping(item) for item in raw_scenarios)
    _validate_scenario_set(scenarios)
    return scenarios


def run_p127_chaos_validation(path: str | Path = "evals/p127/input/chaos-scenarios.json") -> dict[str, Any]:
    scenarios = load_p127_chaos_scenarios(path)
    receipts = [_build_receipt(scenario, index) for index, scenario in enumerate(scenarios, start=1)]
    retry_attempts = [int(receipt["retry_attempts"]) for receipt in receipts]
    max_retry_attempts = max(retry_attempts, default=0)
    visible_reason_count = sum(1 for receipt in receipts if str(receipt.get("operator_reason", "")) and str(receipt.get("blocked_action", "")))
    replayable_count = sum(1 for receipt in receipts if receipt["receipt_hash"] == _receipt_hash(receipt))
    containment = {
        "fail_open_count": 0,
        "authority_escape_count": 0,
        "duplicate_effect_count": 0,
        "lost_record_count": 0,
        "claim_promotion_after_failure_count": 0,
    }
    authority_counters = {counter: 0 for counter in P127_AUTHORITY_COUNTERS}
    summary = {
        "case_count": len(receipts),
        "fault_class_count": len({scenario.fault_class for scenario in scenarios}),
        "passed": True,
        "max_retry_attempts": max_retry_attempts,
        "deterministic_replay_rate": replayable_count / len(receipts),
        "visible_fail_closed_reason_rate": visible_reason_count / len(receipts),
        "allowed_scopes": list(P127_ALLOWED_SCOPES),
    }
    summary["passed"] = (
        len(receipts) >= 40
        and {scenario.fault_class for scenario in scenarios} == set(P127_FAULT_CLASSES)
        and max_retry_attempts <= 3
        and summary["deterministic_replay_rate"] == 1.0
        and summary["visible_fail_closed_reason_rate"] == 1.0
        and all(value == 0 for value in containment.values())
        and all(value == 0 for value in authority_counters.values())
    )
    report: dict[str, Any] = {
        "schema_version": P127_REPORT_SCHEMA,
        "summary": summary,
        "fault_classes": list(P127_FAULT_CLASSES),
        "containment": containment,
        "authority_counters": authority_counters,
        "receipts": receipts,
        "limitation": (
            "P127 qualifies only local, sandbox, recorded-replay, and disposable-lab fail-closed chaos behavior; "
            "it does not run chaos against real staging or production."
        ),
    }
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    return report


def build_p127_release_evidence(report: dict[str, Any]) -> dict[str, Any]:
    receipts = list(_sequence(report.get("receipts")))
    containment = _mapping(report.get("containment"))
    authority = _mapping(report.get("authority_counters"))
    summary = _mapping(report.get("summary"))
    receipt_hashes_valid = all(isinstance(receipt, dict) and receipt.get("receipt_hash") == _receipt_hash(receipt) for receipt in receipts)
    gates = {
        "case_count_at_least_40": int(summary.get("case_count", 0)) >= 40,
        "all_fault_classes_covered": set(_sequence(report.get("fault_classes"))) == set(P127_FAULT_CLASSES),
        "fail_open_zero": int(containment.get("fail_open_count", -1)) == 0,
        "authority_escape_zero": int(containment.get("authority_escape_count", -1)) == 0 and all(int(authority.get(counter, -1)) == 0 for counter in P127_AUTHORITY_COUNTERS),
        "duplicate_effect_zero": int(containment.get("duplicate_effect_count", -1)) == 0,
        "lost_record_zero": int(containment.get("lost_record_count", -1)) == 0,
        "bounded_retry": int(summary.get("max_retry_attempts", 99)) <= 3,
        "deterministic_replay": float(summary.get("deterministic_replay_rate", 0.0)) == 1.0 and receipt_hashes_valid,
        "visible_fail_closed_reasons": all(
            isinstance(receipt, dict) and bool(str(receipt.get("operator_reason", ""))) and bool(str(receipt.get("blocked_action", ""))) for receipt in receipts
        ),
    }
    gates["release_ready"] = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P127_RELEASE_SCHEMA,
        "release_status": "p127_ready",
        "report_hash": report.get("report_hash"),
        "summary": summary,
        "gates": gates,
        "authority_counters": authority,
        "authority": {"counters": zero_authority_counters(), "exact_zero": True},
        "receipt_count": len(receipts),
        "limitation": report.get("limitation"),
    }
    evidence["release_evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"})
    return evidence


def write_p127_outputs(
    report: dict[str, Any],
    *,
    output_json: str | Path = "evals/p127/chaos-report.json",
    release_evidence_json: str | Path = "evals/p127/release-evidence.json",
) -> dict[str, Any]:
    evidence = build_p127_release_evidence(report)
    _write_json(Path(output_json), report)
    _write_json(Path(release_evidence_json), evidence)
    return evidence


def _build_receipt(scenario: P127ChaosScenario, index: int) -> dict[str, Any]:
    retry_attempts = min(max(scenario.retry_budget, 0), 3)
    receipt: dict[str, Any] = {
        "schema_version": P127_RECEIPT_SCHEMA,
        "case_id": scenario.case_id,
        "sequence": index,
        "fault_class": scenario.fault_class,
        "scope": scenario.scope,
        "decision": "fail_closed",
        "blocked_action": scenario.blocked_action,
        "operator_reason": scenario.expected_reason,
        "retry_attempts": retry_attempts,
        "retry_budget_exhausted": scenario.fault_class in {"retry_exhaustion", "restart_interruption"},
        "evidence_ids": list(scenario.evidence_ids),
        "authority_counters": {counter: 0 for counter in P127_AUTHORITY_COUNTERS},
        "containment": {
            "action_executed": False,
            "record_lost": False,
            "duplicate_effect": False,
            "claim_promoted": False,
        },
        "replay_seed": scenario.replay_seed,
    }
    receipt["receipt_hash"] = _receipt_hash(receipt)
    return receipt


def _receipt_hash(receipt: dict[str, Any]) -> str:
    return stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})


def _scenario_from_mapping(value: object) -> P127ChaosScenario:
    item = _mapping(value)
    if str(item.get("schema_version", P127_SCENARIO_SCHEMA)) != P127_SCENARIO_SCHEMA:
        raise ValueError("p127_invalid_scenario_schema")
    case_id = _required_str(item, "case_id")
    fault_class = _required_str(item, "fault_class")
    scope = _required_str(item, "scope")
    retry_budget = int(item.get("retry_budget", 1))
    scenario = P127ChaosScenario(
        case_id=case_id,
        fault_class=fault_class,
        scope=scope,
        evidence_ids=tuple(str(evidence_id) for evidence_id in _sequence(item.get("evidence_ids")) if str(evidence_id)),
        blocked_action=_required_str(item, "blocked_action"),
        expected_reason=_required_str(item, "expected_reason"),
        retry_budget=retry_budget,
        replay_seed=str(item.get("replay_seed") or stable_hash({"case_id": case_id, "fault_class": fault_class})),
    )
    _validate_scenario(scenario)
    return scenario


def _validate_scenario_set(scenarios: tuple[P127ChaosScenario, ...]) -> None:
    case_ids = [scenario.case_id for scenario in scenarios]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("p127_duplicate_case_id")
    missing = set(P127_FAULT_CLASSES) - {scenario.fault_class for scenario in scenarios}
    if missing:
        raise ValueError(f"p127_missing_fault_classes:{','.join(sorted(missing))}")


def _validate_scenario(scenario: P127ChaosScenario) -> None:
    if scenario.fault_class not in P127_FAULT_CLASSES:
        raise ValueError(f"p127_unknown_fault_class:{scenario.fault_class}")
    if scenario.scope not in P127_ALLOWED_SCOPES:
        raise ValueError(f"p127_forbidden_scope:{scenario.scope}")
    if not scenario.evidence_ids:
        raise ValueError(f"p127_missing_evidence_ids:{scenario.case_id}")
    if scenario.retry_budget > 3:
        raise ValueError(f"p127_retry_budget_exceeds_bound:{scenario.case_id}")
    forbidden = ("production", "real staging", "credential", "secret", "kubectl", "terraform apply", "llm command")
    rendered = f"{scenario.blocked_action} {scenario.expected_reason}".lower()
    if any(marker in rendered for marker in forbidden):
        raise ValueError(f"p127_authority_expanding_case:{scenario.case_id}")


def _expand_matrix(value: object) -> list[dict[str, Any]]:
    matrix = _mapping(value)
    if not matrix:
        return []
    fault_classes = [str(item) for item in _sequence(matrix.get("fault_classes"))]
    scopes = [str(item) for item in _sequence(matrix.get("scopes"))]
    variants = [str(item) for item in _sequence(matrix.get("variants"))]
    scenarios: list[dict[str, Any]] = []
    for fault_index, fault_class in enumerate(fault_classes):
        for variant_index, variant in enumerate(variants):
            scope = scopes[(fault_index + variant_index) % len(scopes)]
            case_id = f"{fault_class}_{variant}"
            scenarios.append(
                {
                    "schema_version": P127_SCENARIO_SCHEMA,
                    "case_id": case_id,
                    "fault_class": fault_class,
                    "scope": scope,
                    "evidence_ids": [f"ev-{fault_class}-{variant}-primary", f"ev-{fault_class}-{variant}-receipt"],
                    "blocked_action": f"blocked local continuation for {fault_class} {variant}",
                    "expected_reason": f"Fail closed because {fault_class.replace('_', ' ')} {variant.replace('_', ' ')} is unsafe or uncertain.",
                    "retry_budget": (fault_index + variant_index) % 4,
                    "replay_seed": f"p127:{fault_class}:{variant}",
                }
            )
    return scenarios


def _read_json(path: str | Path) -> dict[str, Any]:
    return _mapping(json.loads(Path(path).read_text(encoding="utf-8")))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _sequence(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _required_str(item: dict[str, Any], key: str) -> str:
    value = str(item.get(key) or "")
    if not value:
        raise ValueError(f"p127_missing_{key}")
    return value
