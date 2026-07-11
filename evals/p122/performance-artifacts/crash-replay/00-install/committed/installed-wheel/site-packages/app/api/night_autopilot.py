from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.incidents import NightAutopilotConfig, NightAutopilotResult
from app.security.dependencies import get_current_principal
from app.services.audit_service import record_audit_event
from app.services.identity_service import Principal
from app.services.night_autopilot import simulate_night_autopilot

router = APIRouter(prefix="/night-autopilot", tags=["night-autopilot"])


@router.post("/simulate", response_model=NightAutopilotResult)
def simulate(config: NightAutopilotConfig, db: Session = Depends(get_db)) -> NightAutopilotResult:
    return simulate_night_autopilot(db, config)


@router.put("/policy")
def update_policy(
    config: NightAutopilotConfig,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    metadata = config.model_dump()
    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        workspace_id=principal.workspace_id,
        actor=principal.email,
        event_type="night_autopilot_policy_updated",
        resource_type="night_autopilot_policy",
        resource_id=f"{principal.tenant_id}:{principal.workspace_id}",
        metadata=metadata,
    )
    db.commit()
    return {
        "tenant_id": principal.tenant_id,
        "workspace_id": principal.workspace_id,
        "actor": principal.email,
        "config": metadata,
    }
