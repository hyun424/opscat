"""P88 bounded local supervisor scheduler contract.

Models a bounded local scheduler over P86-style runner states and P87-style
report statuses. It produces schedule decisions as data only; it does not
sleep, spawn processes, execute commands/actions, call APIs, read credentials,
or mutate production.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "bounded_scheduler_contract_only": True,
    "models_schedule_decisions_as_data": True,
    "consumes_p86_runner_state": True,
    "consumes_p87_report_status": True,
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


class SchedulerStopReason(StrEnum):
    COMPLETED_ALL = "completed_all"
    MAX_CYCLES = "max_cycles"
    NEEDS_HUMAN = "needs_human"
    FAILED_GUARDRAIL = "failed_guardrail"
    NO_SAFE_WORK = "no_safe_work"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class SchedulerLimits:
    max_cycles: int
    modeled_wall_clock_budget_minutes: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            max_cycles=max(1, int(_float(data.get("max_cycles"), 1.0))),
            modeled_wall_clock_budget_minutes=max(1, int(_float(data.get("modeled_wall_clock_budget_minutes"), 1.0))),
        )


@dataclass(frozen=True)
class SchedulerBackoffSettings:
    failure_base_minutes: int
    no_safe_work_base_minutes: int
    max_delay_minutes: int
    failure_streak_limit: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            failure_base_minutes=max(1, int(_float(data.get("failure_base_minutes"), 10.0))),
            no_safe_work_base_minutes=max(1, int(_float(data.get("no_safe_work_base_minutes"), 30.0))),
            max_delay_minutes=max(1, int(_float(data.get("max_delay_minutes"), 120.0))),
            failure_streak_limit=max(1, int(_float(data.get("failure_streak_limit"), 2.0))),
        )


@dataclass(frozen=True)
class ModeledRunState:
    run_state_id: str
    run_id: str
    p86_stop_reason: str
    p87_report_status: str
    terminal_classification: str
    human_decision_required: Mapping[str, Any]
    next_recommended_wakeup: Mapping[str, Any] | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        p87 = _mapping(data.get("p87_report"))
        return cls(
            run_state_id=str(data.get("run_state_id", "run-state")),
            run_id=str(data.get("run_id", "p88-modeled-run")),
            p86_stop_reason=str(data.get("p86_stop_reason", p87.get("status", "no_safe_work"))),
            p87_report_status=str(p87.get("status", data.get("p86_stop_reason", "no_safe_work"))),
            terminal_classification=str(p87.get("terminal_classification", "resumable")),
            human_decision_required=_mapping(p87.get("human_decision_required")),
            next_recommended_wakeup=_optional_mapping(data.get("next_recommended_wakeup")),
        )


@dataclass(frozen=True)
class SchedulerScenario:
    id: str
    scheduler_id: str
    limits: SchedulerLimits
    backoff: SchedulerBackoffSettings
    run_states: tuple[ModeledRunState, ...]
    checkpoint_final_path: str
    initial_state: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            scheduler_id=str(data.get("scheduler_id", "p88-scheduler")),
            limits=SchedulerLimits.from_dict(_mapping(data.get("limits"))),
            backoff=SchedulerBackoffSettings.from_dict(_mapping(data.get("backoff_policy"))),
            run_states=tuple(
                ModeledRunState.from_dict(item)
                for item in _sequence(data.get("run_states", ()))
                if isinstance(item, Mapping)
            ),
            checkpoint_final_path=str(data.get("checkpoint_final_path", "/tmp/opscat-p88-scheduler-state.json")),
            initial_state=_mapping(data.get("initial_state")),
        )


@dataclass(frozen=True)
class SchedulerPlan:
    scenario_id: str
    scheduler_id: str
    current_cycle_index: int
    max_cycles: int
    modeled_wall_clock_budget_minutes: int
    modeled_elapsed_minutes: int
    next_scheduled_wakeup: Mapping[str, Any] | None
    selected_run_state_ids: tuple[str, ...]
    terminal_classification: str
    stop_reason: SchedulerStopReason
    cycles: tuple[Mapping[str, Any], ...]
    backoff_policy: Mapping[str, Any]
    checkpoint_write_plan: Mapping[str, Any]
    human_handoff: Mapping[str, Any] | None
    audit_metadata: Mapping[str, Any]
    resume_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "scheduler_id": self.scheduler_id,
            "current_cycle_index": self.current_cycle_index,
            "max_cycles": self.max_cycles,
            "modeled_wall_clock_budget_minutes": self.modeled_wall_clock_budget_minutes,
            "modeled_elapsed_minutes": self.modeled_elapsed_minutes,
            "next_scheduled_wakeup": dict(self.next_scheduled_wakeup) if self.next_scheduled_wakeup else None,
            "selected_run_state_ids": list(self.selected_run_state_ids),
            "terminal_classification": self.terminal_classification,
            "stop_reason": self.stop_reason.value,
            "cycles": [dict(cycle) for cycle in self.cycles],
            "backoff_policy": dict(self.backoff_policy),
            "checkpoint_write_plan": dict(self.checkpoint_write_plan),
            "human_handoff": dict(self.human_handoff) if self.human_handoff else None,
            "audit_metadata": dict(self.audit_metadata),
            "resume_metadata": dict(self.resume_metadata),
            "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class BoundedLocalSupervisorSchedulerReport:
    suite: Mapping[str, Any]
    scenarios: tuple[SchedulerScenario, ...]
    plans: tuple[SchedulerPlan, ...]

    @classmethod
    def from_scenarios(cls, suite: Mapping[str, Any], scenarios: Sequence[SchedulerScenario]) -> Self:
        return cls(suite=suite, scenarios=tuple(scenarios), plans=tuple(_plan_scenario(scenario) for scenario in scenarios))

    def to_dict(self) -> dict[str, Any]:
        plans = [plan.to_dict() for plan in self.plans]
        summary: dict[str, Any] = {
            "suite_id": str(self.suite.get("id", "p88-bounded-local-supervisor-scheduler")),
            "scenario_count": len(plans),
            "completed_all_count": _stop_count(self.plans, SchedulerStopReason.COMPLETED_ALL),
            "max_cycles_count": _stop_count(self.plans, SchedulerStopReason.MAX_CYCLES),
            "needs_human_count": _stop_count(self.plans, SchedulerStopReason.NEEDS_HUMAN),
            "failed_guardrail_count": _stop_count(self.plans, SchedulerStopReason.FAILED_GUARDRAIL),
            "no_safe_work_count": _stop_count(self.plans, SchedulerStopReason.NO_SAFE_WORK),
            "budget_exhausted_count": _stop_count(self.plans, SchedulerStopReason.BUDGET_EXHAUSTED),
            "executions": 0,
            **_ZERO_SIDE_EFFECT_COUNTERS,
        }
        summary["passed"] = (
            summary["scenario_count"] >= 6
            and summary["completed_all_count"] >= 2
            and summary["max_cycles_count"] >= 1
            and summary["needs_human_count"] >= 1
            and summary["failed_guardrail_count"] >= 1
            and summary["budget_exhausted_count"] >= 1
            and all(summary[key] == 0 for key in _ZERO_SIDE_EFFECT_COUNTERS)
        )
        payload = {
            "summary": summary,
            "boundary": dict(_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "scheduler_plans": plans,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_bounded_local_supervisor_scheduler_fixture(path: str | Path) -> BoundedLocalSupervisorSchedulerReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite = _mapping(data.get("suite"))
    scenarios = tuple(
        SchedulerScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping)
    )
    return BoundedLocalSupervisorSchedulerReport.from_scenarios(suite, scenarios)


def render_bounded_local_supervisor_scheduler_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Bounded Local Supervisor Scheduler Contract",
        "",
        (
            "P88 models bounded local scheduler decisions over P86 runner state and P87 report status. "
            "It emits wakeup and checkpoint plans as data only; it is not a daemon and does not perform unattended production operation."
        ),
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Completed all: {summary.get('completed_all_count', 0)}",
        f"- Max cycles: {summary.get('max_cycles_count', 0)}",
        f"- Needs human: {summary.get('needs_human_count', 0)}",
        f"- Failed guardrail: {summary.get('failed_guardrail_count', 0)}",
        f"- Budget exhausted: {summary.get('budget_exhausted_count', 0)}",
        f"- Executions: {summary.get('executions', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Scheduler plans",
        "",
    ]
    for plan in _sequence(payload.get("scheduler_plans", ())):
        if not isinstance(plan, Mapping):
            continue
        lines.extend(
            [
                f"### {plan.get('scenario_id', 'scenario')}",
                "",
                f"- Scheduler ID: {plan.get('scheduler_id')}",
                f"- Stop reason: {plan.get('stop_reason')}",
                f"- Classification: {plan.get('terminal_classification')}",
                f"- Cycle index: {plan.get('current_cycle_index')}/{plan.get('max_cycles')}",
                f"- Selected run states: {', '.join(str(item) for item in _sequence(plan.get('selected_run_state_ids'))) or 'none'}",
                f"- Next wakeup: {plan.get('next_scheduled_wakeup') or 'none'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            "- Bounded local scheduler contract only.",
            "- Consumes modeled P86 runner state and P87 report status.",
            "- Wakeups, backoff, and checkpoint writes are metadata only; there is no real sleeping, daemon, process spawning, shell execution, or action execution.",
            "- No live APIs, credentials, network calls, production mutation, remediation execution, or unattended production-operation claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_bounded_local_supervisor_scheduler_outputs(
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
        output_md_path.write_text(render_bounded_local_supervisor_scheduler_markdown(payload), encoding="utf-8")


def _plan_scenario(scenario: SchedulerScenario) -> SchedulerPlan:
    initial_cycle_index = max(0, int(_float(scenario.initial_state.get("cycle_index"), 0.0)))
    selected_ids = [str(item) for item in _sequence(scenario.initial_state.get("selected_run_state_ids", ()))]
    current_cycle_index = initial_cycle_index
    elapsed_minutes = max(0, int(_float(scenario.initial_state.get("modeled_elapsed_minutes"), 0.0)))
    failure_streak = max(0, int(_float(scenario.initial_state.get("failure_streak"), 0.0)))
    no_safe_work_streak = max(0, int(_float(scenario.initial_state.get("no_safe_work_streak"), 0.0)))
    cycles: list[Mapping[str, Any]] = []
    stop_reason: SchedulerStopReason | None = None
    next_wakeup: Mapping[str, Any] | None = None
    human_handoff: Mapping[str, Any] | None = None

    for run_state in scenario.run_states:
        if run_state.run_state_id in selected_ids:
            cycles.append(
                {
                    "cycle_index": current_cycle_index,
                    "run_state_id": run_state.run_state_id,
                    "event": "resume_skip_selected",
                    "p86_stop_reason": run_state.p86_stop_reason,
                    "p87_report_status": run_state.p87_report_status,
                    "terminal_classification": run_state.terminal_classification,
                    "executed": False,
                }
            )
            continue

        if current_cycle_index >= scenario.limits.max_cycles:
            stop_reason = SchedulerStopReason.MAX_CYCLES
            next_wakeup = _wakeup("resume_after_max_cycles", 15)
            break

        report_status = run_state.p87_report_status
        scheduler_status = _scheduler_status(report_status)
        delay = _delay_for_status(scheduler_status, scenario.backoff, failure_streak, no_safe_work_streak)
        if elapsed_minutes + delay > scenario.limits.modeled_wall_clock_budget_minutes:
            stop_reason = SchedulerStopReason.BUDGET_EXHAUSTED
            next_wakeup = _wakeup("budget_exhausted", delay)
            break

        current_cycle_index += 1
        elapsed_minutes += delay
        selected_ids.append(run_state.run_state_id)
        if scheduler_status == SchedulerStopReason.FAILED_GUARDRAIL.value:
            failure_streak += 1
        elif scheduler_status == SchedulerStopReason.NO_SAFE_WORK.value:
            no_safe_work_streak += 1
        else:
            failure_streak = 0
            no_safe_work_streak = 0

        cycle = {
            "cycle_index": current_cycle_index,
            "run_state_id": run_state.run_state_id,
            "run_id": run_state.run_id,
            "event": "modeled_resume_invocation",
            "p86_stop_reason": run_state.p86_stop_reason,
            "p87_report_status": report_status,
            "terminal_classification": _cycle_classification(scheduler_status, run_state),
            "next_recommended_wakeup": run_state.next_recommended_wakeup,
            "backoff": {"delay_minutes": delay, "modeled_sleep_executed": False},
            "executed": False,
        }
        cycles.append(cycle)

        if scheduler_status == SchedulerStopReason.COMPLETED_ALL.value:
            stop_reason = SchedulerStopReason.COMPLETED_ALL
            next_wakeup = None
            break
        if scheduler_status == SchedulerStopReason.NEEDS_HUMAN.value:
            stop_reason = SchedulerStopReason.NEEDS_HUMAN
            next_wakeup = _wakeup("human_review_required", 0)
            human_handoff = {
                "required": True,
                "reason": str(run_state.human_decision_required.get("reason", "approval_required")),
                "run_state_id": run_state.run_state_id,
            }
            break
        if scheduler_status == SchedulerStopReason.FAILED_GUARDRAIL.value and failure_streak >= scenario.backoff.failure_streak_limit:
            stop_reason = SchedulerStopReason.FAILED_GUARDRAIL
            next_wakeup = _wakeup("guardrail_review_required", 0)
            break

    if stop_reason is None:
        if current_cycle_index >= scenario.limits.max_cycles:
            stop_reason = SchedulerStopReason.MAX_CYCLES
            next_wakeup = _wakeup("resume_after_max_cycles", 15)
        elif elapsed_minutes >= scenario.limits.modeled_wall_clock_budget_minutes:
            stop_reason = SchedulerStopReason.BUDGET_EXHAUSTED
            next_wakeup = _wakeup("budget_exhausted", 0)
        else:
            stop_reason = SchedulerStopReason.NO_SAFE_WORK
            next_wakeup = _wakeup("no_safe_work_recheck", scenario.backoff.no_safe_work_base_minutes)

    return SchedulerPlan(
        scenario_id=scenario.id,
        scheduler_id=scenario.scheduler_id,
        current_cycle_index=current_cycle_index,
        max_cycles=scenario.limits.max_cycles,
        modeled_wall_clock_budget_minutes=scenario.limits.modeled_wall_clock_budget_minutes,
        modeled_elapsed_minutes=elapsed_minutes,
        next_scheduled_wakeup=next_wakeup,
        selected_run_state_ids=tuple(selected_ids),
        terminal_classification=_plan_classification(stop_reason),
        stop_reason=stop_reason,
        cycles=tuple(cycles),
        backoff_policy={
            "failure_base_minutes": scenario.backoff.failure_base_minutes,
            "no_safe_work_base_minutes": scenario.backoff.no_safe_work_base_minutes,
            "max_delay_minutes": scenario.backoff.max_delay_minutes,
            "failure_streak_limit": scenario.backoff.failure_streak_limit,
            "failure_streak": failure_streak,
            "no_safe_work_streak": no_safe_work_streak,
        },
        checkpoint_write_plan=_checkpoint_write_plan(scenario, current_cycle_index, selected_ids, stop_reason),
        human_handoff=human_handoff,
        audit_metadata={
            "audit_id": f"p88:{scenario.scheduler_id}",
            "local_mock_only": True,
            "p88_bounded_scheduler_contract": True,
            "consumes_p86_runner_state": True,
            "consumes_p87_report_status": True,
            "wakeups_are_modeled_metadata_only": True,
            "unattended_production_operation_claimed": False,
        },
        resume_metadata={
            "resumed_from_state": bool(scenario.initial_state),
            "initial_cycle_index": initial_cycle_index,
            "initial_selected_run_state_ids": [str(item) for item in _sequence(scenario.initial_state.get("selected_run_state_ids", ()))],
        },
    )


def _scheduler_status(status: str) -> str:
    return "max_cycles" if status == "max_iterations" else status


def _delay_for_status(
    status: str,
    backoff: SchedulerBackoffSettings,
    failure_streak: int,
    no_safe_work_streak: int,
) -> int:
    if status == SchedulerStopReason.FAILED_GUARDRAIL.value:
        return min(backoff.max_delay_minutes, backoff.failure_base_minutes * (2**failure_streak))
    if status == SchedulerStopReason.NO_SAFE_WORK.value:
        return min(backoff.max_delay_minutes, backoff.no_safe_work_base_minutes * (2**no_safe_work_streak))
    return 0


def _cycle_classification(status: str, run_state: ModeledRunState) -> str:
    if status in {SchedulerStopReason.COMPLETED_ALL.value, SchedulerStopReason.NEEDS_HUMAN.value}:
        return "terminal"
    if status == SchedulerStopReason.FAILED_GUARDRAIL.value:
        return "resumable"
    return run_state.terminal_classification if run_state.terminal_classification in {"terminal", "resumable"} else "resumable"


def _plan_classification(stop_reason: SchedulerStopReason) -> str:
    if stop_reason in {
        SchedulerStopReason.COMPLETED_ALL,
        SchedulerStopReason.NEEDS_HUMAN,
        SchedulerStopReason.FAILED_GUARDRAIL,
        SchedulerStopReason.NO_SAFE_WORK,
    }:
        return "terminal"
    return "resumable"


def _wakeup(reason: str, delay_minutes: int) -> Mapping[str, Any]:
    return {"reason": reason, "after_minutes": max(0, delay_minutes), "modeled_only": True}


def _checkpoint_write_plan(
    scenario: SchedulerScenario,
    current_cycle_index: int,
    selected_ids: Sequence[str],
    stop_reason: SchedulerStopReason,
) -> Mapping[str, Any]:
    final_path = scenario.checkpoint_final_path
    return {
        "checkpoint_id": f"{scenario.scheduler_id}:checkpoint:{current_cycle_index}",
        "cycle_index": current_cycle_index,
        "selected_run_state_ids": list(selected_ids),
        "stop_reason": stop_reason.value,
        "atomic_write_plan": {
            "temp_path": f"{final_path}.{current_cycle_index}.tmp",
            "final_path": final_path,
            "operation": "write_temp_then_replace",
            "executed": False,
        },
    }


def _stop_count(plans: Sequence[SchedulerPlan], stop_reason: SchedulerStopReason) -> int:
    return sum(1 for plan in plans if plan.stop_reason == stop_reason)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "BoundedLocalSupervisorSchedulerReport",
    "SchedulerStopReason",
    "evaluate_bounded_local_supervisor_scheduler_fixture",
    "render_bounded_local_supervisor_scheduler_markdown",
    "write_bounded_local_supervisor_scheduler_outputs",
]
