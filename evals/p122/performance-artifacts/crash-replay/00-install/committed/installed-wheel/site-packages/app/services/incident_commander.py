"""P9 autonomous incident commander read model.

This module coordinates deterministic local/mock services only. It does not call
providers, networks, shells, Kubernetes, cloud APIs, databases, or unrestricted
execution surfaces.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.autonomy_readiness import AutonomyReadiness, score_autonomy_readiness
from app.services.commander_learning import CommanderLearningSignal, summarize_learning_signals
from app.services.evidence_graph import EvidenceGraph, build_evidence_graph
from app.services.recovery_verifier import RecoveryVerification, verify_recovery
from app.services.redaction import redact_text, redact_value
from app.services.response_planner import ResponsePlan, build_response_plan

COMMANDER_STAGES: tuple[str, ...] = ("observe", "diagnose", "plan", "simulate", "gate", "act_or_escalate", "verify", "learn", "report")


@dataclass(frozen=True)
class CommanderStage:
    name: str
    input_evidence: tuple[str, ...]
    decision: str
    confidence: float
    blockers: tuple[str, ...]
    next_step: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "input_evidence": list(self.input_evidence),
            "decision": redact_text(self.decision),
            "confidence": self.confidence,
            "blockers": list(self.blockers),
            "next_step": redact_text(self.next_step),
        }


@dataclass(frozen=True)
class IncidentCommand:
    incident_id: str
    status: str
    summary: str
    alert_context: dict[str, Any]
    stages: tuple[CommanderStage, ...]
    response_plan: ResponsePlan
    readiness: AutonomyReadiness
    evidence_graph: EvidenceGraph
    recovery_verification: RecoveryVerification
    learning_signal: CommanderLearningSignal
    next_action: str
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "status": redact_text(self.status),
            "summary": redact_text(self.summary),
            "alert_context": redact_value(self.alert_context),
            "stages": [stage.to_dict() for stage in self.stages],
            "response_plan": self.response_plan.to_dict(),
            "readiness": self.readiness.to_dict(),
            "evidence_graph": self.evidence_graph.to_dict(),
            "recovery_verification": self.recovery_verification.to_dict(),
            "learning_signal": self.learning_signal.to_dict(),
            "next_action": redact_text(self.next_action),
            "local_mock_only": self.local_mock_only,
        }


def build_incident_command(incident: Any) -> IncidentCommand:
    incident_id = str(_get(incident, "id", ""))
    evidence_ids = tuple(str(_get(item, "id", f"evidence-{index}")) for index, item in enumerate(_evidence(incident), start=1))
    plan = build_response_plan(incident if isinstance(incident, Mapping) else incident)
    recovery = verify_recovery(incident)
    learning = summarize_learning_signals(_memory_matches(incident))
    readiness = score_autonomy_readiness(_readiness_inputs(incident, plan, recovery, learning))
    graph = build_evidence_graph(incident, plan=plan, verification=recovery, learning=learning)
    stages = _stages(incident, evidence_ids, plan, readiness, recovery, learning)
    return IncidentCommand(
        incident_id=incident_id,
        status=str(_get(incident, "status", "unknown")),
        summary=str(_get(incident, "summary", "")),
        alert_context=dict(_get(incident, "alert_payload", {})) if isinstance(_get(incident, "alert_payload", {}), Mapping) else {},
        stages=stages,
        response_plan=plan,
        readiness=readiness,
        evidence_graph=graph,
        recovery_verification=recovery,
        learning_signal=learning,
        next_action=_next_action(readiness, plan, recovery),
    )


class IncidentCommanderService:
    def build(self, incident: Any) -> dict[str, Any]:
        return build_incident_command(incident).to_dict()


def _stages(
    incident: Any, evidence_ids: tuple[str, ...], plan: ResponsePlan, readiness: AutonomyReadiness, recovery: RecoveryVerification, learning: CommanderLearningSignal
) -> tuple[CommanderStage, ...]:
    confidence = _float(_get(incident, "confidence", 0.0), 0.0)
    plan_dict = plan.to_dict()
    readiness_dict = readiness.to_dict()
    recovery_dict = recovery.to_dict()
    learning_dict = learning.to_dict()
    stage_data = {
        "observe": ("local/mock evidence captured", (), "diagnose"),
        "diagnose": (_get(incident, "root_cause_candidate", "No deterministic root-cause candidate"), tuple(plan_dict.get("blocking_reasons", [])), "plan"),
        "plan": (f"{plan_dict['route']} via {plan_dict['runbook_key']}", tuple(plan_dict.get("blocking_reasons", [])), "simulate"),
        "simulate": ("simulation metadata required before action", tuple(_simulation_blockers(plan)), "gate"),
        "gate": (str(readiness_dict["route"]), tuple(readiness_dict.get("blockers", [])), "act_or_escalate"),
        "act_or_escalate": (_next_action(readiness, plan, recovery), tuple(readiness_dict.get("blockers", [])), "verify"),
        "verify": (str(recovery_dict["status"]), tuple(recovery_dict.get("blockers", [])), "learn"),
        "learn": (str(learning_dict["route"]), tuple(learning_dict.get("warnings", [])), "report"),
        "report": ("render commander report evidence", (), "operator_review"),
    }
    return tuple(
        CommanderStage(
            name=name,
            input_evidence=evidence_ids,
            decision=redact_text(str(stage_data[name][0])),
            confidence=round(confidence, 2),
            blockers=tuple(str(item) for item in stage_data[name][1]),
            next_step=str(stage_data[name][2]),
        )
        for name in COMMANDER_STAGES
    )


def _readiness_inputs(incident: Any, plan: ResponsePlan, recovery: RecoveryVerification, learning: CommanderLearningSignal) -> dict[str, Any]:
    action = _primary_action(incident)
    payload = _get(action, "payload", {}) if action is not None else {}
    simulation = _section(payload, "simulation")
    blast = _section(payload, "blast_radius")
    memory_counts = learning.counts
    memory_outcome = "poisoned" if memory_counts.get("poisoned", 0) else "failed" if memory_counts.get("failed", 0) else "success" if memory_counts.get("success", 0) else "none"
    plan_dict = plan.to_dict()
    first_action_step = next((step for step in plan_dict["steps"] if step["type"] == "safe_local_mock_action"), None)
    return {
        "evidence_count": len(_evidence(incident)),
        "confidence": _get(action, "confidence", None) if action is not None else _get(incident, "confidence", 0.0),
        "blast_radius_scope": blast.get("scope") or blast.get("level") or ("local" if first_action_step else "unknown"),
        "reversible": bool(first_action_step and first_action_step.get("rollback_expectation") != "none") or bool(blast.get("rollback_available")),
        "simulation_status": simulation.get("status", "passed" if first_action_step else "pending"),
        "policy_decision": _get(action, "policy_decision", "REQUIRE_APPROVAL" if first_action_step else "ESCALATE"),
        "memory_outcome": memory_outcome,
        "verification_status": recovery.status,
    }


def _next_action(readiness: AutonomyReadiness, plan: ResponsePlan, recovery: RecoveryVerification) -> str:
    if recovery.recovered:
        return "Report recovered local/mock state and keep monitoring."
    readiness_route = readiness.route
    if readiness_route == "blocked":
        return "Stop: hard safety gate blocks action."
    if readiness_route == "human_required":
        return "Ask human to resolve commander blockers before action."
    if readiness_route == "approval_required":
        return "Prepare approval packet for local/mock response plan."
    first_step = next((step for step in plan.steps if step.type == "safe_local_mock_action"), None)
    return f"Eligible to run local/mock step {first_step.id}: {first_step.goal}." if first_step else "Collect more evidence."


def _simulation_blockers(plan: ResponsePlan) -> tuple[str, ...]:
    blockers = [blocker for step in plan.steps for blocker in step.blockers]
    if plan.route in {"human_required", "blocked"}:
        blockers.append(plan.route)
    return tuple(sorted(set(blockers)))


def _memory_matches(incident: Any) -> list[Any]:
    action = _primary_action(incident)
    payload = _get(action, "payload", {}) if action is not None else {}
    memory = _section(payload, "incident_memory")
    matches = memory.get("similar_incidents", [])
    if isinstance(matches, Sequence) and not isinstance(matches, (str, bytes, bytearray)):
        return list(matches)
    return []


def _primary_action(incident: Any) -> Any:
    actions = _get(incident, "actions", [])
    if isinstance(actions, Sequence) and not isinstance(actions, (str, bytes, bytearray)) and actions:
        return actions[0]
    return None


def _section(payload: Any, key: str) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        value = payload.get(key, {})
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _evidence(incident: Any) -> list[Any]:
    value = _get(incident, "evidence", [])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        safe = redact_value(list(value))
        return list(safe) if isinstance(safe, list) else list(value)
    return []


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
