from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.incidents import ApprovalRequest, ApprovalResponse
from app.services.incident_service import decide_action

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{action_id}", response_model=ApprovalResponse)
def decide(action_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)) -> ApprovalResponse:
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
    return ApprovalResponse(action=action, incident=incident, report=report)
