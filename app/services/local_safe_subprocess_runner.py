"""P75 local safe subprocess runner.

P75 consumes the P74 dry-run gate and performs a local-safe runner pass. The
repository verification transport is simulated: it writes stdout/stderr
artifacts, records success/failure/retry state, and keeps actual subprocess
spawns at zero. A real transport class exists for later explicit opt-in use, but
normal verification never selects it.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.real_subprocess_execution_dry_run_gate import (
    GitWorktreeStatusProvider,
    StaticGitWorktreeStatusProvider,
    run_real_subprocess_execution_dry_run_gate_fixture,
)
from app.services.redaction import redact_value

_FORBIDDEN_SCORE: dict[str, int] = {
    "shell_command_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
}


class LocalSubprocessTransport(Protocol):
    name: str
    actual_spawn_count: int

    def run(self, command: str, *, ticket_id: str, timeout_seconds: int, artifact_dir: Path) -> LocalRunRecord:
        """Run or simulate a local subprocess command."""


@dataclass(frozen=True)
class LocalSafeSubprocessPolicy:
    enable_real_subprocess: bool
    enable_local_subprocess: bool
    transport: str
    max_processes: int
    timeout_seconds: int
    actual_spawn_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enable_real_subprocess": self.enable_real_subprocess,
            "enable_local_subprocess": self.enable_local_subprocess,
            "transport": self.transport,
            "max_processes": self.max_processes,
            "timeout_seconds": self.timeout_seconds,
            "actual_spawn_confirmed": self.actual_spawn_confirmed,
            "actual_spawn_allowed": self.transport == "actual-local-subprocess" and self.enable_local_subprocess and self.actual_spawn_confirmed,
        }


@dataclass(frozen=True)
class LocalRunRecord:
    ticket_id: str
    command: str
    status: str
    exit_code: int
    reason: str
    stdout_path: Path
    stderr_path: Path
    actual_spawned: bool = False
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded" and self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "actual_spawned": self.actual_spawned,
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True)
class LocalRetryItem:
    ticket_id: str
    reason: str
    exit_code: int
    stdout_path: str
    stderr_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "reason": self.reason,
            "exit_code": self.exit_code,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
        }


class SimulatedLocalSubprocessTransport:
    """Local subprocess transport used by repository verification."""

    name = "simulated-local-subprocess"
    actual_spawn_count = 0

    def __init__(self, *, fail_ticket_ids: set[str] | None = None) -> None:
        self.fail_ticket_ids = set(fail_ticket_ids or set())

    def run(self, command: str, *, ticket_id: str, timeout_seconds: int, artifact_dir: Path) -> LocalRunRecord:
        paths = _artifact_paths(ticket_id, artifact_dir)
        paths["stdout"].parent.mkdir(parents=True, exist_ok=True)
        if ticket_id in self.fail_ticket_ids:
            paths["stdout"].write_text(f"simulated local subprocess for {ticket_id}\ncommand={command}\n", encoding="utf-8")
            paths["stderr"].write_text("simulated local subprocess nonzero exit\n", encoding="utf-8")
            return LocalRunRecord(
                ticket_id=ticket_id,
                command=command,
                status="failed",
                exit_code=1,
                reason="simulated local subprocess nonzero exit",
                stdout_path=paths["stdout"],
                stderr_path=paths["stderr"],
            )
        paths["stdout"].write_text(f"simulated local subprocess succeeded for {ticket_id}\ncommand={command}\ntimeout={timeout_seconds}\n", encoding="utf-8")
        paths["stderr"].write_text("", encoding="utf-8")
        return LocalRunRecord(
            ticket_id=ticket_id,
            command=command,
            status="succeeded",
            exit_code=0,
            reason="simulated local subprocess succeeded",
            stdout_path=paths["stdout"],
            stderr_path=paths["stderr"],
        )


class ActualLocalSubprocessTransport:
    """Explicit opt-in actual local subprocess transport for later use."""

    name = "actual-local-subprocess"

    def __init__(self) -> None:
        self.actual_spawn_count = 0

    def run(self, command: str, *, ticket_id: str, timeout_seconds: int, artifact_dir: Path) -> LocalRunRecord:
        paths = _artifact_paths(ticket_id, artifact_dir)
        paths["stdout"].parent.mkdir(parents=True, exist_ok=True)
        self.actual_spawn_count += 1
        try:
            completed = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            paths["stdout"].write_text(str(exc.stdout or ""), encoding="utf-8")
            paths["stderr"].write_text(str(exc.stderr or "timeout"), encoding="utf-8")
            return LocalRunRecord(
                ticket_id=ticket_id,
                command=command,
                status="failed",
                exit_code=124,
                reason="actual local subprocess timed out",
                stdout_path=paths["stdout"],
                stderr_path=paths["stderr"],
                actual_spawned=True,
                timed_out=True,
            )
        paths["stdout"].write_text(completed.stdout, encoding="utf-8")
        paths["stderr"].write_text(completed.stderr, encoding="utf-8")
        return LocalRunRecord(
            ticket_id=ticket_id,
            command=command,
            status="succeeded" if completed.returncode == 0 else "failed",
            exit_code=int(completed.returncode),
            reason="actual local subprocess completed" if completed.returncode == 0 else "actual local subprocess nonzero exit",
            stdout_path=paths["stdout"],
            stderr_path=paths["stderr"],
            actual_spawned=True,
        )


@dataclass(frozen=True)
class LocalSafeSubprocessRunnerReport:
    policy: LocalSafeSubprocessPolicy
    dry_run_payload: Mapping[str, Any]
    local_runs: tuple[LocalRunRecord, ...]
    retry_queue: tuple[LocalRetryItem, ...]
    state_path: Path

    def to_dict(self) -> dict[str, Any]:
        summary = _mapping(self.dry_run_payload.get("summary"))
        dry_ready_count = int(summary.get("dry_run_ready_count", 0) or 0)
        upstream_blocked_count = int(summary.get("validated_command_count", 0) or 0) - dry_ready_count
        started = tuple(run for run in self.local_runs if not run.status.startswith("blocked_"))
        succeeded = tuple(run for run in started if run.succeeded)
        failed = tuple(run for run in started if not run.succeeded)
        local_enablement_blocked = tuple(run for run in self.local_runs if run.status == "blocked_local_enablement_missing")
        actual_spawn_count = sum(1 for run in self.local_runs if run.actual_spawned)
        payload = {
            "summary": {
                "dry_run_ready_count": dry_ready_count,
                "started_run_count": len(started),
                "succeeded_run_count": len(succeeded),
                "failed_run_count": len(failed),
                "retry_queue_count": len(self.retry_queue),
                "upstream_blocked_count": upstream_blocked_count,
                "blocked_by_local_enablement_count": len(local_enablement_blocked),
                "actual_spawn_count": actual_spawn_count,
                "passed": self._passed(dry_ready_count, upstream_blocked_count, failed, local_enablement_blocked, actual_spawn_count),
            },
            "policy": self.policy.to_dict(),
            "score": {
                **_FORBIDDEN_SCORE,
                "simulated_local_process_run_count": len(started) if self.policy.transport == "simulated-local-subprocess" else 0,
                "actual_spawn_count": actual_spawn_count,
                "state_write_count": 1,
            },
            "local_runs": [run.to_dict() for run in self.local_runs],
            "retry_queue": [item.to_dict() for item in self.retry_queue],
            "state_path": str(self.state_path),
            "upstream_dry_run_summary": dict(summary),
            "operator_handoff": {
                "completed_tickets": [run.ticket_id for run in succeeded],
                "retry_tickets": [item.ticket_id for item in self.retry_queue],
                "actual_spawned": actual_spawn_count > 0,
                "next_step": "inspect retry queue before continuing" if self.retry_queue else "feed completed tickets back into the long-run controller",
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _passed(
        self,
        dry_ready_count: int,
        upstream_blocked_count: int,
        failed: Sequence[LocalRunRecord],
        local_enablement_blocked: Sequence[LocalRunRecord],
        actual_spawn_count: int,
    ) -> bool:
        unsafe_upstream = _unsafe_upstream_block_count(self.dry_run_payload)
        return (
            self.policy.enable_real_subprocess
            and self.policy.enable_local_subprocess
            and dry_ready_count > 0
            and len(failed) == 0
            and not self.retry_queue
            and not local_enablement_blocked
            and unsafe_upstream == 0
            and upstream_blocked_count >= 0
            and actual_spawn_count == 0
            and all(value == 0 for value in _FORBIDDEN_SCORE.values())
        )


def run_local_safe_subprocess_runner_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_tickets: int = 3,
    max_parallel: int = 2,
    max_processes: int = 2,
    dispatch_dir: str | Path = "/tmp/opscat-local-safe-subprocess-dispatch",
    state_path: str | Path = "/tmp/opscat-local-safe-subprocess-state.json",
    artifact_dir: str | Path = "/tmp/opscat-local-safe-subprocess-artifacts",
    enable_real_subprocess: bool = False,
    enable_local_subprocess: bool = False,
    actual_spawn_confirmed: bool = False,
    timeout_seconds: int = 1_200,
    git_status_provider: GitWorktreeStatusProvider | None = None,
    transport: LocalSubprocessTransport | None = None,
) -> LocalSafeSubprocessRunnerReport:
    local_transport = transport or SimulatedLocalSubprocessTransport()
    if local_transport.name == "actual-local-subprocess" and not actual_spawn_confirmed:
        local_transport = SimulatedLocalSubprocessTransport()
    policy = LocalSafeSubprocessPolicy(
        enable_real_subprocess=enable_real_subprocess,
        enable_local_subprocess=enable_local_subprocess,
        transport=local_transport.name,
        max_processes=max(1, max_processes),
        timeout_seconds=timeout_seconds,
        actual_spawn_confirmed=actual_spawn_confirmed,
    )
    state_file = Path(state_path)
    artifact_root = Path(artifact_dir)
    dry_run_report = run_real_subprocess_execution_dry_run_gate_fixture(
        path,
        completed=set(completed or set()),
        max_tickets=max_tickets,
        max_parallel=max_parallel,
        max_processes=max_processes,
        dispatch_dir=dispatch_dir,
        state_path=state_file.parent / f"{state_file.stem}-p74-state.json",
        artifact_dir=artifact_root / "p74",
        enable_real_subprocess=enable_real_subprocess,
        timeout_seconds=timeout_seconds,
        git_status_provider=git_status_provider or StaticGitWorktreeStatusProvider(clean=True),
    )
    dry_payload = dry_run_report.to_dict()
    plan = tuple(item for item in _sequence(dry_payload.get("execution_plan", ())) if isinstance(item, Mapping))
    ready_items = tuple(item for item in plan if str(item.get("status", "")) == "dry_run_ready")
    local_runs: list[LocalRunRecord] = []
    if ready_items:
        for item in ready_items:
            ticket_id = str(item.get("ticket_id", ""))
            command = str(item.get("command", ""))
            if not enable_local_subprocess:
                local_runs.append(_blocked_record(ticket_id, command, "blocked_local_enablement_missing", "explicit local subprocess enablement required", artifact_root))
                continue
            local_runs.append(local_transport.run(command, ticket_id=ticket_id, timeout_seconds=timeout_seconds, artifact_dir=artifact_root))
    else:
        for item in plan:
            ticket_id = str(item.get("ticket_id", ""))
            command = str(item.get("command", ""))
            reasons = ", ".join(str(reason) for reason in _sequence(item.get("reasons", ()))) or "upstream dry-run gate blocked"
            local_runs.append(_blocked_record(ticket_id, command, "blocked_upstream_gate", reasons, artifact_root))
    retry_queue = tuple(
        LocalRetryItem(ticket_id=run.ticket_id, reason=run.reason, exit_code=run.exit_code, stdout_path=str(run.stdout_path), stderr_path=str(run.stderr_path))
        for run in local_runs
        if not run.status.startswith("blocked_") and not run.succeeded
    )
    _write_state(state_file, policy, local_runs, retry_queue)
    return LocalSafeSubprocessRunnerReport(policy=policy, dry_run_payload=dry_payload, local_runs=tuple(local_runs), retry_queue=retry_queue, state_path=state_file)


def render_local_safe_subprocess_runner_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    runs = tuple(item for item in _sequence(payload.get("local_runs", ())) if isinstance(item, Mapping))
    retry = tuple(item for item in _sequence(payload.get("retry_queue", ())) if isinstance(item, Mapping))
    lines = [
        "# OpsCat Local Safe Subprocess Runner",
        "",
        "## Summary",
        "",
        f"- dry-run ready: {summary.get('dry_run_ready_count', 0)}",
        f"- started runs: {summary.get('started_run_count', 0)}",
        f"- succeeded runs: {summary.get('succeeded_run_count', 0)}",
        f"- failed runs: {summary.get('failed_run_count', 0)}",
        f"- retry queue: {summary.get('retry_queue_count', 0)}",
        f"- actual spawns: {summary.get('actual_spawn_count', 0)}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Local runs",
        "",
    ]
    for run in runs:
        lines.append(f"- {run.get('ticket_id')}: {run.get('status')} exit={run.get('exit_code')} — {run.get('reason')}")
    lines.extend(["", "## Retry queue", ""])
    if retry:
        for item in retry:
            lines.append(f"- {item.get('ticket_id')}: exit={item.get('exit_code')} — {item.get('reason')}")
    else:
        lines.append("- empty")
    lines.extend(
        [
            "",
            "## Safety counters",
            "",
            f"- simulated local runs: {score.get('simulated_local_process_run_count', 0)}",
            f"- actual spawns: {score.get('actual_spawn_count', 0)}",
            f"- shell execution: {score.get('shell_command_execution_count', 0)}",
            "",
        ]
    )
    return "\n".join(lines)


def write_local_safe_subprocess_runner_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_local_safe_subprocess_runner_markdown(payload), encoding="utf-8")


def _blocked_record(ticket_id: str, command: str, status: str, reason: str, artifact_dir: Path) -> LocalRunRecord:
    paths = _artifact_paths(ticket_id, artifact_dir)
    paths["stdout"].parent.mkdir(parents=True, exist_ok=True)
    paths["stdout"].write_text(f"blocked local subprocess for {ticket_id}\ncommand={command}\n", encoding="utf-8")
    paths["stderr"].write_text(reason + "\n", encoding="utf-8")
    return LocalRunRecord(ticket_id=ticket_id, command=command, status=status, exit_code=126, reason=reason, stdout_path=paths["stdout"], stderr_path=paths["stderr"])


def _write_state(state_path: Path, policy: LocalSafeSubprocessPolicy, local_runs: Sequence[LocalRunRecord], retry_queue: Sequence[LocalRetryItem]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "policy": policy.to_dict(),
        "completed_tickets": [run.ticket_id for run in local_runs if run.succeeded],
        "failed_tickets": [run.ticket_id for run in local_runs if not run.status.startswith("blocked_") and not run.succeeded],
        "blocked_tickets": [run.ticket_id for run in local_runs if run.status.startswith("blocked_")],
        "retry_queue": [item.to_dict() for item in retry_queue],
        "actual_spawn_count": sum(1 for run in local_runs if run.actual_spawned),
        "local_runs": [run.to_dict() for run in local_runs],
    }
    state_path.write_text(json.dumps(redact_value(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _unsafe_upstream_block_count(payload: Mapping[str, Any]) -> int:
    plan = tuple(item for item in _sequence(payload.get("execution_plan", ())) if isinstance(item, Mapping))
    return sum(1 for item in plan if str(item.get("status", "")) not in {"dry_run_ready", "blocked_process_budget"})


def _artifact_paths(ticket_id: str, artifact_dir: Path) -> dict[str, Path]:
    root = artifact_dir / ticket_id
    return {"stdout": root / "stdout.txt", "stderr": root / "stderr.txt"}


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


__all__ = [
    "ActualLocalSubprocessTransport",
    "LocalRunRecord",
    "LocalSafeSubprocessPolicy",
    "LocalSafeSubprocessRunnerReport",
    "LocalSubprocessTransport",
    "SimulatedLocalSubprocessTransport",
    "StaticGitWorktreeStatusProvider",
    "render_local_safe_subprocess_runner_markdown",
    "run_local_safe_subprocess_runner_fixture",
    "write_local_safe_subprocess_runner_outputs",
]
