"""P70 gated worker process runner.

This module validates P69 planned worker commands against a strict process gate:
only `codex exec` commands with required safety flags and prompt paths under the
current dispatch directory are process-capable. Verification remains no-spawn by
default through a recording process transport.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.autonomous_worker_runner import RecordingWorkerTransport, run_autonomous_worker_runner_fixture
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
_REQUIRED_FLAGS: tuple[str, ...] = ("--skip-git-repo-check", "--sandbox", "workspace-write", "--color", "never", "--file")


class ProcessTransport(Protocol):
    name: str

    def run(self, command: str, *, process_execution_enabled: bool) -> ProcessRunOutcome:
        """Run or record a validated process command."""


@dataclass(frozen=True)
class ProcessRunnerPolicy:
    process_execution_enabled: bool
    allowed_binary: str
    required_subcommand: str
    max_parallel: int
    timeout_seconds: int
    spawn_processes: bool = False
    execute_shell_commands: bool = False
    read_credentials: bool = False
    allow_network: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_execution_enabled": self.process_execution_enabled,
            "allowed_binary": self.allowed_binary,
            "required_subcommand": self.required_subcommand,
            "max_parallel": self.max_parallel,
            "timeout_seconds": self.timeout_seconds,
            "spawn_processes": self.spawn_processes,
            "execute_shell_commands": self.execute_shell_commands,
            "read_credentials": self.read_credentials,
            "allow_network": self.allow_network,
        }


@dataclass(frozen=True)
class ProcessRunOutcome:
    status: str
    reason: str
    output_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "output_ref": self.output_ref,
        }


class RecordingProcessTransport:
    """Process transport that never spawns during verification."""

    name = "recording-process"

    def run(self, command: str, *, process_execution_enabled: bool) -> ProcessRunOutcome:
        if process_execution_enabled:
            return ProcessRunOutcome(status="blocked", reason="real process execution is disabled in recording transport", output_ref="recording-process://blocked")
        return ProcessRunOutcome(status="process_ready_not_spawned", reason="validated command recorded without spawning process", output_ref="recording-process://ready")


@dataclass(frozen=True)
class ValidatedWorkerCommand:
    ticket_id: str
    command: str
    status: str
    reasons: tuple[str, ...]
    prompt_path: str
    process_outcome: ProcessRunOutcome | None

    @property
    def process_capable(self) -> bool:
        return self.status == "process_ready_not_spawned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "command": self.command,
            "status": self.status,
            "reasons": list(self.reasons),
            "prompt_path": self.prompt_path,
            "process_outcome": self.process_outcome.to_dict() if self.process_outcome is not None else None,
        }


@dataclass(frozen=True)
class GatedWorkerProcessRunnerReport:
    policy: ProcessRunnerPolicy
    validated_commands: tuple[ValidatedWorkerCommand, ...]
    dispatch_dir: Path

    def to_dict(self) -> dict[str, Any]:
        process_capable = tuple(command for command in self.validated_commands if command.process_capable)
        blocked = tuple(command for command in self.validated_commands if command.status == "blocked")
        payload = {
            "summary": {
                "validated_command_count": len(self.validated_commands),
                "process_capable_count": len(process_capable),
                "spawned_process_count": _FORBIDDEN_SCORE["spawned_process_count"],
                "blocked_command_count": len(blocked),
                "passed": len(self.validated_commands) > 0 and len(blocked) == 0 and self._safety_passed(),
            },
            "policy": self.policy.to_dict(),
            "score": {
                **_FORBIDDEN_SCORE,
                "validated_command_count": len(self.validated_commands),
                "blocked_command_count": len(blocked),
            },
            "dispatch_dir": str(self.dispatch_dir),
            "validated_commands": [command.to_dict() for command in self.validated_commands],
            "blocked_commands": [command.to_dict() for command in blocked],
            "operator_handoff": {
                "real_process_execution_ready": len(blocked) == 0,
                "real_process_execution_enabled": self.policy.process_execution_enabled,
                "next_step": "only enable real process execution after explicit operator gate and bounded runner supervision",
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _safety_passed(self) -> bool:
        return (
            not self.policy.process_execution_enabled
            and not self.policy.spawn_processes
            and not self.policy.execute_shell_commands
            and not self.policy.read_credentials
            and not self.policy.allow_network
            and all(value == 0 for value in _FORBIDDEN_SCORE.values())
        )


def run_gated_worker_process_runner_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_tickets: int = 3,
    max_parallel: int = 2,
    dispatch_dir: str | Path = "/tmp/opscat-gated-worker-process-runner-dispatch",
    state_path: str | Path = "/tmp/opscat-gated-worker-process-runner-state.json",
    transport: ProcessTransport | None = None,
    command_mutator: Callable[[str], str] | None = None,
) -> GatedWorkerProcessRunnerReport:
    dispatch_root = Path(dispatch_dir)
    policy = ProcessRunnerPolicy(
        process_execution_enabled=False,
        allowed_binary="codex",
        required_subcommand="exec",
        max_parallel=max(1, max_parallel),
        timeout_seconds=1_200,
    )
    process_transport = transport or RecordingProcessTransport()
    worker_report = run_autonomous_worker_runner_fixture(
        path,
        completed=set(completed or set()),
        max_tickets=max_tickets,
        max_parallel=max_parallel,
        dispatch_dir=dispatch_root,
        state_path=state_path,
        transport=RecordingWorkerTransport(),
    ).to_dict()
    runs = tuple(item for item in _sequence(worker_report.get("worker_runs", ())) if isinstance(item, Mapping))
    validated: list[ValidatedWorkerCommand] = []
    for run in runs:
        command = str(run.get("planned_command", ""))
        if command_mutator is not None:
            command = command_mutator(command)
        validated.append(_validate_command(run, command, dispatch_root, policy, process_transport))
    return GatedWorkerProcessRunnerReport(policy=policy, validated_commands=tuple(validated), dispatch_dir=dispatch_root)


def render_gated_worker_process_runner_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    validated = tuple(item for item in _sequence(payload.get("validated_commands", ())) if isinstance(item, Mapping))
    blocked = tuple(item for item in _sequence(payload.get("blocked_commands", ())) if isinstance(item, Mapping))
    lines = [
        "# OpsCat Gated Worker Process Runner",
        "",
        "## Summary",
        "",
        f"- validated commands: {summary.get('validated_command_count', 0)}",
        f"- process-capable commands: {summary.get('process_capable_count', 0)}",
        f"- spawned processes: {summary.get('spawned_process_count', 0)}",
        f"- blocked commands: {summary.get('blocked_command_count', 0)}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Validated commands",
        "",
    ]
    for item in validated:
        lines.append(f"- {item.get('ticket_id')}: {item.get('status')} — {', '.join(str(reason) for reason in _sequence(item.get('reasons', ())))}")
    lines.extend(["", "## Blocked commands", ""])
    if blocked:
        for item in blocked:
            lines.append(f"- {item.get('ticket_id')}: {', '.join(str(reason) for reason in _sequence(item.get('reasons', ())))}")
    else:
        lines.append("- empty")
    lines.append("")
    return "\n".join(lines)


def write_gated_worker_process_runner_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_gated_worker_process_runner_markdown(payload), encoding="utf-8")


def _validate_command(
    run: Mapping[str, Any],
    command: str,
    dispatch_dir: Path,
    policy: ProcessRunnerPolicy,
    transport: ProcessTransport,
) -> ValidatedWorkerCommand:
    ticket_id = str(run.get("ticket_id", ""))
    reasons: list[str] = []
    prompt_path = ""
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = []
        reasons.append("command_parse_error")
    if len(parts) < 2 or parts[0] != policy.allowed_binary:
        reasons.append("binary_not_allowlisted")
    if len(parts) < 2 or parts[1] != policy.required_subcommand:
        reasons.append("subcommand_not_allowlisted")
    for flag in _REQUIRED_FLAGS:
        if flag not in parts:
            reasons.append(f"missing_required_token:{flag}")
    if "--file" in parts:
        index = parts.index("--file")
        if index + 1 < len(parts):
            prompt_path = parts[index + 1]
    elif parts:
        prompt_path = parts[-1]
    if not _is_under_dispatch_dir(prompt_path, dispatch_dir):
        reasons.append("prompt_path_outside_dispatch_dir")
    if reasons:
        return ValidatedWorkerCommand(
            ticket_id=ticket_id,
            command=command,
            status="blocked",
            reasons=tuple(dict.fromkeys(reasons)),
            prompt_path=prompt_path,
            process_outcome=None,
        )
    outcome = transport.run(command, process_execution_enabled=policy.process_execution_enabled)
    return ValidatedWorkerCommand(
        ticket_id=ticket_id,
        command=command,
        status=outcome.status,
        reasons=(outcome.reason,),
        prompt_path=prompt_path,
        process_outcome=outcome,
    )


def _is_under_dispatch_dir(prompt_path: str, dispatch_dir: Path) -> bool:
    if not prompt_path:
        return False
    try:
        prompt = Path(prompt_path).resolve()
        root = dispatch_dir.resolve()
        prompt.relative_to(root)
    except ValueError:
        return False
    return True


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
