from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Incident
from app.services.redaction import redact_text, redact_value


def render_incident_report(incident: Incident) -> str:
    lines = [
        f"# Incident Report: {incident.id}",
        "",
        f"- Status: {incident.status}",
        f"- Service: {incident.service}",
        f"- Environment: {incident.environment}",
        f"- Tenant: {incident.tenant_id}",
        f"- Workspace: {incident.workspace_id}",
        f"- Severity: {incident.severity}",
        f"- Summary: {redact_text(incident.summary or '')}",
        f"- Root cause candidate: {redact_text(incident.root_cause_candidate or '')}",
        f"- Confidence: {incident.confidence}",
        "",
        "## Evidence",
    ]
    for evidence in incident.evidence:
        lines.append(f"- `{evidence.id}` {evidence.type}: {redact_text(evidence.content)}")
    lines.extend(["", "## Actions"])
    for action in incident.actions:
        lines.append(f"- `{action.id}` {action.action_type} status={action.status} risk={action.risk_level} policy={action.policy_decision}")
        lines.append(f"  - Rationale: {redact_text(action.rationale)}")
        lines.append(f"  - Post-checks: {', '.join(action.post_checks)}")
        critique = (action.payload or {}).get("self_critique", {})
        if critique:
            lines.append(f"  - Self-critique: ambiguity={critique.get('ambiguity')} blocks_auto_action={critique.get('blocks_auto_action')}")
        blast_radius = (action.payload or {}).get("blast_radius", {})
        if blast_radius:
            lines.append(f"  - Blast radius: scope={blast_radius.get('scope')} rollback_available={blast_radius.get('rollback_available')}")
        simulation = (action.payload or {}).get("simulation", {})
        if simulation:
            lines.append(f"  - Simulation: ok={simulation.get('ok')} touched={', '.join(str(item) for item in simulation.get('touched_resources', []))}")
        if action.execution_result:
            lines.append(f"  - Execution result: {redact_value(action.execution_result)}")
    lines.extend(["", "## Failure modes"])
    if not incident.actions:
        lines.append("- No action was proposed; human review is required before remediation.")
    for action in incident.actions:
        critique = (action.payload or {}).get("self_critique", {})
        simulation = (action.payload or {}).get("simulation", {})
        blast_radius = (action.payload or {}).get("blast_radius", {})
        reasons = list(action.policy_reasons or [])
        if critique.get("missing_evidence"):
            reasons.append("missing evidence: " + ", ".join(str(item) for item in critique["missing_evidence"]))
        if critique.get("alternate_causes"):
            reasons.append("alternate hypotheses: " + ", ".join(str(item) for item in critique["alternate_causes"]))
        if simulation and not simulation.get("ok"):
            reasons.append("simulation failed before execution")
        if blast_radius and blast_radius.get("scope") in {"unknown", "prohibited", "global", "tenant"}:
            reasons.append(f"blast radius {blast_radius.get('scope')} requires human review")
        if not reasons:
            reasons.append("No blocking failure mode detected in local/mock evidence.")
        lines.append(f"- `{action.id}` uncertainty/blocked-action analysis: {redact_text('; '.join(reasons))}")
    lines.extend(["", "## Timeline"])
    for event in incident.timeline:
        lines.append(f"- {event.timestamp.isoformat()} [{event.actor}] {event.event_type}: {redact_text(event.content)}")
    return "\n".join(lines) + "\n"


