from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.incidents import _analysis_response
from app.api.workspace import get_workspace_id
from app.db import get_db
from app.schemas.incidents import MockAlertRequest
from app.services.incident_service import create_and_investigate

router = APIRouter(prefix="/webhooks/alerts", tags=["mock-alerts"])


@router.post("/mock", response_model=None, status_code=status.HTTP_201_CREATED)
def receive_mock_alert(
    payload: MockAlertRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload.workspace_id = workspace_id if payload.workspace_id == "demo" else payload.workspace_id
    incident = create_and_investigate(db, payload)
    return _analysis_response(incident)
