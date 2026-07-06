from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.incidents import _analysis_response
from app.db import get_db
from app.schemas.incidents import MockAlertRequest
from app.security.dependencies import get_current_principal
from app.services.authorization import AuthorizationError, require_signal_scope
from app.services.identity_service import Principal
from app.services.incident_service import create_and_investigate

router = APIRouter(prefix="/webhooks/alerts", tags=["mock-alerts"])


@router.post("/mock", response_model=None, status_code=status.HTTP_201_CREATED)
def receive_mock_alert(
    payload: MockAlertRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        require_signal_scope(principal, tenant_id=payload.tenant_id, workspace_id=payload.workspace_id)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail={"message": str(exc), "workspace_id": exc.workspace_id}) from exc
    payload.tenant_id = principal.tenant_id
    payload.workspace_id = principal.workspace_id
    incident = create_and_investigate(db, payload)
    return _analysis_response(incident)
