"""Self-observability snapshots for the local OpsCat agent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import ActionProposal, AuditEvent, ConnectorCallRecord, Incident, WorkflowJob
from app.services.identity_service import Principal

# Keep this in sync with scripts/run_connector_evals.py. It is intentionally a
# static local evidence count to avoid importing release-runner scripts from the
# FastAPI app process.
CONNECTOR_EVAL_SCENARIOS_REGISTERED = 11


def build_metrics_snapshot(db: Session, principal: Principal) -> dict[str, Any]:
    """Return scoped, secret-free numeric metrics for the agent itself."""
    tenant_id = principal.tenant_id
    workspace_id = principal.workspace_id
    incident_status_counts = _count_by_status(db, Incident, tenant_id=tenant_id, workspace_id=workspace_id)
    workflow_status_counts = _count_by_status(db, WorkflowJob, tenant_id=tenant_id, workspace_id=workspace_id)
    action_status_counts = _count_by_status(db, ActionProposal, tenant_id=tenant_id, workspace_id=workspace_id)
    connector_status_counts = _count_by_status(db, ConnectorCallRecord, tenant_id=tenant_id, workspace_id=workspace_id)
    escalation_count = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.workspace_id == workspace_id,
            AuditEvent.event_type == "human_escalation_required",
        )
        .count()
    )
    return {
        "status": "ok",
        "service": "opscat",
        "mode": "local-mock",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "incidents": {
            "created": sum(incident_status_counts.values()),
            "by_status": incident_status_counts,
        },
        "workflow_jobs": {
            "created": sum(workflow_status_counts.values()),
            "processed": sum(workflow_status_counts.get(status, 0) for status in ("completed", "failed", "dead_letter")),
            "by_status": workflow_status_counts,
        },
        "actions": {
            "proposed": sum(action_status_counts.values()),
            "executed": action_status_counts.get("executed", 0),
            "blocked": sum(action_status_counts.get(status, 0) for status in ("denied", "rejected", "escalated", "failed")),
            "waiting_approval": action_status_counts.get("proposed", 0),
            "by_status": action_status_counts,
        },
        "connector_failures": connector_status_counts.get("failed", 0),
        "connector_calls": {
            "created": sum(connector_status_counts.values()),
            "by_status": connector_status_counts,
        },
        "escalations": escalation_count,
        "evals": {
            "connector_scenarios_registered": CONNECTOR_EVAL_SCENARIOS_REGISTERED,
            "last_full_verify_pass": None,
        },
    }


def _count_by_status(db: Session, model: Any, *, tenant_id: str, workspace_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = db.query(model.status).filter(model.tenant_id == tenant_id, model.workspace_id == workspace_id).all()
    for (status,) in rows:
        counts[str(status)] = counts.get(str(status), 0) + 1
    return counts
