from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.workspace import get_workspace_id
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Incident
from app.security.dependencies import get_current_principal
from app.services.identity_service import Principal
from app.services.observability import build_metrics_snapshot
from app.services.p131_always_on_monitor import evaluate_watchdog, monitor_status_snapshot

router = APIRouter(tags=["health"])


@router.get("/health")
def health(workspace_id: str = Depends(get_workspace_id)) -> dict[str, str]:
    return {"status": "ok", "service": "opscat", "mode": "local-mock", "workspace_id": workspace_id}


@router.get("/monitor/health")
def monitor_health(response: Response, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Expose the independent monitor heartbeat without requiring credentials."""

    result = evaluate_watchdog(
        settings.monitor_state_path,
        now=datetime.now(UTC),
        heartbeat_timeout_seconds=settings.monitor_heartbeat_timeout_seconds,
    )
    if result["healthy"] is not True:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
    return _public_monitor_status(result)


@router.get("/monitor/readiness")
def monitor_readiness(response: Response, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Expose heartbeat, canary, and telemetry-freshness readiness."""

    result = monitor_status_snapshot(
        settings.monitor_state_path,
        now=datetime.now(UTC),
        heartbeat_timeout_seconds=settings.monitor_heartbeat_timeout_seconds,
        data_stale_after_seconds=settings.monitor_data_stale_after_seconds,
    )
    if result["ready"] is not True:
        response.status_code = http_status.HTTP_503_SERVICE_UNAVAILABLE
    return _public_monitor_status(result)


def _public_monitor_status(result: dict[str, object]) -> dict[str, object]:
    """Remove internal runtime identity and integrity material from public GETs."""

    return {key: value for key, value in result.items() if key not in {"runtime_id", "state_hash"}}


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


@router.get("/metrics")
def metrics(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return build_metrics_snapshot(db, principal)
