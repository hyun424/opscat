from sqlalchemy.orm import Session

from app.models import ActionProposal
from app.models.action import ActionMetadata, ActionRequest, RiskLevel
from app.schemas.incidents import MockAlertRequest, NightAutopilotConfig, NightAutopilotResult
from app.services.action_simulator import ActionSimulator
from app.services.blast_radius import BlastRadiusEngine
from app.services.escalation import build_escalation_payload, record_human_escalation
from app.services.incident_memory import build_incident_memory, failed_remediation_warning, search_similar_incidents, summarize_matches
from app.services.incident_service import create_mock_incident, get_incident
from app.services.policy_engine import NightAutopilotConfig as PolicyNightAutopilotConfig
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.report_service import render_incident_report
from app.services.risk_engine import RiskEngine
from app.services.state_machine import transition_incident
from app.services.timeline_service import add_timeline_event
from app.tools.mock_actions import execute_mock_action, verify_recovery


def simulate_night_autopilot(db: Session, config: NightAutopilotConfig) -> NightAutopilotResult:
    target = config.target or f"{config.service}:{config.environment}"
    incident = create_mock_incident(
        db,
        MockAlertRequest(
            scenario=config.scenario,
            service=config.service,
            environment=config.environment,
            severity=config.severity,
            message=f"Night Autopilot detected mock {config.service} incident",
        ),
    )
    db.add(transition_incident(incident, "investigating", actor="night-autopilot", reason="quiet-hours simulation"))
    request = ActionRequest(
        action_type=config.action_type,
        target=target,
        environment=incident.environment,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        incident_id=incident.id,
    )
    policy = PolicyEngine().evaluate(
        request,
        PolicyContext(
            service=incident.service,
            environment=incident.environment,
            severity=incident.severity,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            confidence=0.88,
            blast_radius_scope=blast_radius.scope,
            reversible=blast_radius.rollback_available,
            simulation_status="passed" if simulation.ok else "failed",
            memory_failed_action_warning=memory_failed_warning,
            night_autopilot=True,
            confidence=0.86,
            evidence_count=3,
            blast_radius_scope=blast_radius.scope,
            rollback_available=blast_radius.rollback_available,
            simulation_passed=simulation.success,
            autopilot=PolicyNightAutopilotConfig(
                max_automatic_risk=RiskLevel(config.max_automatic_risk),
                max_attempts_per_incident=config.max_attempts_per_incident,
                allowed_services=tuple(config.allowed_services),
                allowed_environments=tuple(config.allowed_environments),
                allowed_actions=("mock.execute_restart_worker",),
            ),
        ),
    )
    action_metadata = RiskEngine().get_action(config.action_type)
    incident.root_cause_candidate = incident.root_cause_candidate or _default_root_cause(config.scenario)
    incident.confidence = _estimated_confidence(config.scenario)
    memory = build_incident_memory(db, tenant_id=incident.tenant_id, workspace_id=incident.workspace_id, exclude_incident_id=incident.id)
    memory_matches = search_similar_incidents(memory, incident, action_type=config.action_type)
    simulation = _simulate_action(request, action_metadata)
    v2_gates = _evaluate_v2_gates(
        confidence=incident.confidence,
        policy_allowed=policy.decision == "ALLOW",
        action=action_metadata,
        simulation=simulation,
        failed_memory=failed_remediation_warning(memory_matches),
        memory_matches=summarize_matches(memory_matches),
    )
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="night-autopilot",
        event_type="night_autopilot_v2_gate",
        content=f"Night Autopilot v2 gates {'passed' if v2_gates['passed'] else 'blocked'}",
        metadata=v2_gates,
    )
    actions_taken: list[dict[str, object]] = []
    escalations: list[dict[str, object]] = []
    if v2_gates["passed"] and config.max_attempts_per_incident >= 1:
        action = ActionProposal(
            incident_id=incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            action_type=config.action_type,
            target=target,
            environment=incident.environment,
            risk_level=policy.risk_level,
            requires_approval=False,
            rationale="Night Autopilot v2 allowlisted low-risk non-prod worker restart after confidence, blast-radius, simulation, and memory gates passed.",
            payload={"worker_pool": "default", "mode": "night_autopilot_mock", "v2_gates": v2_gates},
            preconditions=["runbook marks restart reversible", "environment is not production"],
            post_checks=["worker heartbeat is healthy", "queue latency decreases"],
            policy_decision=policy.decision,
            policy_reasons=policy.reasons,
            confidence=incident.confidence,
            status="approved",
            payload={
                "worker_pool": "default",
                "mode": "night_autopilot_mock",
                "blast_radius": blast_radius.__dict__,
                "simulation": simulation.to_dict(),
                "memory_matches": [
                    {"incident_id": match.record.incident_id, "similarity": match.similarity, "failed_remediation_warning": match.failed_remediation_warning}
                    for match in memory_matches
                ],
            },
        )
        db.add(action)
        db.flush()
        db.add(transition_incident(incident, "action_proposed", actor="night-autopilot", reason="allowlisted action selected"))
        db.add(transition_incident(incident, "executing", actor="night-autopilot", reason="automatic action allowed"))
        result = execute_mock_action(db, incident, action)
        actions_taken.append({"action_id": action.id, "action_type": action.action_type, "result": result, "v2_gates": v2_gates})
        add_timeline_event(
            db,
            incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="night-autopilot",
            event_type="action_executed",
            content="Automatic mock worker restart executed",
            metadata=result,
        )
        db.add(transition_incident(incident, "verifying", actor="night-autopilot", reason="post-check"))
        verification = verify_recovery(incident, action)
        if verification["recovered"]:
            db.add(transition_incident(incident, "resolved", actor="night-autopilot", reason="recovered during quiet hours"))
        else:
            payload = build_escalation_payload(
                incident,
                trigger="post_check_failed",
                triggers=["post_check_failed"],
                action=action,
                policy=policy,
                verification=verification,
                recommended_next_action=("Wake the configured on-call contact; automatic quiet-hours remediation did not verify."),
            )
            record_human_escalation(db, incident, payload, action=action, transition_to_escalated=True)
            escalations.append(payload)
    else:
        triggers = _v2_block_triggers(v2_gates, policy_decision=str(policy.decision), max_attempts=config.max_attempts_per_incident)
        payload = build_escalation_payload(
            incident,
            trigger=triggers[0],
            triggers=triggers,
            policy=policy,
            recommended_next_action="Wake the configured on-call contact; Night Autopilot v2 cannot proceed safely.",
        )
        payload["v2_gates"] = v2_gates
        record_human_escalation(db, incident, payload, transition_to_escalated=True)
        escalations.append(payload)

    db.commit()
    refreshed = get_incident(db, incident.id)
    morning_report = _render_morning_report(refreshed.status, actions_taken, escalations, render_incident_report(refreshed), gate_evidence)
    return NightAutopilotResult(
        mode="simulated",
        incidents_detected=1,
        actions_taken=actions_taken,
        escalations=escalations,
        morning_report=morning_report,
    )


