"""Deterministic pre-execution simulator for local/mock OpsCat actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.models.action import ActionRequest
from app.services.blast_radius import BlastRadiusEngine


@dataclass(frozen=True)
class SimulationResult:
    success: bool
    action_type: str
    touched_resources: list[str]
    expected_effect: str
    rollback_path: str | None
    precondition_gaps: list[str]
    residual_risks: list[str]
    blast_radius: dict[str, object]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActionSimulator:
    def __init__(self, blast_radius: BlastRadiusEngine | None = None) -> None:
        self.blast_radius = blast_radius or BlastRadiusEngine()

    def simulate(self, request: ActionRequest) -> SimulationResult:
        blast = self.blast_radius.classify(request)
        if blast.blocked:
            return SimulationResult(False, request.action_type, [], "blocked before execution", None, ["bounded simulation unavailable"], blast.reasons, blast.to_dict())
        resources = _resources_for(request)
        gaps = _precondition_gaps(request)
        success = bool(resources) and not gaps
        return SimulationResult(
            success=success,
            action_type=request.action_type,
            touched_resources=resources,
            expected_effect=_expected_effect(request.action_type),
            rollback_path=_rollback_path(request.action_type) if blast.rollback_available else None,
            precondition_gaps=gaps,
            residual_risks=["mock-only effect; production integrations remain disabled", *([] if blast.scope in {"local", "service"} else [f"scope requires review: {blast.scope}"])],
            blast_radius=blast.to_dict(),
        )

    def _report(self, request: ActionRequest) -> SimulationResult:
        return SimulationResult(
            request.action_type,
            True,
            (f"local report for {request.incident_id or request.target}",),
            "write local Markdown/JSON report",
            "delete generated local report artifact",
            (),
            ("report may omit newly collected evidence",),
        )

    def _timeline(self, request: ActionRequest) -> SimulationResult:
        return SimulationResult(
            request.action_type,
            True,
            (f"local incident timeline {request.incident_id or request.target}",),
            "append local timeline note",
            "append corrective note",
            (),
            ("timeline note is append-only",),
        )

    def _ticket(self, request: ActionRequest) -> SimulationResult:
        return SimulationResult(
            request.action_type,
            True,
            ("mock ticket system",),
            "create mock incident ticket",
            "close mock ticket",
            (),
            ("ticket can distract if diagnosis is wrong",),
        )

    def _rollback_pr(self, request: ActionRequest) -> SimulationResult:
        gaps = () if request.payload.get("to_version") or request.payload.get("rollback_to") else ("rollback_target_not_explicit",)
        return SimulationResult(
            request.action_type,
            not gaps,
            ("mock repository draft",),
            "draft rollback PR without calling GitHub",
            "close mock PR without merge",
            gaps,
            ("rollback PR must still be reviewed by a human",),
        )

    def _restart_worker(self, request: ActionRequest) -> SimulationResult:
        gaps = () if request.environment != "production" else ("production_restart_not_allowed",)
        return SimulationResult(
            request.action_type,
            not gaps,
            (request.target, "single non-production worker"),
            "simulate worker restart and verify heartbeat",
            "restart is reversible by starting previous worker process",
            gaps,
            ("queue may refill if root cause is upstream",),
        )

def _expected_effect(action_type: str) -> str:
    return {
        "report.generate": "local report artifact generated",
        "timeline.add_note": "local timeline note appended",
        "mock.create_incident_ticket": "mock ticket draft created without external API calls",
        "mock.create_rollback_pr": "mock rollback PR draft created without GitHub calls",
        "mock.execute_restart_worker": "mock non-production worker restart recorded",
        "mock.verify_recovery": "mock recovery signal read",
    }.get(action_type, "read-only mock context gathered")


def _rollback_path(action_type: str) -> str | None:
    return {
        "report.generate": "delete local generated report artifact",
        "timeline.add_note": "append corrective timeline note",
        "mock.create_incident_ticket": "close mock ticket record",
        "mock.create_rollback_pr": "discard mock PR draft",
        "mock.execute_restart_worker": "restart is reversible by running worker health verification and requeueing jobs",
        "mock.verify_recovery": "no rollback needed for read-only verification",
    }.get(action_type)
