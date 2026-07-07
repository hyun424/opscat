"""P7-009 failure-mode report contracts."""

from __future__ import annotations

from typing import Any


def test_report_contains_failure_mode_analysis_for_blocked_action() -> None:
    incident = Incident(
        id="inc-p7", service="payment-api", environment="staging", severity="high", status="escalated", confidence=0.42, summary="ambiguous", root_cause_candidate="unknown", alert_payload={}
    )
    incident.actions.append(
        ActionProposal(
            action_type="human.escalate",
            target="payment-api",
            environment="staging",
            risk_level="high",
            requires_approval=True,
            rationale="weak evidence",
            payload={},
            preconditions=[],
            post_checks=[],
            evidence_ids=[],
            policy_decision="ESCALATE",
            policy_reasons=["low confidence", "missing evidence"],
            confidence=0.42,
            status="escalated",
        )
    )


def test_report_includes_failure_mode_analysis_for_low_confidence_escalation(client: Any) -> None:
    report = _create_report(
        client,
        {
            "idempotency_key": "p7-failure-mode-low-confidence",
            "scenario": "low_confidence_ambiguous",
            "environment": "staging",
            "severity": "high",
            "message": "ambiguous signal api_key=plain_secret Bearer raw.jwt.token ops@example.com",
        },
    )

    assert "## Failure Mode Analysis" in report
    assert "Uncertainty:" in report
    assert "Alternate hypotheses:" in report
    assert "Missing evidence:" in report
    assert "Blocked actions:" in report
    assert "Escalation reasons:" in report
    assert "low_confidence" in report
    assert "plain_secret" not in report
    assert "raw.jwt.token" not in report
    assert "ops@example.com" not in report
    assert "[REDACTED]" in report


def test_report_explains_policy_denied_action_failure_modes(client: Any) -> None:
    report = _create_report(
        client,
        {
            "idempotency_key": "p7-failure-mode-denied",
            "scenario": "protected_auth_incident",
            "service": "auth-api",
            "environment": "production",
            "severity": "critical",
        },
    )

    assert "## Failure Mode Analysis" in report
    assert "policy_denied_action" in report
    assert "production.restart_service" in report
    assert "Do not execute denied/prohibited action" in report
