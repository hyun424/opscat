from sqlalchemy.orm import Session

from app.agent.mock_agent import analyze_incident
from app.models import ActionProposal, Incident
from app.models.action import ActionRequest
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.state_machine import transition_incident
from app.services.timeline_service import add_timeline_event
from app.tools.mock_context import gather_all_context


class AgentLoop:
    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()

    def investigate(self, db: Session, incident: Incident) -> ActionProposal:
        db.add(transition_incident(incident, "investigating", actor="agent", reason="starting context gather"))
        evidence = gather_all_context(db, incident)
        add_timeline_event(
            db,
            incident.id,
            actor="agent",
            event_type="context_gathered",
            content=f"Gathered {len(evidence)} read-only mock evidence records.",
            metadata={"evidence_ids": [item.id for item in evidence]},
        )
        analysis = analyze_incident(incident, evidence)
        incident.summary = analysis.summary
        incident.root_cause_candidate = analysis.hypotheses[0].title
        incident.confidence = analysis.hypotheses[0].confidence
        db.add(transition_incident(incident, "action_proposed", actor="agent", reason="analysis complete"))

        recommended = analysis.recommended_action
        policy = self.policy_engine.evaluate(
            ActionRequest(
                action_type=recommended.action_type,
                target=recommended.target,
                environment=incident.environment,
                payload=recommended.payload,
                incident_id=incident.id,
            ),
            PolicyContext(environment=incident.environment, service=incident.service),
        )
        action = ActionProposal(
            incident_id=incident.id,
            action_type=recommended.action_type,
            target=recommended.target,
            environment=incident.environment,
            risk_level=policy.risk_level,
            requires_approval=policy.requires_approval or recommended.requires_approval,
            rationale=recommended.rationale,
            payload=recommended.payload,
            preconditions=recommended.preconditions,
            post_checks=recommended.post_checks,
            evidence_ids=recommended.evidence_ids,
            policy_decision=policy.decision,
            policy_reasons=policy.reasons,
            status="proposed",
        )
        db.add(action)
        db.flush()
        add_timeline_event(
            db,
            incident.id,
            actor="policy",
            event_type="policy_decision",
            content=f"Policy decision for {action.action_type}: {policy.decision}",
            metadata={"action_id": action.id, "reasons": policy.reasons},
        )
        if policy.decision == "ALLOW" and not action.requires_approval:
            db.add(transition_incident(incident, "executing", actor="policy", reason="action auto allowed"))
        elif policy.decision == "DENY":
            action.status = "denied"
            db.add(transition_incident(incident, "escalated", actor="policy", reason="action denied"))
        elif policy.decision == "ESCALATE":
            action.status = "escalated"
            db.add(transition_incident(incident, "escalated", actor="policy", reason="policy escalation"))
        else:
            db.add(
                transition_incident(
                    incident,
                    "waiting_approval",
                    actor="policy",
                    reason="human approval required",
                )
            )
        return action
