from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Incident
from app.services.redaction import redact_text, redact_value
from app.services.war_room_service import build_war_room


def render_incident_report(incident: Incident) -> str:
    war_room = build_war_room(incident)
    lines = _render_war_room_markdown(war_room) + [
        "",
        f"## Incident Report: {incident.id}",
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
        latest_attempt = action.execution_attempts[-1] if action.execution_attempts else None
        if latest_attempt and latest_attempt.precondition_result.get("simulation"):
            simulation = latest_attempt.precondition_result["simulation"]
            blast_radius = simulation.get("blast_radius", {})
            lines.append("  - Simulation:")
            lines.append(f"    - Status: {redact_text(str(simulation.get('status', 'unknown')))}")
            lines.append(f"    - Blast radius: {redact_text(str(blast_radius.get('level', 'unknown')))}")
            lines.append(f"    - Expected effect: {redact_text(str(simulation.get('expected_effect', '')))}")
            if simulation.get("rollback_path"):
                lines.append(f"    - Rollback path: {redact_text(str(simulation.get('rollback_path')))}")
        if action.execution_result:
            lines.append(f"  - Execution result: {redact_value(action.execution_result)}")
    lines.extend(["", "## Failure Mode Analysis"])
    if incident.actions:
        for action in incident.actions:
            critique = _payload_section(action.payload, "self_critique")
            simulation = _payload_section(action.payload, "simulation")
            memory = _payload_section(action.payload, "incident_memory")
            missing = critique.get("missing_evidence", []) if critique else []
            alternate = critique.get("alternate_causes", []) if critique else []
            objections = critique.get("action_risk_objections", []) if critique else []
            blocked = action.status in {"denied", "escalated", "failed"} or bool(missing or objections) or (simulation and simulation.get("status") != "passed")
            escalation_reason = redact_text(action.escalation_reason or "; ".join(action.policy_reasons) or "none")
            lines.append(f"- `{action.id}` Failure Mode Analysis")
            lines.append(f"  - Uncertainty: confidence={incident.confidence}")
            lines.append(f"  - Missing evidence: {redact_value(missing)}")
            lines.append(f"  - Alternate hypotheses: {redact_value(alternate)}")
            lines.append(f"  - Blocked actions: {blocked}")
            lines.append(f"  - Escalation reasons: {escalation_reason}")
            if action.policy_decision in {"DENY", "ESCALATE"} or action.status in {"denied", "escalated"}:
                lines.append("  - Do not execute denied/prohibited action without a safer human-approved runbook.")
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


def _render_war_room_markdown(war_room: dict[str, object]) -> list[str]:
    reliability = _as_dict(war_room.get("reliability_score"))
    final_decision = _as_dict(war_room.get("final_decision"))
    commander = _as_dict(war_room.get("commander"))
    readiness = _as_dict(commander.get("readiness"))
    response_plan = _as_dict(commander.get("response_plan"))
    graph = _as_dict(commander.get("evidence_graph"))
    verification = _as_dict(commander.get("recovery_verification"))
    learning = _as_dict(commander.get("learning_signal"))
    impact = _as_dict(war_room.get("impact"))
    lines = [
        f"# War Room Report: {war_room.get('incident_id', 'unknown')}",
        "",
        "## Incident Summary",
        f"- Status: {redact_text(str(war_room.get('status', 'unknown')))}",
        f"- Service: {redact_text(str(war_room.get('service', 'unknown')))}",
        f"- Environment: {redact_text(str(war_room.get('environment', 'unknown')))}",
        f"- Summary: {redact_text(str(war_room.get('summary', '')))}",
        "",
        "## Impact",
        f"- Severity: {redact_text(str(war_room.get('severity', 'unknown')))}",
        f"- Summary: {redact_text(str(impact.get('summary', '')))}",
        "",
        "## Timeline",
    ]
    for item in _as_list(war_room.get("timeline")):
        row = _as_dict(item)
        if row:
            timestamp = redact_text(str(row.get("timestamp", "")))
            event_type = redact_text(str(row.get("event_type", "event")))
            content = redact_text(str(row.get("content", "")))
            lines.append(f"- {timestamp} {event_type}: {content}")
    lines.extend(["", "## Evidence"])
    for item in _as_list(war_room.get("evidence")):
        row = _as_dict(item)
        if row:
            evidence_id = redact_text(str(row.get("id", "")))
            evidence_type = redact_text(str(row.get("type", "evidence")))
            content = redact_text(str(row.get("content", "")))
            lines.append(f"- `{evidence_id}` {evidence_type}: {content}")
    lines.extend(["", "## Hypotheses"])
    for item in _as_list(war_room.get("hypotheses")):
        row = _as_dict(item)
        if row:
            title = redact_text(str(row.get("title", row.get("hypothesis", "Unknown"))))
            confidence = redact_text(str(row.get("confidence", "unknown")))
            status = redact_text(str(row.get("status", "unknown")))
            lines.append(f"- {title} confidence={confidence} status={status}")
    lines.extend([
        "",
        "## P9 Autonomous Incident Commander",
        f"- Readiness route: {redact_text(str(readiness.get('route', 'unknown')))}",
        f"- Readiness score: {redact_text(str(readiness.get('score', 'unknown')))}",
        f"- Response plan: {redact_text(str(response_plan.get('runbook_key', 'unknown')))} / {redact_text(str(response_plan.get('route', 'unknown')))}",
        f"- Evidence graph: nodes={redact_text(str(_as_dict(graph.get('summary')).get('node_count', 0)))} edges={redact_text(str(_as_dict(graph.get('summary')).get('edge_count', 0)))}",
        f"- Recovery verification: {redact_text(str(verification.get('status', 'unknown')))}",
        f"- Learning signal: {redact_text(str(learning.get('route', 'unknown')))}",
        f"- Next action: {redact_text(str(commander.get('next_action', 'unknown')))}",
        "- Boundary: local/mock only; no auth/session work; no unattended production operation.",
        "",
        "## Reliability Score",
        f"- Score: {redact_text(str(reliability.get('score', 'unknown')))}",
        f"- Band: {redact_text(str(reliability.get('band', 'unknown')))}",
        "",
        "## Policy Gates",
    ])
    for item in _as_list(war_room.get("policy_gates")):
        row = _as_dict(item)
        if row:
            name = redact_text(str(row.get("name", "gate")))
            status = redact_text(str(row.get("status", "unknown")))
            reason = redact_text(str(row.get("reason", "")))
            lines.append(f"- {name}: {status} — {reason}")
    critique = _as_dict(war_room.get("runbook_critique"))
    lines.extend([
        "",
        "## Runbook Critique",
        f"- Fit: {redact_text(str(critique.get('fit', 'unknown')))}",
        f"- Suggestions: {redact_value(critique.get('suggestions', []))}",
        "",
        "## Human Questions",
    ])
    for item in _as_list(war_room.get("human_questions")):
        row = _as_dict(item)
        if row:
            question = redact_text(str(row.get("question", "")))
            why = redact_text(str(row.get("why_it_matters", "")))
            lines.append(f"- {question} Why: {why}")
    lines.extend([
        "",
        "## Final Decision",
        f"- Route: {redact_text(str(final_decision.get('route', 'unknown')))}",
        f"- Summary: {redact_text(str(final_decision.get('summary', '')))}",
    ])
    return lines

def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
