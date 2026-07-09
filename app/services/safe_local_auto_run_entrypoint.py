"""P89 safe local auto-run entrypoint.

Composes P85-P88-style local/mock supervisor concepts into one operator-facing
entrypoint result. It loads deterministic fixture/config data, models bounded
cycles, records resume/report write plans, and explains why it stopped. It does
not execute commands, sleep, spawn processes or agents, call APIs, read
credentials, execute actions, or mutate production.
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
    "safe_local_auto_run_entrypoint_only": True,
    "models_cycles_as_data": True,
    "composes_p85_p86_p87_p88_contracts": True,
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


class SafeLocalStopReason(StrEnum):
    COMPLETED = "completed"
    NEEDS_HUMAN = "needs_human"
    FAILED_GUARDRAIL = "failed_guardrail"
    MAX_CYCLES = "max_cycles"
    NO_SAFE_WORK = "no_safe_work"


@dataclass(frozen=True)
class SafeLocalCycle:
    cycle_id: str
    status: str
    iterations: int
    budget_units: int
    human_reason: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            cycle_id=str(data.get("cycle_id", "p89-cycle")),
            status=str(data.get("status", "no_safe_work")).lower(),
            iterations=max(0, int(_float(data.get("iterations"), 0.0))),
            budget_units=max(0, int(_float(data.get("budget_units"), 0.0))),
            human_reason=str(data.get("human_reason", "approval_required")),
        )


@dataclass(frozen=True)
class SafeLocalEntrypointScenario:
    id: str
    entrypoint_id: str
    dry_run: bool
    resume: bool
    max_cycles: int
    max_iterations: int
    budgets: Mapping[str, Any]
    wakeup_policy: Mapping[str, Any]
    backoff_policy: Mapping[str, Any]
    resume_state_path: str
    report_path: str
    initial_state: Mapping[str, Any]
    cycles: tuple[SafeLocalCycle, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            entrypoint_id=str(data.get("entrypoint_id", "p89-entrypoint")),
            dry_run=data.get("dry_run") is not False,
            resume=data.get("resume") is True,
            max_cycles=max(1, int(_float(data.get("max_cycles"), 1.0))),
            max_iterations=max(1, int(_float(data.get("max_iterations"), 1.0))),
            budgets=_mapping(data.get("budgets")),
            wakeup_policy=_mapping(data.get("wakeup_policy")),
            backoff_policy=_mapping(data.get("backoff_policy")),
            resume_state_path=str(data.get("resume_state_path", "/tmp/opscat-p89-state.json")),
            report_path=str(data.get("report_path", "/tmp/opscat-p89-report.md")),
            initial_state=_mapping(data.get("initial_state")),
            cycles=tuple(
                SafeLocalCycle.from_dict(item) for item in _sequence(data.get("cycles", ())) if isinstance(item, Mapping)
            ),
        )


@dataclass(frozen=True)
class SafeLocalEntrypointRun:
    scenario: SafeLocalEntrypointScenario
    scheduled_cycles: tuple[Mapping[str, Any], ...]
    stop_reason: SafeLocalStopReason
    terminal_status: str
    next_scheduled_wakeup: Mapping[str, Any] | None
    next_recommended_command: str
    human_handoff_summary: Mapping[str, Any]
    failure_report: Mapping[str, Any]
    completed_cycle_ids: tuple[str, ...]
    initial_completed_cycle_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario.id,
            "entrypoint_id": self.scenario.entrypoint_id,
            "dry_run": self.scenario.dry_run,
            "resumed": self.scenario.resume,
            "config_summary": {
                "max_cycles": self.scenario.max_cycles,
                "max_iterations": self.scenario.max_iterations,
                "budgets": dict(self.scenario.budgets),
                "wakeup_policy": dict(self.scenario.wakeup_policy),
                "backoff_policy": dict(self.scenario.backoff_policy),
            },
            "scheduled_cycles": [dict(cycle) for cycle in self.scheduled_cycles],
            "scheduled_cycle_ids": list(self.completed_cycle_ids),
            "resume_state_metadata": {
                "path": self.scenario.resume_state_path,
                "resumed_from_checkpoint": self.scenario.resume,
                "initial_completed_cycle_ids": list(self.initial_completed_cycle_ids),
            },
            "resume_state_write_plan": _write_plan(self.scenario.resume_state_path, "json"),
            "generated_report_metadata": {"path": self.scenario.report_path, "format": "markdown"},
            "report_write_plan": _write_plan(self.scenario.report_path, "md"),
            "terminal_status": self.terminal_status,
            "stop_reason": self.stop_reason.value,
            "next_scheduled_wakeup": dict(self.next_scheduled_wakeup) if self.next_scheduled_wakeup else None,
            "next_recommended_command": self.next_recommended_command,
            "human_handoff_summary": dict(self.human_handoff_summary),
            "failure_report": dict(self.failure_report),
            "audit_metadata": {
                "audit_id": f"p89:{self.scenario.entrypoint_id}",
                "local_mock_only": True,
                "p89_safe_local_auto_run_entrypoint": True,
                "composes_p85_p86_p87_p88_contracts": True,
                "side_effect_free": True,
                "dry_run": self.scenario.dry_run,
                "resume": self.scenario.resume,
                "unattended_production_operation_claimed": False,
            },
            "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class SafeLocalAutoRunEntrypointReport:
    suite: Mapping[str, Any]
    scenarios: tuple[SafeLocalEntrypointScenario, ...]
    runs: tuple[SafeLocalEntrypointRun, ...]

    @classmethod
    def from_scenarios(cls, suite: Mapping[str, Any], scenarios: Sequence[SafeLocalEntrypointScenario]) -> Self:
        return cls(suite=suite, scenarios=tuple(scenarios), runs=tuple(_run_scenario(scenario) for scenario in scenarios))

    def to_dict(self) -> dict[str, Any]:
        runs = [run.to_dict() for run in self.runs]
        summary: dict[str, Any] = {
            "suite_id": str(self.suite.get("id", "p89-safe-local-auto-run-entrypoint")),
            "scenario_count": len(runs),
            "dry_run_count": sum(1 for run in runs if run["dry_run"] is True),
            "resumed_count": sum(1 for run in runs if run["resumed"] is True),
            "completed_count": _stop_count(self.runs, SafeLocalStopReason.COMPLETED),
            "needs_human_count": _stop_count(self.runs, SafeLocalStopReason.NEEDS_HUMAN),
            "failed_guardrail_count": _stop_count(self.runs, SafeLocalStopReason.FAILED_GUARDRAIL),
            "max_cycles_count": _stop_count(self.runs, SafeLocalStopReason.MAX_CYCLES),
            "no_safe_work_count": _stop_count(self.runs, SafeLocalStopReason.NO_SAFE_WORK),
            "executions": 0,
            **_ZERO_SIDE_EFFECT_COUNTERS,
        }
        summary["passed"] = (
            summary["scenario_count"] >= 6
            and summary["completed_count"] >= 2
            and summary["needs_human_count"] >= 1
            and summary["failed_guardrail_count"] >= 1
            and summary["max_cycles_count"] >= 1
            and summary["no_safe_work_count"] >= 1
            and all(summary[key] == 0 for key in _ZERO_SIDE_EFFECT_COUNTERS)
        )
        payload = {
            "summary": summary,
            "boundary": dict(_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "entrypoint_runs": runs,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_safe_local_auto_run_entrypoint_fixture(path: str | Path) -> SafeLocalAutoRunEntrypointReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite = _mapping(data.get("suite"))
    scenarios = tuple(
        SafeLocalEntrypointScenario.from_dict(item)
        for item in _sequence(data.get("scenarios", ()))
        if isinstance(item, Mapping)
    )
    return SafeLocalAutoRunEntrypointReport.from_scenarios(suite, scenarios)


def render_safe_local_auto_run_entrypoint_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Safe Local Auto-Run Entrypoint",
        "",
        (
            "P89 models one safe local/mock auto-run entrypoint over supervisor, runner, report, and scheduler "
            "contracts. It emits write plans and next commands as data only; it is not a real daemon and not "
            "unattended production operation."
        ),
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Dry run: {summary.get('dry_run_count', 0)}",
        f"- Resumed: {summary.get('resumed_count', 0)}",
        f"- Completed: {summary.get('completed_count', 0)}",
        f"- Needs human: {summary.get('needs_human_count', 0)}",
        f"- Failed guardrail: {summary.get('failed_guardrail_count', 0)}",
        f"- Max cycles: {summary.get('max_cycles_count', 0)}",
        f"- No safe work: {summary.get('no_safe_work_count', 0)}",
        f"- Executions: {summary.get('executions', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Entrypoint runs",
        "",
    ]
    for run in _sequence(payload.get("entrypoint_runs", ())):
        if not isinstance(run, Mapping):
            continue
        lines.extend(
            [
                f"### {run.get('scenario_id', 'scenario')}",
                "",
                f"- Entrypoint ID: {run.get('entrypoint_id')}",
                f"- Dry run: {run.get('dry_run')}",
                f"- Resumed: {run.get('resumed')}",
                f"- Terminal status: {run.get('terminal_status')}",
                f"- Stop reason: {run.get('stop_reason')}",
                f"- Scheduled cycles: {', '.join(str(item) for item in _sequence(run.get('scheduled_cycle_ids'))) or 'none'}",
                f"- Resume state path: {_mapping(run.get('resume_state_metadata')).get('path')}",
                f"- Report path: {_mapping(run.get('generated_report_metadata')).get('path')}",
                f"- Next command: {run.get('next_recommended_command')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            "- Safe local auto-run entrypoint contract only.",
            "- Cycles, wakeups, checkpoint state, report writes, and next commands are modeled data.",
            "- No live APIs, credentials, network calls, shell execution, sleeping, process spawning, agent spawning, production mutation, remediation execution, or action execution.",
            "- This is not a real daemon and not unattended production operation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_safe_local_auto_run_entrypoint_outputs(
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
        output_md_path.write_text(render_safe_local_auto_run_entrypoint_markdown(payload), encoding="utf-8")


def _run_scenario(scenario: SafeLocalEntrypointScenario) -> SafeLocalEntrypointRun:
    initial_completed_ids = _unique_strings(_sequence(scenario.initial_state.get("completed_cycle_ids", ())))
    completed_ids = list(initial_completed_ids)
    scheduled: list[Mapping[str, Any]] = []
    stop_reason: SafeLocalStopReason | None = None
    next_wakeup: Mapping[str, Any] | None = None
    human_handoff: Mapping[str, Any] = {"required": False, "reason": "none", "summary": "No human handoff required."}
    failure_report: Mapping[str, Any] = {"required": False, "reason": "none", "summary": "No guardrail failure."}

    for cycle in scenario.cycles:
        if cycle.cycle_id in completed_ids:
            scheduled.append(_cycle_event(cycle, event="resume_skip_completed_cycle", executed=False))
            continue
        if len([item for item in scheduled if item.get("event") == "modeled_cycle"]) >= scenario.max_cycles:
            stop_reason = SafeLocalStopReason.MAX_CYCLES
            next_wakeup = {"reason": "resume_after_max_cycles", "after_minutes": 15, "modeled_only": True}
            break
        if cycle.status == SafeLocalStopReason.NO_SAFE_WORK.value:
            stop_reason = SafeLocalStopReason.NO_SAFE_WORK
            next_wakeup = {
                "reason": "no_safe_work_recheck",
                "after_minutes": max(1, int(_float(scenario.backoff_policy.get("no_safe_work_base_minutes"), 45.0))),
                "modeled_only": True,
            }
            break

        scheduled.append(_cycle_event(cycle, event="modeled_cycle", executed=False))
        completed_ids.append(cycle.cycle_id)

        if cycle.status == "completed_all":
            stop_reason = SafeLocalStopReason.COMPLETED
            break
        if cycle.status == SafeLocalStopReason.NEEDS_HUMAN.value:
            stop_reason = SafeLocalStopReason.NEEDS_HUMAN
            next_wakeup = {"reason": "human_review_required", "after_minutes": 0, "modeled_only": True}
            human_handoff = {
                "required": True,
                "reason": cycle.human_reason,
                "summary": "Human approval required before continuing modeled local work.",
                "blocking_cycle_id": cycle.cycle_id,
            }
            break
        if cycle.status == SafeLocalStopReason.FAILED_GUARDRAIL.value:
            stop_reason = SafeLocalStopReason.FAILED_GUARDRAIL
            next_wakeup = {"reason": "guardrail_review_required", "after_minutes": 0, "modeled_only": True}
            failure_report = {
                "required": True,
                "reason": "guardrail_failed",
                "summary": "Guardrail failure stopped the safe local auto-run entrypoint.",
                "failing_cycle_id": cycle.cycle_id,
            }
            break

    if stop_reason is None:
        stop_reason = SafeLocalStopReason.COMPLETED if scenario.cycles else SafeLocalStopReason.NO_SAFE_WORK
    return SafeLocalEntrypointRun(
        scenario=scenario,
        scheduled_cycles=tuple(scheduled),
        stop_reason=stop_reason,
        terminal_status=_terminal_status(stop_reason),
        next_scheduled_wakeup=next_wakeup,
        next_recommended_command=_next_command(stop_reason, scenario),
        human_handoff_summary=human_handoff,
        failure_report=failure_report,
        completed_cycle_ids=tuple(completed_ids),
        initial_completed_cycle_ids=tuple(initial_completed_ids),
    )


def _cycle_event(cycle: SafeLocalCycle, *, event: str, executed: bool) -> Mapping[str, Any]:
    return {
        "cycle_id": cycle.cycle_id,
        "event": event,
        "p86_runner_stop_reason": "max_iterations" if cycle.status == "max_iterations" else cycle.status,
        "p87_report_status": "max_iterations" if cycle.status == "max_iterations" else cycle.status,
        "p88_scheduler_modeled": True,
        "iterations": cycle.iterations,
        "budget_units": cycle.budget_units,
        "executed": executed,
    }


def _terminal_status(stop_reason: SafeLocalStopReason) -> str:
    if stop_reason == SafeLocalStopReason.COMPLETED:
        return "completed"
    if stop_reason == SafeLocalStopReason.NEEDS_HUMAN:
        return "needs_human"
    if stop_reason == SafeLocalStopReason.FAILED_GUARDRAIL:
        return "failed_guardrail"
    if stop_reason == SafeLocalStopReason.NO_SAFE_WORK:
        return "scheduled_recheck"
    return "resumable"


def _next_command(stop_reason: SafeLocalStopReason, scenario: SafeLocalEntrypointScenario) -> str:
    if stop_reason == SafeLocalStopReason.COMPLETED:
        return f"Review {scenario.report_path}"
    if stop_reason == SafeLocalStopReason.NEEDS_HUMAN:
        return "Open the generated report and resolve the human approval gate."
    if stop_reason == SafeLocalStopReason.FAILED_GUARDRAIL:
        return "Review guardrail failure report before any resume attempt."
    if stop_reason == SafeLocalStopReason.MAX_CYCLES:
        return (
            "python scripts/run_safe_local_auto_run_entrypoint.py --cases "
            "evals/actions/p89_safe_local_auto_run_entrypoint.json --resume"
        )
    return "Re-run the safe local auto-run entrypoint after the modeled recheck window."


def _write_plan(final_path: str, suffix: str) -> Mapping[str, Any]:
    return {
        "atomic_write_plan": {
            "temp_path": f"{final_path}.tmp",
            "final_path": final_path,
            "operation": "write_temp_then_replace",
            "format": suffix,
            "executed": False,
        }
    }


def _stop_count(runs: Sequence[SafeLocalEntrypointRun], stop_reason: SafeLocalStopReason) -> int:
    return sum(1 for run in runs if run.stop_reason == stop_reason)


def _unique_strings(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values))


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
    "SafeLocalAutoRunEntrypointReport",
    "SafeLocalStopReason",
    "evaluate_safe_local_auto_run_entrypoint_fixture",
    "render_safe_local_auto_run_entrypoint_markdown",
    "write_safe_local_auto_run_entrypoint_outputs",
]
