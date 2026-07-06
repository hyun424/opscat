from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Incident
from app.schemas.incidents import IncidentRead, MockAlertRequest
from app.services.incident_service import create_and_investigate

router = APIRouter(prefix="/webhooks/alerts", tags=["mock-alerts"])


@router.post("/mock", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
def receive_mock_alert(payload: MockAlertRequest, db: Session = Depends(get_db)) -> Incident:
    return create_and_investigate(db, payload)
