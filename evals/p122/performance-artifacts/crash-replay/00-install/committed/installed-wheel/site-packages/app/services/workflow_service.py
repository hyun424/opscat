"""Durable local workflow queue boundary for OpsCat."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Incident, WorkflowJob
from app.services.audit_service import record_audit_event
from app.services.redaction import redact_value
from app.services.timeline_service import add_timeline_event


def enqueue_incident_workflow(db: Session, incident: Incident, *, payload: dict[str, Any] | None = None) -> WorkflowJob:
    dedupe_key = f"incident.workflow:{incident.alert_fingerprint}"
    existing = (
        db.query(WorkflowJob)
        .filter(
            WorkflowJob.tenant_id == incident.tenant_id,
            WorkflowJob.workspace_id == incident.workspace_id,
            WorkflowJob.queue_name == "incident.workflow",
            WorkflowJob.dedupe_key == dedupe_key,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    job = WorkflowJob(
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        queue_name="incident.workflow",
        job_type="incident.investigate",
        dedupe_key=dedupe_key,
        incident_id=incident.id,
        status="pending",
        payload=dict(redact_value(payload or {"incident_id": incident.id})),
    )
    db.add(job)
    db.flush()
    metadata = {"job_id": job.id, "queue_name": job.queue_name, "dedupe_key": job.dedupe_key, "incident_id": incident.id}
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="workflow",
        event_type="workflow_job_enqueued",
        content="Incident workflow job enqueued.",
        metadata=metadata,
    )
    record_audit_event(
        db,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="workflow",
        event_type="workflow_job_enqueued",
        resource_type="workflow_job",
        resource_id=job.id,
        metadata=metadata,
    )
    return job


def process_next_workflow_job(db: Session, *, queue_name: str = "incident.workflow", worker_id: str = "local-worker") -> WorkflowJob | None:
    from app.services.incident_service import get_incident, run_investigation

    job = db.query(WorkflowJob).filter(WorkflowJob.queue_name == queue_name, WorkflowJob.status == "pending").order_by(WorkflowJob.created_at.asc()).first()
    if job is None:
        return None
    now = datetime.now(UTC)
    job.status = "running"
    job.lease_owner = worker_id
    job.attempt_count += 1
    job.started_at = now
    job.updated_at = now
    incident = get_incident(db, job.incident_id) if job.incident_id else None
    if incident is None:
        job.status = "failed"
        job.last_error = "missing incident"
        return job

    started_metadata = {"job_id": job.id, "queue_name": job.queue_name, "attempt_count": job.attempt_count, "worker_id": worker_id}
    add_timeline_event(
        db,
        incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="workflow",
        event_type="workflow_job_started",
        content=f"Workflow job {job.id} started by {worker_id}.",
        metadata=started_metadata,
    )
    record_audit_event(
        db,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        actor="workflow",
        event_type="workflow_job_started",
        resource_type="workflow_job",
        resource_id=job.id,
        metadata=started_metadata,
    )
    try:
        if not incident.actions and incident.status in {"new", "queued", "investigating"}:
            run_investigation(db, incident)
        job.status = "completed"
        job.completed_at = datetime.now(UTC)
        job.updated_at = job.completed_at
        completed_metadata = {"job_id": job.id, "queue_name": job.queue_name, "attempt_count": job.attempt_count, "incident_status": incident.status}
        add_timeline_event(
            db,
            incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="workflow",
            event_type="workflow_job_completed",
            content=f"Workflow job {job.id} completed.",
            metadata=completed_metadata,
        )
        record_audit_event(
            db,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="workflow",
            event_type="workflow_job_completed",
            resource_type="workflow_job",
            resource_id=job.id,
            metadata=completed_metadata,
        )
    except Exception as exc:
        job.status = "failed" if job.attempt_count >= job.max_attempts else "pending"
        job.last_error = str(exc)
        job.updated_at = datetime.now(UTC)
        record_audit_event(
            db,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="workflow",
            event_type="workflow_job_failed",
            resource_type="workflow_job",
            resource_id=job.id,
            metadata={"job_id": job.id, "error": str(exc), "retry_eligible": job.status == "pending"},
        )
        raise
    finally:
        db.add(job)
        db.flush()
    return job
