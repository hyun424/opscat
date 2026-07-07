"""Deterministic incident war-room read model.

The war room is a local/read-only projection for operator review. It must not
perform provider calls, shell execution, or production mutation; it only derives
redacted data from already-persisted incident state.
"""

from __future__ import annotations

from typing import Any

from app.models import ActionProposal, Incident
from app.services.redaction import redact_text, redact_value


def build_war_room(incident: Incident) -> dict[str, Any]:
    """Build a redacted, deterministic operator-facing war-room projection."""
    action = _latest_action(incident)
    evidence = [_evidence_item(item) for item in sorted(incident.evidence, key=lambda item: (_sortable_dt(item.collected_at), item.id))]
    timeline = [_timeline_item(event) for event in sorted(incident.timeline, key=lambda event: (_sortable_dt(event.timestamp), event.id))]
    hypotheses = _hypotheses(incident, evidence)
    policy_gates = _policy_gates(action, incident)
    reliability_score = _reliability_score(action, incident, evidence, policy_gates)
    runbook_critique = _runbook_critique(action, incident, evidence)
    missing_evidence = _missing_evidence(action, evidence)
    human_questions = _human_questions(action, incident, missing_evidence, policy_gates)
    why_not_auto_execute = _why_not_auto_execute(action, policy_gates, reliability_score)

    return {
        "incident_id": incident.id,
        "tenant_id": incident.tenant_id,
        "workspace_id": incident.workspace_id,
        "status": incident.status,
        "service": incident.service,
        "environment": incident.environment,
        "severity": incident.severity,
        "summary": redact_text(incident.summary or ""),
        "impact": {
            "service": incident.service,
            "environment": incident.environment,
            "severity": incident.severity,
            "summary": redact_text(_impact_summary(incident)),
        },
        "timeline": timeline,
        "evidence": evidence,
        "current_hypothesis": hypotheses[0] if hypotheses else {},
        "hypotheses": hypotheses,
        "missing_evidence": missing_evidence,
        "proposed_action": _proposed_action(action),
        "policy_gates": policy_gates,
        "reliability_score": reliability_score,
        "runbook_critique": runbook_critique,
        "human_questions": human_questions,
        "why_not_auto_execute": why_not_auto_execute,
        "final_decision": _final_decision(incident, action, policy_gates),
        "safety_boundary": "local/mock read model; no external providers, shell execution, credentials, or production mutation",
    }


def _latest_action(incident: Incident) -> ActionProposal | None:
    if not incident.actions:
        return None
    return sorted(incident.actions, key=lambda action: (_sortable_dt(action.created_at), action.id))[-1]


