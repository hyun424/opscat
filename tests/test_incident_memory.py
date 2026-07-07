"""P7-007 deterministic local incident memory."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ActionProposal, Incident
from app.services.incident_memory import build_incident_memory, search_similar_incidents


def _incident(db: Session, *, service: str, environment: str, root: str, action_type: str, action_status: str, incident_status: str = "resolved") -> Incident:
    incident = Incident(
        tenant_id="demo",
        workspace_id="demo",
        alert_fingerprint=f"{service}-{environment}-{root}-{action_status}",
        source="test",
        status=incident_status,
        service=service,
        environment=environment,
        severity="medium",
        alert_payload={"scenario": root.replace(" ", "_")},
        summary=f"{service} {root}",
        root_cause_candidate=root,
        confidence=0.86,
    )
    db.add(incident)
    db.flush()
    db.add(
        ActionProposal(
            incident_id=incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            action_type=action_type,
            target=f"{service}:{environment}",
            environment=environment,
            risk_level="low",
            requires_approval=False,
            rationale="memory fixture",
            payload={"runbook": "queue_backlog"},
            preconditions=["fixture"],
            post_checks=["fixture"],
            evidence_ids=[],
            policy_decision="ALLOW",
            policy_reasons=["fixture"],
            confidence=0.86,
            status=action_status,
        )
    )
    db.commit()
    return incident


def test_incident_memory_returns_similar_success_and_failed_warning(db_session: Session) -> None:
    _incident(db_session, service="worker", environment="staging", root="Worker queue degradation", action_type="mock.execute_restart_worker", action_status="executed")
    _incident(db_session, service="worker", environment="staging", root="Worker queue degradation", action_type="mock.execute_restart_worker", action_status="failed", incident_status="escalated")
    candidate = _incident(db_session, service="worker", environment="staging", root="Worker queue degradation", action_type="mock.create_incident_ticket", action_status="executed")

    memory = build_incident_memory(db_session, tenant_id="demo", workspace_id="demo")
    matches = search_similar_incidents(memory, candidate, action_type="mock.execute_restart_worker")

    assert matches[0].score >= 0.75
    assert any(match.record.outcome == "success" for match in matches)
    failed = [match for match in matches if match.record.outcome == "failed"]
    assert failed
    assert "prior_failed_remediation" in failed[0].warnings
