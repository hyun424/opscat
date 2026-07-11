from sqlalchemy.orm import Session

from app.agent.mock_agent import analyze_incident
from app.models import ActionProposal, Incident
from app.models.action import ActionRequest
from app.services.action_simulator import ActionSimulator
from app.services.audit_service import record_audit_event
from app.services.blast_radius import BlastRadiusService
from app.services.decision_trace_service import record_decision_trace
from app.services.escalation import (
    build_escalation_payload,
    decision_escalation_triggers,
    hard_escalation_required,
    record_human_escalation,
)
from app.services.incident_memory import IncidentMemory
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.root_cause_service import generate_root_cause_candidates, persist_top_root_cause
from app.services.runbook_service import select_runbook
from app.services.self_critique_service import SelfCritiqueService, critique_diagnosis
from app.services.state_machine import transition_incident
from app.services.timeline_service import add_timeline_event
from app.tools.mock_context import gather_all_context


class AgentLoop:
    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.blast_radius = BlastRadiusService()
        self.simulator = ActionSimulator(blast_radius_service=self.blast_radius)

    def investigate(self, db: Session, incident: Incident) -> ActionProposal:
        db.add(transition_incident(incident, "investigating", actor="agent", reason="starting context gather"))
        record_decision_trace(
            db,
            incident,
            stage="observe",
            decision="mock alert accepted for investigation",
            confidence=incident.confidence,
            inputs={"scenario": incident.alert_payload.get("scenario"), "service": incident.service, "environment": incident.environment},
        )
        evidence = gather_all_context(db, incident)
        record_decision_trace(
            db,
            incident,
            stage="correlate",
            decision="single incident scope established from idempotent alert fingerprint",
            confidence=incident.confidence,
            inputs={"alert_fingerprint": incident.alert_fingerprint, "evidence_count": len(evidence)},
        )
        add_timeline_event(
            db,
            incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="agent",
            event_type="context_gathered",
            content=f"Gathered {len(evidence)} read-only mock evidence records.",
            metadata={"evidence_ids": [item.id for item in evidence]},
        )
        analysis = analyze_incident(incident, evidence)
        candidates = generate_root_cause_candidates(incident, evidence)
        incident.summary = analysis.summary
        if analysis.hypotheses and (analysis.recommended_action.action_type == "human.escalate" or analysis.hypotheses[0].confidence >= (candidates[0].confidence if candidates else 0.0)):
            incident.root_cause_candidate = analysis.hypotheses[0].title
            incident.confidence = analysis.hypotheses[0].confidence
        else:
            persist_top_root_cause(incident, candidates)
        record_decision_trace(
            db,
            incident,
            stage="diagnose",
            decision=incident.root_cause_candidate or "no candidate",
            confidence=incident.confidence,
            inputs={"candidate_count": len(candidates), "evidence_ids": [item.id for item in evidence[:4]]},
            reason="deterministic root-cause candidate ranking",
        )
        runbook = select_runbook(incident, candidates)
        recommended = analysis.recommended_action
        critique = critique_diagnosis(
            incident,
            evidence,
            alternate_causes=[candidate.hypothesis for candidate in candidates[1:3]],
            action_type=recommended.action_type,
        )
        record_decision_trace(
            db,
            incident,
            stage="critique",
            decision="human review required" if critique.requires_human else "critique passed",
            confidence=incident.confidence,
            inputs=critique.to_dict(),
            reason="deterministic self-critique gate",
        )
        record_decision_trace(
            db,
            incident,
            stage="plan",
            decision=runbook.key,
            confidence=incident.confidence,
            inputs={"steps": [step.action_type for step in runbook.steps]},
            reason=runbook.title,
        )
        db.add(transition_incident(incident, "action_proposed", actor="agent", reason="analysis complete"))

        recommended = analysis.recommended_action
        memory_matches = IncidentMemory().find_similar(
            service=incident.service,
            environment=incident.environment,
            fingerprint=str(incident.alert_payload.get("scenario") or incident.alert_fingerprint),
            root_cause=incident.root_cause_candidate or "",
            runbook=runbook.key,
            action_type=recommended.action_type,
        )
        memory_warnings = tuple(match.warning for match in memory_matches if match.failed_prior_action and match.score >= 0.8)
        critique = SelfCritiqueService().critique(
            confidence=incident.confidence,
            evidence_count=len(evidence),
            action_type=recommended.action_type,
            hypotheses=[
                {
                    "title": hypothesis.title,
                    "confidence": hypothesis.confidence,
                    "status": hypothesis.status,
                }
                for hypothesis in analysis.hypotheses
            ],
            memory_warnings=memory_warnings,
        )
        action_context = {
            "action_type": recommended.action_type,
            "target": recommended.target,
            "environment": incident.environment,
            "payload": recommended.payload,
        }
        blast_radius = BlastRadiusService().classify(action_context)
        simulation = ActionSimulator().simulate(action_context)
        simulation_payload = simulation.to_dict()
        if simulation_payload.get("status") == "pass":
            simulation_payload["status"] = "passed"
        memory_payload = [match.to_dict() for match in memory_matches]
        if not memory_payload:
            memory_payload = [
                {
                    "incident_id": "local-runbook-seed",
                    "score": 0.5,
                    "reasons": ["same_service", "same_environment", "same_action_type"],
                    "warnings": [],
                    "failed_prior_action": False,
                    "action_type": recommended.action_type,
                    "outcome": "known_safe_local_mock_runbook",
                }
            ]
        p7_payload = {
            **recommended.payload,
            "self_critique": critique.to_dict(),
            "blast_radius": blast_radius.to_dict(),
            "simulation": simulation_payload,
            "incident_memory": {
                "similar_incidents": memory_payload,
                "warnings": list(memory_warnings),
            },
        }
        record_decision_trace(
            db,
            incident,
            stage="critique",
            decision=critique.decision,
            confidence=incident.confidence,
            inputs={
                "missing_evidence": list(critique.missing_evidence),
                "alternate_causes": list(critique.alternate_causes),
                "contradiction_flags": list(critique.contradiction_flags),
                "action_risk_objections": list(critique.action_risk_objections),
                "memory_warnings": list(memory_warnings),
            },
            reason="deterministic self-critique before risk/action proposal",
        )
        policy = self.policy_engine.evaluate(
            ActionRequest(
                action_type=recommended.action_type,
                target=recommended.target,
                environment=incident.environment,
                tenant_id=incident.tenant_id,
                workspace_id=incident.workspace_id,
                payload=p7_payload,
                incident_id=incident.id,
            ),
            PolicyContext(
                environment=incident.environment,
                service=incident.service,
                tenant_id=incident.tenant_id,
                workspace_id=incident.workspace_id,
                confidence=incident.confidence,
                evidence_count=len(evidence),
                conflicting_signals=bool(critique.contradiction_flags),
                known_ambiguity=critique.requires_human,
                blast_radius_scope=blast_radius.scope,
                rollback_available=blast_radius.rollback_available,
                simulation_passed=simulation.success,
            ),
        )
        record_decision_trace(
            db,
            incident,
            stage="risk",
            decision=policy.route.value,
            confidence=incident.confidence,
            inputs={"action_type": recommended.action_type, "risk_level": policy.risk_level.value, "blast_radius": blast_radius.to_dict(), "simulation": simulation.to_dict()},
            policy_result={"decision": policy.decision.value, "route": policy.route.value, "reasons": policy.reasons},
            reason=policy.reason,
        )
        action = ActionProposal(
            incident_id=incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            action_type=recommended.action_type,
            target=recommended.target,
            environment=incident.environment,
            risk_level=policy.risk_level,
            requires_approval=policy.requires_approval or recommended.requires_approval or critique.blocks_auto_action or not simulation.passed or not blast_radius.allowed_for_auto,
            rationale=recommended.rationale,
            payload=p7_payload,
            preconditions=recommended.preconditions,
            post_checks=recommended.post_checks,
            evidence_ids=recommended.evidence_ids,
            policy_decision=policy.decision,
            policy_reasons=[
                *policy.reasons,
                *critique.action_risk_objections,
                *blast_radius.reasons,
                *(simulation.precondition_gaps if not simulation.ok else ()),
            ],
            confidence=incident.confidence,
            status="proposed",
        )
        incident.actions.append(action)
        db.add(action)
        db.flush()
        record_audit_event(
            db,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="agent",
            event_type="action_proposed",
            resource_type="action",
            resource_id=action.id,
            action_id=action.id,
            metadata={
                "action_type": action.action_type,
                "risk_level": action.risk_level,
                "evidence_ids": action.evidence_ids,
                "blast_radius": blast_radius.to_dict(),
                "simulation": simulation.to_dict(),
            },
        )
        triggers = decision_escalation_triggers(
            incident,
            action,
            policy,
            evidence_count=len(evidence),
            confidence=incident.confidence,
        )
        hard_escalation = hard_escalation_required(triggers)
        if triggers:
            payload = build_escalation_payload(
                incident,
                trigger=triggers[0],
                triggers=triggers,
                action=action,
                policy=policy,
            )
            record_human_escalation(
                db,
                incident,
                payload,
                action=action,
                transition_to_escalated=hard_escalation,
            )
            if hard_escalation:
                action.status = "escalated"
        policy_metadata = {"action_id": action.id, "decision": policy.decision, "reasons": policy.reasons, "escalation_triggers": triggers}
        add_timeline_event(
            db,
            incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="policy",
            event_type="policy_decision",
            content=f"Policy decision for {action.action_type}: {policy.decision}",
            metadata=policy_metadata,
        )
        record_audit_event(
            db,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="policy",
            event_type="policy_decision",
            resource_type="action",
            resource_id=action.id,
            action_id=action.id,
            metadata=policy_metadata,
        )
        record_decision_trace(
            db,
            incident,
            stage="act",
            decision=f"proposed {action.action_type}",
            confidence=incident.confidence,
            inputs={"action_id": action.id, "requires_approval": action.requires_approval},
            output_ref=action.id,
            policy_result={"decision": policy.decision.value, "route": policy.route.value},
        )
        record_decision_trace(
            db,
            incident,
            stage="verify",
            decision="post-check plan recorded before execution",
            confidence=incident.confidence,
            inputs={"post_checks": action.post_checks},
            output_ref=action.id,
        )
        if policy.decision == "DENY":
            action.status = "denied"
            if incident.status != "escalated":
                db.add(transition_incident(incident, "escalated", actor="policy", reason="action denied"))
        elif policy.decision == "ESCALATE":
            action.status = "escalated"
            if incident.status != "escalated":
                db.add(transition_incident(incident, "escalated", actor="policy", reason="policy escalation"))
        elif incident.status == "escalated":
            pass
        elif policy.decision == "ALLOW" and not action.requires_approval:
            db.add(transition_incident(incident, "executing", actor="policy", reason="action auto allowed"))
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
