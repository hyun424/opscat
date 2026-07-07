"""Deterministic dry-run simulator for safe local/mock actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from app.models.action import ActionRequest
from app.services.blast_radius import BlastRadiusResult, BlastRadiusService
from app.services.risk_engine import RiskEngine


class SimulationStatus(StrEnum):
    PASS = "pass"
    BLOCKED = "blocked"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class SimulationResult:
    status: SimulationStatus
    action_type: str
    expected_effect: str
    touched_resources: tuple[str, ...]
    rollback_path: str | None
    precondition_gaps: tuple[str, ...]
    residual_risks: tuple[str, ...]
    blast_radius: BlastRadiusResult
    allowed: bool

    @property
    def ok(self) -> bool:
        return self.allowed and self.status == SimulationStatus.PASS

    @property
    def success(self) -> bool:
        return self.ok

    @property
    def passed(self) -> bool:
        return self.ok

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["ok"] = self.ok
        data["success"] = self.success
        data["touched_resources"] = list(self.touched_resources)
        data["precondition_gaps"] = list(self.precondition_gaps)
        data["residual_risks"] = list(self.residual_risks)
        data["blast_radius"] = self.blast_radius.to_dict()
        return data


class ActionSimulator:
    def __init__(self, risk_engine: RiskEngine | None = None, blast_radius_service: BlastRadiusService | None = None) -> None:
        if isinstance(risk_engine, BlastRadiusService) and blast_radius_service is None:
            blast_radius_service = risk_engine
            risk_engine = None
        self.risk_engine = risk_engine or RiskEngine()
        self.blast_radius_service = blast_radius_service or BlastRadiusService(self.risk_engine)

    def simulate(self, request: ActionRequest | Mapping[str, Any]) -> SimulationResult:
        if isinstance(request, Mapping):
            request = ActionRequest(
                action_type=str(request.get("action_type", "unknown")),
                target=str(request.get("target", "unknown")),
                environment=str(request.get("environment", "local")),
                payload=request.get("payload", {}) if isinstance(request.get("payload", {}), Mapping) else {},
            )
        action = self.risk_engine.get_action(request.action_type)
        blast_radius = self.blast_radius_service.evaluate(request)
        if action is None:
            return SimulationResult(
                status=SimulationStatus.BLOCKED if request.action_type == "unknown.mutate" else SimulationStatus.ESCALATE,
                action_type=request.action_type,
                expected_effect="Unknown action cannot be simulated safely.",
                touched_resources=blast_radius.touched_resources,
                rollback_path=None,
                precondition_gaps=("registered_action",),
                residual_risks=("unknown_action", "manual_review_required"),
                blast_radius=blast_radius,
                allowed=False,
            )
        explicit_gaps = _explicit_precondition_gaps(request.payload)
        if not blast_radius.allowed:
            return SimulationResult(
                status=SimulationStatus.BLOCKED,
                action_type=request.action_type,
                expected_effect="Simulation blocked because blast radius is not bounded.",
                touched_resources=blast_radius.touched_resources,
                rollback_path=None,
                precondition_gaps=tuple(explicit_gaps or ("bounded_blast_radius",)),
                residual_risks=(blast_radius.reason,),
                blast_radius=blast_radius,
                allowed=False,
            )
        if explicit_gaps:
            return SimulationResult(
                status=SimulationStatus.BLOCKED,
                action_type=request.action_type,
                expected_effect="Simulation blocked by missing preconditions.",
                touched_resources=blast_radius.touched_resources,
                rollback_path=_rollback_path(request.action_type, blast_radius.rollback_available),
                precondition_gaps=explicit_gaps,
                residual_risks=("missing_preconditions",),
                blast_radius=blast_radius,
                allowed=False,
            )
        return SimulationResult(
            status=SimulationStatus.PASS,
            action_type=request.action_type,
            expected_effect=_expected_effect(request.action_type),
            touched_resources=_touched_resources(request.action_type, blast_radius.touched_resources),
            rollback_path=_rollback_path(request.action_type, blast_radius.rollback_available),
            precondition_gaps=(),
            residual_risks=_residual_risks(request.action_type),
            blast_radius=blast_radius,
            allowed=True,
        )


def _touched_resources(action_type: str, resources: tuple[str, ...]) -> tuple[str, ...]:
    if "rollback" in action_type and resources:
        return (f"mock repository draft for {resources[0]}", *resources)
    return resources


def _explicit_precondition_gaps(payload: Mapping[str, Any]) -> tuple[str, ...]:
    raw = payload.get("missing_preconditions", ())
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple, set)):
        return tuple(str(item) for item in raw)
    return ()


def _expected_effect(action_type: str) -> str:
    return {
        "report.generate": "Generate a local report artifact; no external mutation.",
        "timeline.add_note": "Append a local incident timeline note; no external mutation.",
        "mock.create_incident_ticket": "Create a deterministic mock ticket record; no external mutation.",
        "mock.create_rollback_pr": "Create a deterministic mock rollback PR draft; no external mutation.",
        "mock.execute_restart_worker": "Simulate a single non-production worker restart; no external mutation.",
        "mock.verify_recovery": "Read local/mock recovery evidence; no external mutation.",
    }.get(action_type, "Execute only through the registered local/mock action handler; no external mutation.")


def _rollback_path(action_type: str, available: bool) -> str | None:
    if not available:
        return None
    if "rollback" in action_type:
        return "Discard the mock rollback PR draft; no provider state changed."
    if "restart" in action_type:
        return "Run mock.verify_recovery and keep human escalation available; restart is simulated only."
    if "ticket" in action_type:
        return "Close or annotate the mock ticket artifact."
    return "Remove or supersede the local artifact if needed."


def _residual_risks(action_type: str) -> tuple[str, ...]:
    if "rollback" in action_type:
        return ("human must review before real merge",)
    if "restart" in action_type:
        return ("simulation does not restart real workers",)
    return ("local_mock_evidence_only",)
