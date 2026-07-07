from __future__ import annotations

from app.models import ActionProposal, Incident
from app.services.report_service import render_incident_report


def test_report_contains_failure_mode_analysis_for_blocked_action() -> None:
    incident = Incident(id="inc-p7", service="payment-api", environment="staging", severity="high", status="escalated", confidence=0.42, summary="ambiguous", root_cause_candidate="unknown", alert_payload={})
    incident.actions.append(ActionProposal(action_type="human.escalate", target="payment-api", environment="staging", risk_level="high", requires_approval=True, rationale="weak evidence", payload={}, preconditions=[], post_checks=[], evidence_ids=[], policy_decision="ESCALATE", policy_reasons=["low confidence", "missing evidence"], confidence=0.42, status="escalated"))

    report = render_incident_report(incident)

    assert "## Failure Mode Analysis" in report
    assert "low confidence" in report
    assert "missing evidence" in report
