"""Server-rendered local operator dashboard."""

from __future__ import annotations

import json
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ActionProposal, Incident
from app.security.dependencies import get_current_principal
from app.services.authorization import AuthorizationError, require_same_scope
from app.services.decision_trace_service import DecisionTraceEntry, build_decision_trace
from app.services.identity_service import Principal
from app.services.incident_service import get_incident
from app.services.reliability_dashboard import build_reliability_dashboard
from app.services.replay_service import ReplayService, load_replay_scenarios

router = APIRouter(prefix="/operator", tags=["operator"])


def _page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
body{{font-family:system-ui;margin:2rem;line-height:1.45}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ddd;padding:.45rem;text-align:left}}
.pill{{display:inline-block;padding:.15rem .45rem;border-radius:999px;background:#eef}}
code{{background:#f6f6f6;padding:.1rem .25rem}}
</style>
</head><body data-testid="operator-shell"><h1>OpsCat Operator</h1>{body}</body></html>"""
    return HTMLResponse(html)


@router.get("", response_class=HTMLResponse)
def operator_inbox(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> HTMLResponse:
    incidents = db.query(Incident).filter(Incident.tenant_id == principal.tenant_id, Incident.workspace_id == principal.workspace_id).order_by(Incident.created_at.desc()).all()
    rows = []
    for incident in incidents:
        message = str((incident.alert_payload or {}).get("message") or incident.summary or "")
        rows.append(
            '<tr data-testid="incident-row">'
            f"<td><a href='/operator/incidents/{escape(incident.id)}'>{escape(incident.id)}</a></td>"
            f"<td>{escape(incident.service)}</td>"
            f"<td>{escape(incident.environment)}</td>"
            f"<td><span class='pill'>{escape(incident.status)}</span></td>"
            f"<td>{escape(incident.severity)}</td>"
            f"<td>{escape(message)}</td>"
            "</tr>"
        )
    pending_actions = (
        db.query(ActionProposal)
        .filter(
            ActionProposal.tenant_id == principal.tenant_id,
            ActionProposal.workspace_id == principal.workspace_id,
            ActionProposal.requires_approval.is_(True),
            ActionProposal.status.in_(("proposed", "approved")),
        )
        .order_by(ActionProposal.created_at.desc())
        .all()
    )
    pending_rows = []
    for action in pending_actions:
        incident = action.incident
        message = ""
        if incident is not None:
            message = str((incident.alert_payload or {}).get("message") or incident.summary or "")
        pending_rows.append(
            '<tr data-testid="pending-approval-row">'
            f"<td><a href='/operator/actions/{escape(action.id)}'>{escape(action.id)}</a></td>"
            f"<td><a href='/operator/incidents/{escape(action.incident_id)}'>{escape(action.incident_id)}</a></td>"
            f"<td>{escape(action.action_type)}</td>"
            f"<td><code>{escape(action.policy_decision)}</code></td>"
            f"<td><code>{escape(action.risk_level)}</code></td>"
            f"<td>{escape(action.status)}</td>"
            f"<td>{escape(message)}</td>"
            "</tr>"
        )
    try:
        reliability = ReplayService().run()
        reliability_html = (
            '<section data-testid="reliability-dashboard"><h2>P7 Reliability dashboard</h2>'
            f"<p>Accuracy <code>{reliability['dashboard']['accuracy']:.2f}</code> "
            f"Blocked dangerous actions <code>{reliability['dashboard']['blocked_dangerous_actions']}</code> "
            f"Escalation rate <code>{reliability['dashboard']['escalation_rate']:.2f}</code></p></section>"
        )
    except Exception:
        reliability_html = '<section data-testid="reliability-dashboard"><h2>P7 Reliability dashboard</h2><p>Replay metrics unavailable.</p></section>'
    body = (
        f"<p>Workspace: <code>{escape(principal.tenant_id)}/{escape(principal.workspace_id)}</code></p>" + reliability_html + '<section data-testid="pending-approvals">'
        "<h2>Pending approvals</h2>"
        "<p>Review proposed actions here, then approve/reject through the local API instructions on each action page.</p>"
        '<table data-testid="pending-approval-table"><thead><tr>'
        "<th>Action</th><th>Incident</th><th>Type</th><th>Policy</th><th>Risk</th><th>Status</th><th>Summary</th>"
        "</tr></thead>"
        f"<tbody>{''.join(pending_rows)}</tbody></table>"
        "</section>"
        '<section data-testid="incident-inbox">'
        "<h2>Incident inbox</h2>"
        '<table data-testid="incident-table"><thead><tr><th>ID</th><th>Service</th><th>Env</th><th>Status</th><th>Severity</th><th>Summary</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</section>"
    )
    return _page("OpsCat Operator", body)


@router.get("/reliability")
def operator_reliability_dashboard(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> dict[str, object]:
    replay = ReplayService().run_all(load_replay_scenarios())
    dashboard = build_reliability_dashboard(db, replay)
    return {
        "tenant_id": principal.tenant_id,
        "workspace_id": principal.workspace_id,
        "dashboard": dashboard,
        **dashboard,
    }


@router.get("/actions/{action_id}", response_class=HTMLResponse)
def operator_action_detail(action_id: str, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        action = db.query(ActionProposal).filter(ActionProposal.id == action_id).one()
        require_same_scope(principal, action, action="read action")
        incident = get_incident(db, action.incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=404, detail={"message": "action not found", "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:
        raise HTTPException(status_code=404, detail="action not found") from exc

    body = f"""
<p><a href="/operator">← Inbox</a> · <a href="/operator/incidents/{escape(incident.id)}">Incident detail</a></p>
<main data-testid="action-detail">
<h2>Action {escape(action.id)}</h2>
<section data-testid="action-preview">
<h3>{escape(action.action_type)} → {escape(action.target)}</h3>
<p>Status <code>{escape(action.status)}</code> Environment <code>{escape(action.environment)}</code></p>
<p>{escape(action.rationale)}</p>
<h4>Dry-run payload preview</h4>
<pre><code>{escape(_json_block(action.payload))}</code></pre>
</section>
<section data-testid="action-risk">
<h3>Risk and policy</h3>
<p>Risk <code>{escape(action.risk_level)}</code> Policy <code>{escape(action.policy_decision)}</code> Requires approval <code>{action.requires_approval}</code></p>
<ul>{_list_items(action.policy_reasons)}</ul>
</section>
<section data-testid="action-preconditions">
<h3>Preconditions</h3>
<ul>{_list_items(action.preconditions)}</ul>
</section>
<section data-testid="action-post-checks">
<h3>Post-checks</h3>
<ul>{_list_items(action.post_checks)}</ul>
</section>
<section data-testid="action-evidence-ids">
<h3>Evidence IDs</h3>
<ul>{_list_items(action.evidence_ids)}</ul>
</section>
<section data-testid="action-approval-api">
<h3>Approval API instructions</h3>
<p>No browser mutation form is rendered while auth/session work is deferred.</p>
<p>Approve: <code>POST /approvals/{escape(action.id)}</code> with <code>decision=approve</code>.</p>
<p>Reject: <code>POST /approvals/{escape(action.id)}</code> with <code>decision=reject</code>.</p>
</section>
</main>
"""
    return _page(f"OpsCat Action {action.id}", body)


@router.get("/incidents/{incident_id}", response_class=HTMLResponse)
def operator_incident_detail(incident_id: str, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        incident = get_incident(db, incident_id, principal=principal)
    except AuthorizationError as exc:
        raise HTTPException(status_code=404, detail={"message": "incident not found", "workspace_id": exc.workspace_id}) from exc
    except Exception as exc:
        raise HTTPException(status_code=404, detail="incident not found") from exc

    evidence = "".join(f"<li><code>{escape(item.id)}</code> {escape(item.type)} — {escape(item.content)}</li>" for item in incident.evidence)
    timeline = "".join(f"<li>{escape(event.event_type)} — {escape(event.content)}</li>" for event in incident.timeline)
    decision_trace = _decision_trace_table(build_decision_trace(incident))
    action_blocks = []
    for action in incident.actions:
        attempts = "".join(f"<li><code>{escape(attempt.id)}</code> #{attempt.attempt_number} {escape(attempt.status)} retry={attempt.retry_eligible}</li>" for attempt in action.execution_attempts)
        affordance = (
            f"<p><strong>Approve</strong>: POST JSON to <code>/approvals/{escape(action.id)}</code> with decision=approve.</p>"
            if action.status in {"proposed", "approved"}
            else "<span>approval_granted</span>"
        )
        action_blocks.append(
            '<section data-testid="action-card">'
            f"<h3>{escape(action.action_type)} → {escape(action.target)}</h3>"
            f"<p>Policy: <code>{escape(action.policy_decision)}</code> Risk: <code>{escape(action.risk_level)}</code> Status: <code>{escape(action.status)}</code></p>"
            f"<p>{escape(action.rationale)}</p>{affordance}"
            f'<h4>Execution attempts</h4><ul data-testid="execution-attempt-list">{attempts}</ul>'
            "</section>"
        )
    body = f"""
<p><a href="/operator">← Inbox</a></p>
<main data-testid="incident-detail">
<h2>Incident {escape(incident.id)}</h2>
<p>Status <span class="pill">{escape(incident.status)}</span> Service <code>{escape(incident.service)}</code> Severity <code>{escape(incident.severity)}</code></p>
<p>{escape(incident.summary or "")}</p>
{_p8_war_room_panel(incident)}
<h2>Decision trace</h2>{decision_trace}
<h2>Evidence</h2><ul data-testid="evidence-list">{evidence}</ul>
<h2>Timeline</h2><ul data-testid="timeline-list">{timeline}</ul>
<h2>Actions</h2>{"".join(action_blocks)}
<h2>Report</h2>
<p>
  <a data-testid="report-link" href="/incidents/{escape(incident.id)}/report">Open report JSON</a>
  ·
  <a data-testid="trace-link" href="/incidents/{escape(incident.id)}/trace">Open trace JSON/Markdown</a>
</p>
</main>
"""
    return _page(f"OpsCat Incident {incident.id}", body)


def _p8_war_room_panel(incident: Incident) -> str:
    action = incident.actions[0] if incident.actions else None
    reliability_score = incident.confidence if incident.confidence is not None else 0.0
    policy_decision = action.policy_decision if action is not None else "REVIEW"
    action_status = action.status if action is not None else "none"
    action_target = action.target if action is not None else "no action proposed"
    runbook_evidence = next((item.content for item in incident.evidence if item.type == "runbook"), "Runbook critique unavailable; keep diagnostic-only review until trusted runbook evidence exists.")
    critique = _payload_section(action.payload if action is not None else None, "self_critique")
    missing_evidence = critique.get("missing_evidence", []) if critique else []
    human_question = (
        "Can the operator confirm the proposed local/mock remediation and any missing evidence before approval?"
        if missing_evidence
        else "Does the operator agree this local/mock action remains bounded, reversible, and approval-gated?"
    )
    return f"""
<section data-testid="p8-war-room">
<h2>P8 War Room</h2>
<p><strong>P8 flow:</strong> alert -> war room -> score -> runbook critique -> action gate -> report.</p>
<p>This portfolio demo is <strong>local/mock</strong>; it does not claim unattended production operation.</p>
<section data-testid="p8-reliability-score">
<h3>Reliability score</h3>
<p><code>{reliability_score:.2f}</code> from deterministic incident confidence; hard policy gates still decide whether action is allowed.</p>
</section>
<section data-testid="p8-runbook-critique">
<h3>Runbook critique</h3>
<p>{escape(str(runbook_evidence))}</p>
<p>Missing evidence: <code>{escape(_json_block(missing_evidence))}</code></p>
</section>
<section data-testid="p8-human-questions">
<h3>Human questions</h3>
<ul><li>{escape(human_question)}</li></ul>
</section>
<section data-testid="p8-action-gate">
<h3>Action gate</h3>
<p>Policy <code>{escape(policy_decision)}</code>; status <code>{escape(action_status)}</code>; target <code>{escape(action_target)}</code>.</p>
<p>Browser mutation forms remain absent while auth/session work is deferred.</p>
</section>
<section data-testid="p8-report-export">
<h3>Report export</h3>
<p>Use the report links below to review redacted JSON/Markdown evidence for the war-room decision.</p>
</section>
</section>
"""



def _payload_section(payload: dict[str, object] | None, key: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}

def _decision_trace_table(entries: list[DecisionTraceEntry]) -> str:
    rows = []
    for entry in entries:
        details = _json_block(entry.details)
        rows.append(
            '<tr data-testid="decision-trace-row" data-stage="'
            f'{escape(entry.stage)}">'
            f"<td><code>{escape(entry.stage)}</code></td>"
            f"<td>{escape(entry.title)}</td>"
            f"<td>{escape(entry.summary)}</td>"
            f"<td>{escape(entry.actor)}</td>"
            f"<td>{escape(entry.status or '')}</td>"
            f"<td>{escape(entry.policy_decision or '')}</td>"
            f"<td>{escape(entry.risk_level or '')}</td>"
            f"<td><code>{escape(details)}</code></td>"
            "</tr>"
        )
    return (
        '<table data-testid="decision-trace"><thead><tr>'
        "<th>Stage</th><th>Decision</th><th>Summary</th><th>Actor</th><th>Status</th><th>Policy</th><th>Risk</th><th>Details</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _list_items(values: list[str]) -> str:
    if not values:
        return "<li>None recorded</li>"
    return "".join(f"<li><code>{escape(str(value))}</code></li>" for value in values)


def _json_block(value: object) -> str:
    return json.dumps(value or {}, indent=2, sort_keys=True, default=str)
