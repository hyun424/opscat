from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.action import ActionRequest
from app.schemas.incidents import ActionRead, ApprovalRequest, ApprovalResponse, IncidentRead
from app.services.action_service import ActionService
from app.services.incident_service import decide_action
from app.services.policy_engine import PolicyContext, default_capabilities


class ApprovalProposalPayload(BaseModel):
    action_type: str
    target: str
    environment: str = "local"
    incident_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class ApprovalDecisionPayload(BaseModel):
    actor: str = "human"
    reason: str = "approved"


service = ActionService()
router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("")
def propose_action(payload: ApprovalProposalPayload) -> dict[str, Any]:
    request = ActionRequest(
        action_type=payload.action_type,
        target=payload.target,
        environment=payload.environment,
        incident_id=payload.incident_id,
        payload=payload.payload,
    )
    context = PolicyContext(
        capabilities=default_capabilities(payload.capabilities),
        environment=payload.environment,
    )
    record = service.propose(request, context)
    return service.serialize_record(record)


@router.post("/{action_id}", response_model=ApprovalResponse)
def decide_persisted_action(
    action_id: str,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    try:
        action, incident, report = decide_action(
            db,
            action_id,
            decision=payload.decision,
            actor=payload.actor,
            reason=payload.reason,
        )
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="action not found or invalid") from exc
    return ApprovalResponse(
        action=ActionRead.model_validate(action),
        incident=IncidentRead.model_validate(incident),
        report=report,
    )


@router.post("/{approval_id}/approve")
def approve_action(approval_id: str, payload: ApprovalDecisionPayload) -> dict[str, Any]:
    try:
        record = service.approve(approval_id, payload.actor, payload.reason)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.serialize_record(record)


@router.post("/{approval_id}/reject")
def reject_action(approval_id: str, payload: ApprovalDecisionPayload) -> dict[str, Any]:
    try:
        record = service.reject(approval_id, payload.actor, payload.reason)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.serialize_record(record)


@router.post("/{approval_id}/execute")
def execute_action(approval_id: str) -> dict[str, Any]:
    try:
        result = service.execute(approval_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "action_type": result.action_type,
        "target": result.target,
        "status": result.status,
        "message": result.message,
        "output": dict(result.output),
        "verification": dict(result.verification),
    }
