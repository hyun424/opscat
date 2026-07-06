from sqlalchemy.orm import Session, selectinload

from app.agent.loop import AgentLoop
from app.models import ActionProposal, ApprovalDecision, Incident
from app.models.action import ActionRequest
from app.schemas.incidents import MockAlertRequest
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.report_service import save_incident_report
from app.services.state_machine import transition_incident
from app.services.timeline_service import add_timeline_event
from app.tools.mock_actions import execute_mock_action, verify_recovery


def _service_for_alert(payload: MockAlertRequest) -> str:
    if payload.service:
        return payload.service
    if payload.scenario == "worker_queue_backlog":
        return "worker"
    return "payment-api"


def create_mock_incident(db: Session, payload: MockAlertRequest) -> Incident:
    incident = Incident(
        source="mock_alert",
        status="new",
        service=_service_for_alert(payload),
        environment=payload.environment,
        severity=payload.severity,
        alert_payload=payload.model_dump(),
        summary=payload.message or f"Mock alert for {payload.scenario}",
    )
    db.add(incident)
    db.flush()
    add_timeline_event(
        db,
        incident.id,
        actor="integration",
        event_type="alert_received",
        content=incident.summary or "Mock alert received",
        metadata={"source": "mock", "fingerprint": payload.fingerprint},
    )
    db.add(transition_incident(incident, "queued", actor="system", reason="mock alert accepted"))
    return incident


def run_investigation(db: Session, incident: Incident) -> ActionProposal:
    action = AgentLoop().investigate(db, incident)
    db.flush()
    return action


def create_and_investigate(db: Session, payload: MockAlertRequest) -> Incident:
    incident = create_mock_incident(db, payload)
    run_investigation(db, incident)
    db.commit()
    return get_incident(db, incident.id)


def get_incident(db: Session, incident_id: str) -> Incident:
    incident = (
        db.query(Incident)
        .options(
            selectinload(Incident.evidence),
            selectinload(Incident.actions),
            selectinload(Incident.timeline),
        )
        .filter(Incident.id == incident_id)
        .one()
    )
    return incident


def decide_action(
    db: Session,
    action_id: str,
    *,
    decision: str,
    actor: str,
    reason: str | None = None,
) -> tuple[ActionProposal, Incident, str | None]:
    action = db.query(ActionProposal).filter(ActionProposal.id == action_id).one()
    incident = db.query(Incident).filter(Incident.id == action.incident_id).one()
    approval = ApprovalDecision(action_id=action.id, decision=decision, actor=actor, reason=reason)
    db.add(approval)

    if decision == "reject":
        action.status = "rejected"
        db.add(transition_incident(incident, "escalated", actor=actor, reason=reason or "action rejected"))
        add_timeline_event(db, incident.id, actor=actor, event_type="approval_rejected", content="Action rejected")
        db.commit()
        return action, get_incident(db, incident.id), None

    policy = PolicyEngine().evaluate(
        ActionRequest(
            action_type=action.action_type,
            target=action.target,
            environment=incident.environment,
            payload=action.payload,
            incident_id=incident.id,
            approved=True,
            approval_id=approval.id,
        ),
        PolicyContext(environment=incident.environment, service=incident.service),
    )
    if policy.decision != "ALLOW":
        action.status = "denied"
        action.policy_decision = policy.decision
        action.policy_reasons = policy.reasons
        db.add(transition_incident(incident, "failed", actor="policy", reason="approval could not override policy"))
        db.commit()
        return action, get_incident(db, incident.id), None

    action.status = "approved"
    action.policy_decision = policy.decision
    action.policy_reasons = policy.reasons
    add_timeline_event(db, incident.id, actor=actor, event_type="approval_granted", content="Action approved")
    db.add(transition_incident(incident, "executing", actor="executor", reason="approved action"))
    result = execute_mock_action(db, incident, action)
    add_timeline_event(
        db,
        incident.id,
        actor="executor",
        event_type="action_executed",
        content=f"Executed {action.action_type}: ok={result['ok']}",
        metadata=result,
    )
    db.add(transition_incident(incident, "verifying", actor="verifier", reason="post-check started"))
    verification = verify_recovery(incident, action)
    add_timeline_event(
        db,
        incident.id,
        actor="verifier",
        event_type="recovery_verified",
        content=f"Recovery verified={verification['recovered']}",
        metadata=verification,
    )
    if verification["recovered"]:
        db.add(transition_incident(incident, "resolved", actor="verifier", reason="mock recovery passed"))
    else:
        db.add(transition_incident(incident, "escalated", actor="verifier", reason="mock recovery failed"))
    db.flush()
    report = save_incident_report(db, incident)
    add_timeline_event(db, incident.id, actor="reporter", event_type="report_generated", content=report)
    db.commit()
    return action, get_incident(db, incident.id), report
