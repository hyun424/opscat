"""P7 local/mock action simulator used as a pre-execution safety gate."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.action import ActionRequest
from app.services.blast_radius import BlastRadiusEngine


@dataclass(frozen=True)
class SimulationResult:
    action_type: str
    ok: bool
    touched_resources: tuple[str, ...]
    expected_effect: str
    rollback_path: str | None
    precondition_gaps: tuple[str, ...]
    residual_risks: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "action_type": self.action_type,
            "ok": self.ok,
            "touched_resources": list(self.touched_resources),
            "expected_effect": self.expected_effect,
            "rollback_path": self.rollback_path,
            "precondition_gaps": list(self.precondition_gaps),
            "residual_risks": list(self.residual_risks),
        }


class ActionSimulator:
    def __init__(self, blast_radius: BlastRadiusEngine | None = None) -> None:
        self.blast_radius = blast_radius or BlastRadiusEngine()

    def simulate(self, request: ActionRequest) -> SimulationResult:
        radius = self.blast_radius.evaluate(request)
        if not radius.allowed and request.action_type != "mock.create_rollback_pr":
            return SimulationResult(
                action_type=request.action_type,
                ok=False,
                touched_resources=radius.touched_resources,
                expected_effect="blocked before execution",
                rollback_path=None,
                precondition_gaps=radius.reasons,
                residual_risks=("unbounded_or_prohibited_blast_radius",),
            )
        handlers = {
            "report.generate": self._report,
            "timeline.add_note": self._timeline,
            "mock.create_incident_ticket": self._ticket,
            "mock.create_rollback_pr": self._rollback_pr,
            "mock.execute_restart_worker": self._restart_worker,
            "mock.verify_recovery": self._verify_only,
        }
        handler = handlers.get(request.action_type)
        if handler is None:
            return SimulationResult(
                action_type=request.action_type,
                ok=False,
                touched_resources=radius.touched_resources,
                expected_effect="no bounded simulator exists",
                rollback_path=None,
                precondition_gaps=("missing_simulator",),
                residual_risks=("cannot_predict_touched_resources",),
            )
        return handler(request)

    def _report(self, request: ActionRequest) -> SimulationResult:
        return SimulationResult(request.action_type, True, (f"local report for {request.incident_id or request.target}",), "write local Markdown/JSON report", "delete generated local report artifact", (), ("report may omit newly collected evidence",))

    def _timeline(self, request: ActionRequest) -> SimulationResult:
        return SimulationResult(request.action_type, True, (f"local incident timeline {request.incident_id or request.target}",), "append local timeline note", "append corrective note", (), ("timeline note is append-only",))

    def _ticket(self, request: ActionRequest) -> SimulationResult:
        return SimulationResult(request.action_type, True, ("mock ticket system",), "create mock incident ticket", "close mock ticket", (), ("ticket can distract if diagnosis is wrong",))

    def _rollback_pr(self, request: ActionRequest) -> SimulationResult:
        gaps = () if request.payload.get("to_version") or request.payload.get("rollback_to") else ("rollback_target_not_explicit",)
        return SimulationResult(request.action_type, not gaps, ("mock repository draft",), "draft rollback PR without calling GitHub", "close mock PR without merge", gaps, ("rollback PR must still be reviewed by a human",))

    def _restart_worker(self, request: ActionRequest) -> SimulationResult:
        gaps = () if request.environment != "production" else ("production_restart_not_allowed",)
        return SimulationResult(request.action_type, not gaps, (request.target, "single non-production worker"), "simulate worker restart and verify heartbeat", "restart is reversible by starting previous worker process", gaps, ("queue may refill if root cause is upstream",))

    def _verify_only(self, request: ActionRequest) -> SimulationResult:
        return SimulationResult(request.action_type, True, (request.target,), "read recovery signals only", None, (), ("verification source may be stale",))
