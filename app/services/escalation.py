"""Human-on-exception escalation helpers for the local OpsCat MVP.

The helpers in this module do not send pages, Slack messages, or external
webhooks. They build and persist the exact wake-up payload OpsCat would hand to
a connector later, then add an auditable timeline event so failures are never
silent in the mock/local MVP.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.models import ActionProposal, Incident
from app.models.action import PolicyDecision, PolicyEvaluation
from app.services.state_machine import InvalidStateTransition, transition_incident
from app.services.timeline_service import add_timeline_event

MIN_AUTO_CONFIDENCE = 0.70
PROTECTED_SERVICE_MARKERS = ("payment", "billing", "auth", "security", "data")
HIGH_IMPACT_SEVERITIES = {"critical"}
HARD_ESCALATION_TRIGGERS = {
    "missing_required_context",
    "low_confidence",
    "no_matching_runbook",
    "policy_denied_action",
    "policy_escalated_action",
    "execution_failed",
    "post_check_failed",
    "max_attempts_reached",
}


def protected_domain(service: str) -> bool:
    normalized = service.lower()
    return any(marker in normalized for marker in PROTECTED_SERVICE_MARKERS)


def decision_escalation_triggers(
    incident: Incident,
    action: ActionProposal,
    policy: PolicyEvaluation,
    *,
    evidence_count: int,
    confidence: float | None,
) -> list[str]:
    """Return no-silent-failure wake-up triggers for an action decision."""

    triggers: list[str] = []
    if evidence_count < 2:
        triggers.append("missing_required_context")
    if confidence is None or confidence < MIN_AUTO_CONFIDENCE:
        triggers.append("low_confidence")
    if not action.preconditions or not action.post_checks:
        triggers.append("no_matching_runbook")
    if policy.decision == PolicyDecision.DENY:
        triggers.append("policy_denied_action")
    if policy.decision == PolicyDecision.ESCALATE:
        triggers.append("policy_escalated_action")
    if protected_domain(incident.service) or incident.severity in HIGH_IMPACT_SEVERITIES:
        triggers.append("protected_domain_or_high_impact")
    return triggers


def build_escalation_payload(
    incident: Incident,
    *,
    trigger: str,
    triggers: Sequence[str] | None = None,
    action: ActionProposal | None = None,
    policy: PolicyEvaluation | None = None,
    verification: dict[str, Any] | None = None,
    recommended_next_action: str | None = None,
) -> dict[str, Any]:
    """Build the stable human wake-up payload required by the product docs."""

    evidence = [
        {
            "id": item.id,
            "type": item.type,
            "source": item.source,
            "source_url": item.source_url,
            "summary": item.content,
        }
        for item in incident.evidence
    ]
    actions_taken = []
    blocked_actions = []
    for proposal in incident.actions:
        entry: dict[str, Any] = {
            "id": proposal.id,
            "action_type": proposal.action_type,
            "target": proposal.target,
            "status": proposal.status,
            "policy_decision": proposal.policy_decision,
            "risk_level": proposal.risk_level,
        }
        if proposal.execution_result:
            entry["execution_result"] = proposal.execution_result
        if proposal.status in {"executed", "approved"}:
            actions_taken.append(entry)
        if proposal.status in {"denied", "failed", "escalated", "proposed", "rejected"}:
            entry["blocked_reason"] = proposal.escalation_reason or "; ".join(proposal.policy_reasons)
            blocked_actions.append(entry)

    if action is not None and not any(item["id"] == action.id for item in blocked_actions + actions_taken):
        blocked_actions.append(
            {
                "id": action.id,
                "action_type": action.action_type,
                "target": action.target,
                "status": action.status,
                "policy_decision": action.policy_decision,
                "risk_level": action.risk_level,
                "blocked_reason": action.escalation_reason or "; ".join(action.policy_reasons),
            }
        )

    policy_reasons = policy.reasons if policy is not None else (action.policy_reasons if action is not None else [])
    return {
        "wake_human": True,
        "escalation_decision": "wake_human",
        "trigger": trigger,
        "triggers": list(triggers or [trigger]),
        "what_happened": incident.summary or incident.alert_payload.get("message") or "Incident requires review.",
        "affected_service": incident.service,
        "environment": incident.environment,
        "current_severity": incident.severity,
        "customer_business_impact": _impact_summary(incident),
        "hypotheses": [
            {
                "title": incident.root_cause_candidate or "Unknown root cause",
                "confidence": incident.confidence,
                "status": (
                    "supported"
                    if incident.confidence and incident.confidence >= MIN_AUTO_CONFIDENCE
                    else "uncertain"
                ),
            }
        ],
        "confidence": incident.confidence,
        "risk_level": action.risk_level if action is not None else (policy.risk_level if policy is not None else None),
        "policy_decision": (
            action.policy_decision if action is not None else (policy.decision if policy is not None else None)
        ),
        "policy_reasons": policy_reasons,
        "evidence_collected": evidence,
        "actions_already_taken": actions_taken,
        "actions_blocked": blocked_actions,
        "verification": verification,
        "recommended_next_action": recommended_next_action or _recommended_next_action(trigger, action),
        "links": {
            "incident": f"local://incidents/{incident.id}",
            "report": f"local://incidents/{incident.id}/report",
        },
    }


def record_human_escalation(
    db: Session,
    incident: Incident,
    payload: dict[str, Any],
    *,
    action: ActionProposal | None = None,
    transition_to_escalated: bool,
) -> None:
    """Persist an auditable wake-up event and optionally move incident state."""

    if action is not None:
        action.escalation_required = True
        action.escalation_decision = str(payload.get("escalation_decision", "wake_human"))
        action.escalation_reason = str(payload.get("trigger", "human_review_required"))
        action.escalation_payload = payload
        db.add(action)

    add_timeline_event(
        db,
        incident.id,
        actor="escalation",
        event_type="human_escalation_required",
        content=f"Human wake-up required: {payload.get('trigger')}",
        metadata=payload,
    )
    if transition_to_escalated and incident.status != "escalated":
        try:
            db.add(
                transition_incident(
                    incident,
                    "escalated",
                    actor="escalation",
                    reason=str(payload.get("trigger", "human_review_required")),
                )
            )
        except InvalidStateTransition:
            add_timeline_event(
                db,
                incident.id,
                actor="escalation",
                event_type="escalation_state_transition_blocked",
                content="Escalation recorded without changing terminal incident state.",
                metadata={"current_status": incident.status, "payload": payload},
            )


def hard_escalation_required(triggers: Sequence[str]) -> bool:
    return any(trigger in HARD_ESCALATION_TRIGGERS for trigger in triggers)


def _impact_summary(incident: Incident) -> str:
    if protected_domain(incident.service):
        return f"{incident.service} is a protected/customer-impacting service; review before mutation."
    if incident.severity in HIGH_IMPACT_SEVERITIES:
        return f"{incident.severity} severity incident requires human accountability."
    return "Impact appears bounded in the local/mock MVP; review evidence before approving writes."


def _recommended_next_action(trigger: str, action: ActionProposal | None) -> str:
    if trigger == "post_check_failed":
        return "Review failed verification evidence, stop automatic retries, and choose the next runbook step."
    if trigger == "policy_denied_action":
        return "Do not execute the denied action; select a safer runbook or approve a future hardened integration."
    if trigger == "low_confidence":
        return "Collect more context or assign a human investigator before attempting remediation."
    if action is not None and action.requires_approval:
        return f"Review and approve or reject {action.action_type} with the cited evidence."
    return "Review incident evidence and decide the next manual action."