def _render_morning_report(
    incident_status: str,
    actions_taken: list[dict[str, object]],
    escalations: list[dict[str, object]],
    incident_report: str,
    gate_evidence: dict[str, object],
) -> str:
    resolved = 1 if incident_status == "resolved" else 0
    escalated = 1 if incident_status == "escalated" else 0
    blocked_actions = 0 if actions_taken else len(escalations)
    verification = "recovered" if resolved else "blocked_or_escalated_before_execution"
    follow_up = "No human follow-up required." if resolved else "Review escalation payload and choose a safer runbook."
    gate_summary = _render_v2_gate_summary(actions_taken, escalations)
    summary = "\n".join(
        [
            "# Night Autopilot Morning Report",
            "",
            "## Overnight summary",
            "- Detected: 1",
            f"- Resolved: {resolved}",
            f"- Escalated: {escalated}",
            f"- Actions taken: {len(actions_taken)}",
            f"- Blocked actions: {blocked_actions}",
            f"- Verification outcomes: {verification}",
            f"- Follow-ups: {follow_up}",
            f"- Reliability gates: {reliability}",
            f"- Simulation: {simulation_status}",
            f"- Blast radius: {blast_scope}",
            f"- {blocked_rationale}",
            "",
            "## Reliability gates",
            gate_summary,
            "",
            "## Reliability gates",
            gate_summary,
            "",
            "## Incident evidence",
            "",
        ]
    )
    return summary + incident_report


