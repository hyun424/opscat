from sqlalchemy.orm import Session

from app.models import ActionProposal
from app.models.action import ActionRequest, RiskLevel
from app.schemas.incidents import MockAlertRequest, NightAutopilotConfig, NightAutopilotResult
from app.services.action_simulator import ActionSimulator
from app.services.blast_radius import BlastRadiusEngine
from app.services.escalation import build_escalation_payload, record_human_escalation
from app.services.incident_memory import IncidentMemory
from app.services.incident_service import create_mock_incident, get_incident
from app.services.action_simulator import ActionSimulator
from app.services.blast_radius import BlastRadiusEngine
from app.services.policy_engine import NightAutopilotConfig as PolicyNightAutopilotConfig
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.report_service import render_incident_report
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
    blast_radius = BlastRadiusEngine().classify(request)
    simulation = ActionSimulator().simulate(request)
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
    actions_taken: list[dict[str, object]] = []
    escalations: list[dict[str, object]] = []
    if policy.decision == "ALLOW" and config.max_attempts_per_incident >= 1:
        action = ActionProposal(
            incident_id=incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            action_type=config.action_type,
            target=target,
            environment=incident.environment,
            risk_level=policy.risk_level,
            requires_approval=False,
            rationale="Night Autopilot allowlisted low-risk non-prod worker restart.",
            payload={"worker_pool": "default", "mode": "night_autopilot_mock", "blast_radius": blast_radius.to_dict(), "simulation": simulation.to_dict()},
            preconditions=["runbook marks restart reversible", "environment is not production"],
            post_checks=["worker heartbeat is healthy", "queue latency decreases"],
            policy_decision=policy.decision,
            policy_reasons=policy.reasons,
            confidence=0.82,
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
        db.add(
            transition_incident(
                incident, "action_proposed", actor="night-autopilot", reason="allowlisted action selected"
            )
        )
        db.add(transition_incident(incident, "executing", actor="night-autopilot", reason="automatic action allowed"))
        result = execute_mock_action(db, incident, action)
        actions_taken.append({"action_id": action.id, "action_type": action.action_type, "result": result, "simulation": simulation.to_dict(), "blast_radius": blast_radius.to_dict()})
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
            db.add(
                transition_incident(
                    incident, "resolved", actor="night-autopilot", reason="recovered during quiet hours"
                )
            )
        else:
            payload = build_escalation_payload(
                incident,
                trigger="post_check_failed",
                triggers=["post_check_failed"],
                action=action,
                policy=policy,
                verification=verification,
                recommended_next_action=(
                    "Wake the configured on-call contact; automatic quiet-hours remediation did not verify."
                ),
            )
            record_human_escalation(db, incident, payload, action=action, transition_to_escalated=True)
            escalations.append(payload)
    else:
        trigger = (
            "max_attempts_reached"
            if config.max_attempts_per_incident < 1
            else "policy_escalated_action"
            if policy.decision == "ESCALATE"
            else "policy_denied_action"
        )
        payload = build_escalation_payload(
            incident,
            trigger=trigger,
            triggers=[trigger],
            policy=policy,
            recommended_next_action="Wake the configured on-call contact; Night Autopilot cannot proceed safely.",
            verification={"simulation": simulation.to_dict(), "blast_radius": blast_radius.to_dict()},
        )
        record_human_escalation(db, incident, payload, transition_to_escalated=True)
        escalations.append(payload)

    db.commit()
    refreshed = get_incident(db, incident.id)
    morning_report = _render_morning_report(refreshed.status, actions_taken, escalations, render_incident_report(refreshed))
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
) -> str:
    resolved = 1 if incident_status == "resolved" else 0
    escalated = 1 if incident_status == "escalated" else 0
    blocked_actions = 0 if actions_taken else len(escalations)
    verification = "recovered" if resolved else "blocked_or_escalated_before_execution"
    follow_up = "No human follow-up required." if resolved else "Review escalation payload and choose a safer runbook."
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
            "",
            "## Incident evidence",
            "",
        ]
    )
    return summary + incident_report
