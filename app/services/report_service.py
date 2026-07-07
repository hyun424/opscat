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
    lines.extend(["", "## Failure Mode Analysis"])
    failure_modes = _failure_modes(incident)
    if failure_modes:
        for mode in failure_modes:
            lines.append(f"- {redact_text(mode)}")
    else:
        lines.append("- No deterministic failure-mode blockers recorded; continue to verify post-checks.")
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


def _failure_modes(incident: Incident) -> list[str]:
    modes: list[str] = []
    if incident.confidence is None or incident.confidence < 0.7:
        modes.append("low confidence may make the diagnosis wrong")
    if not incident.evidence or len(incident.evidence) < 2:
        modes.append("missing evidence limits confidence")
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
    alert_payload = incident.alert_payload or {}
    scenario = str(alert_payload.get("scenario", ""))
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
