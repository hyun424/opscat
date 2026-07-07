from app.models import Evidence, Incident
from app.schemas.agent import AgentAnalysis, Hypothesis, RecommendedAction


def analyze_incident(incident: Incident, evidence: list[Evidence]) -> AgentAnalysis:
    evidence_ids = [item.id for item in evidence]
    scenario = str(incident.alert_payload.get("scenario", "payment_api_deploy_regression"))

    if scenario in {"low_confidence_ambiguous", "conflicting_evidence_payment", "critical_unknown_multi_service"}:
        return _human_escalation_analysis(
            incident,
            evidence_ids,
            title="Ambiguous multi-system symptom with low confidence",
            confidence=0.42,
            reason="Confidence is below the human-on-exception threshold; wake a human with collected evidence.",
        )
    if scenario in {"missing_runbook_context", "unknown_service_5xx"}:
        return _human_escalation_analysis(
            incident,
            evidence_ids,
            title="No matching runbook or trusted context for affected service",
            confidence=0.61,
            reason="No matching runbook/context exists for this non-trivial incident; escalate instead of guessing.",
        )
    if scenario in {"protected_auth_incident", "auth_login_spike", "security_signal", "data_store_integrity"} or incident.service in {"auth-api", "security", "data-store"}:
        return _protected_domain_analysis(incident, evidence_ids)
    if scenario in {"worker_queue_backlog", "worker_poison_message", "worker_heartbeat_loss"} or incident.service == "worker":
        return _worker_queue_analysis(incident, evidence_ids)
    if scenario in {"external_api_timeout", "external_provider_rate_limit", "checkout_dependency_degraded"}:
        return _external_api_timeout_analysis(incident, evidence_ids)
    if scenario in {"duplicate_alert_storm", "stale_alert_after_recovery", "false_positive_metric_blip"}:
        return _duplicate_alert_storm_analysis(incident, evidence_ids)
    return _payment_deploy_analysis(incident, evidence_ids, force_verification_failure=scenario == "verification_failure")


def _human_escalation_analysis(
    incident: Incident,
    evidence_ids: list[str],
    *,
    title: str,
    confidence: float,
    reason: str,
) -> AgentAnalysis:
    action = RecommendedAction(
        action_type="human.escalate",
        target=f"{incident.service}:{incident.environment}",
        risk_level="high",
        requires_approval=True,
        rationale=reason,
        payload={"wake_human": True, "reason": reason},
        preconditions=["include collected evidence", "explain uncertainty"],
        post_checks=["human acknowledged escalation"],
        evidence_ids=evidence_ids[: max(2, min(len(evidence_ids), 4))],
    )
    hypotheses = [
        Hypothesis(
            title=title,
            confidence=confidence,
            supporting_evidence_ids=evidence_ids[: max(2, min(len(evidence_ids), 4))],
            status="unknown",
        )
    ]
    return _analysis(incident, hypotheses, action)


def _protected_domain_analysis(incident: Incident, evidence_ids: list[str]) -> AgentAnalysis:
    action = RecommendedAction(
        action_type="production.restart_service",
        target=f"{incident.service}:{incident.environment}",
        risk_level="prohibited",
        requires_approval=True,
        rationale="Protected auth/security/data domain requires human authority; production restart is prohibited in the MVP.",
        payload={"protected_domain": incident.service, "wake_human": True},
        preconditions=["human incident commander assigned", "customer impact understood"],
        post_checks=["human approved safe next action"],
        evidence_ids=evidence_ids[: max(2, min(len(evidence_ids), 4))],
    )
    hypotheses = [
        Hypothesis(
            title="Protected domain incident requires human judgment",
            confidence=0.78,
            supporting_evidence_ids=evidence_ids[: max(2, min(len(evidence_ids), 4))],
            status="unknown",
        )
    ]
    return _analysis(incident, hypotheses, action)


def _worker_queue_analysis(incident: Incident, evidence_ids: list[str]) -> AgentAnalysis:
    action = RecommendedAction(
        action_type="mock.execute_restart_worker",
        target=f"{incident.service}:{incident.environment}",
        risk_level="low",
        requires_approval=True,
        rationale="Runbook marks non-production worker restart reversible and prior incident recovered after restart.",
        payload={"worker_pool": "default", "mode": "mock_restart"},
        preconditions=["runbook marks restart reversible", "environment is not production"],
        post_checks=["worker heartbeat is healthy", "queue latency decreases"],
        evidence_ids=evidence_ids[:3],
    )
    hypotheses = [
        Hypothesis(
            title="Queue worker degradation after broker maintenance",
            confidence=0.82,
            supporting_evidence_ids=evidence_ids[:3],
            status="supported",
        ),
        Hypothesis(
            title="Application deploy regression",
            confidence=0.28,
            supporting_evidence_ids=evidence_ids[1:2],
            refuting_evidence_ids=evidence_ids[2:3],
            status="weak",
        ),
    ]
    return _analysis(incident, hypotheses, action)


