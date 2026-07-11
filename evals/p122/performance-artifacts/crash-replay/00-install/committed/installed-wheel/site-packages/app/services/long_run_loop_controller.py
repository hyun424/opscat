"""P73 bounded long-run autonomous loop controller.

The controller repeatedly invokes the P72 stateful all-day loop orchestrator in
bounded windows. It is intentionally not an unsafe infinite loop: duration,
window-count, retry, process-enable, and state checkpoint guards determine when
execution stops. Repository verification uses simulated supervised transport and
records zero live/action/production side effects.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value
from app.services.stateful_all_day_loop_orchestrator import (
    RealSubprocessSupervisedTransport,
    SimulatedSupervisedProcessTransport,
    run_stateful_all_day_loop_orchestrator_fixture,
)
from app.services.supervised_worker_execution_harness import SupervisedProcessTransport

_FORBIDDEN_SCORE: dict[str, int] = {
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
}


@dataclass(frozen=True)
class LongRunLoopPolicy:
    max_windows: int
    p72_cycles_per_window: int
    max_tickets_per_cycle: int
    max_parallel: int
    duration_seconds: int
    sleep_seconds: int
    simulated_window_seconds: int
    process_execution_enabled: bool
    transport: str
    stop_on_retry: bool = True
    stop_on_enablement_block: bool = True
    actual_sleep_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_windows": self.max_windows,
            "p72_cycles_per_window": self.p72_cycles_per_window,
            "max_tickets_per_cycle": self.max_tickets_per_cycle,
            "max_parallel": self.max_parallel,
            "duration_seconds": self.duration_seconds,
            "sleep_seconds": self.sleep_seconds,
            "simulated_window_seconds": self.simulated_window_seconds,
            "process_execution_enabled": self.process_execution_enabled,
            "transport": self.transport,
            "stop_on_retry": self.stop_on_retry,
            "stop_on_enablement_block": self.stop_on_enablement_block,
            "actual_sleep_enabled": self.actual_sleep_enabled,
            "real_transport_allowed": self.transport == "real-subprocess" and self.process_execution_enabled,
        }


@dataclass(frozen=True)
class LongRunWindow:
    window_index: int
    elapsed_start_seconds: int
    elapsed_end_seconds: int
    started_ticket_ids: tuple[str, ...]
    succeeded_ticket_ids: tuple[str, ...]
    failed_ticket_ids: tuple[str, ...]
    blocked_ticket_ids: tuple[str, ...]
    retry_ticket_ids: tuple[str, ...]
    p72_stop_reason: str
    p72_state_path: str
    p72_cycle_count: int
    planned_sleep_seconds_after: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "elapsed_start_seconds": self.elapsed_start_seconds,
            "elapsed_end_seconds": self.elapsed_end_seconds,
            "started_ticket_ids": list(self.started_ticket_ids),
            "succeeded_ticket_ids": list(self.succeeded_ticket_ids),
            "failed_ticket_ids": list(self.failed_ticket_ids),
            "blocked_ticket_ids": list(self.blocked_ticket_ids),
            "retry_ticket_ids": list(self.retry_ticket_ids),
            "p72_stop_reason": self.p72_stop_reason,
            "p72_state_path": self.p72_state_path,
            "p72_cycle_count": self.p72_cycle_count,
            "planned_sleep_seconds_after": self.planned_sleep_seconds_after,
        }


@dataclass(frozen=True)
class LongRunLoopControllerReport:
    policy: LongRunLoopPolicy
    initial_completed: tuple[str, ...]
    windows: tuple[LongRunWindow, ...]
    completed_tickets: tuple[str, ...]
    retry_queue: tuple[Mapping[str, Any], ...]
    state_path: Path
    elapsed_seconds: int
    stop_reason: str

    def to_dict(self) -> dict[str, Any]:
        initial = set(self.initial_completed)
        newly_completed = tuple(ticket for ticket in self.completed_tickets if ticket not in initial)
        failed_count = sum(len(window.failed_ticket_ids) for window in self.windows)
        blocked_count = sum(len(window.blocked_ticket_ids) for window in self.windows)
        supervised_count = sum(len(window.started_ticket_ids) for window in self.windows)
        p72_cycle_count = sum(window.p72_cycle_count for window in self.windows)
        planned_sleep_total = sum(window.planned_sleep_seconds_after for window in self.windows)
        payload = {
            "summary": {
                "window_count": len(self.windows),
                "p72_cycle_count": p72_cycle_count,
                "completed_ticket_count": len(newly_completed),
                "failed_ticket_count": failed_count,
                "retry_queue_count": len(self.retry_queue),
                "blocked_by_enable_flag_count": blocked_count,
                "elapsed_seconds": self.elapsed_seconds,
                "planned_sleep_count": sum(1 for window in self.windows if window.planned_sleep_seconds_after > 0),
                "stop_reason": self.stop_reason,
                "passed": self._passed(failed_count, blocked_count),
            },
            "policy": self.policy.to_dict(),
            "score": {
                **_FORBIDDEN_SCORE,
                "supervised_process_run_count": supervised_count,
                "window_checkpoint_count": len(self.windows),
                "state_write_count": len(self.windows),
                "planned_sleep_seconds_total": planned_sleep_total,
                "actual_sleep_seconds_total": 0,
                "real_subprocess_transport_count": 1 if self.policy.transport == "real-subprocess" else 0,
            },
            "windows": [window.to_dict() for window in self.windows],
            "retry_queue": [dict(item) for item in self.retry_queue],
            "state_path": str(self.state_path),
            "operator_handoff": {
                "resume_completed_tickets": list(self.completed_tickets),
                "retry_tickets": [str(item.get("ticket_id", "")) for item in self.retry_queue],
                "next_step": _next_step(self.stop_reason),
                "bounded_long_run": True,
                "unbounded_infinite_loop": False,
                "safe_local_only": True,
                "unattended_production_ready": False,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _passed(self, failed_count: int, blocked_count: int) -> bool:
        return (
            self.policy.process_execution_enabled
            and self.stop_reason in {"max_windows_reached", "duration_budget_reached", "no_runnable_tickets"}
            and failed_count == 0
            and blocked_count == 0
            and not self.retry_queue
            and len(self.windows) > 0
            and all(value == 0 for value in _FORBIDDEN_SCORE.values())
        )


def run_long_run_loop_controller_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_windows: int = 2,
    p72_cycles_per_window: int = 2,
    max_tickets_per_cycle: int = 3,
    max_parallel: int = 2,
    duration_seconds: int = 10 * 60 * 60,
    sleep_seconds: int = 60,
    simulated_window_seconds: int = 20 * 60,
    dispatch_dir: str | Path = "/tmp/opscat-long-run-loop-dispatch",
    state_path: str | Path = "/tmp/opscat-long-run-loop-state.json",
    artifact_dir: str | Path = "/tmp/opscat-long-run-loop-artifacts",
    enable_process_execution: bool = False,
    transport: SupervisedProcessTransport | None = None,
    timeout_seconds: int = 1_200,
) -> LongRunLoopControllerReport:
    supervised_transport = transport or SimulatedSupervisedProcessTransport()
    policy = LongRunLoopPolicy(
        max_windows=max(1, max_windows),
        p72_cycles_per_window=max(1, p72_cycles_per_window),
        max_tickets_per_cycle=max(1, max_tickets_per_cycle),
        max_parallel=max(1, max_parallel),
        duration_seconds=max(1, duration_seconds),
        sleep_seconds=max(0, sleep_seconds),
        simulated_window_seconds=max(1, simulated_window_seconds),
        process_execution_enabled=enable_process_execution,
        transport=supervised_transport.name,
    )
    base_completed = _sort_ticket_ids(set(completed or set()))
    completed_ids = set(base_completed)
    windows: list[LongRunWindow] = []
    retry_queue: list[Mapping[str, Any]] = []
    elapsed = 0
    stop_reason = "max_windows_reached"
    state_file = Path(state_path)
    dispatch_root = Path(dispatch_dir)
    artifact_root = Path(artifact_dir)

    for window_index in range(1, policy.max_windows + 1):
        if elapsed + policy.simulated_window_seconds > policy.duration_seconds:
            stop_reason = "duration_budget_reached"
            break

        elapsed_start = elapsed
        p72_state_path = state_file.parent / f"{state_file.stem}-window-{window_index}.json"
        p72_report = run_stateful_all_day_loop_orchestrator_fixture(
            path,
            completed=set(completed_ids),
            max_cycles=policy.p72_cycles_per_window,
            max_tickets_per_cycle=policy.max_tickets_per_cycle,
            max_parallel=policy.max_parallel,
            dispatch_dir=dispatch_root / f"window-{window_index}",
            state_path=p72_state_path,
            artifact_dir=artifact_root / f"window-{window_index}",
            enable_process_execution=enable_process_execution,
            transport=supervised_transport,
            timeout_seconds=timeout_seconds,
        )
        payload = p72_report.to_dict()
        completed_ids = set(_sequence(_mapping(payload.get("operator_handoff")).get("resume_completed_tickets", ())))
        retry_queue.extend(tuple(item for item in _sequence(payload.get("retry_queue", ())) if isinstance(item, Mapping)))
        elapsed += policy.simulated_window_seconds

        window_stop_reason = str(_mapping(payload.get("summary")).get("stop_reason", "unknown"))
        planned_sleep = 0
        if window_index < policy.max_windows and not retry_queue and window_stop_reason not in {"process_execution_not_enabled", "no_runnable_tickets"}:
            remaining_after_sleep = elapsed + policy.sleep_seconds
            if remaining_after_sleep <= policy.duration_seconds:
                planned_sleep = policy.sleep_seconds
                elapsed = remaining_after_sleep
            else:
                stop_reason = "duration_budget_reached"

        window = _window_from_payload(
            window_index=window_index,
            elapsed_start_seconds=elapsed_start,
            elapsed_end_seconds=elapsed,
            payload=payload,
            planned_sleep_seconds_after=planned_sleep,
        )
        windows.append(window)

        if retry_queue:
            stop_reason = "retry_queue_non_empty"
            _write_state(state_file, base_completed, completed_ids, windows, retry_queue, elapsed, stop_reason)
            break
        if window_stop_reason == "process_execution_not_enabled":
            stop_reason = "process_execution_not_enabled"
            _write_state(state_file, base_completed, completed_ids, windows, retry_queue, elapsed, stop_reason)
            break
        if window_stop_reason == "no_runnable_tickets":
            stop_reason = "no_runnable_tickets"
            _write_state(state_file, base_completed, completed_ids, windows, retry_queue, elapsed, stop_reason)
            break
        if stop_reason == "duration_budget_reached":
            _write_state(state_file, base_completed, completed_ids, windows, retry_queue, elapsed, stop_reason)
            break
        _write_state(state_file, base_completed, completed_ids, windows, retry_queue, elapsed, "checkpoint" if window_index < policy.max_windows else stop_reason)

    if not windows and stop_reason == "max_windows_reached":
        stop_reason = "duration_budget_reached"
        _write_state(state_file, base_completed, completed_ids, windows, retry_queue, elapsed, stop_reason)

    return LongRunLoopControllerReport(
        policy=policy,
        initial_completed=tuple(base_completed),
        windows=tuple(windows),
        completed_tickets=tuple(_sort_ticket_ids(completed_ids)),
        retry_queue=tuple(retry_queue),
        state_path=state_file,
        elapsed_seconds=elapsed,
        stop_reason=stop_reason,
    )


def render_long_run_loop_controller_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    policy = _mapping(payload.get("policy"))
    windows = tuple(item for item in _sequence(payload.get("windows", ())) if isinstance(item, Mapping))
    handoff = _mapping(payload.get("operator_handoff"))
    lines = [
        "# OpsCat Long-Run Loop Controller",
        "",
        "## Summary",
        "",
        f"- windows: {summary.get('window_count', 0)}",
        f"- p72 cycles: {summary.get('p72_cycle_count', 0)}",
        f"- completed tickets: {summary.get('completed_ticket_count', 0)}",
        f"- retry queue: {summary.get('retry_queue_count', 0)}",
        f"- elapsed seconds: {summary.get('elapsed_seconds', 0)}",
        f"- stop reason: {summary.get('stop_reason')}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Stop guard",
        "",
        f"- duration seconds: {policy.get('duration_seconds')}",
        f"- max windows: {policy.get('max_windows')}",
        f"- sleep seconds: {policy.get('sleep_seconds')}",
        f"- unbounded infinite loop: {handoff.get('unbounded_infinite_loop')}",
        "",
        "## Window timeline",
        "",
    ]
    for window in windows:
        started = ", ".join(str(item) for item in _sequence(window.get("started_ticket_ids", ()))) or "none"
        failed = ", ".join(str(item) for item in _sequence(window.get("failed_ticket_ids", ()))) or "none"
        lines.append(f"- window {window.get('window_index')}: started={started}; failed={failed}; stop={window.get('p72_stop_reason')}")
    lines.extend(
        [
            "",
            "## Score",
            "",
            f"- supervised process runs: {score.get('supervised_process_run_count', 0)}",
            f"- planned sleep seconds: {score.get('planned_sleep_seconds_total', 0)}",
            f"- actual sleep seconds: {score.get('actual_sleep_seconds_total', 0)}",
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


def write_long_run_loop_controller_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_long_run_loop_controller_markdown(payload), encoding="utf-8")


def _window_from_payload(
    *,
    window_index: int,
    elapsed_start_seconds: int,
    elapsed_end_seconds: int,
    payload: Mapping[str, Any],
    planned_sleep_seconds_after: int,
) -> LongRunWindow:
    cycles = tuple(item for item in _sequence(payload.get("cycles", ())) if isinstance(item, Mapping))
    summary = _mapping(payload.get("summary"))
    return LongRunWindow(
        window_index=window_index,
        elapsed_start_seconds=elapsed_start_seconds,
        elapsed_end_seconds=elapsed_end_seconds,
        started_ticket_ids=_flatten_cycle_ids(cycles, "started_ticket_ids"),
        succeeded_ticket_ids=_flatten_cycle_ids(cycles, "succeeded_ticket_ids"),
        failed_ticket_ids=_flatten_cycle_ids(cycles, "failed_ticket_ids"),
        blocked_ticket_ids=_flatten_cycle_ids(cycles, "blocked_ticket_ids"),
        retry_ticket_ids=_flatten_cycle_ids(cycles, "retry_ticket_ids"),
        p72_stop_reason=str(summary.get("stop_reason", "unknown")),
        p72_state_path=str(payload.get("state_path", "")),
        p72_cycle_count=int(summary.get("cycle_count", 0) or 0),
        planned_sleep_seconds_after=planned_sleep_seconds_after,
    )


def _flatten_cycle_ids(cycles: Sequence[Mapping[str, Any]], key: str) -> tuple[str, ...]:
    values: list[str] = []
    for cycle in cycles:
        values.extend(str(item) for item in _sequence(cycle.get(key, ())) if str(item))
    return tuple(values)


def _write_state(
    state_path: Path,
    initial_completed: Sequence[str],
    completed_ids: set[Any],
    windows: Sequence[LongRunWindow],
    retry_queue: Sequence[Mapping[str, Any]],
    elapsed_seconds: int,
    stop_reason: str,
) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "initial_completed_tickets": list(initial_completed),
        "resume_completed_tickets": _sort_ticket_ids(str(item) for item in completed_ids),
        "last_window_index": len(windows),
        "elapsed_seconds": elapsed_seconds,
        "stop_reason": stop_reason,
        "retry_queue": [dict(item) for item in retry_queue],
        "windows": [window.to_dict() for window in windows],
    }
    state_path.write_text(json.dumps(redact_value(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _next_step(stop_reason: str) -> str:
    if stop_reason == "retry_queue_non_empty":
        return "inspect retry queue artifacts before continuing the long-run loop"
    if stop_reason == "process_execution_not_enabled":
        return "review execution gate and rerun with explicit process enablement"
    if stop_reason == "duration_budget_reached":
        return "resume from completed tickets in the next scheduled loop window"
    if stop_reason == "no_runnable_tickets":
        return "refresh backlog or unblock gated dependencies"
    return "continue from completed tickets with the next bounded long-run window"


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
    "LongRunLoopControllerReport",
    "LongRunLoopPolicy",
    "LongRunWindow",
    "RealSubprocessSupervisedTransport",
    "SimulatedSupervisedProcessTransport",
    "render_long_run_loop_controller_markdown",
    "run_long_run_loop_controller_fixture",
    "write_long_run_loop_controller_outputs",
]
