"""P90 safe auto-run readiness gate.

Evaluates P89-style safe local auto-run output plus prior local/mock safety
evidence to decide which longer-running local or shadow mode can be trusted.
It is a readiness gate only: no live APIs, credentials, network, shell,
production mutation, action execution, or production unattended approval.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value

_GATE_WEIGHTS: dict[str, int] = {
    "evidence": 16,
    "approval_safety": 12,
    "sandbox_safety": 12,
    "resume_safety": 10,
    "reportability": 12,
    "bounded_scheduling": 10,
    "zero_side_effects": 16,
    "human_handoff": 6,
    "failure_handling": 6,
}
_ZERO_SIDE_EFFECT_COUNTERS: dict[str, int] = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "shell_execution_count": 0,
    "process_spawn_count": 0,
    "agent_spawn_count": 0,
    "sleep_call_count": 0,
}
_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "safe_auto_run_readiness_gate_only": True,
    "models_p89_entrypoint_result": True,
    "consumes_prior_safety_evidence": True,
    "live_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "process_spawn_enabled": False,
    "agent_spawn_enabled": False,
    "sleep_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_FORBIDDEN_CLAIMS = (
    "unattended_production_ready",
    "operator_replacement_approved",
    "production_mutation_safe",
    "live_api_operation_approved",
)


class P90ReadinessLevel(StrEnum):
    NOT_READY = "not_ready"
    LOCAL_DRY_RUN_READY = "local_dry_run_ready"
    SUPERVISED_SHADOW_READY = "supervised_shadow_ready"
    HUMAN_GATED_STAGING_READY = "human_gated_staging_ready"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SafeAutoRunReadinessScenario:
    id: str
    p89_entrypoint: Mapping[str, Any]
    prior_evidence: Mapping[str, Any]
    human_severity: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            p89_entrypoint=_mapping(data.get("p89_entrypoint")),
            prior_evidence=_mapping(data.get("prior_evidence")),
            human_severity=str(data.get("human_severity", "none")).lower(),
        )


@dataclass(frozen=True)
class SafeAutoRunReadinessResult:
    scenario: SafeAutoRunReadinessScenario
    readiness_level: P90ReadinessLevel
    score: int
    gates: Mapping[str, Mapping[str, Any]]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    required_next_capabilities: tuple[str, ...]
    allowed_operating_mode: str

    def to_dict(self) -> dict[str, Any]:
        counters = _side_effect_counters(self.scenario.p89_entrypoint)
        payload = {
            "scenario_id": self.scenario.id,
            "readiness_level": self.readiness_level.value,
            "score": self.score,
            "component_scores": _component_scores(self.gates),
            "gates": {key: dict(value) for key, value in self.gates.items()},
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "required_next_capabilities": list(self.required_next_capabilities),
            "allowed_operating_mode": self.allowed_operating_mode,
            "forbidden_claims": list(_FORBIDDEN_CLAIMS),
            "audit_metadata": {
                "audit_id": f"p90:{self.scenario.id}",
                "p90_safe_auto_run_readiness_gate": True,
                "consumes_p89_entrypoint_result": True,
                "consumes_p76_p79_p80_p83_p84_p87_p88_evidence": True,
                "local_mock_only": True,
                "side_effect_free": all(value == 0 for value in counters.values()),
                "not_production_unattended_approval": True,
            },
            "zero_side_effect_counters": counters,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class SafeAutoRunReadinessGateReport:
    suite: Mapping[str, Any]
    scenarios: tuple[SafeAutoRunReadinessScenario, ...]
    results: tuple[SafeAutoRunReadinessResult, ...]

    @classmethod
    def from_scenarios(cls, suite: Mapping[str, Any], scenarios: Sequence[SafeAutoRunReadinessScenario]) -> Self:
        return cls(suite=suite, scenarios=tuple(scenarios), results=tuple(_evaluate(item) for item in scenarios))

    def to_dict(self) -> dict[str, Any]:
        results = [result.to_dict() for result in self.results]
        summary: dict[str, Any] = {
            "suite_id": str(self.suite.get("id", "p90-safe-auto-run-readiness-gate")),
            "scenario_count": len(results),
            "local_ready_count": _level_count(self.results, P90ReadinessLevel.LOCAL_DRY_RUN_READY),
            "shadow_ready_count": _level_count(self.results, P90ReadinessLevel.SUPERVISED_SHADOW_READY),
            "human_gated_count": _level_count(self.results, P90ReadinessLevel.HUMAN_GATED_STAGING_READY),
            "not_ready_count": _level_count(self.results, P90ReadinessLevel.NOT_READY),
            "blocked_count": _level_count(self.results, P90ReadinessLevel.BLOCKED),
            "executions": 0,
            **_ZERO_SIDE_EFFECT_COUNTERS,
        }
        summary["passed"] = (
            summary["scenario_count"] >= 6
            and summary["local_ready_count"] >= 1
            and summary["shadow_ready_count"] >= 1
            and summary["human_gated_count"] >= 1
            and summary["not_ready_count"] >= 1
            and summary["blocked_count"] >= 2
            and summary["executions"] == 0
        )
        payload = {
            "summary": summary,
            "boundary": dict(_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "readiness_results": results,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_safe_auto_run_readiness_gate_fixture(path: str | Path) -> SafeAutoRunReadinessGateReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite = _mapping(data.get("suite"))
    scenarios = tuple(
        SafeAutoRunReadinessScenario.from_dict(item)
        for item in _sequence(data.get("scenarios", ()))
        if isinstance(item, Mapping)
    )
    return SafeAutoRunReadinessGateReport.from_scenarios(suite, scenarios)


def render_safe_auto_run_readiness_gate_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat P90 Safe Auto-Run Readiness Gate",
        "",
        (
            "P90 scores P89-style safe local auto-run readiness for longer local dry-run, supervised shadow, "
            "or human-gated staging dry-run operation. It is not production unattended approval."
        ),
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Local dry-run ready: {summary.get('local_ready_count', 0)}",
        f"- Supervised shadow ready: {summary.get('shadow_ready_count', 0)}",
        f"- Human-gated staging ready: {summary.get('human_gated_count', 0)}",
        f"- Not ready: {summary.get('not_ready_count', 0)}",
        f"- Blocked: {summary.get('blocked_count', 0)}",
        f"- Executions: {summary.get('executions', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Readiness results",
        "",
    ]
    for result in _sequence(payload.get("readiness_results", ())):
        if not isinstance(result, Mapping):
            continue
        lines.extend(
            [
                f"### {result.get('scenario_id', 'scenario')}",
                "",
                f"- Level: {result.get('readiness_level')}",
                f"- Score: {result.get('score')}",
                f"- Allowed mode: {result.get('allowed_operating_mode')}",
                f"- Blockers: {', '.join(str(item) for item in _sequence(result.get('blockers'))) or 'none'}",
                f"- Warnings: {', '.join(str(item) for item in _sequence(result.get('warnings'))) or 'none'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            "- Local/mock readiness gate only.",
            "- Consumes modeled P89 entrypoint output and prior P76/P79/P80/P83/P84/P87/P88 evidence.",
            "- No live APIs, credentials, network, shell execution, sleeping, process spawning, agents, actions, or production mutation.",
            "- This is not production unattended approval and not operator replacement approval.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_safe_auto_run_readiness_gate_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        output_json_path = Path(output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md_path = Path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_safe_auto_run_readiness_gate_markdown(payload), encoding="utf-8")


def _evaluate(scenario: SafeAutoRunReadinessScenario) -> SafeAutoRunReadinessResult:
    gates = _gates(scenario)
    blockers = _blockers(scenario, gates)
    warnings = _warnings(scenario)
    score = sum(_GATE_WEIGHTS[gate_id] for gate_id, gate in gates.items() if gate["passed"])
    level = _readiness_level(scenario, gates, blockers, score)
    if level == P90ReadinessLevel.BLOCKED:
        score = min(score, 60)
    return SafeAutoRunReadinessResult(
        scenario=scenario,
        readiness_level=level,
        score=score,
        gates=gates,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        required_next_capabilities=tuple(_required_next_capabilities(level, blockers)),
        allowed_operating_mode=_allowed_mode(level),
    )


def _gates(scenario: SafeAutoRunReadinessScenario) -> dict[str, Mapping[str, Any]]:
    evidence = scenario.prior_evidence
    entrypoint = scenario.p89_entrypoint
    counters = _side_effect_counters(entrypoint)
    failure = str(entrypoint.get("stop_reason", "")).lower() == "failed_guardrail"
    gates = {
        "evidence": bool(evidence.get("p76_evidence_sufficiency")),
        "approval_safety": bool(evidence.get("p80_approval_policy")),
        "sandbox_safety": bool(evidence.get("p79_sandbox_safety")),
        "resume_safety": bool(entrypoint.get("resume_safe")),
        "reportability": bool(entrypoint.get("report_present")) and bool(evidence.get("p87_report")),
        "bounded_scheduling": bool(entrypoint.get("bounded_scheduler")) and bool(evidence.get("p88_scheduler_stop_reason")),
        "zero_side_effects": all(value == 0 for value in counters.values()),
        "human_handoff": _human_handoff_safe(scenario),
        "failure_handling": not failure and bool(evidence.get("p83_closed_loop_outcome")) and bool(evidence.get("p84_next_action_plan")),
    }
    return {
        key: {
            "passed": passed,
            "score": _GATE_WEIGHTS[key] if passed else 0,
            "max_score": _GATE_WEIGHTS[key],
            "reason": _gate_reason(key, passed),
        }
        for key, passed in gates.items()
    }


def _human_handoff_safe(scenario: SafeAutoRunReadinessScenario) -> bool:
    status = str(scenario.p89_entrypoint.get("terminal_status", "")).lower()
    required = scenario.p89_entrypoint.get("human_handoff_required") is True
    if status == "needs_human":
        return required and scenario.human_severity not in {"critical", "destructive"}
    return True


def _blockers(scenario: SafeAutoRunReadinessScenario, gates: Mapping[str, Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    stop_reason = str(scenario.p89_entrypoint.get("stop_reason", "")).lower()
    if not gates["evidence"]["passed"]:
        blockers.append("p76_evidence_sufficiency_missing")
    if not gates["reportability"]["passed"]:
        blockers.append("p87_report_missing")
    if not gates["zero_side_effects"]["passed"]:
        blockers.append("side_effect_counter_non_zero")
    if stop_reason == "failed_guardrail" or not gates["failure_handling"]["passed"]:
        blockers.append("guardrail_failure_requires_fix_before_auto_run")
    if not gates["approval_safety"]["passed"]:
        blockers.append("p80_approval_policy_missing")
    if not gates["sandbox_safety"]["passed"]:
        blockers.append("p79_sandbox_safety_missing")
    return list(dict.fromkeys(blockers))


def _warnings(scenario: SafeAutoRunReadinessScenario) -> list[str]:
    warnings: list[str] = []
    status = str(scenario.p89_entrypoint.get("terminal_status", "")).lower()
    if status == "resumable":
        warnings.append("incomplete_run_requires_supervised_resume")
    if status == "needs_human":
        warnings.append("human_review_required_before_continue")
    return warnings


def _readiness_level(
    scenario: SafeAutoRunReadinessScenario,
    gates: Mapping[str, Mapping[str, Any]],
    blockers: Sequence[str],
    score: int,
) -> P90ReadinessLevel:
    stop_reason = str(scenario.p89_entrypoint.get("stop_reason", "")).lower()
    status = str(scenario.p89_entrypoint.get("terminal_status", "")).lower()
    hard_blockers = {"side_effect_counter_non_zero", "guardrail_failure_requires_fix_before_auto_run"}
    if any(blocker in hard_blockers for blocker in blockers):
        return P90ReadinessLevel.BLOCKED
    if blockers:
        return P90ReadinessLevel.NOT_READY
    if status == "needs_human":
        return P90ReadinessLevel.HUMAN_GATED_STAGING_READY
    if status == "resumable" or stop_reason == "max_cycles":
        return P90ReadinessLevel.SUPERVISED_SHADOW_READY
    if score >= 90 and all(gate["passed"] for gate in gates.values()):
        return P90ReadinessLevel.LOCAL_DRY_RUN_READY
    return P90ReadinessLevel.NOT_READY


def _required_next_capabilities(level: P90ReadinessLevel, blockers: Sequence[str]) -> list[str]:
    required = [
        "live_read_only_soak_testing",
        "operator_handoff_sla_contract",
        "production_credential_boundary_review",
        "human_override_and_abort_controls",
        "long_duration_local_soak_evidence",
    ]
    if level == P90ReadinessLevel.BLOCKED:
        required.insert(0, "resolve_blockers_before_any_auto_run")
    if blockers:
        required.extend(blockers)
    return list(dict.fromkeys(required))


def _allowed_mode(level: P90ReadinessLevel) -> str:
    if level == P90ReadinessLevel.LOCAL_DRY_RUN_READY:
        return "local_dry_run_only"
    if level == P90ReadinessLevel.SUPERVISED_SHADOW_READY:
        return "supervised_shadow_only"
    if level == P90ReadinessLevel.HUMAN_GATED_STAGING_READY:
        return "human_gated_staging_dry_run"
    return "no_auto_run"


def _component_scores(gates: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return {key: int(_float(value.get("score"))) for key, value in gates.items()}


def _side_effect_counters(entrypoint: Mapping[str, Any]) -> dict[str, int]:
    raw = _mapping(entrypoint.get("zero_side_effect_counters"))
    return {key: max(0, int(_float(raw.get(key), 0.0))) for key in _ZERO_SIDE_EFFECT_COUNTERS}


def _level_count(results: Sequence[SafeAutoRunReadinessResult], level: P90ReadinessLevel) -> int:
    return sum(1 for result in results if result.readiness_level == level)


def _gate_reason(gate_id: str, passed: bool) -> str:
    state = "passed" if passed else "failed"
    return f"{gate_id} gate {state} for P90 local/mock readiness."


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "P90ReadinessLevel",
    "SafeAutoRunReadinessGateReport",
    "evaluate_safe_auto_run_readiness_gate_fixture",
    "render_safe_auto_run_readiness_gate_markdown",
    "write_safe_auto_run_readiness_gate_outputs",
]
