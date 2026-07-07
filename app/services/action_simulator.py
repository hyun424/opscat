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


def _resources_for(request: ActionRequest) -> list[str]:
    target = request.target or "local"
    return {
        "report.generate": [f"report:{request.incident_id or target}"],
        "timeline.add_note": [f"timeline:{request.incident_id or target}"],
        "mock.create_incident_ticket": [f"mock-ticket:{target}"],
        "mock.create_rollback_pr": [f"mock-pr:{target}"],
        "mock.execute_restart_worker": [f"mock-worker:{target}"],
        "mock.verify_recovery": [f"mock-verification:{target}"],
        "mock.get_error_context": [f"mock-context:{target}"],
        "mock.get_recent_deploys": [f"mock-deploys:{target}"],
        "mock.get_runbook": [f"mock-runbook:{target}"],
        "mock.search_prior_incidents": [f"mock-memory:{target}"],
    }.get(request.action_type, [])


def _precondition_gaps(request: ActionRequest) -> list[str]:
    gaps: list[str] = []
    if request.environment == "production" and request.action_type.startswith("mock.execute"):
        gaps.append("mock execution is not allowed in production")
    if request.action_type == "mock.create_rollback_pr" and not request.payload.get("to_version"):
        gaps.append("rollback target not identified")
    return gaps


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
