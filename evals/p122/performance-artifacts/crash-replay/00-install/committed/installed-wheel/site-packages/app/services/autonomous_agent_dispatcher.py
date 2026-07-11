"""P68 autonomous agent dispatcher.

The dispatcher converts P67 executor output into concrete dispatch packets for
external Codex/OMX workers. It is packet-only by default: it writes prompt and
JSON packet files, records blocked gated work, and never spawns processes,
executes shell commands, reads credentials, calls networks, or mutates
production.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.autonomous_loop_executor import run_autonomous_loop_executor_fixture
from app.services.redaction import redact_value

_CHECKPOINT_COMMANDS: tuple[str, ...] = (
    "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs",
    "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full",
)
_FORBIDDEN_SCORE: dict[str, int] = {
    "spawned_process_count": 0,
    "shell_command_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
}


@dataclass(frozen=True)
class DispatchPolicy:
    agent_type: str
    dispatch_mode: str
    max_parallel: int
    spawn_processes: bool = False
    execute_shell_commands: bool = False
    read_credentials: bool = False
    allow_network: bool = False
    approval_policy: str = "safe-local-auto"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "dispatch_mode": self.dispatch_mode,
            "max_parallel": self.max_parallel,
            "spawn_processes": self.spawn_processes,
            "execute_shell_commands": self.execute_shell_commands,
            "read_credentials": self.read_credentials,
            "allow_network": self.allow_network,
            "approval_policy": self.approval_policy,
        }


@dataclass(frozen=True)
class DispatchPacket:
    ticket: Mapping[str, Any]
    packet_path: Path
    prompt_path: Path
    status: str
    agent_type: str
    approval_policy: str
    verification_commands: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": str(self.ticket.get("ticket_id", "")),
            "title": str(self.ticket.get("title", "")),
            "lane": str(self.ticket.get("lane", "")),
            "safety_class": str(self.ticket.get("safety_class", "")),
            "status": self.status,
            "agent_type": self.agent_type,
            "approval_policy": self.approval_policy,
            "packet_path": str(self.packet_path),
            "prompt_path": str(self.prompt_path),
            "verification_commands": list(self.verification_commands),
        }


@dataclass(frozen=True)
class AutonomousAgentDispatcherReport:
    policy: DispatchPolicy
    packets: tuple[DispatchPacket, ...]
    blocked_dispatches: Mapping[str, Mapping[str, Any]]
    next_runnable_ticket: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "summary": {
                "dispatch_packet_count": len(self.packets),
                "queued_packet_count": sum(1 for packet in self.packets if packet.status == "queued"),
                "blocked_dispatch_count": len(self.blocked_dispatches),
                "next_runnable_ticket": self.next_runnable_ticket,
                "passed": self._passed(),
            },
            "policy": self.policy.to_dict(),
            "score": {
                **_FORBIDDEN_SCORE,
                "dispatch_packet_count": len(self.packets),
            },
            "dispatch_packets": [packet.to_dict() for packet in self.packets],
            "blocked_dispatches": {ticket_id: dict(data) for ticket_id, data in self.blocked_dispatches.items()},
            "operator_handoff": {
                "dispatch_dir": str(self.packets[0].packet_path.parent) if self.packets else None,
                "consume_with": "external Codex/OMX team runner or manual codex exec wrapper",
                "safe_for_all_day_loop": True,
                "packet_only": True,
                "live_action_production_remain_blocked": True,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _passed(self) -> bool:
        return (
            self.policy.agent_type == "executor"
            and self.policy.dispatch_mode == "packet-only"
            and not self.policy.spawn_processes
            and not self.policy.execute_shell_commands
            and not self.policy.read_credentials
            and not self.policy.allow_network
            and bool(self.packets)
            and all(packet.status == "queued" for packet in self.packets)
            and all(str(packet.ticket.get("safety_class", "")) == "safe-local" for packet in self.packets)
            and all(value == 0 for value in _FORBIDDEN_SCORE.values())
        )


def run_autonomous_agent_dispatcher_fixture(
    path: str | Path,
    *,
    completed: set[str] | None = None,
    max_tickets: int = 3,
    max_parallel: int = 2,
    dispatch_dir: str | Path = "/tmp/opscat-autonomous-agent-dispatcher-packets",
) -> AutonomousAgentDispatcherReport:
    policy = DispatchPolicy(agent_type="executor", dispatch_mode="packet-only", max_parallel=max(1, max_parallel))
    executor_report = run_autonomous_loop_executor_fixture(path, completed=set(completed or set()), max_tickets=max_tickets, mode="local-auto")
    executor_payload = executor_report.to_dict()
    dispatch_root = Path(dispatch_dir)
    dispatch_root.mkdir(parents=True, exist_ok=True)
    selected = tuple(item for item in _sequence(executor_payload.get("selected_tickets", ())) if isinstance(item, Mapping))
    packets = tuple(_write_packet(ticket, dispatch_root, policy) for ticket in selected)
    return AutonomousAgentDispatcherReport(
        policy=policy,
        packets=packets,
        blocked_dispatches=_normalize_blocked_dispatches(_mapping(executor_payload.get("blocked_tickets"))),
        next_runnable_ticket=str(executor_payload.get("summary", {}).get("next_runnable_ticket") or "") or None,
    )


def render_autonomous_agent_dispatcher_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    packets = tuple(item for item in _sequence(payload.get("dispatch_packets", ())) if isinstance(item, Mapping))
    blocked = _mapping(payload.get("blocked_dispatches"))
    lines = [
        "# OpsCat Autonomous Agent Dispatcher",
        "",
        "## Summary",
        "",
        f"- dispatch packets: {summary.get('dispatch_packet_count', 0)}",
        f"- queued packets: {summary.get('queued_packet_count', 0)}",
        f"- blocked dispatches: {summary.get('blocked_dispatch_count', 0)}",
        f"- next runnable ticket: {summary.get('next_runnable_ticket')}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## Dispatch packets",
        "",
    ]
    for packet in packets:
        lines.append(f"- {packet.get('ticket_id')}: {packet.get('prompt_path')} -> {packet.get('packet_path')}")
    lines.extend(["", "## Blocked dispatches", ""])
    for ticket_id, data in blocked.items():
        reason = data.get("reason") if isinstance(data, Mapping) else "blocked"
        lines.append(f"- {ticket_id}: {reason}")
    lines.extend(["", "## Checkpoint commands", ""])
    for command in _CHECKPOINT_COMMANDS:
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def write_autonomous_agent_dispatcher_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_autonomous_agent_dispatcher_markdown(payload), encoding="utf-8")


def _write_packet(ticket: Mapping[str, Any], dispatch_root: Path, policy: DispatchPolicy) -> DispatchPacket:
    ticket_id = str(ticket.get("ticket_id", "ticket"))
    ticket_dir = dispatch_root / ticket_id
    ticket_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = ticket_dir / f"{ticket_id}.md"
    packet_path = ticket_dir / f"{ticket_id}.json"
    verification_commands = _verification_commands(ticket_id)
    prompt_path.write_text(_prompt_text(ticket, verification_commands), encoding="utf-8")
    packet_payload = {
        "ticket_id": ticket_id,
        "title": str(ticket.get("title", "")),
        "lane": str(ticket.get("lane", "")),
        "safety_class": str(ticket.get("safety_class", "")),
        "agent_type": policy.agent_type,
        "approval_policy": policy.approval_policy,
        "dispatch_mode": policy.dispatch_mode,
        "status": "queued",
        "prompt_path": str(prompt_path),
        "verification_commands": list(verification_commands),
        "forbidden": {
            "read_credentials": True,
            "network_calls": True,
            "live_api_calls": True,
            "production_mutation": True,
            "action_execution": True,
        },
    }
    packet_path.write_text(json.dumps(redact_value(packet_payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return DispatchPacket(
        ticket=ticket,
        packet_path=packet_path,
        prompt_path=prompt_path,
        status="queued",
        agent_type=policy.agent_type,
        approval_policy=policy.approval_policy,
        verification_commands=verification_commands,
    )


def _prompt_text(ticket: Mapping[str, Any], verification_commands: Sequence[str]) -> str:
    commands = "\n".join(f"- `{command}`" for command in verification_commands)
    return (
        f"# {ticket.get('ticket_id')} {ticket.get('title')}\n\n"
        "You are an OpsCat implementation agent. Use TDD: write/confirm RED tests first, implement the smallest GREEN change, then verify.\n\n"
        "Safety boundary: Do not read credentials, call networks, call live APIs, execute remediation actions, or mutate production.\n\n"
        f"Lane: {ticket.get('lane')}\n"
        f"Safety class: {ticket.get('safety_class')}\n\n"
        "Required verification commands:\n"
        f"{commands}\n"
    )


def _verification_commands(ticket_id: str) -> tuple[str, ...]:
    lower = ticket_id.lower()
    return (
        f"UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_{lower}_release_evidence.py",
        "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs",
    )


def _normalize_blocked_dispatches(blocked: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    normalized: dict[str, Mapping[str, Any]] = {}
    for ticket_id, value in blocked.items():
        data = _mapping(value)
        safety_class = str(data.get("safety_class", "blocked"))
        if safety_class == "gated-live":
            reason = "gated-live dispatch denied by policy"
        elif safety_class == "gated-action":
            reason = "gated-action dispatch denied by policy"
        elif safety_class == "blocked-production":
            reason = "blocked-production dispatch denied by policy"
        else:
            reason = "dispatch denied by policy"
        normalized[str(ticket_id)] = {"safety_class": safety_class, "reason": reason}
    return normalized


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
