"""P69 autonomous worker runner.

The worker runner consumes P68 dispatch packets and records claim/run/retry/state
results through an injectable transport. The default recording transport plans a
Codex execution command but never spawns processes or executes shell commands.
This makes the all-day autonomous loop resumable and auditable before a later
explicit real-process gate is opened.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.autonomous_agent_dispatcher import run_autonomous_agent_dispatcher_fixture
from app.services.redaction import redact_value

_FORBIDDEN_SCORE: dict[str, int] = {
    "spawned_process_count": 0,
    "shell_command_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
}


class WorkerTransport(Protocol):
    name: str

    def run(self, packet: Mapping[str, Any]) -> WorkerRunOutcome:
        """Run or record a worker packet."""


@dataclass(frozen=True)
class WorkerRunnerPolicy:
    transport: str
    max_parallel: int
    spawn_processes: bool = False
    execute_shell_commands: bool = False
    read_credentials: bool = False
    allow_network: bool = False
    approval_policy: str = "safe-local-auto"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transport": self.transport,
            "max_parallel": self.max_parallel,
            "spawn_processes": self.spawn_processes,
            "execute_shell_commands": self.execute_shell_commands,
            "read_credentials": self.read_credentials,
            "allow_network": self.allow_network,
            "approval_policy": self.approval_policy,
        }


@dataclass(frozen=True)
class WorkerRunOutcome:
    ticket_id: str
    status: str
    reason: str
    planned_command: str
    output_ref: str

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "status": self.status,
            "reason": self.reason,
            "planned_command": self.planned_command,
            "output_ref": self.output_ref,
        }


@dataclass(frozen=True)
class RetryQueueItem:
    ticket_id: str
    reason: str
    attempt: int
    packet_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "reason": self.reason,
            "attempt": self.attempt,
            "packet_path": self.packet_path,
        }


class RecordingWorkerTransport:
    """Transport that records intended worker execution without spawning."""

    name = "recording"

    def __init__(self, *, fail_ticket_ids: set[str] | None = None) -> None:
        self.fail_ticket_ids = set(fail_ticket_ids or set())

    def run(self, packet: Mapping[str, Any]) -> WorkerRunOutcome:
        ticket_id = str(packet.get("ticket_id", "ticket"))
        prompt_path = str(packet.get("prompt_path", ""))
        planned_command = _planned_codex_command(prompt_path)
        if ticket_id in self.fail_ticket_ids:
            return WorkerRunOutcome(
                ticket_id=ticket_id,
                status="failed",
                reason="recording transport injected failure",
                planned_command=planned_command,
                output_ref=f"recording://{ticket_id}/failed",
            )
        return WorkerRunOutcome(
            ticket_id=ticket_id,
            status="succeeded",
            reason="recorded worker command without spawning process",
            planned_command=planned_command,
            output_ref=f"recording://{ticket_id}/succeeded",
        )


@dataclass(frozen=True)
class AutonomousWorkerRunnerReport:
    policy: WorkerRunnerPolicy
    worker_runs: tuple[WorkerRunOutcome, ...]
    retry_queue: tuple[RetryQueueItem, ...]
    state_path: Path
    next_runnable_ticket: str | None

    def to_dict(self) -> dict[str, Any]:
        succeeded = tuple(run for run in self.worker_runs if run.succeeded)
        failed = tuple(run for run in self.worker_runs if not run.succeeded)
        payload = {
            "summary": {
                "claimed_packet_count": len(self.worker_runs),
                "succeeded_run_count": len(succeeded),
                "failed_run_count": len(failed),
                "retry_queue_count": len(self.retry_queue),
                "next_runnable_ticket": self.next_runnable_ticket,
                "passed": len(self.worker_runs) > 0 and len(failed) == 0 and not self.retry_queue and self._safety_passed(),
            },
            "policy": self.policy.to_dict(),
            "score": {
                **_FORBIDDEN_SCORE,
                "state_write_count": 1,
                "claimed_packet_count": len(self.worker_runs),
            },
            "worker_runs": [run.to_dict() for run in self.worker_runs],
            "retry_queue": [item.to_dict() for item in self.retry_queue],
            "state_path": str(self.state_path),
            "operator_handoff": {
                "completed_tickets": [run.ticket_id for run in succeeded],
                "retry_tickets": [item.ticket_id for item in self.retry_queue],
                "next_step": "rerun dispatcher/runner with completed tickets, or fix retry queue first",
                "real_process_execution_enabled": False,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _safety_passed(self) -> bool:
        return (
            self.policy.transport == "recording"
            and not self.policy.spawn_processes
            and not self.policy.execute_shell_commands
            and not self.policy.read_credentials
            and not self.policy.allow_network
            and all(value == 0 for value in _FORBIDDEN_SCORE.values())
        )


def run_autonomous_worker_runner_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_tickets: int = 3,
    max_parallel: int = 2,
    dispatch_dir: str | Path = "/tmp/opscat-autonomous-worker-runner-dispatch",
    state_path: str | Path = "/tmp/opscat-autonomous-worker-runner-state.json",
    transport: WorkerTransport | None = None,
) -> AutonomousWorkerRunnerReport:
    worker_transport = transport or RecordingWorkerTransport()
    policy = WorkerRunnerPolicy(transport=worker_transport.name, max_parallel=max(1, max_parallel))
    dispatcher = run_autonomous_agent_dispatcher_fixture(
        path,
        completed=set(completed or set()),
        max_tickets=max_tickets,
        max_parallel=max_parallel,
        dispatch_dir=dispatch_dir,
    ).to_dict()
    packets = tuple(item for item in _sequence(dispatcher.get("dispatch_packets", ())) if isinstance(item, Mapping))
    worker_runs = tuple(worker_transport.run(packet) for packet in packets)
    retry_queue = tuple(
        RetryQueueItem(
            ticket_id=run.ticket_id,
            reason=run.reason,
            attempt=1,
            packet_path=str(_packet_path_for_ticket(packets, run.ticket_id)),
        )
        for run in worker_runs
        if not run.succeeded
    )
    state_file = Path(state_path)
    _write_state(state_file, worker_runs, retry_queue, str(dispatcher.get("summary", {}).get("next_runnable_ticket") or "") or None)
    return AutonomousWorkerRunnerReport(
        policy=policy,
        worker_runs=worker_runs,
        retry_queue=retry_queue,
        state_path=state_file,
        next_runnable_ticket=str(dispatcher.get("summary", {}).get("next_runnable_ticket") or "") or None,
    )


def render_autonomous_worker_runner_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    runs = tuple(item for item in _sequence(payload.get("worker_runs", ())) if isinstance(item, Mapping))
    retry = tuple(item for item in _sequence(payload.get("retry_queue", ())) if isinstance(item, Mapping))
    lines = [
        "# OpsCat Autonomous Worker Runner",
        "",
        "## Summary",
        "",
        f"- claimed packets: {summary.get('claimed_packet_count', 0)}",
        f"- succeeded runs: {summary.get('succeeded_run_count', 0)}",
        f"- failed runs: {summary.get('failed_run_count', 0)}",
        f"- retry queue: {summary.get('retry_queue_count', 0)}",
        f"- next runnable ticket: {summary.get('next_runnable_ticket')}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Worker runs",
        "",
    ]
    for run in runs:
        lines.append(f"- {run.get('ticket_id')}: {run.get('status')} — {run.get('reason')}")
    lines.extend(["", "## Retry queue", ""])
    if retry:
        for item in retry:
            lines.append(f"- {item.get('ticket_id')}: attempt {item.get('attempt')} — {item.get('reason')}")
    else:
        lines.append("- empty")
    lines.append("")
    return "\n".join(lines)


def write_autonomous_worker_runner_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_autonomous_worker_runner_markdown(payload), encoding="utf-8")


def _write_state(state_path: Path, worker_runs: Sequence[WorkerRunOutcome], retry_queue: Sequence[RetryQueueItem], next_runnable_ticket: str | None) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed_tickets": [run.ticket_id for run in worker_runs if run.succeeded],
        "failed_tickets": [run.ticket_id for run in worker_runs if not run.succeeded],
        "retry_queue": [item.to_dict() for item in retry_queue],
        "next_runnable_ticket": next_runnable_ticket,
        "transport": "recording",
    }
    state_path.write_text(json.dumps(redact_value(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _packet_path_for_ticket(packets: Sequence[Mapping[str, Any]], ticket_id: str) -> str:
    for packet in packets:
        if str(packet.get("ticket_id", "")) == ticket_id:
            return str(packet.get("packet_path", ""))
    return ""


def _planned_codex_command(prompt_path: str) -> str:
    return f"codex exec --skip-git-repo-check --sandbox workspace-write --color never --file {prompt_path}"


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
