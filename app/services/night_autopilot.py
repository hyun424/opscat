from sqlalchemy.orm import Session

from app.models import ActionProposal
from app.models.action import ActionRequest, RiskLevel
from app.schemas.incidents import MockAlertRequest, NightAutopilotConfig, NightAutopilotResult
from app.services.incident_service import create_mock_incident, get_incident
from app.services.policy_engine import NightAutopilotConfig as PolicyNightAutopilotConfig
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.report_service import render_incident_report
from app.services.state_machine import transition_incident
from app.services.timeline_service import add_timeline_event
from app.tools.mock_actions import execute_mock_action, verify_recovery


def simulate_night_autopilot(db: Session, config: NightAutopilotConfig) -> NightAutopilotResult:
    incident = create_mock_incident(
        db,
        MockAlertRequest(
            scenario="worker_queue_backlog",
            service="worker",
            environment="staging",
            severity="medium",
            message="Night Autopilot detected mock worker queue backlog",
        ),
    )
    db.add(transition_incident(incident, "investigating", actor="night-autopilot", reason="quiet-hours simulation"))
    policy = PolicyEngine().evaluate(
        ActionRequest(
            action_type="mock.execute_restart_worker",
            target="worker:staging",
            environment=incident.environment,
            incident_id=incident.id,
        ),
        PolicyContext(
            service=incident.service,
            environment=incident.environment,
            night_autopilot=True,
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
            action_type="mock.execute_restart_worker",
            target="worker:staging",
            environment="staging",
            risk_level=policy.risk_level,
            requires_approval=False,
            rationale="Night Autopilot allowlisted low-risk non-prod worker restart.",
            payload={"worker_pool": "default", "mode": "night_autopilot_mock"},
            preconditions=["runbook marks restart reversible", "environment is not production"],
            post_checks=["worker heartbeat is healthy", "queue latency decreases"],
            policy_decision=policy.decision,
            policy_reasons=[policy.reason],
            status="approved",
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
        actions_taken.append({"action_id": action.id, "action_type": action.action_type, "result": result})
        add_timeline_event(
            db,
            incident.id,
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
            db.add(transition_incident(incident, "escalated", actor="night-autopilot", reason="verification failed"))
            escalations.append({"incident_id": incident.id, "reason": "verification failed"})
    else:
        db.add(
            transition_incident(
                incident, "escalated", actor="night-autopilot", reason="policy did not allow automatic action"
            )
        )
        escalations.append({"incident_id": incident.id, "reason": "; ".join(policy.reasons)})

    db.commit()
    refreshed = get_incident(db, incident.id)
    morning_report = "# Night Autopilot Morning Report\n\n" + render_incident_report(refreshed)
    return NightAutopilotResult(
        mode="simulated",
        incidents_detected=1,
        actions_taken=actions_taken,
        escalations=escalations,
        morning_report=morning_report,
    )
