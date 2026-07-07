from __future__ import annotations

from typing import Any

from app.models import AuditEvent, Incident, WorkflowJob
from app.services.workflow_service import process_next_workflow_job


def test_mock_alert_defaults_to_queued_workflow_job(client: Any, db_session: Any) -> None:
    response = client.post(
        "/webhooks/alerts/mock",
        json={"idempotency_key": "queue-red-1", "scenario": "payment_bad_deploy", "message": "queued first"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["actions"] == []
    job = db_session.query(WorkflowJob).one()
    assert job.status == "pending"
    assert job.queue_name == "incident.workflow"
    assert job.incident_id == body["id"]
    assert job.dedupe_key.endswith(body["alert_fingerprint"])
    assert [event.event_type for event in db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()] == [
        "alert_received",
        "workflow_job_enqueued",
    ]


def test_local_worker_processes_queued_incident_and_records_job_lifecycle(client: Any, db_session: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock",
        json={"idempotency_key": "queue-red-2", "scenario": "payment_bad_deploy"},
    )
    assert created.status_code == 202
    incident_id = created.json()["id"]

    job = process_next_workflow_job(db_session, queue_name="incident.workflow", worker_id="unit-worker")
    db_session.commit()

    assert job is not None
    refreshed_job = db_session.query(WorkflowJob).filter(WorkflowJob.id == job.id).one()
    assert refreshed_job.status == "completed"
    assert refreshed_job.attempt_count == 1
    incident = db_session.query(Incident).filter(Incident.id == incident_id).one()
    assert incident.status in {"waiting_approval", "escalated", "executing"}
    assert incident.actions
    timeline_types = [event.event_type for event in incident.timeline]
    assert "workflow_job_started" in timeline_types
    assert "workflow_job_completed" in timeline_types
    audit_types = [event.event_type for event in db_session.query(AuditEvent).all()]
    assert "workflow_job_started" in audit_types
    assert "workflow_job_completed" in audit_types


def test_duplicate_alert_reuses_incident_and_active_workflow_job(client: Any, db_session: Any) -> None:
    payload = {"idempotency_key": "queue-red-duplicate", "scenario": "payment_bad_deploy"}
    first = client.post("/webhooks/alerts/mock", json=payload)
    second = client.post("/webhooks/alerts/mock", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert db_session.query(Incident).count() == 1
    assert db_session.query(WorkflowJob).count() == 1
