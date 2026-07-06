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


def create_router(action_service: ActionService | None = None):
    if APIRouter is None:  # pragma: no cover
        raise RuntimeError("FastAPI is not installed; install app dependencies to enable approval routes.")
    svc = action_service or service
    router = APIRouter(prefix="/approvals", tags=["approvals"])


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