def _external_api_timeout_analysis(incident: Incident, evidence_ids: list[str]) -> AgentAnalysis:
    action = RecommendedAction(
        action_type="mock.create_incident_ticket",
        target=f"{incident.service}:{incident.environment}",
        risk_level="low",
        requires_approval=True,
        rationale="Evidence points to a sanitized upstream dependency timeout; open a local mock vendor-tracking ticket rather than mutating production.",
        payload={"dependency": "payment-processor", "mode": "mock_ticket"},
        preconditions=["upstream timeout evidence cited", "no deploy rollback target identified"],
        post_checks=["ticket_id_recorded", "error budget monitored"],
        evidence_ids=evidence_ids[:3],
    )
    hypotheses = [
        Hypothesis(
            title="External payment processor timeout is degrading checkout",
            confidence=0.84,
            supporting_evidence_ids=evidence_ids[:3],
            status="supported",
        ),
        Hypothesis(
            title="Recent app deploy regression",
            confidence=0.24,
            supporting_evidence_ids=evidence_ids[1:2],
            refuting_evidence_ids=evidence_ids[2:3],
            status="weak",
        ),
    ]
    return _analysis(incident, hypotheses, action)


def _duplicate_alert_storm_analysis(incident: Incident, evidence_ids: list[str]) -> AgentAnalysis:
    action = RecommendedAction(
        action_type="timeline.add_note",
        target=f"{incident.service}:{incident.environment}",
        risk_level="low",
        requires_approval=False,
        rationale="Evidence indicates duplicate alerts for a recovered condition; append an audit note and suppress escalation in the mock workflow.",
        payload={"classification": "false_positive_duplicate", "mode": "mock_note"},
        preconditions=["duplicate fingerprint evidence present", "no active error spike remains"],
        post_checks=["timeline_contains_false_positive_note"],
        evidence_ids=evidence_ids[:3],
    )
    hypotheses = [
        Hypothesis(
            title="False positive duplicate alert storm after recovery",
            confidence=0.88,
            supporting_evidence_ids=evidence_ids[:3],
            status="supported",
        ),
        Hypothesis(
            title="New production regression",
            confidence=0.18,
            supporting_evidence_ids=evidence_ids[:1],
            refuting_evidence_ids=evidence_ids[1:3],
            status="weak",
        ),
    ]
    return _analysis(incident, hypotheses, action)


def _payment_deploy_analysis(
    incident: Incident,
    evidence_ids: list[str],
    *,
    force_verification_failure: bool = False,
) -> AgentAnalysis:
    action = RecommendedAction(
        action_type="mock.create_rollback_pr",
        target=f"{incident.service}:{incident.environment}",
        risk_level="medium",
        requires_approval=True,
        rationale="Error spike began immediately after deploy v1.42.0 and prior matching incident recovered via rollback PR draft.",
        payload={"from_version": "v1.42.0", "to_version": "v1.41.3", "dry_run": True, "force_verification_failure": force_verification_failure},
        preconditions=["bad deploy evidence present", "rollback target identified"],
        post_checks=["mock recovery check passes", "report includes PR reference"],
        evidence_ids=evidence_ids[:4],
    )
    hypotheses = [
        Hypothesis(
            title="Recent payment-api deploy introduced timeout regression",
            confidence=0.91,
            supporting_evidence_ids=evidence_ids[:4],
            status="supported",
        ),
        Hypothesis(
            title="External payment processor outage",
            confidence=0.34,
            supporting_evidence_ids=evidence_ids[:1],
            refuting_evidence_ids=evidence_ids[1:2],
            status="weak",
        ),
    ]
    return _analysis(incident, hypotheses, action)


def _analysis(incident: Incident, hypotheses: list[Hypothesis], action: RecommendedAction) -> AgentAnalysis:
    return AgentAnalysis(
        summary=(
            f"{incident.severity.upper()} {incident.service} incident in {incident.environment}: deterministic mock analysis found "
            f"{hypotheses[0].title.lower()}."
        ),
        affected_service=incident.service,
        environment=incident.environment,
        severity=incident.severity,
        hypotheses=hypotheses,
        recommended_action=action,
        verification_plan=["Execute mock.verify_recovery", "Confirm error rate decreases", "Write final report"],
        escalation_condition="Escalate if confidence drops below 0.70, verification fails, or requested action is denied.",
    )
