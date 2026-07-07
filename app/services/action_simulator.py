"""P7 deterministic dry-run simulator for safe mock actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.blast_radius import BlastRadiusService


@dataclass(frozen=True)
class ActionSimulation:
    status: str
    touched_resources: tuple[str, ...]
    expected_effect: str
    rollback_path: str | None
    precondition_gaps: tuple[str, ...]
    residual_risks: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "touched_resources": list(self.touched_resources),
            "expected_effect": self.expected_effect,
            "rollback_path": self.rollback_path,
            "precondition_gaps": list(self.precondition_gaps),
            "residual_risks": list(self.residual_risks),
        }


class ActionSimulator:
    def __init__(self, blast_radius: BlastRadiusService | None = None) -> None:
        self.blast_radius = blast_radius or BlastRadiusService()

    def simulate(self, action: Mapping[str, Any]) -> ActionSimulation:
        action_type = str(action.get("action_type", ""))
        assessment = self.blast_radius.classify(action)
        if assessment.scope.value in {"unknown", "prohibited", "global"}:
            return ActionSimulation(
                status="blocked",
                touched_resources=assessment.touched_resources,
                expected_effect="No bounded dry-run available.",
                rollback_path=None,
                precondition_gaps=(assessment.reason,),
                residual_risks=("fail-closed",),
            )
        if action_type == "mock.execute_restart_worker":
            return ActionSimulation(
                status="passed",
                touched_resources=assessment.touched_resources,
                expected_effect="Simulated non-production worker restart and heartbeat recovery check.",
                rollback_path="Re-run worker start from previous local state; no production mutation performed.",
                precondition_gaps=(),
                residual_risks=("restart may not fix a poisoned queue message",),
            )
        if action_type == "mock.create_incident_ticket":
            return ActionSimulation("passed", assessment.touched_resources, "Mock ticket payload is persisted locally.", "Close local mock ticket.", (), ("ticket may be duplicate",))
        if action_type == "mock.create_rollback_pr":
            return ActionSimulation("passed", assessment.touched_resources, "Mock rollback PR draft generated without GitHub calls.", "Discard local draft.", (), ("rollback target may be stale",))
        if action_type == "report.generate":
            return ActionSimulation("passed", assessment.touched_resources, "Report file can be generated locally.", "Delete local report artifact.", (), ())
        if action_type == "timeline.add_note":
            return ActionSimulation("passed", assessment.touched_resources, "Timeline note can be appended to local DB.", "Append corrective note.", (), ())
        return ActionSimulation(
            status="blocked",
            touched_resources=assessment.touched_resources,
            expected_effect="Action simulator has no registered deterministic handler.",
            rollback_path=None,
            precondition_gaps=("missing simulator handler",),
            residual_risks=("unbounded effect",),
        )
