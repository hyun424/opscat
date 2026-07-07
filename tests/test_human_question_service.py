from __future__ import annotations

from app.models import ActionProposal, Incident
from app.services.escalation import build_escalation_payload
from app.services.human_question_service import generate_human_questions

FORBIDDEN_QUESTION_TERMS = ("password", "token", "secret", "credential", "api key")


def _incident(*, service: str = "worker", confidence: float = 0.86, severity: str = "medium") -> Incident:
    return Incident(
        service=service,
        environment="staging",
        severity=severity,
        confidence=confidence,
        root_cause_candidate="Worker queue degradation",
        alert_payload={"scenario": "queue_backlog_worker"},
        summary="queue backlog with worker heartbeat loss",
    )


def test_question_generator_low_confidence_asks_for_decision_relevant_evidence() -> None:
    questions = generate_human_questions(_incident(confidence=0.42), missing_evidence=["deploy_marker"])

    assert questions[0].source_gate == "low_confidence"
    assert "evidence" in questions[0].question.lower()
    assert questions[0].why_it_matters
    assert questions[0].safe_to_ask is True


def test_question_generator_conflicting_evidence_is_specific() -> None:
    questions = generate_human_questions(_incident(), conflicting_evidence=["deploy evidence conflicts with provider outage metrics"])

    assert any(question.source_gate == "conflicting_evidence" for question in questions)
    assert any("conflict" in question.question.lower() for question in questions)


def test_question_generator_protected_domain_requests_human_approval_not_secret() -> None:
    questions = generate_human_questions(_incident(service="payment-api"), policy_reasons=["protected payment service"])

    joined_questions = " ".join(question.question.lower() for question in questions)
    assert "approve" in joined_questions or "safe" in joined_questions
    assert not any(term in joined_questions for term in FORBIDDEN_QUESTION_TERMS)


def test_question_generator_failed_simulation_asks_about_precondition_gap() -> None:
    questions = generate_human_questions(_incident(), simulation={"status": "failed", "precondition_gaps": ["worker target not confirmed"]})

    assert any(question.source_gate == "simulation_failed" for question in questions)
    assert any("worker target not confirmed" in question.why_it_matters for question in questions)


def test_question_generator_never_asks_for_sensitive_values() -> None:
    questions = generate_human_questions(
        _incident(service="connector"),
        policy_reasons=["missing secret token for connector"],
        missing_evidence=["SENTRY_AUTH_TOKEN"],
    )

    joined_questions = " ".join(question.question.lower() for question in questions)
    assert not any(term in joined_questions for term in FORBIDDEN_QUESTION_TERMS)
    assert all(question.safe_to_ask for question in questions)


def test_escalation_payload_includes_human_questions() -> None:
    incident = _incident(confidence=0.41)
    action = ActionProposal(
        incident_id="incident-1",
        tenant_id="demo",
        workspace_id="demo",
        action_type="mock.execute_restart_worker",
        target="worker:staging",
        environment="staging",
        risk_level="low",
        requires_approval=True,
        rationale="test",
        payload={},
        preconditions=[],
        post_checks=[],
        evidence_ids=[],
        policy_decision="REQUIRE_APPROVAL",
        policy_reasons=["confidence below 0.70"],
        confidence=0.41,
        status="proposed",
    )

    payload = build_escalation_payload(incident, trigger="low_confidence", triggers=["low_confidence"], action=action)

    assert payload["human_questions"]
    assert payload["human_questions"][0]["source_gate"] == "low_confidence"
