"""P85 local autonomous supervisor loop.

Models a resumable local/mock supervisor over candidate work items. It selects
only safe local checks, records checkpoints, and stops on budget, human-review,
failure-streak, or no-safe-work guardrails. It never executes commands, spawns
processes or agents, contacts external systems, reads credentials, or mutates
production.
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
    "supervisor_only": True,
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
_WORSENED_OUTCOMES = {"worsened_rollback_or_escalate", "blocked_unsafe_to_continue"}
_ROLLBACK_REVIEW_ACTIONS = {"prepare_rollback_review", "block_unsafe_path"}


class SupervisorStopReason(StrEnum):
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_SAFE_WORK = "no_safe_work"
    NEEDS_HUMAN = "needs_human"
    FAILED_GUARDRAIL = "failed_guardrail"
    COMPLETED_BATCH = "completed_batch"


@dataclass(frozen=True)
class SupervisorLimits:
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
class SupervisorWorkItem:
    id: str
    title: str
    budget_units: int
    p76_decision: str
    p79_decision: str
    p80_decision: str
    p83_decision: str
    p84_next_action: str
    p84_human_approval_required: bool
    dry_run_command_name: str
    mock_step_result: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        p76 = _mapping(data.get("p76_gate"))
        p79 = _mapping(data.get("p79_sandbox"))
        p80 = _mapping(data.get("p80_approval"))
        p83 = _mapping(data.get("p83_outcome"))
        p84 = _mapping(data.get("p84_next_action"))
        return cls(
            id=str(data.get("id", "work-item")),
            title=str(data.get("title", "Local supervisor work item")),
            budget_units=max(1, int(_float(data.get("budget_units"), 1.0))),
            p76_decision=str(p76.get("decision", "")).lower(),
            p79_decision=str(p79.get("decision", "")).lower(),
            p80_decision=str(p80.get("decision", "")).lower(),
            p83_decision=str(p83.get("decision", "")).lower(),
            p84_next_action=str(p84.get("selected_next_action", "")).lower(),
            p84_human_approval_required=p84.get("human_approval_required") is True,
            dry_run_command_name=str(data.get("dry_run_command_name", "local-mock-check")),
            mock_step_result=str(data.get("mock_step_result", "passed")).lower(),
        )


@dataclass(frozen=True)
class SupervisorScenario:
    id: str
    run_id: str
    limits: SupervisorLimits
    backlog: tuple[SupervisorWorkItem, ...]
    resume_checkpoint: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            run_id=str(data.get("run_id", "p85-run")),
            limits=SupervisorLimits.from_dict(_mapping(data.get("limits"))),
            backlog=tuple(
                SupervisorWorkItem.from_dict(item)
                for item in _sequence(data.get("backlog", ()))
                if isinstance(item, Mapping)
            ),
            resume_checkpoint=_mapping(data.get("resume_checkpoint")),
        )


@dataclass(frozen=True)
class SupervisorRunState:
    scenario_id: str
    run_id: str
    stop_reason: SupervisorStopReason
    selected_item_ids: tuple[str, ...]
    skipped_items: tuple[Mapping[str, str], ...]
    completed_mock_steps: tuple[Mapping[str, Any], ...]
    queued_review_items: tuple[Mapping[str, str], ...]
    next_wakeup_recommendation: Mapping[str, Any]
    checkpoint_records: tuple[Mapping[str, Any], ...]
    audit_metadata: Mapping[str, Any]
    resume_metadata: Mapping[str, Any]
    failure_streak: int
    resumable_cursor: int

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "stop_reason": self.stop_reason.value,
            "selected_item_ids": list(self.selected_item_ids),
            "skipped_item_ids": [item["item_id"] for item in self.skipped_items],
            "skipped_items": [dict(item) for item in self.skipped_items],
            "completed_mock_steps": [dict(item) for item in self.completed_mock_steps],
            "queued_review_items": [dict(item) for item in self.queued_review_items],
            "next_wakeup_recommendation": dict(self.next_wakeup_recommendation),
            "checkpoint_records": [dict(item) for item in self.checkpoint_records],
            "audit_metadata": dict(self.audit_metadata),
            "resume_metadata": dict(self.resume_metadata),
            "failure_streak": self.failure_streak,
            "resumable_cursor": self.resumable_cursor,
            "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class LocalAutonomousSupervisorReport:
    suite: Mapping[str, Any]
    scenarios: tuple[SupervisorScenario, ...]
    runs: tuple[SupervisorRunState, ...]

    @classmethod
    def from_scenarios(cls, suite: Mapping[str, Any], scenarios: Sequence[SupervisorScenario]) -> Self:
        runs = tuple(_run_scenario(scenario) for scenario in scenarios)
        return cls(suite=suite, scenarios=tuple(scenarios), runs=runs)

    def to_dict(self) -> dict[str, Any]:
        run_dicts = [run.to_dict() for run in self.runs]
        payload = {
            "summary": {
                "suite_id": str(self.suite.get("id", "p85-local-autonomous-supervisor-loop")),
                "scenario_count": len(self.scenarios),
                "completed_batch_count": _stop_count(self.runs, SupervisorStopReason.COMPLETED_BATCH),
                "needs_human_count": _stop_count(self.runs, SupervisorStopReason.NEEDS_HUMAN),
                "failed_guardrail_count": _stop_count(self.runs, SupervisorStopReason.FAILED_GUARDRAIL),
                "budget_exhausted_count": _stop_count(self.runs, SupervisorStopReason.BUDGET_EXHAUSTED),
                "no_safe_work_count": _stop_count(self.runs, SupervisorStopReason.NO_SAFE_WORK),
                "selected_item_count": sum(len(run.selected_item_ids) for run in self.runs),
                "completed_mock_step_count": sum(len(run.completed_mock_steps) for run in self.runs),
                **_ZERO_SIDE_EFFECT_COUNTERS,
                "passed": _passed(self.runs, len(self.scenarios)),
            },
            "boundary": dict(_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "runs": run_dicts,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_local_autonomous_supervisor_fixture(path: str | Path) -> LocalAutonomousSupervisorReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite = _mapping(data.get("suite"))
    scenarios = tuple(
        SupervisorScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping)
    )
    return LocalAutonomousSupervisorReport.from_scenarios(suite, scenarios)


def render_local_autonomous_supervisor_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Local Autonomous Supervisor Loop",
        "",
        "P85 models a resumable local/mock supervisor loop without executing actions, commands, processes, agents, APIs, or production mutations.",
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Completed batches: {summary.get('completed_batch_count', 0)}",
        f"- Needs human: {summary.get('needs_human_count', 0)}",
        f"- Failed guardrail: {summary.get('failed_guardrail_count', 0)}",
        f"- Budget exhausted: {summary.get('budget_exhausted_count', 0)}",
        f"- No safe work: {summary.get('no_safe_work_count', 0)}",
        f"- Selected items: {summary.get('selected_item_count', 0)}",
        f"- Completed mock steps: {summary.get('completed_mock_step_count', 0)}",
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
                    f"- Selected: {', '.join(str(item) for item in _sequence(run.get('selected_item_ids', ()))) or 'none'}",
                    f"- Skipped: {', '.join(str(item) for item in _sequence(run.get('skipped_item_ids', ()))) or 'none'}",
                    f"- Completed mock steps: {len(_sequence(run.get('completed_mock_steps', ())))}",
                    f"- Resumable cursor: {run.get('resumable_cursor', 0)}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Zero-side-effect boundary",
            "",
            "- Local/mock supervisor modeling only.",
            "- No live APIs, credentials, network calls, shell execution, process spawning, agent spawning, production mutation, remediation execution, or action execution.",
            "- Dry-run command names are modeled as text and are not executed.",
            "- This is a local supervisor foundation, not unattended production operation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_local_autonomous_supervisor_outputs(
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
        output_md_path.write_text(render_local_autonomous_supervisor_markdown(payload), encoding="utf-8")


def _run_scenario(scenario: SupervisorScenario) -> SupervisorRunState:
    checkpoint = scenario.resume_checkpoint
    cursor = max(0, int(_float(checkpoint.get("cursor"), 0.0))) if checkpoint else 0
    initial_completed = tuple(str(item) for item in _sequence(checkpoint.get("completed_item_ids", ()))) if checkpoint else ()
    completed_ids = list(initial_completed)
    selected_ids: list[str] = []
    skipped: list[Mapping[str, str]] = []
    completed_steps: list[Mapping[str, Any]] = []
    queued_reviews: list[Mapping[str, str]] = []
    checkpoints: list[Mapping[str, Any]] = []
    failure_streak = max(0, int(_float(checkpoint.get("failure_streak"), 0.0))) if checkpoint else 0
    budget_used = 0
    iterations = 0
    human_blocked = False
    stop_reason: SupervisorStopReason | None = None

    _append_checkpoint(checkpoints, scenario, cursor, completed_ids, failure_streak, "start")

    while cursor < len(scenario.backlog):
        if iterations >= scenario.limits.max_iterations or budget_used >= scenario.limits.max_budget_units:
            stop_reason = SupervisorStopReason.BUDGET_EXHAUSTED
            break

        item = scenario.backlog[cursor]
        if item.id in completed_ids:
            cursor += 1
            _append_checkpoint(checkpoints, scenario, cursor, completed_ids, failure_streak, "resume_skip_completed")
            continue

        safety_reason = _unsafe_reason(item)
        if safety_reason is not None:
            skipped.append({"item_id": item.id, "reason": safety_reason})
            if safety_reason == "outcome_worsened":
                queued_reviews.append(
                    {"item_id": item.id, "review_type": "rollback_or_escalation", "reason": "outcome_worsened"}
                )
                human_blocked = True
            elif safety_reason in {"approval_required", "insufficient_evidence"}:
                human_blocked = True
            cursor += 1
            _append_checkpoint(checkpoints, scenario, cursor, completed_ids, failure_streak, safety_reason)
            continue

        if budget_used + item.budget_units > scenario.limits.max_budget_units:
            stop_reason = SupervisorStopReason.BUDGET_EXHAUSTED
            break

        selected_ids.append(item.id)
        budget_used += item.budget_units
        iterations += 1
        if item.mock_step_result == "passed":
            completed_ids.append(item.id)
            failure_streak = 0
            completed_steps.append(
                {
                    "item_id": item.id,
                    "title": item.title,
                    "dry_run_command_name": item.dry_run_command_name,
                    "result": "passed",
                    "executed": False,
                }
            )
            cursor += 1
            _append_checkpoint(checkpoints, scenario, cursor, completed_ids, failure_streak, "mock_step_passed")
            continue

        failure_streak += 1
        cursor += 1
        _append_checkpoint(checkpoints, scenario, cursor, completed_ids, failure_streak, "mock_step_failed")
        if failure_streak >= scenario.limits.failure_streak_limit:
            stop_reason = SupervisorStopReason.FAILED_GUARDRAIL
            break

    if stop_reason is None:
        if cursor < len(scenario.backlog) and (budget_used >= scenario.limits.max_budget_units or iterations >= scenario.limits.max_iterations):
            stop_reason = SupervisorStopReason.BUDGET_EXHAUSTED
        elif selected_ids:
            stop_reason = SupervisorStopReason.COMPLETED_BATCH
        elif human_blocked:
            stop_reason = SupervisorStopReason.NEEDS_HUMAN
        else:
            stop_reason = SupervisorStopReason.NO_SAFE_WORK

    _append_checkpoint(checkpoints, scenario, cursor, completed_ids, failure_streak, f"stop:{stop_reason.value}")
    return SupervisorRunState(
        scenario_id=scenario.id,
        run_id=scenario.run_id,
        stop_reason=stop_reason,
        selected_item_ids=tuple(selected_ids),
        skipped_items=tuple(skipped),
        completed_mock_steps=tuple(completed_steps),
        queued_review_items=tuple(queued_reviews),
        next_wakeup_recommendation=_next_wakeup(stop_reason),
        checkpoint_records=tuple(checkpoints),
        audit_metadata={
            "audit_id": f"p85:{scenario.run_id}",
            "local_mock_only": True,
            "supervisor_only": True,
            "allowed_check_mode": "modeled_dry_run_names_only",
            "unattended_production_operation_claimed": False,
        },
        resume_metadata={
            "resumed_from_checkpoint": bool(checkpoint),
            "initial_cursor": max(0, int(_float(checkpoint.get("cursor"), 0.0))) if checkpoint else 0,
            "initial_completed_item_ids": list(initial_completed),
        },
        failure_streak=failure_streak,
        resumable_cursor=cursor,
    )


def _unsafe_reason(item: SupervisorWorkItem) -> str | None:
    if item.p83_decision in _WORSENED_OUTCOMES or item.p84_next_action in _ROLLBACK_REVIEW_ACTIONS:
        return "outcome_worsened"
    if item.p76_decision not in _SAFE_P76:
        return "insufficient_evidence"
    if item.p79_decision == "block" or item.p80_decision == "block":
        return "blocked_guardrail"
    if item.p79_decision not in _SAFE_P79 or item.p80_decision not in _SAFE_P80 or item.p84_human_approval_required:
        return "approval_required"
    return None


def _append_checkpoint(
    checkpoints: list[Mapping[str, Any]],
    scenario: SupervisorScenario,
    cursor: int,
    completed_ids: Sequence[str],
    failure_streak: int,
    event: str,
) -> None:
    checkpoints.append(
        {
            "checkpoint_id": f"{scenario.run_id}:checkpoint:{len(checkpoints) + 1}",
            "cursor": cursor,
            "completed_item_ids": list(completed_ids),
            "failure_streak": failure_streak,
            "event": event,
            "side_effects": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
    )


def _next_wakeup(stop_reason: SupervisorStopReason) -> Mapping[str, Any]:
    if stop_reason == SupervisorStopReason.COMPLETED_BATCH:
        return {"reason": "batch_complete", "recheck_after_minutes": 60}
    if stop_reason == SupervisorStopReason.BUDGET_EXHAUSTED:
        return {"reason": "resume_after_budget", "recheck_after_minutes": 30}
    if stop_reason == SupervisorStopReason.FAILED_GUARDRAIL:
        return {"reason": "guardrail_review_required", "recheck_after_minutes": 0}
    if stop_reason == SupervisorStopReason.NEEDS_HUMAN:
        return {"reason": "human_review_required", "recheck_after_minutes": 0}
    return {"reason": "backlog_recheck", "recheck_after_minutes": 120}


def _passed(runs: Sequence[SupervisorRunState], scenario_count: int) -> bool:
    return (
        scenario_count >= 6
        and _stop_count(runs, SupervisorStopReason.COMPLETED_BATCH) >= 2
        and _stop_count(runs, SupervisorStopReason.NEEDS_HUMAN) >= 2
        and _stop_count(runs, SupervisorStopReason.FAILED_GUARDRAIL) >= 1
        and _stop_count(runs, SupervisorStopReason.BUDGET_EXHAUSTED) >= 1
        and all(counter == 0 for counter in _ZERO_SIDE_EFFECT_COUNTERS.values())
    )


def _stop_count(runs: Sequence[SupervisorRunState], stop_reason: SupervisorStopReason) -> int:
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
    "LocalAutonomousSupervisorReport",
    "SupervisorStopReason",
    "evaluate_local_autonomous_supervisor_fixture",
    "render_local_autonomous_supervisor_markdown",
    "write_local_autonomous_supervisor_outputs",
]