def save_incident_report(db: Session, incident: Incident) -> str:
    db.refresh(incident)
    settings = get_settings()
    report_dir = Path(settings.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"incident-{incident.id}.md"
    path.write_text(render_incident_report(incident), encoding="utf-8")
    return str(path)


def _render_failure_mode_analysis(incident: Incident) -> list[str]:
    confidence = incident.confidence
    uncertainty = _failure_mode_uncertainty(incident)
    alternate_hypotheses = _alternate_hypotheses(incident)
    missing_evidence = _missing_evidence(incident)
    blocked_actions = _blocked_actions(incident)
    escalation_reasons = _escalation_reasons(incident)

    lines = [
        "",
        "## Failure Mode Analysis",
        f"- Uncertainty: {redact_text(uncertainty)}",
        f"- Confidence basis: {confidence if confidence is not None else 'unknown'}",
        "- Alternate hypotheses:",
    ]
    lines.extend(f"  - {redact_text(item)}" for item in alternate_hypotheses)
    lines.append("- Missing evidence:")
    lines.extend(f"  - {redact_text(item)}" for item in missing_evidence)
    lines.append("- Blocked actions:")
    lines.extend(f"  - {redact_text(item)}" for item in blocked_actions)
    lines.append("- Escalation reasons:")
    lines.extend(f"  - {redact_text(item)}" for item in escalation_reasons)
    lines.append(f"- Recommended next action: {redact_text(_recommended_next_action(incident, escalation_reasons))}")
    return lines


def _failure_mode_uncertainty(incident: Incident) -> str:
    if incident.confidence is None:
        return "No calibrated confidence was recorded; fail closed and require human review."
    if incident.confidence < 0.70:
        return "Diagnosis confidence is below the automatic-action threshold; similar symptoms may have another root cause."
    if any(action.status in {"denied", "escalated", "failed", "rejected"} for action in incident.actions):
        return "A policy, operator, or verification gate blocked at least one action; the proposed remediation may be unsafe or incomplete."
    if incident.status in {"waiting_approval", "escalated"}:
        return "Incident has not reached an autonomously verified terminal success state."
    return "No active failure-mode warnings were detected in the local/mock evidence, but production safety is not implied."


def _alternate_hypotheses(incident: Incident) -> list[str]:
    hypotheses: list[str] = []
    for action in incident.actions:
        payload = action.escalation_payload or {}
        for hypothesis in _list_payload(payload.get("hypotheses")):
            if isinstance(hypothesis, dict):
                title = str(hypothesis.get("title") or "Unknown alternate hypothesis")
                status = hypothesis.get("status")
                confidence = hypothesis.get("confidence")
                hypotheses.append(f"{title} (status={status}, confidence={confidence})")
    if incident.root_cause_candidate:
        hypotheses.append(f"Top candidate may be wrong: {incident.root_cause_candidate}")
    scenario = str(incident.alert_payload.get("scenario", ""))
    if "ambiguous" in scenario or "conflicting" in scenario:
        hypotheses.append("Signals are ambiguous or conflicting; alternate infrastructure, deploy, or provider causes remain plausible.")
    if not hypotheses:
        hypotheses.append("No explicit alternate hypothesis was recorded; operator should review raw evidence before approving mutation.")
    return _unique(hypotheses)


def _missing_evidence(incident: Incident) -> list[str]:
    missing: list[str] = []
    if len(incident.evidence) < 2:
        missing.append("At least two independent evidence records are required before action.")
    if incident.confidence is None or incident.confidence < 0.70:
        missing.append("Additional corroborating logs, metrics, or deploy markers are needed before auto-remediation.")
    for action in incident.actions:
        if not action.preconditions:
            missing.append(f"{action.action_type} has no recorded preconditions.")
        if not action.post_checks:
            missing.append(f"{action.action_type} has no recorded post-checks.")
        if action.policy_decision in {"DENY", "ESCALATE"}:
            missing.append(f"Safe bounded alternative for {action.action_type} was not established.")
    if not missing:
        missing.append("No missing evidence was detected by deterministic report checks.")
    return _unique(missing)


def _blocked_actions(incident: Incident) -> list[str]:
    blocked: list[str] = []
    blocked_statuses = {"denied", "escalated", "failed", "proposed", "rejected"}
    for action in incident.actions:
        if action.status in blocked_statuses or action.policy_decision in {"DENY", "ESCALATE", "REQUIRE_APPROVAL"}:
            reason = action.escalation_reason or "; ".join(action.policy_reasons) or "human approval or safer evidence required"
            blocked.append(f"{action.action_type} status={action.status} policy={action.policy_decision} risk={action.risk_level}: {reason}")
    if not blocked:
        blocked.append("None recorded; no denied, escalated, rejected, failed, or approval-waiting action is present.")
    return _unique(blocked)


def _escalation_reasons(incident: Incident) -> list[str]:
    reasons: list[str] = []
    for action in incident.actions:
        payload = action.escalation_payload or {}
        reasons.extend(str(item) for item in _list_payload(payload.get("triggers")))
        if action.escalation_reason:
            reasons.append(action.escalation_reason)
        reasons.extend(str(item) for item in action.policy_reasons)
    for event in incident.timeline:
        metadata = event.event_metadata if hasattr(event, "event_metadata") else {}
        if isinstance(metadata, dict):
            reasons.extend(str(item) for item in _list_payload(metadata.get("triggers")))
            trigger = metadata.get("trigger")
            if trigger:
                reasons.append(str(trigger))
    if incident.status == "waiting_approval":
        reasons.append("waiting_for_human_approval")
    if not reasons:
        reasons.append("No escalation trigger recorded.")
    return _unique(reasons)


def _recommended_next_action(incident: Incident, escalation_reasons: list[str]) -> str:
    if any(reason == "policy_denied_action" for reason in escalation_reasons):
        return "Do not execute denied/prohibited action; choose a safer local/mock runbook or keep human escalation open."
    if any(reason == "low_confidence" for reason in escalation_reasons):
        return "Collect more corroborating evidence and keep automation blocked until confidence is calibrated."
    if incident.status == "waiting_approval":
        return "Review cited evidence, blast radius, and post-checks before approving or rejecting the action."
    if incident.status == "resolved":
        return "Review verification evidence and capture lessons learned for future incident memory."
    return "Review failure modes with a human operator before attempting further remediation."


def _list_payload(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
