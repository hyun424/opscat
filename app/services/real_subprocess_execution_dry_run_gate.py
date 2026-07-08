"""P74 real subprocess execution dry-run gate.

This module is the safety gate between validated `codex exec` commands and any
future real subprocess transport. It does not spawn processes. It verifies that
P70 command validation passed, explicit real-subprocess enablement was provided,
the worktree is clean, process budget is respected, and artifact/state paths are
ready before a later ticket may enable real execution.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.gated_worker_process_runner import run_gated_worker_process_runner_fixture
from app.services.redaction import redact_value

_FORBIDDEN_SCORE: dict[str, int] = {
    "actual_spawn_count": 0,
    "shell_command_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
}


class GitWorktreeStatusProvider(Protocol):
    name: str

    def status(self) -> GitWorktreeStatus:
        """Return current worktree status without mutating anything."""


@dataclass(frozen=True)
class GitWorktreeStatus:
    clean: bool
    entries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"clean": self.clean, "entries": list(self.entries)}


class StaticGitWorktreeStatusProvider:
    """Deterministic git status provider for safe verification and tests."""

    name = "static-git-status"

    def __init__(self, *, clean: bool, entries: Sequence[str] = ()) -> None:
        self._status = GitWorktreeStatus(clean=clean, entries=tuple(entries))

    def status(self) -> GitWorktreeStatus:
        return self._status


@dataclass(frozen=True)
class RealSubprocessDryRunPolicy:
    enable_real_subprocess: bool
    max_processes: int
    timeout_seconds: int
    require_clean_git: bool
    allowed_binary: str = "codex"
    required_subcommand: str = "exec"
    actual_spawn_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enable_real_subprocess": self.enable_real_subprocess,
            "max_processes": self.max_processes,
            "timeout_seconds": self.timeout_seconds,
            "require_clean_git": self.require_clean_git,
            "allowed_binary": self.allowed_binary,
            "required_subcommand": self.required_subcommand,
            "actual_spawn_enabled": self.actual_spawn_enabled,
        }


@dataclass(frozen=True)
class DryRunExecutionPlanItem:
    ticket_id: str
    command: str
    status: str
    reasons: tuple[str, ...]
    prompt_path: str
    stdout_path: Path
    stderr_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "command": self.command,
            "status": self.status,
            "reasons": list(self.reasons),
            "prompt_path": self.prompt_path,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
        }


@dataclass(frozen=True)
class RealSubprocessExecutionDryRunGateReport:
    policy: RealSubprocessDryRunPolicy
    git_status: GitWorktreeStatus
    execution_plan: tuple[DryRunExecutionPlanItem, ...]
    state_path: Path
    dispatch_dir: Path

    def to_dict(self) -> dict[str, Any]:
        dry_run_ready = tuple(item for item in self.execution_plan if item.status == "dry_run_ready")
        budget_blocked = tuple(item for item in self.execution_plan if item.status == "blocked_process_budget")
        dirty_git_blocked = tuple(item for item in self.execution_plan if item.status == "blocked_dirty_git")
        enablement_blocked = tuple(item for item in self.execution_plan if item.status == "blocked_enablement_missing")
        command_gate_blocked = tuple(item for item in self.execution_plan if item.status == "blocked_command_gate")
        payload = {
            "summary": {
                "validated_command_count": len(self.execution_plan),
                "dry_run_ready_count": len(dry_run_ready),
                "budget_blocked_count": len(budget_blocked),
                "dirty_git_block_count": len(dirty_git_blocked),
                "enablement_blocked_count": len(enablement_blocked),
                "command_gate_blocked_count": len(command_gate_blocked),
                "actual_spawn_count": _FORBIDDEN_SCORE["actual_spawn_count"],
                "passed": self._passed(dry_run_ready, dirty_git_blocked, enablement_blocked, command_gate_blocked),
            },
            "policy": self.policy.to_dict(),
            "git_status": self.git_status.to_dict(),
            "score": {
                **_FORBIDDEN_SCORE,
                "would_spawn_count": len(dry_run_ready),
                "state_write_count": 1,
            },
            "dispatch_dir": str(self.dispatch_dir),
            "state_path": str(self.state_path),
            "execution_plan": [item.to_dict() for item in self.execution_plan],
            "operator_handoff": {
                "real_subprocess_dry_run_ready": bool(dry_run_ready) and self._passed(dry_run_ready, dirty_git_blocked, enablement_blocked, command_gate_blocked),
                "dry_run_ready_tickets": [item.ticket_id for item in dry_run_ready],
                "blocked_tickets": [item.ticket_id for item in self.execution_plan if item.status != "dry_run_ready"],
                "next_step": _next_step(self.git_status, dirty_git_blocked, enablement_blocked, command_gate_blocked),
                "actual_spawned": False,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _passed(
        self,
        dry_run_ready: Sequence[DryRunExecutionPlanItem],
        dirty_git_blocked: Sequence[DryRunExecutionPlanItem],
        enablement_blocked: Sequence[DryRunExecutionPlanItem],
        command_gate_blocked: Sequence[DryRunExecutionPlanItem],
    ) -> bool:
        return (
            self.policy.enable_real_subprocess
            and self.policy.actual_spawn_enabled is False
            and self.git_status.clean
            and bool(dry_run_ready)
            and not dirty_git_blocked
            and not enablement_blocked
            and not command_gate_blocked
            and all(value == 0 for value in _FORBIDDEN_SCORE.values())
        )


def run_real_subprocess_execution_dry_run_gate_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_tickets: int = 3,
    max_parallel: int = 2,
    max_processes: int = 2,
    dispatch_dir: str | Path = "/tmp/opscat-real-subprocess-dry-run-dispatch",
    state_path: str | Path = "/tmp/opscat-real-subprocess-dry-run-state.json",
    artifact_dir: str | Path = "/tmp/opscat-real-subprocess-dry-run-artifacts",
    enable_real_subprocess: bool = False,
    require_clean_git: bool = True,
    timeout_seconds: int = 1_200,
    git_status_provider: GitWorktreeStatusProvider | None = None,
    command_mutator: Callable[[str], str] | None = None,
) -> RealSubprocessExecutionDryRunGateReport:
    dispatch_root = Path(dispatch_dir)
    state_file = Path(state_path)
    artifact_root = Path(artifact_dir)
    policy = RealSubprocessDryRunPolicy(
        enable_real_subprocess=enable_real_subprocess,
        max_processes=max(1, max_processes),
        timeout_seconds=timeout_seconds,
        require_clean_git=require_clean_git,
    )
    status_provider = git_status_provider or StaticGitWorktreeStatusProvider(clean=True)
    git_status = status_provider.status()
    gate_payload = run_gated_worker_process_runner_fixture(
        path,
        completed=set(completed or set()),
        max_tickets=max_tickets,
        max_parallel=max_parallel,
        dispatch_dir=dispatch_root,
        state_path=state_file.parent / f"{state_file.stem}-p70-state.json",
        command_mutator=command_mutator,
    ).to_dict()
    validated_commands = tuple(item for item in _sequence(gate_payload.get("validated_commands", ())) if isinstance(item, Mapping))
    plan: list[DryRunExecutionPlanItem] = []
    ready_budget_used = 0
    for command in validated_commands:
        status, reasons = _classify_command(command, policy, git_status, ready_budget_used)
        if status == "dry_run_ready":
            ready_budget_used += 1
        item = _plan_item(command, status=status, reasons=reasons, artifact_dir=artifact_root)
        _write_artifacts(item)
        plan.append(item)
    _write_state(state_file, policy, git_status, plan)
    return RealSubprocessExecutionDryRunGateReport(
        policy=policy,
        git_status=git_status,
        execution_plan=tuple(plan),
        state_path=state_file,
        dispatch_dir=dispatch_root,
    )


def render_real_subprocess_execution_dry_run_gate_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    git_status = _mapping(payload.get("git_status"))
    plan = tuple(item for item in _sequence(payload.get("execution_plan", ())) if isinstance(item, Mapping))
    lines = [
        "# OpsCat Real Subprocess Execution Dry-Run Gate",
        "",
        "## Summary",
        "",
        f"- validated commands: {summary.get('validated_command_count', 0)}",
        f"- dry-run ready: {summary.get('dry_run_ready_count', 0)}",
        f"- budget blocked: {summary.get('budget_blocked_count', 0)}",
        f"- dirty git blocked: {summary.get('dirty_git_block_count', 0)}",
        f"- enablement blocked: {summary.get('enablement_blocked_count', 0)}",
        f"- command gate blocked: {summary.get('command_gate_blocked_count', 0)}",
        f"- actual spawns: {summary.get('actual_spawn_count', 0)}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Git guard",
        "",
        f"- clean: {git_status.get('clean', False)}",
        f"- entries: {', '.join(str(item) for item in _sequence(git_status.get('entries', ()))) or 'empty'}",
        "",
        "## Execution plan",
        "",
    ]
    for item in plan:
        reasons = ", ".join(str(reason) for reason in _sequence(item.get("reasons", ())))
        lines.append(f"- {item.get('ticket_id')}: {item.get('status')} — {reasons}")
    lines.extend(
        [
            "",
            "## Safety counters",
            "",
            f"- would spawn: {score.get('would_spawn_count', 0)}",
            f"- actual spawn: {score.get('actual_spawn_count', 0)}",
            f"- shell command execution: {score.get('shell_command_execution_count', 0)}",
            (
                "- live/network/action/production: "
                f"{score.get('live_api_call_count', 0)}/{score.get('network_call_count', 0)}/"
                f"{score.get('action_execution_count', 0)}/{score.get('production_mutation_count', 0)}"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_real_subprocess_execution_dry_run_gate_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_real_subprocess_execution_dry_run_gate_markdown(payload), encoding="utf-8")


def _classify_command(command: Mapping[str, Any], policy: RealSubprocessDryRunPolicy, git_status: GitWorktreeStatus, ready_budget_used: int) -> tuple[str, tuple[str, ...]]:
    gate_status = str(command.get("status", ""))
    gate_reasons = tuple(str(reason) for reason in _sequence(command.get("reasons", ())))
    if gate_status != "process_ready_not_spawned":
        return "blocked_command_gate", gate_reasons or ("p70_command_gate_blocked",)
    if not policy.enable_real_subprocess:
        return "blocked_enablement_missing", ("explicit real subprocess enablement required",)
    if policy.require_clean_git and not git_status.clean:
        return "blocked_dirty_git", ("git worktree must be clean before real subprocess execution",)
    if ready_budget_used >= policy.max_processes:
        return "blocked_process_budget", (f"max process budget reached: {policy.max_processes}",)
    return "dry_run_ready", ("would spawn real subprocess if non-dry-run execution were enabled",)


def _plan_item(command: Mapping[str, Any], *, status: str, reasons: Sequence[str], artifact_dir: Path) -> DryRunExecutionPlanItem:
    ticket_id = str(command.get("ticket_id", ""))
    stdout_path = artifact_dir / ticket_id / "stdout.txt"
    stderr_path = artifact_dir / ticket_id / "stderr.txt"
    return DryRunExecutionPlanItem(
        ticket_id=ticket_id,
        command=str(command.get("command", "")),
        status=status,
        reasons=tuple(reasons),
        prompt_path=str(command.get("prompt_path", "")),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def _write_artifacts(item: DryRunExecutionPlanItem) -> None:
    item.stdout_path.parent.mkdir(parents=True, exist_ok=True)
    item.stdout_path.write_text(f"dry-run status={item.status}\nticket={item.ticket_id}\ncommand={item.command}\n", encoding="utf-8")
    item.stderr_path.write_text("\n".join(item.reasons) + "\n", encoding="utf-8")


def _write_state(state_path: Path, policy: RealSubprocessDryRunPolicy, git_status: GitWorktreeStatus, plan: Sequence[DryRunExecutionPlanItem]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    dry_run_ready = [item.ticket_id for item in plan if item.status == "dry_run_ready"]
    payload = {
        "policy": policy.to_dict(),
        "git_status": git_status.to_dict(),
        "dry_run_ready_tickets": dry_run_ready,
        "blocked_tickets": [item.ticket_id for item in plan if item.status != "dry_run_ready"],
        "actual_spawn_count": 0,
        "execution_plan": [item.to_dict() for item in plan],
    }
    state_path.write_text(json.dumps(redact_value(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _next_step(
    git_status: GitWorktreeStatus,
    dirty_git_blocked: Sequence[DryRunExecutionPlanItem],
    enablement_blocked: Sequence[DryRunExecutionPlanItem],
    command_gate_blocked: Sequence[DryRunExecutionPlanItem],
) -> str:
    if dirty_git_blocked or not git_status.clean:
        return "clean or explicitly review worktree changes before real subprocess execution"
    if enablement_blocked:
        return "rerun with explicit real subprocess enablement after reviewing the dry-run plan"
    if command_gate_blocked:
        return "fix P70 command gate violations before real subprocess execution"
    return "review dry-run plan, then enable the real subprocess transport in a separately gated ticket"


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
    "GitWorktreeStatus",
    "GitWorktreeStatusProvider",
    "RealSubprocessDryRunPolicy",
    "RealSubprocessExecutionDryRunGateReport",
    "StaticGitWorktreeStatusProvider",
    "render_real_subprocess_execution_dry_run_gate_markdown",
    "run_real_subprocess_execution_dry_run_gate_fixture",
    "write_real_subprocess_execution_dry_run_gate_outputs",
]
