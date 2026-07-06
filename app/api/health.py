from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.workspace import get_workspace_id
from app.db import get_db
from app.models import Incident
from app.security.dependencies import get_current_principal
from app.services.identity_service import Principal

router = APIRouter(tags=["health"])


@router.get("/health")
def health(workspace_id: str = Depends(get_workspace_id)) -> dict[str, str]:
    return {"status": "ok", "service": "opscat", "mode": "local-mock", "workspace_id": workspace_id}


@router.get("/status")
def status(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    counts: dict[str, int] = {}
    rows = db.query(Incident.status).filter(Incident.tenant_id == principal.tenant_id, Incident.workspace_id == principal.workspace_id).all()
    for (incident_status,) in rows:
        counts[incident_status] = counts.get(incident_status, 0) + 1
    return {
        "status": "ok",
        "service": "opscat",
        "mode": "local-mock",
        "tenant_id": principal.tenant_id,
        "workspace_id": principal.workspace_id,
        "actor": principal.email,
        "incident_counts": counts,
        "generated_at": datetime.now(UTC).isoformat(),
        "known_gaps": [
            "local-header authentication is a placeholder; service-layer tenant authorization is enforced for MVP resources",
            "integration tokens are not stored in this mock MVP",
            "real Sentry/GitHub/Slack connectors are out of scope",
        ],
    }
