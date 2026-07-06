from hashlib import sha256
from uuid import uuid4

from sqlalchemy.orm import Session, selectinload

from app.agent.loop import AgentLoop
from app.models import ActionProposal, ApprovalDecision, Incident
from app.models.action import ActionRequest
from app.schemas.incidents import MockAlertRequest
from app.services.escalation import build_escalation_payload, record_human_escalation
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.redaction import redact_text
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


def alert_fingerprint(payload: MockAlertRequest) -> str:
    raw_key = payload.idempotency_key or payload.fingerprint or str(uuid4())
    stable = f"{payload.tenant_id}|{payload.workspace_id}|{_service_for_alert(payload)}|{payload.environment}|{payload.scenario}|{raw_key}"
    return sha256(stable.encode("utf-8")).hexdigest()[:32]


def create_mock_incident(db: Session, payload: MockAlertRequest) -> Incident:
    fingerprint = alert_fingerprint(payload)
    existing = (
        db.query(Incident)
        .filter(
            Incident.tenant_id == payload.tenant_id,
            Incident.workspace_id == payload.workspace_id,
            Incident.alert_fingerprint == fingerprint,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    incident = Incident(
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        alert_fingerprint=fingerprint,
        source="mock_alert",
        status="new",
        service=_service_for_alert(payload),
        environment=payload.environment,
        severity=payload.severity,
        alert_payload=payload.model_dump(),
        summary=redact_text(payload.message or f"Mock alert for {payload.scenario}"),
    )
    db.add(incident)
    db.flush()
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="integration",
        event_type="alert_received",
        content=incident.summary or "Mock alert received",
        metadata={"source": "mock", "fingerprint": payload.fingerprint, "alert_fingerprint": fingerprint},
    )
    db.add(transition_incident(incident, "queued", actor="system", reason="mock alert accepted"))
    return incident


def run_investigation(db: Session, incident: Incident) -> ActionProposal:
    action = AgentLoop().investigate(db, incident)
    db.flush()
    return action


def create_and_investigate(db: Session, payload: MockAlertRequest) -> Incident:
    incident = create_mock_incident(db, payload)
    if not incident.actions and incident.status in {"new", "queued", "investigating"}:
        run_investigation(db, incident)
    incident_id = incident.id
    db.commit()
    db.expire_all()
    return get_incident(db, incident_id)


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
    approval = ApprovalDecision(
        action_id=action.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        decision=decision,
        actor=actor,
        reason=reason,
    )
    db.add(approval)

    if decision == "reject":
        action.status = "rejected"
        db.add(transition_incident(incident, "escalated", actor=actor, reason=reason or "action rejected"))
        add_timeline_event(
            db,
            incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor=actor,
            event_type="approval_rejected",
            content="Action rejected",
        )
        db.commit()
        return action, get_incident(db, incident.id), None

    policy = PolicyEngine().evaluate(
        ActionRequest(
            action_type=action.action_type,
            target=action.target,
            environment=incident.environment,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            payload=action.payload,
            incident_id=incident.id,
            approved=True,
            approval_id=approval.id,
        ),
        PolicyContext(
            environment=incident.environment,
            service=incident.service,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
        ),
    )
    if policy.decision != "ALLOW":
        action.status = "denied"
        action.policy_decision = policy.decision
        action.policy_reasons = policy.reasons
        payload = build_escalation_payload(
            incident,
            trigger="policy_denied_action",
            triggers=["policy_denied_action"],
            action=action,
            policy=policy,
            recommended_next_action="Do not execute the denied action; choose a safer runbook.",
        )
        record_human_escalation(db, incident, payload, action=action, transition_to_escalated=True)
        db.commit()
        return action, get_incident(db, incident.id), None

    action.status = "approved"
    action.policy_decision = policy.decision
    action.policy_reasons = [policy.reason]
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor=actor,
        event_type="approval_granted",
        content="Action approved",
    )
    db.add(transition_incident(incident, "executing", actor="executor", reason="approved action"))
    result = execute_mock_action(db, incident, action)
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="executor",
        event_type="action_executed",
        content=f"Executed {action.action_type}: ok={result['ok']}",
        metadata=result,
    )
    if not result["ok"]:
        payload = build_escalation_payload(
            incident,
            trigger="execution_failed",
            triggers=["execution_failed"],
            action=action,
            verification={"execution": result},
            recommended_next_action="Stop automatic execution and inspect the failed mock action result.",
        )
        record_human_escalation(db, incident, payload, action=action, transition_to_escalated=True)
        db.commit()
        return action, get_incident(db, incident.id), None
    db.add(transition_incident(incident, "verifying", actor="verifier", reason="post-check started"))
    verification = verify_recovery(incident, action)
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="verifier",
        event_type="recovery_verified",
        content=f"Recovery verified={verification['recovered']}",
        metadata=verification,
    )
    if verification["recovered"]:
        db.add(transition_incident(incident, "resolved", actor="verifier", reason="mock recovery passed"))
    else:
        payload = build_escalation_payload(
            incident,
            trigger="post_check_failed",
            triggers=["post_check_failed"],
            action=action,
            verification=verification,
        )
        record_human_escalation(db, incident, payload, action=action, transition_to_escalated=True)
    db.flush()
    report = save_incident_report(db, incident)
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="reporter",
        event_type="report_generated",
        content=report,
    )
    db.commit()
    return action, get_incident(db, incident.id), report
