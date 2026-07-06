from app.models import Evidence, Incident
from app.schemas.agent import AgentAnalysis, Hypothesis, RecommendedAction


def analyze_incident(incident: Incident, evidence: list[Evidence]) -> AgentAnalysis:
    evidence_ids = [item.id for item in evidence]

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

    return AgentAnalysis(
        summary=(
            f"{incident.severity.upper()} {incident.service} incident in "
            f"{incident.environment}: deterministic mock analysis found "
            f"{hypotheses[0].title.lower()}."
        ),
        affected_service=incident.service,
        environment=incident.environment,
        severity=incident.severity
        hypotheses=hypotheses,
        recommended_action=action,
        verification_plan=["Execute mock.verify_recovery", "Confirm error rate decreases", "Write final report"],
        escalation_condition=(
            "Escalate if confidence drops below 0.70, verification fails, or requested action is denied."
        ),
    )
