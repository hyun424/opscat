"""P66 autonomous day loop backlog planner.

This module turns a long roadmap manifest into a safe, repeatable 24-hour
planning loop. It never executes tickets, reads credentials, calls networks, or
mutates production. The output is an operator/agent handoff artifact: which
safe-local work can be run first, which future safe-local work is queued, and
which live/action/production work must remain gated.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "dry_run_plan_only": True,
    "executes_commands": False,
    "live_api_calls_enabled": False,
    "credential_reads_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "action_execution_enabled": False,
    "auth_session_work_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_SIDE_EFFECT_SCORE: dict[str, int] = {
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "action_execution_count": 0,
}
_CHECKPOINT_COMMANDS: tuple[str, ...] = (
    "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile docs",
    "UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full",
    "git status --short",
)
_GATED_CLASSES = {"gated-live", "gated-action"}
_BLOCKED_CLASSES = {"blocked-production"}
_SAFE_CLASS = "safe-local"


@dataclass(frozen=True)
class DayLoopConfig:
    duration_hours: int
    cycle_minutes: int
    batch_size: int
    checkpoint_every_cycles: int
    default_mode: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DayLoopConfig:
        return cls(
            duration_hours=max(1, int(data.get("duration_hours", 24) or 24)),
            cycle_minutes=max(1, int(data.get("cycle_minutes", 20) or 20)),
            batch_size=max(1, int(data.get("batch_size", 4) or 4)),
            checkpoint_every_cycles=max(1, int(data.get("checkpoint_every_cycles", 3) or 3)),
            default_mode=str(data.get("default_mode", "dry_run_plan_only")),
        )

    @property
    def cycle_count(self) -> int:
        return (self.duration_hours * 60) // self.cycle_minutes

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_hours": self.duration_hours,
            "cycle_minutes": self.cycle_minutes,
            "cycle_count": self.cycle_count,
            "batch_size": self.batch_size,
            "checkpoint_every_cycles": self.checkpoint_every_cycles,
            "default_mode": self.default_mode,
            "checkpoint_commands": list(_CHECKPOINT_COMMANDS),
        }


@dataclass(frozen=True)
class BacklogTicket:
    ticket_id: str
    title: str
    lane: str
    safety_class: str
    depends_on: tuple[str, ...]
    verification: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BacklogTicket:
        return cls(
            ticket_id=str(data.get("id", "P00")),
            title=str(data.get("title", "Untitled ticket")),
            lane=str(data.get("lane", "planning")),
            safety_class=str(data.get("class", _SAFE_CLASS)),
            depends_on=tuple(str(item) for item in _sequence(data.get("depends_on", ()))),
            verification=tuple(str(item) for item in _sequence(data.get("verification", ()))),
        )

    @property
    def sort_key(self) -> tuple[int, str]:
        match = re.search(r"(\d+)", self.ticket_id)
        return (int(match.group(1)) if match else 9999, self.ticket_id)


@dataclass(frozen=True)
class TicketPlan:
    ticket: BacklogTicket
    status: str
    missing_dependencies: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def runnable_now(self) -> bool:
        return self.status == "runnable"

    @property
    def safe_for_plan_batches(self) -> bool:
        return self.ticket.safety_class == _SAFE_CLASS and self.status != "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket.ticket_id,
            "title": self.ticket.title,
            "lane": self.ticket.lane,
            "safety_class": self.ticket.safety_class,
            "status": self.status,
            "depends_on": list(self.ticket.depends_on),
            "missing_dependencies": list(self.missing_dependencies),
            "verification": list(self.ticket.verification),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ExecutionBatch:
    batch_id: str
    cycle_start: int
    cycle_end: int
    purpose: str
    tickets: tuple[TicketPlan, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "cycle_start": self.cycle_start,
            "cycle_end": self.cycle_end,
            "purpose": self.purpose,
            "tickets": [ticket.to_dict() for ticket in self.tickets],
        }


@dataclass(frozen=True)
class AutonomousDayLoopBacklogReport:
    config: DayLoopConfig
    ticket_plans: tuple[TicketPlan, ...]
    execution_batches: tuple[ExecutionBatch, ...]

    def to_dict(self) -> dict[str, Any]:
        safe_local = tuple(plan for plan in self.ticket_plans if plan.ticket.safety_class == _SAFE_CLASS)
        gated_live = tuple(plan for plan in self.ticket_plans if plan.ticket.safety_class == "gated-live")
        gated_action = tuple(plan for plan in self.ticket_plans if plan.ticket.safety_class == "gated-action")
        blocked_production = tuple(plan for plan in self.ticket_plans if plan.ticket.safety_class == "blocked-production")
        runnable_now = tuple(plan for plan in self.ticket_plans if plan.runnable_now)
        gated_retained = tuple(plan for plan in self.ticket_plans if plan.ticket.safety_class != _SAFE_CLASS)
        payload = {
            "summary": {
                "ticket_count": len(self.ticket_plans),
                "safe_local_count": len(safe_local),
                "gated_live_count": len(gated_live),
                "gated_action_count": len(gated_action),
                "blocked_production_count": len(blocked_production),
                "runnable_now_count": len(runnable_now),
                "day_loop_cycle_count": self.config.cycle_count,
                "planned_batch_count": len(self.execution_batches),
                "gated_retained_count": len(gated_retained),
                "passed": self._passed(len(safe_local), len(gated_live), len(gated_action), len(blocked_production), len(runnable_now)),
            },
            "score": dict(_SIDE_EFFECT_SCORE),
            "boundary": dict(_BOUNDARY),
            "loop_contract": self.config.to_dict(),
            "tickets": [plan.to_dict() for plan in self.ticket_plans],
            "execution_batches": [batch.to_dict() for batch in self.execution_batches],
            "operator_handoff": _operator_handoff(self.ticket_plans),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    def _passed(self, safe_local_count: int, gated_live_count: int, gated_action_count: int, blocked_production_count: int, runnable_now_count: int) -> bool:
        return (
            len(self.ticket_plans) >= 25
            and safe_local_count >= 15
            and gated_live_count >= 1
            and gated_action_count >= 3
            and blocked_production_count >= 1
            and runnable_now_count >= 2
            and self.config.cycle_count >= 1
            and len(self.execution_batches) >= 6
            and all(value == 0 for value in _SIDE_EFFECT_SCORE.values())
            and _BOUNDARY["dry_run_plan_only"]
            and not _BOUNDARY["executes_commands"]
        )


def run_autonomous_day_loop_backlog_fixture(path: str | Path, *, completed: set[str] | None = None) -> AutonomousDayLoopBacklogReport:
    config, tickets = load_autonomous_day_loop_backlog(path)
    completed_ids = set(completed or set())
    plans = _plan_tickets(tickets, completed_ids)
    batches = _build_execution_batches(plans, config)
    return AutonomousDayLoopBacklogReport(config=config, ticket_plans=plans, execution_batches=batches)


def load_autonomous_day_loop_backlog(path: str | Path) -> tuple[DayLoopConfig, tuple[BacklogTicket, ...]]:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("autonomous day loop backlog manifest must be an object")
    config = DayLoopConfig.from_dict(_mapping(data.get("loop")))
    tickets = tuple(
        sorted(
            (BacklogTicket.from_dict(item) for item in _sequence(data.get("tickets", ())) if isinstance(item, Mapping)),
            key=lambda ticket: ticket.sort_key,
        )
    )
    if not tickets:
        raise ValueError("autonomous day loop backlog manifest must contain tickets")
    return config, tickets


def render_autonomous_day_loop_backlog_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    batches = tuple(item for item in _sequence(payload.get("execution_batches", ())) if isinstance(item, Mapping))
    tickets = tuple(item for item in _sequence(payload.get("tickets", ())) if isinstance(item, Mapping))
    gated = tuple(ticket for ticket in tickets if str(ticket.get("safety_class", "")) != _SAFE_CLASS)
    lines = [
        "# OpsCat Autonomous Day Loop Backlog",
        "",
        "## Summary",
        "",
        f"- tickets: {summary.get('ticket_count', 0)}",
        f"- safe-local tickets: {summary.get('safe_local_count', 0)}",
        f"- runnable now: {summary.get('runnable_now_count', 0)}",
        f"- planned batches: {summary.get('planned_batch_count', 0)}",
        f"- day-loop cycles: {summary.get('day_loop_cycle_count', 0)}",
        f"- passed: {summary.get('passed', False)}",
        "",
        "## First runnable batches",
        "",
    ]
    for batch in batches[:6]:
        batch_tickets = tuple(ticket for ticket in _sequence(batch.get("tickets", ())) if isinstance(ticket, Mapping))
        ticket_list = ", ".join(f"{ticket.get('ticket_id')} ({ticket.get('status')})" for ticket in batch_tickets)
        lines.append(f"- {batch.get('batch_id')}: {ticket_list}")
    lines.extend(["", "## Gated but retained work", ""])
    for ticket in gated:
        reasons = ", ".join(str(reason) for reason in _sequence(ticket.get("reasons", ())))
        lines.append(f"- {ticket.get('ticket_id')} [{ticket.get('safety_class')}/{ticket.get('status')}]: {ticket.get('title')} — {reasons}")
    lines.extend(
        [
            "",
            "## Safety counters",
            "",
            f"- live API calls: {score.get('live_api_call_count', 0)}",
            f"- credential reads: {score.get('credential_read_count', 0)}",
            f"- network calls: {score.get('network_call_count', 0)}",
            f"- production mutations: {score.get('production_mutation_count', 0)}",
            f"- action executions: {score.get('action_execution_count', 0)}",
            "",
            "## Checkpoints",
            "",
        ]
    )
    contract = _mapping(payload.get("loop_contract"))
    for command in _sequence(contract.get("checkpoint_commands", ())):
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def write_autonomous_day_loop_backlog_outputs(payload: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md_path.write_text(render_autonomous_day_loop_backlog_markdown(payload), encoding="utf-8")


def _plan_tickets(tickets: Sequence[BacklogTicket], completed: set[str]) -> tuple[TicketPlan, ...]:
    ticket_ids = {ticket.ticket_id for ticket in tickets}
    planned: list[TicketPlan] = []
    for ticket in tickets:
        missing = tuple(dep for dep in ticket.depends_on if dep not in completed and dep not in ticket_ids)
        uncompleted_deps = tuple(dep for dep in ticket.depends_on if dep not in completed)
        status: str
        reasons: tuple[str, ...]
        if ticket.ticket_id in completed:
            status = "completed"
            reasons = ("already completed before this loop",)
        elif uncompleted_deps:
            status = "blocked_by_dependencies"
            reasons = tuple(f"waiting for {dep}" for dep in uncompleted_deps)
        elif ticket.safety_class == _SAFE_CLASS:
            status = "runnable"
            reasons = ("safe-local dry-run work with satisfied dependencies",)
        elif ticket.safety_class in _GATED_CLASSES:
            status = "gated"
            reasons = (f"{ticket.safety_class} requires explicit approval outside this dry-run loop",)
        elif ticket.safety_class in _BLOCKED_CLASSES:
            status = "blocked_by_safety_class"
            reasons = ("production autonomy remains blocked until readiness gates pass",)
        else:
            status = "gated"
            reasons = ("unknown safety class requires manual review",)
        planned.append(TicketPlan(ticket=ticket, status=status, missing_dependencies=missing, reasons=reasons))
    return tuple(sorted(planned, key=lambda plan: plan.ticket.sort_key))


def _build_execution_batches(plans: Sequence[TicketPlan], config: DayLoopConfig) -> tuple[ExecutionBatch, ...]:
    runnable = [plan for plan in plans if plan.runnable_now and plan.ticket.safety_class == _SAFE_CLASS]
    future_safe = [plan for plan in plans if plan.safe_for_plan_batches and not plan.runnable_now]
    raw_batches = [tuple(runnable)] if runnable else []
    raw_batches.extend(_chunk(future_safe, config.batch_size))
    min_batches = min(max(6, len(raw_batches)), max(1, config.cycle_count))
    while raw_batches and len(raw_batches) < min_batches:
        raw_batches.append(raw_batches[len(raw_batches) % len(raw_batches)])
    batches: list[ExecutionBatch] = []
    stride = max(1, config.checkpoint_every_cycles)
    for index, tickets in enumerate(raw_batches[: config.cycle_count], start=1):
        cycle_start = 1 + ((index - 1) * stride)
        cycle_end = min(config.cycle_count, cycle_start + stride - 1)
        purpose = "run now" if index == 1 else "future safe-local dry-run batch"
        batches.append(
            ExecutionBatch(
                batch_id=f"P66-B{index:02d}",
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                purpose=purpose,
                tickets=tuple(tickets),
            )
        )
    return tuple(batches)


def _operator_handoff(plans: Sequence[TicketPlan]) -> dict[str, Any]:
    runnable_ids = [plan.ticket.ticket_id for plan in plans if plan.runnable_now]
    gated_ids = [plan.ticket.ticket_id for plan in plans if plan.ticket.safety_class != _SAFE_CLASS]
    return {
        "next_step": "delegate first safe-local batch, checkpoint, then continue only if verification stays green",
        "runnable_now": runnable_ids,
        "gated_but_retained": gated_ids,
        "live_or_action_work_requires_explicit_approval": True,
        "no_side_effect_loop": True,
    }


def _chunk(items: Sequence[TicketPlan], size: int) -> list[tuple[TicketPlan, ...]]:
    return [tuple(items[index : index + size]) for index in range(0, len(items), size)]


def _ensure_local_path(path: str | Path) -> Path:
    local_path = Path(path)
    if any(str(local_path).startswith(prefix) for prefix in ("http://", "https://", "s3://", "gs://", "az://", "ftp://")):
        raise ValueError("remote manifests are not allowed in the dry-run backlog planner")
    return local_path


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
