"""P86 resumable local supervisor runner.

Models repeated P85-style supervisor iterations from a JSON state contract. It
persists checkpoint plans as atomic temp-to-final metadata only; it never
executes commands, spawns agents/processes, calls APIs, reads credentials, or
mutates production.
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
    "resumable_runner_only": True,
    "live_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "process_spawn_enabled": False,
    "agent_spawn_enabled": False,
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
}

_SAFE_P76 = {"approval_ready", "sufficient_read_only"}
_SAFE_P79 = {"allow", "mock_only"}
_SAFE_P80 = {"auto_approve", "mock_only"}


class ResumableSupervisorStopReason(StrEnum):
    MAX_ITERATIONS = "max_iterations"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NEEDS_HUMAN = "needs_human"
    FAILED_GUARDRAIL = "failed_guardrail"
    NO_SAFE_WORK = "no_safe_work"
    COMPLETED_ALL = "completed_all"


@dataclass(frozen=True)
class ResumableSupervisorLimits:
    max_iterations: int
    max_budget_units: int
    failure_streak_limit: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            max_iterations=max(0, int(_float(data.get("max_iterations"), 1.0))),
            max_budget_units=max(0, int(_float(data.get("max_budget_units"), 1.0))),
            failure_streak_limit=max(1, int(_float(data.get("failure_streak_limit"), 1.0))),
        )


@dataclass(frozen=True)
class ResumableSupervisorWorkItem:
    id: str
    title: str
    budget_units: int
    p76_decision: str
    p79_decision: str
    p80_decision: str
    human_approval_required: bool
    dry_run_command_name: str
    mock_step_result: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        p76 = _mapping(data.get("p76_gate"))
        p79 = _mapping(data.get("p79_sandbox"))
        p80 = _mapping(data.get("p80_approval"))
        next_action = _mapping(data.get("p84_next_action"))
        return cls(
            id=str(data.get("id", "work-item")),
            title=str(data.get("title", "Local supervisor work item")),
            budget_units=max(1, int(_float(data.get("budget_units"), 1.0))),
            p76_decision=str(p76.get("decision", "")).lower(),
            p79_decision=str(p79.get("decision", "")).lower(),
            p80_decision=str(p80.get("decision", "")).lower(),
            human_approval_required=next_action.get("human_approval_required") is True,
            dry_run_command_name=str(data.get("dry_run_command_name", "local-mock-check")),
            mock_step_result=str(data.get("mock_step_result", "passed")).lower(),
        )


@dataclass(frozen=True)
class ResumableSupervisorScenario:
    id: str
    run_id: str
    limits: ResumableSupervisorLimits
    backlog: tuple[ResumableSupervisorWorkItem, ...]
    initial_state: Mapping[str, Any]
    checkpoint_final_path: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            run_id=str(data.get("run_id", "p86-run")),
            limits=ResumableSupervisorLimits.from_dict(_mapping(data.get("limits"))),
            backlog=tuple(
                ResumableSupervisorWorkItem.from_dict(item)
                for item in _sequence(data.get("backlog", ()))
                if isinstance(item, Mapping)
            ),
            initial_state=_mapping(data.get("initial_state")),
            checkpoint_final_path=str(data.get("checkpoint_final_path", "/tmp/opscat-p86-state.json")),
        )


@dataclass(frozen=True)
class ResumableSupervisorRunState:
    scenario_id: str
    run_id: str
    cursor: int
    completed_item_ids: tuple[str, ...]
    selected_item_ids: tuple[str, ...]
    skipped_items: tuple[Mapping[str, str], ...]
    iteration_count: int
    failure_streak: int
    checkpoints: tuple[Mapping[str, Any], ...]
    stop_reason: ResumableSupervisorStopReason
    next_recommended_wakeup: Mapping[str, Any] | None
    terminal_recommendation: Mapping[str, Any] | None
    audit_metadata: Mapping[str, Any]
    resume_metadata: Mapping[str, Any]
    modeled_steps: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "cursor": self.cursor,
            "completed_item_ids": list(self.completed_item_ids),
            "selected_item_ids": list(self.selected_item_ids),
            "skipped_item_ids": [item["item_id"] for item in self.skipped_items],
            "skipped_items": [dict(item) for item in self.skipped_items],
            "iteration_count": self.iteration_count,
            "failure_streak": self.failure_streak,
            "checkpoints": [dict(item) for item in self.checkpoints],
            "stop_reason": self.stop_reason.value,
            "next_recommended_wakeup": dict(self.next_recommended_wakeup) if self.next_recommended_wakeup else None,
            "terminal_recommendation": dict(self.terminal_recommendation) if self.terminal_recommendation else None,
            "audit_metadata": dict(self.audit_metadata),
            "resume_metadata": dict(self.resume_metadata),
            "modeled_steps": [dict(item) for item in self.modeled_steps],
            "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ResumableLocalSupervisorReport:
    suite: Mapping[str, Any]
    scenarios: tuple[ResumableSupervisorScenario, ...]
    runs: tuple[ResumableSupervisorRunState, ...]

    @classmethod
    def from_scenarios(cls, suite: Mapping[str, Any], scenarios: Sequence[ResumableSupervisorScenario]) -> Self:
        return cls(suite=suite, scenarios=tuple(scenarios), runs=tuple(_run_scenario(scenario) for scenario in scenarios))

    def to_dict(self) -> dict[str, Any]:
        run_dicts = [run.to_dict() for run in self.runs]
        payload = {
            "summary": {
                "suite_id": str(self.suite.get("id", "p86-resumable-local-supervisor-runner")),
                "scenario_count": len(self.scenarios),
                "resumed_count": sum(1 for run in self.runs if run.resume_metadata.get("resumed_from_state") is True),
                "completed_all_count": _stop_count(self.runs, ResumableSupervisorStopReason.COMPLETED_ALL),
                "max_iteration_count": _stop_count(self.runs, ResumableSupervisorStopReason.MAX_ITERATIONS),
                "needs_human_count": _stop_count(self.runs, ResumableSupervisorStopReason.NEEDS_HUMAN),
                "failed_guardrail_count": _stop_count(self.runs, ResumableSupervisorStopReason.FAILED_GUARDRAIL),
                "budget_exhausted_count": _stop_count(self.runs, ResumableSupervisorStopReason.BUDGET_EXHAUSTED),
                "no_safe_work_count": _stop_count(self.runs, ResumableSupervisorStopReason.NO_SAFE_WORK),
                "completed_item_count": sum(len(run.completed_item_ids) for run in self.runs),
                **_ZERO_SIDE_EFFECT_COUNTERS,
                "passed": _passed(self.runs, len(self.scenarios)),
            },
            "boundary": dict(_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "runs": run_dicts,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_resumable_local_supervisor_fixture(path: str | Path) -> ResumableLocalSupervisorReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite = _mapping(data.get("suite"))
    scenarios = tuple(
        ResumableSupervisorScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping)
    )
    return ResumableLocalSupervisorReport.from_scenarios(suite, scenarios)


def render_resumable_local_supervisor_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Resumable Local Supervisor Runner",
        "",
        (
            "P86 models a resumable local/mock runner for repeated supervisor iterations. It records checkpoint "
            "write plans but performs no live actions, shell commands, process spawning, agent spawning, API calls, "
            "credential reads, network calls, or production mutations."
        ),
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Resumed: {summary.get('resumed_count', 0)}",
        f"- Completed all: {summary.get('completed_all_count', 0)}",
        f"- Max iteration: {summary.get('max_iteration_count', 0)}",
        f"- Needs human: {summary.get('needs_human_count', 0)}",
        f"- Failed guardrail: {summary.get('failed_guardrail_count', 0)}",
        f"- Budget exhausted: {summary.get('budget_exhausted_count', 0)}",
        f"- No safe work: {summary.get('no_safe_work_count', 0)}",
        f"- Executions: {summary.get('action_execution_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Supervisor runs",
        "",
    ]
    for run in _sequence(payload.get("runs", ())):
        if isinstance(run, Mapping):
            lines.extend(
                [
                    f"### {run.get('scenario_id', 'scenario')}",
                    "",
                    f"- Run ID: {run.get('run_id')}",
                    f"- Stop reason: {run.get('stop_reason')}",
                    f"- Cursor: {run.get('cursor', 0)}",
                    f"- Completed: {', '.join(str(item) for item in _sequence(run.get('completed_item_ids', ()))) or 'none'}",
                    f"- Skipped: {', '.join(str(item) for item in _sequence(run.get('skipped_item_ids', ()))) or 'none'}",
                    f"- Next wakeup: {run.get('next_recommended_wakeup') or 'none'}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Atomic checkpoint write plan",
            "",
            "Each checkpoint records temp_path -> final_path metadata only. Tests and smoke reports do not write supervisor state outside the requested output paths.",
            "",
            "## Boundary",
            "",
            "- Local/mock runner modeling only.",
            "- Dry-run command names are text and are not executed.",
            "- No live APIs, credentials, network calls, shell execution, process spawning, agent spawning, production mutation, remediation execution, or action execution.",
            "- This is a local resumable runner foundation, not unattended production operation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_resumable_local_supervisor_outputs(
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
        output_md_path.write_text(render_resumable_local_supervisor_markdown(payload), encoding="utf-8")


def _run_scenario(scenario: ResumableSupervisorScenario) -> ResumableSupervisorRunState:
    state = scenario.initial_state
    initial_cursor = max(0, int(_float(state.get("cursor"), 0.0))) if state else 0
    cursor = initial_cursor
    completed_ids = [str(item) for item in _sequence(state.get("completed_item_ids", ()))] if state else []
    initial_skipped = [dict(item) for item in _sequence(state.get("skipped_items", ())) if isinstance(item, Mapping)] if state else []
    skipped = list(initial_skipped)
    iteration_count = max(0, int(_float(state.get("iteration_count"), 0.0))) if state else 0
    failure_streak = max(0, int(_float(state.get("failure_streak"), 0.0))) if state else 0
    budget_used = max(0, int(_float(state.get("budget_used"), 0.0))) if state else 0
    selected_ids: list[str] = []
    modeled_steps: list[Mapping[str, Any]] = []
    checkpoints: list[Mapping[str, Any]] = []
    stop_reason: ResumableSupervisorStopReason | None = None

    _append_checkpoint(checkpoints, scenario, cursor, completed_ids, skipped, iteration_count, failure_streak, "start")

    while cursor < len(scenario.backlog):
        if iteration_count >= scenario.limits.max_iterations:
            stop_reason = ResumableSupervisorStopReason.MAX_ITERATIONS
            break
        if budget_used >= scenario.limits.max_budget_units:
            stop_reason = ResumableSupervisorStopReason.BUDGET_EXHAUSTED
            break

        item = scenario.backlog[cursor]
        if item.id in completed_ids:
            cursor += 1
            _append_checkpoint(checkpoints, scenario, cursor, completed_ids, skipped, iteration_count, failure_streak, "resume_skip_completed")
            continue

        unsafe_reason = _unsafe_reason(item)
        if unsafe_reason is not None:
            skipped.append({"item_id": item.id, "reason": unsafe_reason, "blocked_by": _blocked_by(unsafe_reason)})
            cursor += 1
            _append_checkpoint(checkpoints, scenario, cursor, completed_ids, skipped, iteration_count, failure_streak, unsafe_reason)
            stop_reason = ResumableSupervisorStopReason.NEEDS_HUMAN if unsafe_reason == "approval_required" else ResumableSupervisorStopReason.NO_SAFE_WORK
            break

        if budget_used + item.budget_units > scenario.limits.max_budget_units:
            stop_reason = ResumableSupervisorStopReason.BUDGET_EXHAUSTED
            break

        selected_ids.append(item.id)
        iteration_count += 1
        budget_used += item.budget_units
        if item.mock_step_result == "passed":
            completed_ids.append(item.id)
            failure_streak = 0
            modeled_steps.append(
                {
                    "item_id": item.id,
                    "title": item.title,
                    "dry_run_command_name": item.dry_run_command_name,
                    "result": "passed",
                    "executed": False,
                }
            )
            cursor += 1
            _append_checkpoint(checkpoints, scenario, cursor, completed_ids, skipped, iteration_count, failure_streak, "mock_step_passed")
            continue

        failure_streak += 1
        cursor += 1
        _append_checkpoint(checkpoints, scenario, cursor, completed_ids, skipped, iteration_count, failure_streak, "mock_step_failed")
        if failure_streak >= scenario.limits.failure_streak_limit:
            stop_reason = ResumableSupervisorStopReason.FAILED_GUARDRAIL
            break

    if stop_reason is None:
        stop_reason = ResumableSupervisorStopReason.COMPLETED_ALL if cursor >= len(scenario.backlog) else ResumableSupervisorStopReason.NO_SAFE_WORK

    _append_checkpoint(checkpoints, scenario, cursor, completed_ids, skipped, iteration_count, failure_streak, f"stop:{stop_reason.value}")
    return ResumableSupervisorRunState(
        scenario_id=scenario.id,
        run_id=scenario.run_id,
        cursor=cursor,
        completed_item_ids=tuple(completed_ids),
        selected_item_ids=tuple(selected_ids),
        skipped_items=tuple(skipped),
        iteration_count=iteration_count,
        failure_streak=failure_streak,
        checkpoints=tuple(checkpoints),
        stop_reason=stop_reason,
        next_recommended_wakeup=_next_wakeup(stop_reason),
        terminal_recommendation=None if stop_reason == ResumableSupervisorStopReason.COMPLETED_ALL else {"reason": stop_reason.value},
        audit_metadata={
            "audit_id": f"p86:{scenario.run_id}",
            "local_mock_only": True,
            "p86_resumable_runner": True,
            "allowed_check_mode": "modeled_dry_run_names_only",
            "unattended_production_operation_claimed": False,
        },
        resume_metadata={
            "resumed_from_state": bool(state),
            "initial_cursor": initial_cursor,
            "initial_completed_item_ids": [str(item) for item in _sequence(state.get("completed_item_ids", ()))],
            "initial_skipped_item_ids": [str(item.get("item_id", "")) for item in initial_skipped if isinstance(item, Mapping)],
        },
        modeled_steps=tuple(modeled_steps),
    )


def _unsafe_reason(item: ResumableSupervisorWorkItem) -> str | None:
    if item.p76_decision not in _SAFE_P76:
        return "insufficient_evidence"
    if item.p79_decision not in _SAFE_P79 or item.p80_decision not in _SAFE_P80 or item.human_approval_required:
        return "approval_required"
    return None


def _blocked_by(reason: str) -> str:
    return "human_review" if reason == "approval_required" else "no_safe_local_work"


def _append_checkpoint(
    checkpoints: list[Mapping[str, Any]],
    scenario: ResumableSupervisorScenario,
    cursor: int,
    completed_ids: Sequence[str],
    skipped_items: Sequence[Mapping[str, str]],
    iteration_count: int,
    failure_streak: int,
    event: str,
) -> None:
    checkpoint_number = len(checkpoints) + 1
    final_path = scenario.checkpoint_final_path
    checkpoints.append(
        {
            "checkpoint_id": f"{scenario.run_id}:checkpoint:{checkpoint_number}",
            "cursor": cursor,
            "completed_item_ids": list(completed_ids),
            "skipped_item_ids": [item["item_id"] for item in skipped_items],
            "iteration_count": iteration_count,
            "failure_streak": failure_streak,
            "event": event,
            "atomic_write_plan": {
                "temp_path": f"{final_path}.{checkpoint_number}.tmp",
                "final_path": final_path,
                "operation": "write_temp_then_replace",
                "executed": False,
            },
            "side_effects": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
    )


def _next_wakeup(stop_reason: ResumableSupervisorStopReason) -> Mapping[str, Any] | None:
    if stop_reason == ResumableSupervisorStopReason.COMPLETED_ALL:
        return None
    if stop_reason == ResumableSupervisorStopReason.MAX_ITERATIONS:
        return {"reason": "resume_after_iteration_limit", "recheck_after_minutes": 15}
    if stop_reason == ResumableSupervisorStopReason.BUDGET_EXHAUSTED:
        return {"reason": "resume_after_budget", "recheck_after_minutes": 30}
    if stop_reason == ResumableSupervisorStopReason.NEEDS_HUMAN:
        return {"reason": "human_review_required", "recheck_after_minutes": 0}
    if stop_reason == ResumableSupervisorStopReason.FAILED_GUARDRAIL:
        return {"reason": "guardrail_review_required", "recheck_after_minutes": 0}
    return {"reason": "backlog_recheck", "recheck_after_minutes": 120}


def _passed(runs: Sequence[ResumableSupervisorRunState], scenario_count: int) -> bool:
    return (
        scenario_count >= 6
        and _stop_count(runs, ResumableSupervisorStopReason.COMPLETED_ALL) >= 3
        and _stop_count(runs, ResumableSupervisorStopReason.MAX_ITERATIONS) >= 1
        and _stop_count(runs, ResumableSupervisorStopReason.NEEDS_HUMAN) >= 1
        and _stop_count(runs, ResumableSupervisorStopReason.FAILED_GUARDRAIL) >= 1
        and all(counter == 0 for counter in _ZERO_SIDE_EFFECT_COUNTERS.values())
    )


def _stop_count(runs: Sequence[ResumableSupervisorRunState], stop_reason: ResumableSupervisorStopReason) -> int:
    return sum(1 for run in runs if run.stop_reason == stop_reason)


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
    "ResumableLocalSupervisorReport",
    "ResumableSupervisorStopReason",
    "evaluate_resumable_local_supervisor_fixture",
    "render_resumable_local_supervisor_markdown",
    "write_resumable_local_supervisor_outputs",
]
