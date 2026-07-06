from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.workspace import get_workspace_id
from app.db import get_db
from app.models import Incident

router = APIRouter(tags=["health"])


@router.get("/health")
def health(workspace_id: str = Depends(get_workspace_id)) -> dict[str, str]:
    return {"status": "ok", "service": "opscat", "mode": "local-mock", "workspace_id": workspace_id}


@router.get("/status")
def status(
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    counts: dict[str, int] = {}
    rows = db.query(Incident.status).filter(Incident.workspace_id == workspace_id).all()
    for (incident_status,) in rows:
        counts[incident_status] = counts.get(incident_status, 0) + 1
    return {
        "status": "ok",
        "service": "opscat",
        "mode": "local-mock",
        "workspace_id": workspace_id,
        "incident_counts": counts,
        "generated_at": datetime.now(UTC).isoformat(),
        "known_gaps": [
            "authentication and tenant authorization are placeholders",
            "integration tokens are not stored in this mock MVP",
            "real Sentry/GitHub/Slack connectors are out of scope",
        ],
    }
