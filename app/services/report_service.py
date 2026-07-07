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
        critique = _payload_section(action.payload, "self_critique")
        blast_radius = _payload_section(action.payload, "blast_radius")
        simulation = _payload_section(action.payload, "simulation")
        memory = _payload_section(action.payload, "incident_memory")
        if critique:
            lines.append(f"  - Self-critique: {redact_value(critique)}")
        if blast_radius:
            lines.append(f"  - Blast radius: {redact_value(blast_radius)}")
        if simulation:
            lines.append(f"  - Simulation: {redact_value(simulation)}")
        if memory:
            lines.append(f"  - Incident memory: {redact_value(memory)}")
        if action.execution_result:
            lines.append(f"  - Execution result: {redact_value(action.execution_result)}")
    lines.extend(["", "## Failure modes"])
    if incident.actions:
        for action in incident.actions:
            critique = _payload_section(action.payload, "self_critique")
            simulation = _payload_section(action.payload, "simulation")
            memory = _payload_section(action.payload, "incident_memory")
            missing = critique.get("missing_evidence", []) if critique else []
            alternate = critique.get("alternate_causes", []) if critique else []
            objections = critique.get("action_risk_objections", []) if critique else []
            blocked = action.status in {"denied", "escalated", "failed"} or bool(missing or objections) or (simulation and simulation.get("status") != "passed")
            lines.append(f"- `{action.id}` uncertainty: missing_evidence={redact_value(missing)} alternate_hypotheses={redact_value(alternate)}")
            lines.append(f"  - Blocked action: {blocked}; escalation reason: {redact_text(action.escalation_reason or '; '.join(action.policy_reasons) or 'none')}")
            if memory:
                lines.append(f"  - Prior-outcome warnings: {redact_value(memory.get('warnings', []))}")
    else:
        lines.append("- No action was proposed; human review required before remediation.")
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


def _payload_section(payload: dict[str, object] | None, key: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}
