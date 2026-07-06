from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Incident
from app.schemas.incidents import ApprovalRequest, IncidentRead
from app.services.incident_service import decide_action, get_incident, run_investigation
from app.services.report_service import render_incident_report

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentRead])
def list_incidents(db: Session = Depends(get_db)) -> list[Incident]:
    return db.query(Incident).options(selectinload(Incident.evidence), selectinload(Incident.actions), selectinload(Incident.timeline)).order_by(Incident.created_at.desc()).all()


@router.get("/{incident_id}", response_model=IncidentRead)
def read_incident(incident_id: str, db: Session = Depends(get_db)) -> Incident:
    try:
        return get_incident(db, incident_id)
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc


@router.post("/{incident_id}/investigate")
def investigate_incident(incident_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    incident = db.query(Incident).filter(Incident.id == incident_id).one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    if incident.status in {"new", "queued", "investigating"} and not incident.actions:
        run_investigation(db, incident)
        db.commit()
    return _analysis_payload(get_incident(db, incident_id))


@router.get("/{incident_id}/report", response_model=dict[str, str])
def incident_report(incident_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        incident = get_incident(db, incident_id)
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc
    return {"report": render_incident_report(incident)}


def _analysis_payload(incident: Incident) -> dict[str, object]:
    action = incident.actions[0] if incident.actions else None
    evidence_ids = [item.id for item in incident.evidence]
    return {
        "id": incident.id,
        "incident_id": incident.id,
        "status": incident.status,
        "service": incident.service,
        "environment": incident.environment,
        "severity": incident.severity,
        "summary": incident.summary,
        "hypotheses": [
            {
                "title": incident.root_cause_candidate or "Mock evidence-backed incident hypothesis",
                "confidence": incident.confidence or 0.75,
                "supporting_evidence_ids": evidence_ids[: max(2, min(len(evidence_ids), 4))],
                "refuting_evidence_ids": [],
                "status": "supported",
            }
        ],
        "recommended_action": None
        if action is None
        else {
            "id": action.id,
            "action_type": action.action_type,
            "target": action.target,
            "risk_level": action.risk_level,
            "requires_approval": action.requires_approval,
            "rationale": action.rationale,
            "payload": action.payload,
            "preconditions": action.preconditions,
            "post_checks": action.post_checks,
            "evidence_ids": action.evidence_ids,
            "policy_decision": action.policy_decision,
            "status": action.status,
        },
    }


@router.post("/{incident_id}/actions/{action_id}/approve")
def approve_incident_action(
    incident_id: str,
    action_id: str,
    payload: ApprovalRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    decision_payload = payload or ApprovalRequest(decision="approve")
    action, incident, report = decide_action(
        db,
        action_id,
        decision="approve",
        actor=decision_payload.actor,
        reason=decision_payload.reason,
    )
    if incident.id != incident_id:
        raise HTTPException(status_code=404, detail="action not found for incident")
    return {"action_id": action.id, "incident_id": incident.id, "status": action.status, "incident_status": incident.status, "report": report}


@router.post("/{incident_id}/actions/{action_id}/reject")
def reject_incident_action(
    incident_id: str,
    action_id: str,
    payload: ApprovalRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    decision_payload = payload or ApprovalRequest(decision="reject")
    action, incident, report = decide_action(
        db,
        action_id,
        decision="reject",
        actor=decision_payload.actor,
        reason=decision_payload.reason,
    )
    if incident.id != incident_id:
        raise HTTPException(status_code=404, detail="action not found for incident")
    return {"action_id": action.id, "incident_id": incident.id, "status": action.status, "incident_status": incident.status, "report": report}


@router.post("/{incident_id}/verify")
def verify_incident(incident_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    incident = get_incident(db, incident_id)
    recovered = incident.status == "resolved"
    return {"incident_id": incident.id, "recovered": recovered, "status": incident.status}
