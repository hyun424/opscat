from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Incident


def render_incident_report(incident: Incident) -> str:
    lines = [
        f"# Incident Report: {incident.id}",
        "",
        f"- Status: {incident.status}",
        f"- Service: {incident.service}",
        f"- Environment: {incident.environment}",
        f"- Severity: {incident.severity}",
        f"- Summary: {incident.summary}",
        f"- Root cause candidate: {incident.root_cause_candidate}",
        f"- Confidence: {incident.confidence}",
        "",
        "## Evidence",
    ]
    for evidence in incident.evidence:
        lines.append(f"- `{evidence.id}` {evidence.type}: {evidence.content}")
    lines.extend(["", "## Actions"])
    for action in incident.actions:
        lines.append(
            f"- `{action.id}` {action.action_type} status={action.status} risk={action.risk_level} policy={action.policy_decision}"
        )
        lines.append(f"  - Rationale: {action.rationale}")
        lines.append(f"  - Post-checks: {', '.join(action.post_checks)}")
        if action.execution_result:
            lines.append(f"  - Execution result: {action.execution_result}")
    lines.extend(["", "## Timeline"])
    for event in incident.timeline:
        lines.append(f"- {event.timestamp.isoformat()} [{event.actor}] {event.event_type}: {event.content}")
    return "\n".join(lines) + "\n"


def save_incident_report(db: Session, incident: Incident) -> str:
    db.refresh(incident)
    settings = get_settings()
    report_dir = Path(settings.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"incident-{incident.id}.md"
    path.write_text(render_incident_report(incident), encoding="utf-8")
    return str(path)
