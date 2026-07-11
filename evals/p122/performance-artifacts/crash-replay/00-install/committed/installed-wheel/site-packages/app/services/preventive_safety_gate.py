"""Shared fail-closed safety gate for preventive planning paths."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from app.models.action import ActionRequest, PolicyDecision, PolicyEvaluation
from app.services.action_simulator import ActionSimulator, SimulationResult
from app.services.blast_radius import BlastRadiusResult, BlastRadiusService
from app.services.incident_memory import IncidentMemoryMatch, failed_remediation_warning, summarize_matches
from app.services.policy_engine import PolicyContext, PolicyEngine

SAFE_BLAST_RADIUS_SCOPES = frozenset({"local", "service"})
PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})
PROHIBITED_ACTION_MARKERS = frozenset(("shell", "secret", "database", "cloud.delete", "production."))


@dataclass(frozen=True)
class PreventiveSafetyGateResult:
    """Typed safety decision shared by P106 planning and Night Autopilot."""

    passed: bool
    route: str
    reasons: tuple[str, ...]
    confidence: Mapping[str, Any]
    policy: Mapping[str, Any]
    blast_radius: Mapping[str, Any]
    reversible: bool
    simulation: Mapping[str, Any]
    memory: Mapping[str, Any]
    environment: Mapping[str, Any]
    ambiguity: Mapping[str, Any]
    execution_enabled: bool = False
    simulation_only: bool = True
    p107_required_for_execution: bool = True
    trace: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data

    def to_night_autopilot_v2_dict(self) -> dict[str, object]:
        """Return the legacy Night Autopilot gate metadata shape."""

        return {
            "passed": self.passed,
            "confidence": dict(self.confidence),
            "policy_allowed": bool(self.policy.get("allowed")),
            "blast_radius": {
                "scope": self.blast_radius.get("scope"),
                "ok": bool(self.blast_radius.get("ok")),
                "rollback_available": self.reversible,
            },
            "reversible": self.reversible,
            "simulation": dict(self.simulation),
            "memory": dict(self.memory),
            "reasons": list(self.reasons),
            "route": self.route,
            "execution_enabled": self.execution_enabled,
            "simulation_only": self.simulation_only,
            "p107_required_for_execution": self.p107_required_for_execution,
        }


def evaluate_preventive_safety_gate(case: Mapping[str, Any]) -> PreventiveSafetyGateResult:
    """Evaluate a dict-shaped P106/Night-Autopilot candidate fail-closed.

    The adapter accepts raw fixture dictionaries as well as already-composed
    PolicyEngine, blast-radius, simulator, and incident-memory decisions.
    """

    request = _coerce_request(case)
    policy_engine = case.get("policy_engine")
    if not isinstance(policy_engine, PolicyEngine):
        policy_engine = PolicyEngine()
    blast_radius_service = case.get("blast_radius_service")
    if not isinstance(blast_radius_service, BlastRadiusService):
        blast_radius_service = policy_engine.blast_radius_service
    action_simulator = case.get("action_simulator")
    if not isinstance(action_simulator, ActionSimulator):
        action_simulator = policy_engine.action_simulator

    # Safety authority always comes from the shared engine graph. Raw fixture
    # fields may only make a decision more restrictive; they can never turn a
    # denied engine result into an allow.
    blast_radius = _coerce_blast_radius(request, blast_radius_service)
    simulation = _coerce_simulation(request, action_simulator)
    memory_matches = _coerce_memory_matches(case)
    failed_memory = bool(
        case.get("failed_memory")
        or case.get("failed_remediation_warning")
        or case.get("memory_failed_action_warning")
        or case.get("prior_failed_remediation")
        or failed_remediation_warning(memory_matches)
    )
    policy = _coerce_policy(case, request, policy_engine, blast_radius, simulation, failed_memory)

    confidence = _confidence(case)
    environment = str(case.get("environment", request.environment or "local"))
    severity = str(case.get("severity", "medium"))
    conflicting = bool(case.get("conflicting_signals") or case.get("conflicting_evidence"))
    ambiguous = bool(case.get("known_ambiguity") or case.get("ambiguity"))
    registry_hash_parity = bool(case.get("registry_hash_parity", True))
    policy_allowed = _policy_allowed(policy, case)
    scope = _restrictive_blast_scope(_blast_scope(blast_radius), case.get("blast_radius_scope"))
    rollback_available = _rollback_available(blast_radius) and case.get("rollback_available") is not False
    simulation_ok = bool(_simulation_ok(simulation, case))
    action_known = _action_known(policy_engine, request.action_type, case)

    reasons: list[str] = []
    if environment.lower() in PRODUCTION_ENVIRONMENTS:
        reasons.append("production environment is not eligible for preventive automation")
    if severity.lower() == "critical":
        reasons.append("critical severity requires human escalation")
    if confidence is None or confidence < float(case.get("confidence_threshold", 0.80)):
        reasons.append("confidence below preventive safety threshold")
    if conflicting:
        reasons.append("conflicting evidence signals require observation or escalation")
    if ambiguous:
        reasons.append("known ambiguity requires observation or escalation")
    if not registry_hash_parity:
        reasons.append("registry hash parity check failed")
    if not action_known:
        reasons.append(f"unknown action {request.action_type!r} is not registered")
    if _is_prohibited_action(request.action_type):
        reasons.append(f"prohibited action {request.action_type!r} is denied")
    if not policy_allowed:
        reasons.append("policy did not allow the candidate action")
    if scope not in SAFE_BLAST_RADIUS_SCOPES:
        reasons.append(f"blast_radius scope {scope!r} is not local or service")
    if not rollback_available:
        reasons.append("rollback is unavailable")
    if not simulation_ok:
        reasons.append("simulation did not pass")
    if failed_memory:
        reasons.append("incident memory found prior failed remediation")

    passed = not reasons
    return PreventiveSafetyGateResult(
        passed=passed,
        route="observe" if passed else _blocked_route(reasons),
        reasons=tuple(reasons),
        confidence={"value": confidence, "ok": confidence is not None and confidence >= float(case.get("confidence_threshold", 0.80)), "threshold": float(case.get("confidence_threshold", 0.80))},
        policy={"allowed": policy_allowed, "decision": _policy_decision(policy), "reasons": _policy_reasons(policy)},
        blast_radius={"scope": scope, "ok": scope in SAFE_BLAST_RADIUS_SCOPES, "rollback_available": rollback_available},
        reversible=rollback_available,
        simulation=_simulation_dict(simulation, case),
        memory={"failed_remediation_warning": failed_memory, "similar_incidents": _memory_summary(case, memory_matches)},
        environment={"value": environment, "ok": environment.lower() not in PRODUCTION_ENVIRONMENTS, "severity": severity},
        ambiguity={"conflicting_signals": conflicting, "known_ambiguity": ambiguous, "ok": not conflicting and not ambiguous},
        trace={"action_type": request.action_type, "target": request.target, "registry_hash_parity": registry_hash_parity},
    )


def _coerce_request(case: Mapping[str, Any]) -> ActionRequest:
    request = case.get("request")
    if isinstance(request, ActionRequest):
        return request
    payload = case.get("payload", {})
    if not isinstance(payload, Mapping):
        payload = {}
    service = str(case.get("service", payload.get("service", "demo-service")))
    return ActionRequest(
        action_type=str(case.get("action_type", payload.get("action_type", "unknown"))),
        target=str(case.get("target", payload.get("target", service))),
        environment=str(case.get("environment", payload.get("environment", "local"))),
        tenant_id=str(case.get("tenant_id", "demo")),
        workspace_id=str(case.get("workspace_id", "demo")),
        incident_id=str(case["incident_id"]) if case.get("incident_id") is not None else None,
        payload=payload,
    )


def _coerce_blast_radius(request: ActionRequest, service: BlastRadiusService) -> BlastRadiusResult:
    return service.evaluate(request)


def _coerce_simulation(request: ActionRequest, simulator: ActionSimulator) -> SimulationResult:
    return simulator.simulate(request)


def _coerce_policy(
    case: Mapping[str, Any],
    request: ActionRequest,
    engine: PolicyEngine,
    blast_radius: BlastRadiusResult,
    simulation: SimulationResult,
    failed_memory: bool,
) -> PolicyEvaluation:
    return engine.evaluate(request, _policy_context(case, blast_radius, simulation, failed_memory))


def _policy_context(
    case: Mapping[str, Any],
    blast_radius: BlastRadiusResult,
    simulation: SimulationResult,
    failed_memory: bool,
) -> PolicyContext:
    return PolicyContext(
        service=str(case.get("service", "demo-service")),
        environment=str(case.get("environment", "local")),
        severity=str(case.get("severity", "medium")),
        mode=str(case.get("mode", "preventive_safety_gate")),
        night_autopilot=bool(case.get("night_autopilot", False)),
        confidence=_confidence(case),
        evidence_count=int(case.get("evidence_count", 3)),
        conflicting_signals=bool(case.get("conflicting_signals") or case.get("conflicting_evidence")),
        known_ambiguity=bool(case.get("known_ambiguity") or case.get("ambiguity")),
        blast_radius_scope=_restrictive_blast_scope(str(blast_radius.scope), case.get("blast_radius_scope")),
        rollback_available=bool(blast_radius.rollback_available) and case.get("rollback_available") is not False,
        simulation_passed=_simulation_ok(simulation, case),
        simulation_status="passed" if _simulation_ok(simulation, case) else "failed",
        failed_memory_warning=failed_memory,
        memory_failed_action_warning=failed_memory,
    )


def _coerce_memory_matches(case: Mapping[str, Any]) -> Sequence[IncidentMemoryMatch]:
    matches = case.get("memory_matches", ())
    if isinstance(matches, Sequence) and not isinstance(matches, (str, bytes, bytearray)):
        return tuple(match for match in matches if isinstance(match, IncidentMemoryMatch))
    return ()


def _memory_summary(case: Mapping[str, Any], matches: Sequence[IncidentMemoryMatch]) -> list[dict[str, object]]:
    raw = case.get("memory_matches", ())
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        summary = [dict(item) for item in raw if isinstance(item, Mapping)]
        if summary:
            return summary
    return summarize_matches(matches)


def _confidence(case: Mapping[str, Any]) -> float | None:
    value = case.get("confidence")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _policy_allowed(policy: PolicyEvaluation, case: Mapping[str, Any]) -> bool:
    return policy.decision == PolicyDecision.ALLOW and case.get("policy_allowed") is not False


def _policy_decision(policy: PolicyEvaluation) -> str:
    return str(policy.decision.value if isinstance(policy.decision, PolicyDecision) else policy.decision)


def _policy_reasons(policy: PolicyEvaluation) -> list[str]:
    return list(policy.reasons)


def _blast_scope(blast_radius: BlastRadiusResult) -> str:
    return str(blast_radius.scope)


def _rollback_available(blast_radius: BlastRadiusResult) -> bool:
    return bool(blast_radius.rollback_available)


def _simulation_ok(simulation: SimulationResult, case: Mapping[str, Any]) -> bool:
    if case.get("simulation_allowed") is False:
        return False
    status = case.get("simulation_status")
    if status is not None and str(status) not in {"pass", "passed", "success", "ok"}:
        return False
    return bool(simulation.success)


def _simulation_dict(simulation: SimulationResult, case: Mapping[str, Any]) -> dict[str, Any]:
    data = simulation.to_dict()
    ok = _simulation_ok(simulation, case)
    data["status"] = "passed" if ok else "failed"
    data["ok"] = ok
    data["success"] = ok
    data["allowed"] = ok
    return data


def _restrictive_blast_scope(authoritative: str, declared: Any) -> str:
    """Return the riskier scope so caller input can only fail closed."""

    rank = {"local": 0, "service": 1, "workspace": 2, "global": 3, "unknown": 4}
    declared_scope = str(declared) if declared is not None else authoritative
    authoritative_rank = rank.get(authoritative, rank["unknown"])
    declared_rank = rank.get(declared_scope, rank["unknown"])
    return declared_scope if declared_rank > authoritative_rank else authoritative


def _action_known(engine: PolicyEngine, action_type: str, case: Mapping[str, Any]) -> bool:
    if bool(case.get("unknown_action")):
        return False
    return engine.risk_engine.get_action(action_type) is not None


def _is_prohibited_action(action_type: str) -> bool:
    lowered = action_type.lower()
    return any(marker in lowered for marker in PROHIBITED_ACTION_MARKERS)


def _blocked_route(reasons: Sequence[str]) -> str:
    joined = " ".join(reasons)
    if any(token in joined for token in ("unknown action", "prohibited", "registry", "simulation", "blast_radius")):
        return "blocked_fail_closed"
    return "escalate"
