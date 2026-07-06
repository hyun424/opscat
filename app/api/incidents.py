from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Incident
from app.schemas.incidents import IncidentRead
from app.services.incident_service import get_incident, run_investigation
from app.services.report_service import render_incident_report

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentRead])
def list_incidents(db: Session = Depends(get_db)) -> list[Incident]:
    return (
        db.query(Incident)
        .options(
            selectinload(Incident.evidence),
            selectinload(Incident.actions),
            selectinload(Incident.timeline),
        )
        .order_by(Incident.created_at.desc())
        .all()
    )


@router.get("/{incident_id}", response_model=IncidentRead)
def read_incident(incident_id: str, db: Session = Depends(get_db)) -> Incident:
    try:
        return get_incident(db, incident_id)
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc


@router.post("/{incident_id}/investigate", response_model=IncidentRead)
def investigate_incident(incident_id: str, db: Session = Depends(get_db)) -> Incident:
    incident = db.query(Incident).filter(Incident.id == incident_id).one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    run_investigation(db, incident)
    db.commit()
    return get_incident(db, incident_id)


@router.get("/{incident_id}/report", response_model=dict[str, str])
def incident_report(incident_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        incident = get_incident(db, incident_id)
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="incident not found") from exc
    return {"report": render_incident_report(incident)}