def _render_v2_gate_summary(actions_taken: list[dict[str, object]], escalations: list[dict[str, object]]) -> str:
    gates: object | None = None
    if actions_taken:
        gates = actions_taken[0].get("v2_gates")
    elif escalations:
        gates = escalations[0].get("v2_gates")
    if not isinstance(gates, dict):
        return "- Night Autopilot v2 gates: unavailable"
    memory = gates.get("memory") if isinstance(gates.get("memory"), dict) else {}
    simulation = gates.get("simulation") if isinstance(gates.get("simulation"), dict) else {}
    similar = memory.get("similar_incidents", []) if isinstance(memory, dict) else []
    failed_warning = memory.get("failed_remediation_warning") if isinstance(memory, dict) else None
    return "\n".join(
        [
            f"- Night Autopilot v2 gates: {'passed' if gates.get('passed') else 'blocked'}",
            f"- confidence: {gates.get('confidence')}",
            f"- blast_radius: {gates.get('blast_radius')}",
            f"- simulation: {simulation}",
            f"- memory: failed_remediation_warning={failed_warning}; similar_incidents={similar}",
        ]
    )


def _estimated_confidence(scenario: str) -> float:
    if scenario in {"low_confidence_ambiguous", "conflicting_evidence_payment", "critical_unknown_multi_service"}:
        return 0.42
    return 0.82


def _default_root_cause(scenario: str) -> str:
    if scenario in {"worker_queue_backlog", "worker_poison_message", "worker_heartbeat_loss"}:
        return "Worker queue degradation"
    return scenario.replace("_", " ").title()


def _simulate_action(request: ActionRequest, action: ActionMetadata | None) -> dict[str, object]:
    if action is None or action.prohibited_reason:
        return {"ok": False, "reason": "simulation_failed_unregistered_or_prohibited", "touched_resources": []}
    if not action.reversible:
        return {"ok": False, "reason": "simulation_failed_not_reversible", "touched_resources": [request.target]}
    if not _bounded_blast_radius(action):
        return {"ok": False, "reason": "simulation_failed_unbounded_blast_radius", "touched_resources": [request.target]}
    return {
        "ok": True,
        "expected_effect": action.description,
        "rollback_path": action.blast_radius if action.reversible else "none",
        "touched_resources": [request.target],
        "residual_risks": [],
    }


def _evaluate_v2_gates(
    *,
    confidence: float | None,
    policy_allowed: bool,
    action: ActionMetadata | None,
    simulation: dict[str, object],
    failed_memory: bool,
    memory_matches: list[dict[str, object]],
) -> dict[str, object]:
    high_confidence = confidence is not None and confidence >= 0.80
    blast_radius_ok = _bounded_blast_radius(action)
    reversible = bool(action and action.reversible)
    simulation_ok = bool(simulation.get("ok"))
    passed = all([high_confidence, policy_allowed, blast_radius_ok, reversible, simulation_ok, not failed_memory])
    return {
        "passed": passed,
        "confidence": {"value": confidence, "ok": high_confidence, "threshold": 0.80},
        "policy_allowed": policy_allowed,
        "blast_radius": {"value": action.blast_radius if action else "unknown", "ok": blast_radius_ok},
        "reversible": reversible,
        "simulation": simulation,
        "memory": {
            "failed_remediation_warning": failed_memory,
            "similar_incidents": memory_matches,
        },
    }


def _bounded_blast_radius(action: ActionMetadata | None) -> bool:
    if action is None:
        return False
    return action.blast_radius in {"none", "local incident record", "single non-production worker", "mock ticket system"}


def _v2_block_triggers(v2_gates: dict[str, object], *, policy_decision: str, max_attempts: int) -> list[str]:
    triggers: list[str] = []
    if max_attempts < 1:
        triggers.append("max_attempts_reached")
    confidence = v2_gates.get("confidence")
    if isinstance(confidence, dict) and not confidence.get("ok"):
        triggers.append("low_confidence")
    blast_radius = v2_gates.get("blast_radius")
    if isinstance(blast_radius, dict) and not blast_radius.get("ok"):
        triggers.append("unbounded_blast_radius")
    simulation = v2_gates.get("simulation")
    if isinstance(simulation, dict) and not simulation.get("ok"):
        triggers.append("simulation_failed")
    memory = v2_gates.get("memory")
    if isinstance(memory, dict) and memory.get("failed_remediation_warning"):
        triggers.append("memory_failed_remediation")
    if not bool(v2_gates.get("policy_allowed")):
        triggers.append("policy_escalated_action" if policy_decision == "ESCALATE" else "policy_denied_action")
    return triggers or ["policy_escalated_action"]
