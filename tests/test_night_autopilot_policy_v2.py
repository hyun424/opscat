"""P7-008 Night Autopilot v2 reliability gates."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ActionProposal, Incident
from app.schemas.incidents import NightAutopilotConfig
from app.services.night_autopilot import simulate_night_autopilot


def _prior_worker_action(db: Session, *, status: str) -> None:
    incident = Incident(
        tenant_id="demo",
        workspace_id="demo",
        alert_fingerprint=f"prior-worker-{status}",
        source="test",
        status="escalated" if status == "failed" else "resolved",
        service="worker",
        environment="staging",
        severity="medium",
        alert_payload={"scenario": "worker_queue_backlog"},
        summary="Prior worker queue degradation",
        root_cause_candidate="Worker queue degradation",
        confidence=0.88,
    )
    db.add(incident)
    db.flush()
    db.add(
        ActionProposal(
            incident_id=incident.id,
            tenant_id="demo",
            workspace_id="demo",
            action_type="mock.execute_restart_worker",
            target="worker:staging",
            environment="staging",
            risk_level="low",
            requires_approval=False,
            rationale="prior memory fixture",
            payload={"worker_pool": "default"},
            preconditions=["worker_target_confirmed"],
            post_checks=["mock.verify_recovery"],
            evidence_ids=[],
            policy_decision="ALLOW",
            policy_reasons=["fixture"],
            confidence=0.88,
            status=status,
        )
    )
    db.commit()


def test_night_autopilot_v2_allows_reversible_action_with_successful_memory_and_simulation(db_session: Session) -> None:
    _prior_worker_action(db_session, status="executed")

    result = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(
            allowed_services=["worker"],
            allowed_environments=["staging"],
            max_automatic_risk="low",
            max_attempts_per_incident=1,
        ),
    )

    assert result.actions_taken
    action = result.actions_taken[0]
    assert action["v2_gates"]["simulation"]["ok"] is True
    assert action["v2_gates"]["memory"]["failed_remediation_warning"] is False
    assert "Night Autopilot v2 gates: passed" in result.morning_report
    assert "similar_incidents" in result.morning_report


def test_night_autopilot_v2_blocks_prior_failed_remediation(db_session: Session) -> None:
    _prior_worker_action(db_session, status="failed")

    result = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(
            allowed_services=["worker"],
            allowed_environments=["staging"],
            max_automatic_risk="low",
            max_attempts_per_incident=1,
        ),
    )

    assert result.actions_taken == []
    assert result.escalations
    assert "memory_failed_remediation" in result.escalations[0]["triggers"]
    assert "Night Autopilot v2 gates: blocked" in result.morning_report


def test_night_autopilot_v2_blocks_unbounded_or_failed_simulation(db_session: Session) -> None:
    unbounded = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(
            service="worker",
            environment="staging",
            action_type="shell.execute",
            allowed_services=["worker"],
            allowed_environments=["staging"],
        ),
    )

    assert unbounded.actions_taken == []
    assert unbounded.escalations
    assert "simulation_failed" in unbounded.escalations[0]["triggers"] or "policy_escalated_action" in unbounded.escalations[0]["triggers"]
    assert "Night Autopilot v2 gates: blocked" in unbounded.morning_report
