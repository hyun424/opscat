"""Night Autopilot policy editor and morning-report contracts for P5."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.schemas.incidents import NightAutopilotConfig
from app.services.night_autopilot import simulate_night_autopilot
from tests.test_operator_dashboard import ALPHA_HEADERS, BETA_HEADERS


def test_night_autopilot_allows_low_risk_quiet_hours_action_with_morning_counts(db_session: Session) -> None:
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
    assert result.escalations == []
    assert "Detected: 1" in result.morning_report
    assert "Resolved: 1" in result.morning_report
    assert "Escalated: 0" in result.morning_report
    assert "Blocked actions: 0" in result.morning_report
    assert "Verification outcomes" in result.morning_report
    assert "Follow-ups" in result.morning_report


def test_night_autopilot_escalates_production_or_high_risk_paths(db_session: Session) -> None:
    production = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(
            service="worker",
            environment="production",
            allowed_services=["worker"],
            allowed_environments=["production"],
            max_automatic_risk="low",
        ),
    )

    assert production.actions_taken == []
    assert production.escalations
    assert production.escalations[0]["wake_human"] is True
    assert "Escalated: 1" in production.morning_report
    assert "Blocked actions: 1" in production.morning_report

    high_risk = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(
            service="payment-api",
            environment="staging",
            action_type="mock.create_rollback_pr",
            target="payment-api:staging",
            allowed_services=["payment-api"],
            allowed_environments=["staging"],
            max_automatic_risk="low",
        ),
    )

    assert high_risk.actions_taken == []
    assert high_risk.escalations
    assert high_risk.escalations[0]["wake_human"] is True
    assert "Blocked actions: 1" in high_risk.morning_report


def test_night_autopilot_policy_update_is_scoped_and_audited(client: Any, db_session: Session) -> None:
    response = client.put(
        "/night-autopilot/policy",
        headers=ALPHA_HEADERS,
        json={
            "quiet_start": "23:00",
            "quiet_end": "06:30",
            "timezone": "Asia/Seoul",
            "max_automatic_risk": "low",
            "max_attempts_per_incident": 1,
            "allowed_services": ["worker"],
            "allowed_environments": ["staging"],
            "escalation_contacts": ["primary-oncall"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant-a"
    assert body["workspace_id"] == "alpha"
    assert body["config"]["allowed_services"] == ["worker"]
    assert body["config"]["quiet_start"] == "23:00"

    events = db_session.query(AuditEvent).filter(AuditEvent.event_type == "night_autopilot_policy_updated").all()
    assert len(events) == 1
    assert events[0].tenant_id == "tenant-a"
    assert events[0].workspace_id == "alpha"
    assert events[0].actor == ALPHA_HEADERS["X-OpsCat-Actor"]
    assert events[0].event_metadata["allowed_services"] == ["worker"]
    assert "primary-oncall" in events[0].event_metadata["escalation_contacts"]

    beta_page = client.put(
        "/night-autopilot/policy",
        headers=BETA_HEADERS,
        json={"allowed_services": ["worker"], "allowed_environments": ["staging"]},
    )
    assert beta_page.status_code == 200
    beta_events = db_session.query(AuditEvent).filter(AuditEvent.workspace_id == "beta").all()
    assert beta_events, "policy edits must be scoped to the caller workspace"
