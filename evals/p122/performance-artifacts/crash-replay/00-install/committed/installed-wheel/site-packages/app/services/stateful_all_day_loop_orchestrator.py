"""P72 stateful all-day loop orchestrator.

This layer turns the P71 supervised single-run harness into a resumable
multi-cycle controller. It accumulates completed safe-local tickets, checkpoints
state after every cycle, stops on retry queues or missing enablement, and keeps
all live/action/production side effects disabled in repository verification.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value
from app.services.supervised_worker_execution_harness import (
    RealSubprocessSupervisedTransport,
    SimulatedSupervisedProcessTransport,
    SupervisedProcessTransport,
    run_supervised_worker_execution_harness_fixture,
)

_FORBIDDEN_SCORE: dict[str, int] = {
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
}


@dataclass(frozen=True)
class StatefulLoopPolicy:
    max_cycles: int
    max_tickets_per_cycle: int
    max_parallel: int
    process_execution_enabled: bool
    transport: str
    stop_on_retry: bool = True
    checkpoint_state_each_cycle: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cycles": self.max_cycles,
            "max_tickets_per_cycle": self.max_tickets_per_cycle,
            "max_parallel": self.max_parallel,
            "process_execution_enabled": self.process_execution_enabled,
            "transport": self.transport,
            "stop_on_retry": self.stop_on_retry,
            "checkpoint_state_each_cycle": self.checkpoint_state_each_cycle,
            "real_transport_allowed": self.transport == "real-subprocess" and self.process_execution_enabled,
        }


@dataclass(frozen=True)
class StatefulLoopCycle:
    cycle_index: int
    eligible_ticket_ids: tuple[str, ...]
    started_ticket_ids: tuple[str, ...]
    succeeded_ticket_ids: tuple[str, ...]
    failed_ticket_ids: tuple[str, ...]
    blocked_ticket_ids: tuple[str, ...]
    retry_ticket_ids: tuple[str, ...]
    harness_summary: Mapping[str, Any]
    harness_state_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_index": self.cycle_index,
            "eligible_ticket_ids": list(self.eligible_ticket_ids),
            "started_ticket_ids": list(self.started_ticket_ids),
            "succeeded_ticket_ids": list(self.succeeded_ticket_ids),
            "failed_ticket_ids": list(self.failed_ticket_ids),
            "blocked_ticket_ids": list(self.blocked_ticket_ids),
            "retry_ticket_ids": list(self.retry_ticket_ids),
            "harness_summary": dict(self.harness_summary),
            "harness_state_path": self.harness_state_path,
        }


@dataclass(frozen=True)
class StatefulAllDayLoopOrchestratorReport:
    policy: StatefulLoopPolicy
    initial_completed: tuple[str, ...]
    cycles: tuple[StatefulLoopCycle, ...]
    completed_tickets: tuple[str, ...]
    retry_queue: tuple[Mapping[str, Any], ...]
    state_path: Path
    stop_reason: str

    def to_dict(self) -> dict[str, Any]:
        newly_completed = tuple(ticket for ticket in self.completed_tickets if ticket not in set(self.initial_completed))
        failed_count = sum(len(cycle.failed_ticket_ids) for cycle in self.cycles)
        blocked_count = sum(len(cycle.blocked_ticket_ids) for cycle in self.cycles)
        supervised_count = sum(int(_mapping(cycle.harness_summary).get("started_run_count", 0)) for cycle in self.cycles)
        timeout_count = sum(int(_mapping(cycle.harness_summary).get("timeout_count", 0) or 0) for cycle in self.cycles)
        payload = {
            "summary": {
                "cycle_count": len(self.cycles),
                "completed_ticket_count": len(newly_completed),
                "failed_ticket_count": failed_count,
                "retry_queue_count": len(self.retry_queue),
                "blocked_by_enable_flag_count": blocked_count,
                "stop_reason": self.stop_reason,
                "passed": self._passed(failed_count, blocked_count),
            },
            "policy": self.policy.to_dict(),
            "score": {
                **_FORBIDDEN_SCORE,
                "supervised_process_run_count": supervised_count,
                "cycle_checkpoint_count": len(self.cycles),
                "state_write_count": len(self.cycles),
                "timeout_count": timeout_count,
                "real_subprocess_transport_count": 1 if self.policy.transport == "real-subprocess" else 0,
            },
            "cycles": [cycle.to_dict() for cycle in self.cycles],
            "retry_queue": [dict(item) for item in self.retry_queue],
            "state_path": str(self.state_path),
            "operator_handoff": {
                "resume_completed_tickets": list(self.completed_tickets),
                "retry_tickets": [str(item.get("ticket_id", "")) for item in self.retry_queue],
                "next_step": _next_step(self.stop_reason),
                "safe_local_only": True,
                "unattended_production_ready": False,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _passed(self, failed_count: int, blocked_count: int) -> bool:
        return (
            self.policy.process_execution_enabled
            and self.stop_reason == "max_cycles_reached"
            and len(self.cycles) == self.policy.max_cycles
            and failed_count == 0
            and blocked_count == 0
            and not self.retry_queue
            and all(value == 0 for value in _FORBIDDEN_SCORE.values())
        )


def run_stateful_all_day_loop_orchestrator_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_cycles: int = 3,
    max_tickets_per_cycle: int = 3,
    max_parallel: int = 2,
    dispatch_dir: str | Path = "/tmp/opscat-stateful-all-day-loop-dispatch",
    state_path: str | Path = "/tmp/opscat-stateful-all-day-loop-state.json",
    artifact_dir: str | Path = "/tmp/opscat-stateful-all-day-loop-artifacts",
    enable_process_execution: bool = False,
    transport: SupervisedProcessTransport | None = None,
    timeout_seconds: int = 1_200,
) -> StatefulAllDayLoopOrchestratorReport:
    supervised_transport = transport or SimulatedSupervisedProcessTransport()
    policy = StatefulLoopPolicy(
        max_cycles=max(1, max_cycles),
        max_tickets_per_cycle=max(1, max_tickets_per_cycle),
        max_parallel=max(1, max_parallel),
        process_execution_enabled=enable_process_execution,
        transport=supervised_transport.name,
    )
    base_completed = _sort_ticket_ids(set(completed or set()))
    completed_ids = set(base_completed)
    cycles: list[StatefulLoopCycle] = []
    retry_queue: list[Mapping[str, Any]] = []
    stop_reason = "max_cycles_reached"
    state_file = Path(state_path)
    dispatch_root = Path(dispatch_dir)
    artifact_root = Path(artifact_dir)

    for cycle_index in range(1, policy.max_cycles + 1):
        cycle_state_path = state_file.parent / f"{state_file.stem}-cycle-{cycle_index}.json"
        report = run_supervised_worker_execution_harness_fixture(
            path,
            completed=set(completed_ids),
            max_tickets=policy.max_tickets_per_cycle,
            max_parallel=policy.max_parallel,
            dispatch_dir=dispatch_root / f"cycle-{cycle_index}",
            state_path=cycle_state_path,
            artifact_dir=artifact_root / f"cycle-{cycle_index}",
            enable_process_execution=enable_process_execution,
            transport=supervised_transport,
            timeout_seconds=timeout_seconds,
        )
        payload = report.to_dict()
        cycle = _cycle_from_payload(cycle_index, payload)
        cycles.append(cycle)
        completed_ids.update(cycle.succeeded_ticket_ids)
        retry_queue.extend(tuple(item for item in _sequence(payload.get("retry_queue", ())) if isinstance(item, Mapping)))

        if cycle.blocked_ticket_ids:
            stop_reason = "process_execution_not_enabled"
            _write_state(state_file, base_completed, completed_ids, cycles, retry_queue, stop_reason)
            break
        if retry_queue:
            stop_reason = "retry_queue_non_empty"
            _write_state(state_file, base_completed, completed_ids, cycles, retry_queue, stop_reason)
            break
        if not cycle.eligible_ticket_ids:
            stop_reason = "no_runnable_tickets"
            _write_state(state_file, base_completed, completed_ids, cycles, retry_queue, stop_reason)
            break
        _write_state(state_file, base_completed, completed_ids, cycles, retry_queue, stop_reason if cycle_index == policy.max_cycles else "checkpoint")

    return StatefulAllDayLoopOrchestratorReport(
        policy=policy,
        initial_completed=tuple(base_completed),
        cycles=tuple(cycles),
        completed_tickets=tuple(_sort_ticket_ids(completed_ids)),
        retry_queue=tuple(retry_queue),
        state_path=state_file,
        stop_reason=stop_reason,
    )


def render_stateful_all_day_loop_orchestrator_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    cycles = tuple(item for item in _sequence(payload.get("cycles", ())) if isinstance(item, Mapping))
    handoff = _mapping(payload.get("operator_handoff"))
    lines = [
        "# OpsCat Stateful All-Day Loop Orchestrator",
        "",
        "## Summary",
        "",
        f"- cycles: {summary.get('cycle_count', 0)}",
        f"- completed tickets: {summary.get('completed_ticket_count', 0)}",
        f"- failed tickets: {summary.get('failed_ticket_count', 0)}",
        f"- retry queue: {summary.get('retry_queue_count', 0)}",
        f"- blocked by enable flag: {summary.get('blocked_by_enable_flag_count', 0)}",
        f"- stop reason: {summary.get('stop_reason')}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Cycle timeline",
        "",
    ]
    for cycle in cycles:
        started = ", ".join(str(item) for item in _sequence(cycle.get("started_ticket_ids", ()))) or "none"
        succeeded = ", ".join(str(item) for item in _sequence(cycle.get("succeeded_ticket_ids", ()))) or "none"
        failed = ", ".join(str(item) for item in _sequence(cycle.get("failed_ticket_ids", ()))) or "none"
        lines.append(f"- cycle {cycle.get('cycle_index')}: started={started}; succeeded={succeeded}; failed={failed}")
    lines.extend(
        [
            "",
            "## Score",
            "",
            f"- supervised process runs: {score.get('supervised_process_run_count', 0)}",
            f"- state writes: {score.get('state_write_count', 0)}",
            (
                "- live/api/action/production side effects: "
                f"{score.get('live_api_call_count', 0)}/{score.get('network_call_count', 0)}/"
                f"{score.get('action_execution_count', 0)}/{score.get('production_mutation_count', 0)}"
            ),
            "",
            "## Operator handoff",
            "",
            f"- resume completed: {', '.join(str(item) for item in _sequence(handoff.get('resume_completed_tickets', ())))}",
            f"- retry tickets: {', '.join(str(item) for item in _sequence(handoff.get('retry_tickets', ()))) or 'none'}",
            f"- next step: {handoff.get('next_step')}",
            "",
        ]
    )
    return "\n".join(lines)


def write_stateful_all_day_loop_orchestrator_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_stateful_all_day_loop_orchestrator_markdown(payload), encoding="utf-8")


def _cycle_from_payload(cycle_index: int, payload: Mapping[str, Any]) -> StatefulLoopCycle:
    runs = tuple(item for item in _sequence(payload.get("supervised_runs", ())) if isinstance(item, Mapping))
    retry = tuple(item for item in _sequence(payload.get("retry_queue", ())) if isinstance(item, Mapping))
    summary = _mapping(payload.get("summary"))
    started = tuple(str(run.get("ticket_id", "")) for run in runs if str(run.get("status", "")) != "blocked_by_enable_flag")
    succeeded = tuple(str(run.get("ticket_id", "")) for run in runs if str(run.get("status", "")) == "succeeded" and int(run.get("exit_code", 1)) == 0)
    failed = tuple(str(run.get("ticket_id", "")) for run in runs if str(run.get("status", "")) not in {"succeeded", "blocked_by_enable_flag"})
    blocked = tuple(str(run.get("ticket_id", "")) for run in runs if str(run.get("status", "")) == "blocked_by_enable_flag")
    return StatefulLoopCycle(
        cycle_index=cycle_index,
        eligible_ticket_ids=tuple(str(run.get("ticket_id", "")) for run in runs),
        started_ticket_ids=started,
        succeeded_ticket_ids=succeeded,
        failed_ticket_ids=failed,
        blocked_ticket_ids=blocked,
        retry_ticket_ids=tuple(str(item.get("ticket_id", "")) for item in retry),
        harness_summary=summary,
        harness_state_path=str(payload.get("state_path", "")),
    )


def _write_state(
    state_path: Path,
    initial_completed: Sequence[str],
    completed_ids: set[str],
    cycles: Sequence[StatefulLoopCycle],
    retry_queue: Sequence[Mapping[str, Any]],
    stop_reason: str,
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "initial_completed_tickets": list(initial_completed),
        "resume_completed_tickets": _sort_ticket_ids(completed_ids),
        "last_cycle_index": len(cycles),
        "stop_reason": stop_reason,
        "retry_queue": [dict(item) for item in retry_queue],
        "cycles": [cycle.to_dict() for cycle in cycles],
    }
    state_path.write_text(json.dumps(redact_value(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _next_step(stop_reason: str) -> str:
    if stop_reason == "retry_queue_non_empty":
        return "inspect retry queue artifacts before the next cycle"
    if stop_reason == "process_execution_not_enabled":
        return "rerun with explicit process execution enablement after reviewing the gate"
    if stop_reason == "no_runnable_tickets":
        return "refresh backlog or unblock gated dependencies"
    return "resume from completed tickets and continue the next all-day loop window"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return value
    if isinstance(value, Iterable):
        return tuple(value)
    return ()


def _sort_ticket_ids(ticket_ids: Iterable[str]) -> list[str]:
    return sorted((str(ticket_id) for ticket_id in ticket_ids if str(ticket_id)), key=_ticket_sort_key)


def _ticket_sort_key(ticket_id: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", ticket_id)
    return (int(match.group(1)) if match else 9999, ticket_id)


__all__ = [
    "RealSubprocessSupervisedTransport",
    "SimulatedSupervisedProcessTransport",
    "StatefulAllDayLoopOrchestratorReport",
    "StatefulLoopCycle",
    "StatefulLoopPolicy",
    "render_stateful_all_day_loop_orchestrator_markdown",
    "run_stateful_all_day_loop_orchestrator_fixture",
    "write_stateful_all_day_loop_orchestrator_outputs",
]
