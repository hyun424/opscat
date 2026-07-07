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
        for reason in action.policy_reasons or []:
            modes.append(str(reason))
        payload = action.payload or {}
        critique = payload.get("self_critique") if isinstance(payload, dict) else None
        if isinstance(critique, dict):
            modes.extend(str(reason) for reason in critique.get("reasons", []))
        simulation = payload.get("simulation") if isinstance(payload, dict) else None
        if isinstance(simulation, dict) and not simulation.get("success", True):
            modes.append("action simulation failed before execution")
        if action.status in {"denied", "escalated"}:
            modes.append(f"action {action.action_type} ended in {action.status}")
    return list(dict.fromkeys(mode for mode in modes if mode))
