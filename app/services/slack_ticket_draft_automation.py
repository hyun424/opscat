"""P82 Slack and ticket draft automation.

Builds local/mock communication and ticket drafts after incident triage or
rollback planning. This module never calls Slack, Jira, GitHub, Linear, reads
credentials, calls networks, sends messages, creates tickets, or mutates
production.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "draft_only": True,
    "slack_api_calls_enabled": False,
    "ticket_api_calls_enabled": False,
    "github_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "message_sending_enabled": False,
    "ticket_creation_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "action_execution_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}

_BLOCKED_TYPES = {"credential_auth", "credential", "auth", "secret", "identity"}
_MIN_DRAFT_SCORE = 0.75


class SlackTicketDraftDecision(StrEnum):
    DRAFT_READY = "draft_ready"
    INVESTIGATION_ONLY = "investigation_only"
    BLOCKED = "blocked"
    REJECTED = "rejected"


@dataclass(frozen=True)
class EvidenceLink:
    id: str
    source: str
    summary: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "evidence:missing")),
            source=str(data.get("source", "unknown")),
            summary=str(data.get("summary", "Evidence summary unavailable.")),
        )

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "source": self.source, "summary": self.summary}


@dataclass(frozen=True)
class SlackTicketDraftScenario:
    id: str
    title: str
    service: str
    incident_type: str
    severity: str
    audience: str
    p76_gate: Mapping[str, Any]
    p80_approval: Mapping[str, Any]
    p81_rollback_draft: Mapping[str, Any]
    evidence_links: tuple[EvidenceLink, ...]
    claim: str
    uncertainty: tuple[str, ...]
    next_actions: tuple[str, ...]
    ticket: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            title=str(data.get("title", "Slack and ticket draft")),
            service=str(data.get("service", "unknown")),
            incident_type=str(data.get("incident_type", "unknown")).lower(),
            severity=str(data.get("severity", "sev3")).lower(),
            audience=str(data.get("audience", "internal")).lower(),
            p76_gate=_mapping(data.get("p76_gate")),
            p80_approval=_mapping(data.get("p80_approval")),
            p81_rollback_draft=_mapping(data.get("p81_rollback_draft")),
            evidence_links=tuple(EvidenceLink.from_dict(item) for item in _sequence(data.get("evidence_links", ())) if isinstance(item, Mapping)),
            claim=str(data.get("claim", "Investigation in progress.")),
            uncertainty=tuple(str(item) for item in _sequence(data.get("uncertainty", ()))),
            next_actions=tuple(str(item) for item in _sequence(data.get("next_actions", ()))),
            ticket=_mapping(data.get("ticket")),
        )


@dataclass(frozen=True)
class SlackTicketDraftArtifact:
    scenario_id: str
    decision: SlackTicketDraftDecision
    reasons: tuple[str, ...]
    slack_incident_update_draft: Mapping[str, Any]
    escalation_dm_draft: Mapping[str, Any]
    status_update_draft: Mapping[str, Any]
    ticket_draft: Mapping[str, Any]
    evidence_links: tuple[EvidenceLink, ...]
    uncertainty: tuple[str, ...]
    next_actions: tuple[str, ...]
    approval_requirement: Mapping[str, Any]
    p76_gate: Mapping[str, Any]
    p80_approval: Mapping[str, Any]
    p81_rollback_draft: Mapping[str, Any]
    audit_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "draft_only": True,
            "human_approval_required": True,
            "slack_incident_update_draft": dict(self.slack_incident_update_draft),
            "escalation_dm_draft": dict(self.escalation_dm_draft),
            "status_update_draft": dict(self.status_update_draft),
            "ticket_draft": dict(self.ticket_draft),
            "evidence_links": [item.to_dict() for item in self.evidence_links],
            "uncertainty": list(self.uncertainty),
            "next_actions": list(self.next_actions),
            "approval_requirement": dict(self.approval_requirement),
            "p76_gate": dict(self.p76_gate),
            "p80_approval": dict(self.p80_approval),
            "p81_rollback_draft": dict(self.p81_rollback_draft),
            "audit_metadata": dict(self.audit_metadata),
            "execution_plan": {
                "mode": "draft_only",
                "message_send_count": 0,
                "ticket_creation_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "network_call_count": 0,
                "production_mutation_count": 0,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class SlackTicketDraftReport:
    incident: Mapping[str, Any]
    scenarios: tuple[SlackTicketDraftScenario, ...]
    drafts: tuple[SlackTicketDraftArtifact, ...]

    @classmethod
    def from_scenarios(cls, incident: Mapping[str, Any], scenarios: Sequence[SlackTicketDraftScenario]) -> Self:
        drafts = tuple(_build_draft(scenario) for scenario in scenarios)
        return cls(incident=incident, scenarios=tuple(scenarios), drafts=drafts)

    def to_dict(self) -> dict[str, Any]:
        draft_ready_count = _decision_count(self.drafts, SlackTicketDraftDecision.DRAFT_READY)
        investigation_only_count = _decision_count(self.drafts, SlackTicketDraftDecision.INVESTIGATION_ONLY)
        blocked_count = _decision_count(self.drafts, SlackTicketDraftDecision.BLOCKED)
        rejected_count = _decision_count(self.drafts, SlackTicketDraftDecision.REJECTED)
        payload = {
            "summary": {
                "incident_id": str(self.incident.get("id", "p82-incident")),
                "scenario_count": len(self.scenarios),
                "draft_ready_count": draft_ready_count,
                "investigation_only_count": investigation_only_count,
                "blocked_count": blocked_count,
                "rejected_count": rejected_count,
                "required_human_approval_count": len(self.drafts),
                "message_send_count": 0,
                "ticket_creation_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "network_call_count": 0,
                "production_mutation_count": 0,
                "passed": len(self.scenarios) >= 5 and draft_ready_count >= 2 and investigation_only_count >= 1 and blocked_count >= 1 and rejected_count >= 1,
            },
            "boundary": dict(_BOUNDARY),
            "incident": redact_value(dict(self.incident)),
            "drafts": [draft.to_dict() for draft in self.drafts],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_slack_ticket_draft_fixture(path: str | Path) -> SlackTicketDraftReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    incident = _mapping(data.get("incident"))
    scenarios = tuple(SlackTicketDraftScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping))
    return SlackTicketDraftReport.from_scenarios(incident, scenarios)


def render_slack_ticket_draft_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Slack and Ticket Draft Automation",
        "",
        "P82 prepares evidence-grounded Slack/status-update and ticket drafts from local/mock incident decisions only.",
        "",
        "## Summary",
        "",
        f"- Incident: {summary.get('incident_id', 'unknown')}",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Draft ready: {summary.get('draft_ready_count', 0)}",
        f"- Investigation only: {summary.get('investigation_only_count', 0)}",
        f"- Blocked: {summary.get('blocked_count', 0)}",
        f"- Rejected: {summary.get('rejected_count', 0)}",
        f"- Required human approvals: {summary.get('required_human_approval_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Draft artifacts",
        "",
    ]
    for draft in _sequence(payload.get("drafts", ())):
        if isinstance(draft, Mapping):
            slack = _mapping(draft.get("slack_incident_update_draft"))
            ticket = _mapping(draft.get("ticket_draft"))
            evidence_ids = ", ".join(str(item) for item in _sequence(slack.get("cited_evidence_ids", ()))) or "none"
            lines.extend(
                [
                    f"### {ticket.get('title', 'Ticket draft')}",
                    "",
                    f"- Scenario: `{draft.get('scenario_id')}`",
                    f"- Decision: {draft.get('decision')}",
                    f"- Slack draft: {slack.get('text', '')}",
                    f"- Evidence: {evidence_ids}",
                    f"- Priority: {ticket.get('priority', 'P3')}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Zero-external-side-effect boundary",
            "",
            "- Draft artifact generation only.",
            "- No live Slack, Jira, GitHub, Linear, ticketing, credential, or network API calls.",
            "- No message sending, ticket creation, production mutation, remediation execution, or unattended production-operation claim.",
            "- Every draft requires human approval before any external communication or ticket action.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_slack_ticket_draft_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        output_json_path = Path(output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md_path = Path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_slack_ticket_draft_markdown(payload), encoding="utf-8")


def _build_draft(scenario: SlackTicketDraftScenario) -> SlackTicketDraftArtifact:
    decision = _decision(scenario)
    reasons = tuple(dict.fromkeys(_reasons(scenario, decision)))
    evidence_ids = _evidence_ids(scenario)
    p76_gate = _normalized_p76_gate(scenario, evidence_ids)
    approval_type = str(scenario.p80_approval.get("approval_type", "incident_commander_review"))
    text = _slack_text(scenario, decision, evidence_ids)
    return SlackTicketDraftArtifact(
        scenario_id=scenario.id,
        decision=decision,
        reasons=reasons,
        slack_incident_update_draft={
            "channel": "#incidents-local-mock",
            "text": text,
            "cited_evidence_ids": evidence_ids,
            "send_allowed": False,
        },
        escalation_dm_draft={
            "recipient_role": approval_type,
            "text": f"Draft escalation for {scenario.service}: {scenario.claim}. Evidence: {', '.join(evidence_ids)}. Approval required before external action.",
            "send_allowed": False,
        },
        status_update_draft={
            "audience": scenario.audience,
            "text": _status_text(scenario, decision, evidence_ids),
            "cited_evidence_ids": evidence_ids,
            "publish_allowed": False,
        },
        ticket_draft={
            "title": str(scenario.ticket.get("title", scenario.title)),
            "body": _ticket_body(scenario, decision, evidence_ids),
            "labels": _ticket_labels(scenario, decision),
            "priority": str(scenario.ticket.get("priority", _priority(scenario.severity))),
            "create_allowed": False,
        },
        evidence_links=scenario.evidence_links or (EvidenceLink("missing:evidence", "missing", "No evidence link supplied."),),
        uncertainty=scenario.uncertainty,
        next_actions=scenario.next_actions or ("collect additional evidence",),
        approval_requirement={
            "required": True,
            "approval_type": approval_type,
            "reason": "P82 emits local/mock drafts only; a human must approve before any external message or ticket action.",
        },
        p76_gate=p76_gate,
        p80_approval=dict(scenario.p80_approval),
        p81_rollback_draft=dict(scenario.p81_rollback_draft),
        audit_metadata={
            "audit_id": f"p82:{scenario.id}",
            "scenario_id": scenario.id,
            "service": scenario.service,
            "local_mock_only": True,
            "draft_only": True,
            "approval_gate": _approval_gate(scenario),
        },
    )


def _decision(scenario: SlackTicketDraftScenario) -> SlackTicketDraftDecision:
    p80_decision = str(scenario.p80_approval.get("decision", "")).lower()
    p81_decision = str(scenario.p81_rollback_draft.get("decision", "")).lower()
    p76_score = _float(scenario.p76_gate.get("score"))
    if scenario.incident_type in _BLOCKED_TYPES or p80_decision == "block" or p81_decision == "blocked":
        return SlackTicketDraftDecision.BLOCKED
    if p76_score < _MIN_DRAFT_SCORE or len(scenario.evidence_links) < 2:
        return SlackTicketDraftDecision.REJECTED
    if "human_confirmation_required" in scenario.uncertainty:
        return SlackTicketDraftDecision.INVESTIGATION_ONLY
    return SlackTicketDraftDecision.DRAFT_READY


def _reasons(scenario: SlackTicketDraftScenario, decision: SlackTicketDraftDecision) -> list[str]:
    reasons = ["p82_draft_only_no_external_send_or_ticket_create"]
    p76_decision = str(scenario.p76_gate.get("decision", "human_required")).lower()
    p80_decision = str(scenario.p80_approval.get("decision", "require_human")).lower()
    p81_decision = str(scenario.p81_rollback_draft.get("decision", "not_applicable")).lower()
    if p76_decision == "approval_ready":
        reasons.append("p76_evidence_sufficiency_approval_ready")
    else:
        reasons.append("p76_requires_human_or_more_evidence")
    if p80_decision == "block" or scenario.incident_type in _BLOCKED_TYPES:
        reasons.append("credential_or_auth_issue_blocked")
    elif p80_decision:
        reasons.append(f"p80_{p80_decision}_preserved")
    if p81_decision == "draft_ready":
        reasons.append("p81_rollback_draft_ready_preserved")
    elif p81_decision == "blocked":
        reasons.append("p81_blocked_status_preserved")
    elif p81_decision == "rejected":
        reasons.append("p81_rejected_status_preserved")
    if "human_confirmation_required" in scenario.uncertainty:
        reasons.append("human_confirmation_required_before_status_claim")
    if decision == SlackTicketDraftDecision.REJECTED:
        reasons.append("insufficient_evidence_for_status_or_ticket_claims")
    if decision == SlackTicketDraftDecision.DRAFT_READY:
        reasons.append("draft_artifacts_ready_for_human_review")
    return reasons


def _slack_text(scenario: SlackTicketDraftScenario, decision: SlackTicketDraftDecision, evidence_ids: Sequence[str]) -> str:
    citations = f" Evidence: {', '.join(evidence_ids)}."
    if decision == SlackTicketDraftDecision.BLOCKED:
        return f"Draft blocked for {scenario.service}: {scenario.claim}. Escalate to the listed owner; no external message will be sent.{citations}"
    if decision == SlackTicketDraftDecision.REJECTED:
        return f"Investigation-only draft for {scenario.service}: evidence is insufficient for a status or ticket claim.{citations}"
    return f"Draft update for {scenario.service}: {scenario.claim}.{citations}"


def _status_text(scenario: SlackTicketDraftScenario, decision: SlackTicketDraftDecision, evidence_ids: Sequence[str]) -> str:
    if decision == SlackTicketDraftDecision.REJECTED:
        claim = "Investigation is continuing; no customer-impact or remediation claim is made."
    elif decision == SlackTicketDraftDecision.BLOCKED:
        claim = "Sensitive remediation is blocked pending the named human owner."
    else:
        claim = scenario.claim
    return f"{claim} Cited evidence: {', '.join(evidence_ids)}. This is a draft pending approval."


def _ticket_body(scenario: SlackTicketDraftScenario, decision: SlackTicketDraftDecision, evidence_ids: Sequence[str]) -> str:
    uncertainty = ", ".join(scenario.uncertainty) if scenario.uncertainty else "none"
    actions = "; ".join(scenario.next_actions) if scenario.next_actions else "collect additional evidence"
    rollback_id = str(scenario.p81_rollback_draft.get("audit_id", ""))
    rollback_line = f"\nRollback draft: {rollback_id}" if rollback_id else ""
    return (
        f"Decision: {decision.value}\n"
        f"Claim: {scenario.claim}\n"
        f"Evidence IDs: {', '.join(evidence_ids)}\n"
        f"Uncertainty: {uncertainty}\n"
        f"Next actions: {actions}"
        f"{rollback_line}\n"
        "External send/create is disabled; human approval is required."
    )


def _ticket_labels(scenario: SlackTicketDraftScenario, decision: SlackTicketDraftDecision) -> list[str]:
    labels = [str(item) for item in _sequence(scenario.ticket.get("labels", ()))]
    if decision == SlackTicketDraftDecision.REJECTED:
        return ["investigation-only", "insufficient-evidence"]
    return labels or ["incident", decision.value]


def _normalized_p76_gate(scenario: SlackTicketDraftScenario, evidence_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "decision": str(scenario.p76_gate.get("decision", "human_required")),
        "score": _float(scenario.p76_gate.get("score")),
        "evidence_ids": evidence_ids,
        "sources": [str(item) for item in _sequence(scenario.p76_gate.get("sources", ()))],
    }


def _approval_gate(scenario: SlackTicketDraftScenario) -> str:
    p81_decision = str(scenario.p81_rollback_draft.get("decision", "")).lower()
    if p81_decision and p81_decision != "not_applicable":
        return "p81"
    if scenario.p80_approval:
        return "p80"
    return "p82"


def _evidence_ids(scenario: SlackTicketDraftScenario) -> list[str]:
    ids = [item.id for item in scenario.evidence_links]
    if ids:
        return ids
    return [str(item) for item in _sequence(scenario.p76_gate.get("evidence_ids", ()))] or ["missing:evidence"]


def _priority(severity: str) -> str:
    return {"sev1": "P1", "sev2": "P2", "sev3": "P3"}.get(severity, "P3")


def _decision_count(drafts: Sequence[SlackTicketDraftArtifact], decision: SlackTicketDraftDecision) -> int:
    return sum(1 for item in drafts if item.decision == decision)


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0


__all__ = [
    "SlackTicketDraftDecision",
    "SlackTicketDraftReport",
    "evaluate_slack_ticket_draft_fixture",
    "render_slack_ticket_draft_markdown",
    "write_slack_ticket_draft_outputs",
]
