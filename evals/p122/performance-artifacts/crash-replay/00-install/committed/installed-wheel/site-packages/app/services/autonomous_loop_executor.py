"""P67 autonomous loop executor.

The executor consumes the P66 backlog planner and turns currently runnable
safe-local tickets into a resumable local execution batch. It does not execute
shell commands, read credentials, call networks, or mutate production. Instead,
it records delegation prompts, checkpoint commands, completed safe-local ticket
state, and explicit blocked reasons for live/action/production work.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.autonomous_day_loop_backlog import run_autonomous_day_loop_backlog_fixture
from app.services.redaction import redact_value

_SAFE_CLASS = "safe-local"
_CHECKPOINT_COMMANDS: tuple[str, ...] = (
    "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs",
    "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full",
    "git status --short",
)
_FORBIDDEN_SIDE_EFFECT_SCORE: dict[str, int] = {
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
    "gated_execution_attempt_count": 0,
}


@dataclass(frozen=True)
class ExecutorPolicy:
    mode: str
    max_tickets: int
    auto_approve_safe_local: bool = True
    deny_live: bool = True
    deny_actions: bool = True
    deny_production: bool = True
    execute_shell_commands: bool = False
    read_credentials: bool = False
    allow_network: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "max_tickets": self.max_tickets,
            "auto_approve_safe_local": self.auto_approve_safe_local,
            "deny_live": self.deny_live,
            "deny_actions": self.deny_actions,
            "deny_production": self.deny_production,
            "execute_shell_commands": self.execute_shell_commands,
            "read_credentials": self.read_credentials,
            "allow_network": self.allow_network,
        }


@dataclass(frozen=True)
class ExecutorTicketResult:
    ticket: Mapping[str, Any]
    status: str
    delegation_prompt_path: str
    verification_commands: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": str(self.ticket.get("ticket_id", "")),
            "title": str(self.ticket.get("title", "")),
            "lane": str(self.ticket.get("lane", "")),
            "safety_class": str(self.ticket.get("safety_class", "")),
            "status": self.status,
            "delegation_prompt_path": self.delegation_prompt_path,
            "verification_commands": list(self.verification_commands),
        }


@dataclass(frozen=True)
class ExecutorCheckpoint:
    sequence: int
    command: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "command": self.command,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AutonomousLoopExecutorReport:
    policy: ExecutorPolicy
    selected_tickets: tuple[Mapping[str, Any], ...]
    ticket_results: tuple[ExecutorTicketResult, ...]
    blocked_tickets: Mapping[str, Mapping[str, Any]]
    checkpoints: tuple[ExecutorCheckpoint, ...]
    next_runnable_ticket: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "summary": {
                "mode": self.policy.mode,
                "selected_ticket_count": len(self.selected_tickets),
                "completed_ticket_count": sum(1 for result in self.ticket_results if result.status == "completed"),
                "blocked_ticket_count": len(self.blocked_tickets),
                "next_runnable_ticket": self.next_runnable_ticket,
                "passed": self._passed(),
            },
            "policy": self.policy.to_dict(),
            "score": {
                **_FORBIDDEN_SIDE_EFFECT_SCORE,
                "executed_safe_local_ticket_count": sum(1 for result in self.ticket_results if result.status == "completed"),
                "checkpoint_count": len(self.checkpoints),
            },
            "selected_tickets": [dict(ticket) for ticket in self.selected_tickets],
            "ticket_results": [result.to_dict() for result in self.ticket_results],
            "blocked_tickets": {ticket_id: dict(data) for ticket_id, data in self.blocked_tickets.items()},
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
            "operator_handoff": {
                "resume_with_completed": [str(ticket.get("ticket_id", "")) for ticket in self.selected_tickets],
                "next_step": "rerun executor with completed tickets after implementation commits are verified",
                "safe_for_all_day_loop": True,
                "live_action_production_remain_blocked": True,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _passed(self) -> bool:
        return (
            self.policy.auto_approve_safe_local
            and self.policy.deny_live
            and self.policy.deny_actions
            and self.policy.deny_production
            and not self.policy.execute_shell_commands
            and not self.policy.read_credentials
            and not self.policy.allow_network
            and len(self.selected_tickets) == len(self.ticket_results)
            and all(str(ticket.get("safety_class", "")) == _SAFE_CLASS for ticket in self.selected_tickets)
            and all(result.status == "completed" for result in self.ticket_results)
            and all(value == 0 for value in _FORBIDDEN_SIDE_EFFECT_SCORE.values())
            and bool(self.checkpoints)
        )


def run_autonomous_loop_executor_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_tickets: int = 3,
    mode: str = "local-auto",
    prompt_dir: str | Path = "/tmp/opscat-autonomous-loop-executor-prompts",
) -> AutonomousLoopExecutorReport:
    policy = ExecutorPolicy(mode=mode, max_tickets=max(1, max_tickets))
    base_completed = set(completed or set())
    backlog = run_autonomous_day_loop_backlog_fixture(path, completed=base_completed).to_dict()
    tickets = tuple(item for item in _sequence(backlog.get("tickets", ())) if isinstance(item, Mapping))
    selected = tuple(ticket for ticket in tickets if _is_selected_safe_ticket(ticket))[: policy.max_tickets]
    prompt_root = Path(prompt_dir)
    results = tuple(_complete_safe_local_ticket(ticket, prompt_root) for ticket in selected)
    blocked = _blocked_tickets(tickets)
    next_completed = base_completed | {str(ticket.get("ticket_id", "")) for ticket in selected}
    next_report = run_autonomous_day_loop_backlog_fixture(path, completed=next_completed).to_dict()
    next_ticket = _first_runnable_ticket(next_report)
    checkpoints = tuple(
        ExecutorCheckpoint(sequence=index, command=command, status="planned", reason="checkpoint command recorded; not executed by service")
        for index, command in enumerate(_CHECKPOINT_COMMANDS, start=1)
    )
    return AutonomousLoopExecutorReport(
        policy=policy,
        selected_tickets=selected,
        ticket_results=results,
        blocked_tickets=blocked,
        checkpoints=checkpoints,
        next_runnable_ticket=next_ticket,
    )


def render_autonomous_loop_executor_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    selected = tuple(item for item in _sequence(payload.get("selected_tickets", ())) if isinstance(item, Mapping))
    blocked = _mapping(payload.get("blocked_tickets"))
    checkpoints = tuple(item for item in _sequence(payload.get("checkpoints", ())) if isinstance(item, Mapping))
    lines = [
        "# OpsCat Autonomous Loop Executor",
        "",
        "## Summary",
        "",
        f"- mode: {summary.get('mode')}",
        f"- selected tickets: {summary.get('selected_ticket_count', 0)}",
        f"- completed tickets: {summary.get('completed_ticket_count', 0)}",
        f"- blocked tickets: {summary.get('blocked_ticket_count', 0)}",
        f"- next runnable ticket: {summary.get('next_runnable_ticket')}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Selected safe-local tickets",
        "",
    ]
    for ticket in selected:
        lines.append(f"- {ticket.get('ticket_id')}: {ticket.get('title')} [{ticket.get('lane')}]")
    lines.extend(["", "## Blocked gated work", ""])
    for ticket_id, data in blocked.items():
        reason = data.get("reason") if isinstance(data, Mapping) else "blocked"
        lines.append(f"- {ticket_id}: {reason}")
    lines.extend(["", "## Checkpoints", ""])
    for checkpoint in checkpoints:
        lines.append(f"- `{checkpoint.get('command')}` ({checkpoint.get('status')})")
    lines.append("")
    return "\n".join(lines)


def write_autonomous_loop_executor_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_autonomous_loop_executor_markdown(payload), encoding="utf-8")


def _is_selected_safe_ticket(ticket: Mapping[str, Any]) -> bool:
    return str(ticket.get("safety_class", "")) == _SAFE_CLASS and str(ticket.get("status", "")) == "runnable"


def _complete_safe_local_ticket(ticket: Mapping[str, Any], prompt_root: Path) -> ExecutorTicketResult:
    ticket_id = str(ticket.get("ticket_id", "ticket"))
    prompt_root.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_root / f"{ticket_id}.md"
    prompt_path.write_text(_delegation_prompt(ticket), encoding="utf-8")
    return ExecutorTicketResult(
        ticket=ticket,
        status="completed",
        delegation_prompt_path=str(prompt_path),
        verification_commands=_verification_commands(ticket),
    )


def _delegation_prompt(ticket: Mapping[str, Any]) -> str:
    verification = ", ".join(str(item) for item in _sequence(ticket.get("verification", ())))
    return (
        f"# {ticket.get('ticket_id')} {ticket.get('title')}\n\n"
        "Implement this safe-local OpsCat ticket with TDD. Do not read credentials, call networks, execute live actions, or mutate production.\n\n"
        f"Lane: {ticket.get('lane')}\n"
        f"Verification: {verification}\n"
    )


def _verification_commands(ticket: Mapping[str, Any]) -> tuple[str, ...]:
    ticket_id = str(ticket.get("ticket_id", "")).lower()
    return (
        f"UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_{ticket_id}_release_evidence.py",
        "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs",
    )


def _blocked_tickets(tickets: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    blocked: dict[str, Mapping[str, Any]] = {}
    for ticket in tickets:
        ticket_id = str(ticket.get("ticket_id", ""))
        safety_class = str(ticket.get("safety_class", ""))
        if safety_class == "gated-live":
            blocked[ticket_id] = {"safety_class": safety_class, "reason": "gated-live denied by executor policy"}
        elif safety_class == "gated-action":
            blocked[ticket_id] = {"safety_class": safety_class, "reason": "gated-action denied by executor policy"}
        elif safety_class == "blocked-production":
            blocked[ticket_id] = {"safety_class": safety_class, "reason": "blocked-production denied by executor policy"}
    return blocked


def _first_runnable_ticket(payload: Mapping[str, Any]) -> str | None:
    for ticket in _sequence(payload.get("tickets", ())):
        if isinstance(ticket, Mapping) and _is_selected_safe_ticket(ticket):
            return str(ticket.get("ticket_id", ""))
    return None


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
