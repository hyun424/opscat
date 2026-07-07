from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Incident
from app.schemas.incidents import ActionRead, ApprovalRequest, ApprovalResponse, IncidentRead
from app.security.dependencies import get_current_principal
from app.services.authorization import AuthorizationError
from app.services.decision_trace_service import build_decision_trace, render_trace_markdown
from app.services.identity_service import Principal
from app.services.incident_service import decide_action, get_incident, run_investigation
from app.services.report_service import render_incident_report
from app.services.war_room_service import build_war_room

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentRead])
def list_incidents(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> list[Incident]:
    return (
        db.query(Incident)
        .options(selectinload(Incident.evidence), selectinload(Incident.actions), selectinload(Incident.timeline))
        .filter(Incident.tenant_id == principal.tenant_id, Incident.workspace_id == principal.workspace_id)
        .order_by(Incident.created_at.desc())
        .all()
    )


@router.get("/{incident_id}", response_model=IncidentRead)
def read_incident(
    incident_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Incident:
    try:
        return get_incident(db, incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=404, detail={"message": "incident not found", "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc


@router.post("/{incident_id}/investigate", response_model=dict[str, Any])
def investigate_incident(
    incident_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    incident = db.query(Incident).filter(Incident.id == incident_id).one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        get_incident(db, incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail={"message": str(exc), "workspace_id": exc.workspace_id}) from exc
    if not incident.actions:
        run_investigation(db, incident)
        db.commit()
    return _analysis_response(get_incident(db, incident_id))


@router.get("/{incident_id}/war-room", response_model=dict[str, Any])
def incident_war_room(
    incident_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        incident = get_incident(db, incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=404, detail={"message": "incident not found", "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc
    return {"war_room": build_war_room(incident)}


@router.get("/{incident_id}/report", response_model=dict[str, str])
def incident_report(
    incident_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        incident = get_incident(db, incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail={"message": str(exc), "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc
    return {"report": render_incident_report(incident)}


@router.get("/{incident_id}/decision-trace", response_model=dict[str, list[dict[str, Any]]])
def incident_decision_trace(
    incident_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    try:
        incident = get_incident(db, incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=404, detail={"message": "incident not found", "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc
    return {"decision_trace": [entry.to_dict() for entry in build_decision_trace(incident)]}


@router.get("/{incident_id}/trace", response_model=dict[str, Any])
def incident_trace_legacy(
    incident_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        incident = get_incident(db, incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=404, detail={"message": "incident not found", "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc
    entries = [entry.to_dict() for entry in build_decision_trace(incident)]
    return {"decision_trace": entries, "markdown": render_trace_markdown(incident)}


@router.post(
    "/{incident_id}/actions/{action_id}/approve",
    response_model=ApprovalResponse,
)
def approve_incident_action_alias(
    incident_id: str,
    action_id: str,
    payload: ApprovalRequest | None = None,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    return _decide_incident_action(incident_id, action_id, payload or ApprovalRequest(decision="approve"), db, principal)


@router.post(
    "/{incident_id}/actions/{action_id}/reject",
    response_model=ApprovalResponse,
)
def reject_incident_action_alias(
    incident_id: str,
    action_id: str,
    payload: ApprovalRequest | None = None,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    request = payload or ApprovalRequest(decision="reject")
    if request.decision != "reject":
        request = ApprovalRequest(decision="reject", actor=request.actor, reason=request.reason)
    return _decide_incident_action(incident_id, action_id, request, db, principal)


@router.post("/{incident_id}/verify", response_model=IncidentRead)
def verify_incident_alias(
    incident_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Incident:
    # Verification runs during mock execution in the MVP; this endpoint returns
    # the current auditable incident state for contract compatibility.
    try:
        return get_incident(db, incident_id, principal=principal)
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc


def _decide_incident_action(
    incident_id: str,
    action_id: str,
    payload: ApprovalRequest,
    db: Session,
    principal: Principal,
) -> ApprovalResponse:
    try:
        action, incident, report = decide_action(
            db,
            action_id,
            decision=payload.decision,
            actor=payload.actor,
            reason=payload.reason,
            principal=principal,
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail={"message": str(exc), "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="action not found or invalid") from exc
    if incident.id != incident_id:
        raise HTTPException(status_code=404, detail="action does not belong to incident")
    return ApprovalResponse(
        action=ActionRead.model_validate(action),
        incident=IncidentRead.model_validate(incident),
        report=report,
    )


def _analysis_response(incident: Incident) -> dict[str, Any]:
    body = IncidentRead.model_validate(incident).model_dump(mode="json")
    evidence_ids = [item.id for item in incident.evidence]
    action = incident.actions[0] if incident.actions else None
    body["hypotheses"] = [
        {
            "title": incident.root_cause_candidate or "Recent deploy regression",
            "confidence": incident.confidence or 0.0,
            "supporting_evidence_ids": evidence_ids[: max(2, min(len(evidence_ids), 4))],
            "refuting_evidence_ids": [],
            "status": "supported" if evidence_ids else "unknown",
        }
    ]
    if action is not None:
        body["recommended_action"] = {
            "action_type": action.action_type,
            "target": action.target,
            "risk_level": action.risk_level,
            "requires_approval": action.requires_approval,
            "rationale": action.rationale,
            "payload": action.payload,
            "preconditions": action.preconditions,
            "post_checks": action.post_checks,
            "evidence_ids": action.evidence_ids,
        }
    return body
