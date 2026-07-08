"""Local/mock runtime shell around P20 closed-loop response."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.services.closed_loop_response import ClosedLoopResult, run_closed_loop_response
from app.services.judgment_dataset import JudgmentCase
from app.services.redaction import redact_text, redact_value

_MUTATING_TOOL_MARKERS = ("kubectl", "restart", "rollback", "shell", "database", "db_", "cloud", "kubernetes", "terraform", "aws", "gcloud")


class ApprovalMode(StrEnum):
    LOCKED = "locked"
    MANUAL = "manual"
    ENTER_TO_APPROVE = "enter_to_approve"
    AUTO_READONLY = "auto_readonly"
    AUTO_SAFE_MOCK = "auto_safe_mock"


@dataclass(frozen=True)
class ApprovalProfile:
    mode: ApprovalMode
    allowed_capabilities: tuple[str, ...]
    denied_tools: tuple[str, ...] = _MUTATING_TOOL_MARKERS

    @classmethod
    def for_mode(cls, mode: ApprovalMode | str) -> ApprovalProfile:
        resolved = ApprovalMode(mode)
        allowed = {
            ApprovalMode.LOCKED: (),
            ApprovalMode.MANUAL: (),
            ApprovalMode.ENTER_TO_APPROVE: ("operator_prompt",),
            ApprovalMode.AUTO_READONLY: ("read_only_evidence", "simulation"),
            ApprovalMode.AUTO_SAFE_MOCK: ("read_only_evidence", "simulation", "safe_mock_artifact"),
        }[resolved]
        return cls(mode=resolved, allowed_capabilities=allowed)

    def allows_capability(self, capability: str) -> bool:
        return capability in self.allowed_capabilities

    def denies_tool(self, tool: str) -> bool:
        lowered = tool.lower()
        return any(marker in lowered for marker in self.denied_tools)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "allowed_capabilities": list(self.allowed_capabilities),
            "denied_tools": list(self.denied_tools),
        }


@dataclass
class RuntimeQueueItem:
    case: JudgmentCase
    status: str = "queued"
    attempts: int = 0
    status_reason: str = ""
    closed_loop: ClosedLoopResult | None = None

    @classmethod
    def from_case(cls, case: JudgmentCase) -> RuntimeQueueItem:
        return cls(case=case)

    def to_dict(self) -> dict[str, Any]:
        closed_loop_payload = self.closed_loop.to_dict() if self.closed_loop is not None else None
        trace_summary: list[str] = []
        if closed_loop_payload is not None:
            trace_summary = [str(step.get("step")) for step in closed_loop_payload.get("trace", []) if isinstance(step, Mapping)]
        return {
            "case_id": self.case.id,
            "case_title": self.case.title,
            "status": self.status,
            "attempts": self.attempts,
            "status_reason": self.status_reason,
            "final_route": closed_loop_payload.get("final_decision", {}).get("route") if isinstance(closed_loop_payload, Mapping) else None,
            "trace_summary": trace_summary,
            "closed_loop": closed_loop_payload,
        }


@dataclass
class RuntimeLoopRunner:
    approval_profile: ApprovalProfile = field(default_factory=lambda: ApprovalProfile.for_mode(ApprovalMode.MANUAL))
    status: str = "running"
    status_reason: str = ""
    _queue: deque[RuntimeQueueItem] = field(default_factory=deque)
    _items: list[RuntimeQueueItem] = field(default_factory=list)

    def enqueue_case(self, case: JudgmentCase) -> RuntimeQueueItem:
        item = RuntimeQueueItem.from_case(case)
        self._queue.append(item)
        self._items.append(item)
        return item

    def process_tick(self) -> RuntimeQueueItem | None:
        if self.status == "paused" or not self._queue:
            return None
        item = self._queue.popleft()
        if item.status != "queued":
            return item
        item.status = "running"
        item.attempts += 1
        item.closed_loop = run_closed_loop_response(item.case)
        item.status = self._status_from_closed_loop(item.closed_loop)
        item.status_reason = self._status_reason(item.closed_loop)
        return item

    def pause(self, reason: str = "paused by operator") -> None:
        self.status = "paused"
        self.status_reason = reason

    def resume(self) -> None:
        self.status = "running"
        self.status_reason = ""

    def abort_next(self, reason: str = "aborted by operator") -> RuntimeQueueItem | None:
        if not self._queue:
            return None
        item = self._queue.popleft()
        item.status = "aborted"
        item.status_reason = reason
        return item

    def snapshot(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "status_reason": self.status_reason,
            "queue_depth": len(self._queue),
            "processed_count": sum(1 for item in self._items if item.status in {"completed", "approval_waiting", "blocked"}),
            "approval_profile": self.approval_profile.to_dict(),
            "items": [item.to_dict() for item in self._items],
            "boundary": {
                "local_mock_only": True,
                "action_execution_enabled": False,
                "production_mutation_enabled": False,
                "default_external_model_calls": False,
            },
        }
        return dict(redact_value(payload))

    def _status_from_closed_loop(self, result: ClosedLoopResult) -> str:
        route = str(result.final_decision.get("route", "human_required"))
        if self.approval_profile.mode == ApprovalMode.LOCKED:
            return "approval_waiting"
        if route == "blocked":
            return "blocked"
        if route in {"human_required", "approval_required"}:
            return "approval_waiting"
        if route == "local_mock_auto_allowed" and self.approval_profile.allows_capability("safe_mock_artifact"):
            return "completed"
        return "approval_waiting"

    def _status_reason(self, result: ClosedLoopResult) -> str:
        route = str(result.final_decision.get("route", "human_required"))
        if route == "local_mock_auto_allowed" and self.approval_profile.allows_capability("safe_mock_artifact"):
            return "safe mock artifact route completed without remediation execution"
        return f"route {route} requires operator review under {self.approval_profile.mode.value}"


def render_runtime_markdown(snapshot: Mapping[str, Any]) -> str:
    profile = snapshot.get("approval_profile", {}) if isinstance(snapshot.get("approval_profile"), Mapping) else {}
    lines = [
        "# OpsCat Runtime Loop Runner",
        "",
        "Boundary: no-auth/local-mock by default; no default external model/API calls; no remediation execution; no production mutation; does not claim unattended production operation.",
        "",
        f"- Status: {snapshot.get('status')}",
        f"- Queue depth: {snapshot.get('queue_depth')}",
        f"- Processed count: {snapshot.get('processed_count')}",
        f"- Approval mode: {profile.get('mode')}",
        "",
        "## Items",
    ]
    for item in snapshot.get("items", []):
        if isinstance(item, Mapping):
            lines.append(
                f"- `{item.get('case_id')}` status={item.get('status')} final_route={item.get('final_route')} reason={redact_text(str(item.get('status_reason', '')))}"
            )
    return "\n".join(lines) + "\n"


def write_runtime_outputs(
    snapshot: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_runtime_markdown(snapshot), encoding="utf-8")


def run_runtime_for_cases(
    cases: Sequence[JudgmentCase],
    *,
    approval_mode: ApprovalMode | str = ApprovalMode.MANUAL,
    max_ticks: int = 1,
    pause_after: int | None = None,
) -> dict[str, Any]:
    runner = RuntimeLoopRunner(approval_profile=ApprovalProfile.for_mode(approval_mode))
    for case in cases:
        runner.enqueue_case(case)
    for tick in range(max_ticks):
        if pause_after is not None and tick >= pause_after:
            runner.pause(f"pause_after={pause_after}")
            break
        if runner.process_tick() is None:
            break
    return runner.snapshot()
