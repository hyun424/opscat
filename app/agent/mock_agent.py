from app.models import Evidence, Incident
from app.schemas.agent import AgentAnalysis, Hypothesis, RecommendedAction


def analyze_incident(incident: Incident, evidence: list[Evidence]) -> AgentAnalysis:
    evidence_ids = [item.id for item in evidence]
    scenario = str(incident.alert_payload.get("scenario", "payment_api_deploy_regression"))

    if incident.service == "worker":
        action = RecommendedAction(
            action_type="mock.execute_restart_worker",
            target=f"{incident.service}:{incident.environment}",
            risk_level="low",
            requires_approval=True,
            rationale=(
                "Runbook marks non-production worker restart reversible and prior incident recovered after restart."
            ),
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
    else:
        action = RecommendedAction(
            action_type="mock.create_rollback_pr",
            target=f"{incident.service}:{incident.environment}",
            risk_level="medium",
            requires_approval=True,
            rationale=(
                "Error spike began immediately after deploy v1.42.0 and prior "
                "matching incident recovered via rollback PR draft."
            ),
            payload={"from_version": "v1.42.0", "to_version": "v1.41.3", "dry_run": True},
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


def _payment_deploy_analysis(incident: Incident, evidence_ids: list[str]) -> AgentAnalysis:
    action = RecommendedAction(
        action_type="mock.create_rollback_pr",
        target=f"{incident.service}:{incident.environment}",
        risk_level="medium",
        requires_approval=True,
        rationale="Error spike began immediately after deploy v1.42.0 and prior matching incident recovered via rollback PR draft.",
        payload={"from_version": "v1.42.0", "to_version": "v1.41.3", "dry_run": True},
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
            f"{incident.severity.upper()} {incident.service} incident in "
            f"{incident.environment}: deterministic mock analysis found "
            f"{hypotheses[0].title.lower()}."
        ),
        affected_service=incident.service,
        environment=incident.environment,
        severity=incident.severity,
        hypotheses=hypotheses,
        recommended_action=action,
        verification_plan=[
            "Execute mock.verify_recovery",
            "Confirm error rate decreases",
            "Write final report",
        ],
        escalation_condition=(
            "Escalate if confidence drops below 0.70, verification fails, or requested action is denied."
        ),
    )