def _sortable_dt(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _evidence_item(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "type": item.type,
        "source": item.source,
        "source_url": redact_text(item.source_url or "") or None,
        "content": redact_text(item.content),
        "metadata": redact_value(item.evidence_metadata or {}),
        "collected_at": item.collected_at.isoformat(),
    }


def _timeline_item(event: Any) -> dict[str, Any]:
    return {
        "id": event.id,
        "timestamp": event.timestamp.isoformat(),
        "actor": redact_text(event.actor),
        "event_type": event.event_type,
        "content": redact_text(event.content),
        "metadata": redact_value(event.event_metadata or {}),
    }


def _hypotheses(incident: Incident, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_ids = [str(item["id"]) for item in evidence]
    title = incident.root_cause_candidate or incident.summary or "Root cause requires investigation"
    confidence = float(incident.confidence or 0.0)
    candidates = [
        {
            "title": redact_text(title),
            "confidence": confidence,
            "supporting_evidence_ids": evidence_ids[:4],
            "refuting_evidence_ids": [],
            "status": "supported" if evidence_ids else "insufficient_evidence",
        }
    ]
    if evidence and len(candidates) < 3:
        candidates.append(
            {
                "title": "External dependency or transient platform degradation",
                "confidence": min(confidence, 0.35),
                "supporting_evidence_ids": evidence_ids[:2],
                "refuting_evidence_ids": [],
                "status": "alternate",
            }
        )
    return candidates[:3]


def _proposed_action(action: ActionProposal | None) -> dict[str, Any] | None:
    if action is None:
        return None
    latest_attempt = action.execution_attempts[-1] if action.execution_attempts else None
    return {
        "id": action.id,
        "action_type": action.action_type,
        "target": redact_text(action.target),
        "environment": action.environment,
        "status": action.status,
        "risk_level": action.risk_level,
        "requires_approval": action.requires_approval,
        "policy_decision": action.policy_decision,
        "rationale": redact_text(action.rationale),
        "preconditions": redact_value(action.preconditions or []),
        "post_checks": redact_value(action.post_checks or []),
        "evidence_ids": list(action.evidence_ids or []),
        "latest_attempt_status": latest_attempt.status if latest_attempt is not None else None,
    }


def _policy_gates(action: ActionProposal | None, incident: Incident) -> list[dict[str, Any]]:
    if action is None:
        return [
            {
                "name": "action_present",
                "status": "blocked",
                "reason": "No action has been proposed; human review is required before remediation.",
            }
        ]
    gates = [
        {
            "name": "policy_decision",
            "status": _gate_status(action.policy_decision in {"ALLOW", "REQUIRE_APPROVAL"}),
            "reason": redact_text(action.policy_decision),
        },
        {
            "name": "risk_level",
            "status": _gate_status(action.risk_level not in {"high", "prohibited"}),
            "reason": redact_text(action.risk_level),
        },
        {
            "name": "approval_required",
            "status": "needs_human" if action.requires_approval else "passed",
            "reason": "Approval is required before mutation." if action.requires_approval else "Read-only or low-risk local/mock action.",
        },
        {
            "name": "environment_boundary",
            "status": _gate_status(incident.environment in {"local", "dev", "test", "staging"}),
            "reason": f"environment={redact_text(incident.environment)}; production mutation remains out of scope",
        },
    ]
    for reason in action.policy_reasons or []:
        gates.append({"name": "policy_reason", "status": "info", "reason": redact_text(str(reason))})
    return gates


def _reliability_score(action: ActionProposal | None, incident: Incident, evidence: list[dict[str, Any]], policy_gates: list[dict[str, Any]]) -> dict[str, Any]:
    embedded = _payload_section(action, "agent_reliability_score")
    if embedded:
        redacted = redact_value(embedded)
        redacted.setdefault("cannot_bypass_policy", True)
        return redacted

    score = 45
    reasons: list[str] = []
    if evidence:
        score += min(len(evidence) * 7, 20)
        reasons.append("evidence_present")
    else:
        score -= 15
        reasons.append("missing_evidence")
    if incident.confidence is not None:
        score += int(max(0.0, min(float(incident.confidence), 1.0)) * 20)
        reasons.append(f"confidence={incident.confidence:.2f}")
    if action is not None and action.policy_decision in {"DENY", "ESCALATE"}:
        score = min(score, 49)
        reasons.append("hard_policy_gate")
    if any(gate["status"] == "blocked" for gate in policy_gates):
        score = min(score, 49)
        reasons.append("blocked_gate")
    score = max(0, min(score, 100))
    return {
        "score": score,
        "band": "high" if score >= 75 else "medium" if score >= 50 else "low",
        "reasons": reasons,
        "cannot_bypass_policy": True,
    }


def _runbook_critique(action: ActionProposal | None, incident: Incident, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    embedded = _payload_section(action, "runbook_critique")
    if embedded:
        return redact_value(embedded)
    if action is None:
        return {"fit": "insufficient_evidence", "reasons": ["No proposed action/runbook available."], "suggestions": ["Gather minimum evidence before remediation."]}
    if action.policy_decision in {"DENY", "ESCALATE"} or action.risk_level in {"high", "prohibited"}:
        fit = "unsafe"
    elif len(evidence) < 2 or (incident.confidence or 0.0) < 0.5:
        fit = "weak_fit"
    else:
        fit = "good_fit"
    return {
        "fit": fit,
        "reasons": [redact_text(action.rationale), f"policy={action.policy_decision}", f"risk={action.risk_level}"],
        "suggestions": ["Keep remediation local/mock and policy-gated.", "Verify recovery evidence before closing the incident."],
    }


def _missing_evidence(action: ActionProposal | None, evidence: list[dict[str, Any]]) -> list[str]:
    critique = _payload_section(action, "self_critique")
    raw_missing = critique.get("missing_evidence") if critique else None
    if isinstance(raw_missing, list) and raw_missing:
        return [redact_text(str(item)) for item in raw_missing]
    if not evidence:
        return ["No evidence has been collected yet."]
    if len(evidence) < 2:
        return ["Collect one independent corroborating signal before autonomous remediation."]
    return []


def _human_questions(action: ActionProposal | None, incident: Incident, missing_evidence: list[str], policy_gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    embedded = _payload_section(action, "human_questions")
    if embedded.get("questions") and isinstance(embedded["questions"], list):
        return redact_value(embedded["questions"])
    questions: list[dict[str, Any]] = []
    for item in missing_evidence[:2]:
        questions.append(
            {
                "question": f"Can you confirm this missing evidence: {redact_text(item)}?",
                "why_it_matters": "OpsCat must not auto-execute without enough supporting evidence.",
                "source_gate": "missing_evidence",
                "safe_to_ask": True,
            }
        )
    if any(gate["status"] in {"blocked", "needs_human"} for gate in policy_gates):
        questions.append(
            {
                "question": f"Should the on-call approve the proposed local/mock action for {redact_text(incident.service)}?",
                "why_it_matters": "Human approval is required when policy gates block autonomous execution.",
                "source_gate": "policy_gate",
                "safe_to_ask": True,
            }
        )
    if not questions:
        questions.append(
            {
                "question": "Is there any recent operator context that contradicts the current hypothesis?",
                "why_it_matters": "Human context can prevent over-trusting a plausible automated diagnosis.",
                "source_gate": "operator_context",
                "safe_to_ask": True,
            }
        )
    return questions


def _why_not_auto_execute(action: ActionProposal | None, policy_gates: list[dict[str, Any]], reliability_score: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if action is None:
        reasons.append("No proposed action exists.")
    elif action.requires_approval:
        reasons.append("The proposed action requires human approval.")
    for gate in policy_gates:
        if gate["status"] in {"blocked", "needs_human"}:
            reasons.append(f"{gate['name']}: {gate['reason']}")
    if reliability_score.get("band") != "high":
        reasons.append(f"Reliability score band is {reliability_score.get('band', 'unknown')}.")
    return [redact_text(reason) for reason in dict.fromkeys(reasons)] or ["No autonomous blocker recorded; execution still remains policy-gated and local/mock only."]


def _final_decision(incident: Incident, action: ActionProposal | None, policy_gates: list[dict[str, Any]]) -> dict[str, Any]:
    if action is None:
        route = "needs_human"
    elif action.status in {"executed"}:
        route = "executed_local_mock"
    elif action.status in {"denied", "escalated", "failed", "rejected"}:
        route = "human_required"
    elif any(gate["status"] in {"blocked", "needs_human"} for gate in policy_gates):
        route = "approval_or_human_required"
    else:
        route = "policy_gated_local_mock"
    return {
        "incident_status": incident.status,
        "action_status": action.status if action is not None else None,
        "route": route,
        "summary": redact_text(f"Incident {incident.status}; action {action.status if action is not None else 'not_proposed'}; route {route}."),
    }


def _impact_summary(incident: Incident) -> str:
    return f"{incident.severity} incident affecting {incident.service} in {incident.environment}."


def _gate_status(passed: bool) -> str:
    return "passed" if passed else "blocked"


def _payload_section(action: ActionProposal | None, key: str) -> dict[str, Any]:
    if action is None or not isinstance(action.payload, dict):
        return {}
    value = action.payload.get(key)
    return dict(value) if isinstance(value, dict) else {}
