"""Workflow worker CLI gates for P5 local operations."""

from __future__ import annotations

from typing import Any

from app.models import Incident, WorkflowJob
from scripts.workflow_cli import run_workflow_cli


def test_workflow_cli_reports_stats_and_drains_pending_jobs(client: Any, db_session: Any, capsys: Any) -> None:
    first = client.post("/webhooks/alerts/mock", json={"idempotency_key": "cli-drain-1", "scenario": "payment_bad_deploy"})
    second = client.post("/webhooks/alerts/mock", json={"idempotency_key": "cli-drain-2", "scenario": "worker_queue_backlog"})
    assert first.status_code == 202
    assert second.status_code == 202

    assert run_workflow_cli(["stats"], db=db_session) == 0
    stats_output = capsys.readouterr().out
    assert "pending=2" in stats_output
    assert "queue=incident.workflow" in stats_output

    assert run_workflow_cli(["drain", "--limit", "2", "--worker-id", "cli-test"], db=db_session) == 0
    drain_output = capsys.readouterr().out
    assert "processed=2" in drain_output
    assert db_session.query(WorkflowJob).filter(WorkflowJob.status == "completed").count() == 2
    assert all(incident.actions for incident in db_session.query(Incident).all())


def test_workflow_cli_dead_letters_failed_jobs(db_session: Any, capsys: Any) -> None:
    job = WorkflowJob(
        tenant_id="tenant-a",
        workspace_id="alpha",
        queue_name="incident.workflow",
        job_type="incident.investigate",
        dedupe_key="cli-dead-letter-1",
        incident_id="missing-incident",
        status="failed",
        payload={"reason": "missing incident"},
        max_attempts=1,
        last_error="missing incident",
    )
    db_session.add(job)
    db_session.flush()

    assert run_workflow_cli(["dead-letter-failed", "--reason", "missing incident in fixture"], db=db_session) == 0
    output = capsys.readouterr().out
    assert "dead_lettered=1" in output
    db_session.refresh(job)
    assert job.status == "dead_letter"
    assert job.last_error == "missing incident in fixture"
