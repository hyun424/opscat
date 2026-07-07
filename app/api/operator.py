"""Server-rendered local operator dashboard."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Incident
from app.security.dependencies import get_current_principal
from app.services.authorization import AuthorizationError
from app.services.identity_service import Principal
from app.services.incident_service import get_incident

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
</head><body><h1>OpsCat Operator</h1>{body}</body></html>"""
    return HTMLResponse(html)


@router.get("", response_class=HTMLResponse)
def operator_inbox(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> HTMLResponse:
    incidents = (
        db.query(Incident)
        .filter(Incident.tenant_id == principal.tenant_id, Incident.workspace_id == principal.workspace_id)
        .order_by(Incident.created_at.desc())
        .all()
    )
    rows = []
    for incident in incidents:
        message = str((incident.alert_payload or {}).get("message") or incident.summary or "")
        rows.append(
            "<tr>"
            f"<td><a href='/operator/incidents/{escape(incident.id)}'>{escape(incident.id)}</a></td>"
            f"<td>{escape(incident.service)}</td>"
            f"<td>{escape(incident.environment)}</td>"
            f"<td><span class='pill'>{escape(incident.status)}</span></td>"
            f"<td>{escape(incident.severity)}</td>"
            f"<td>{escape(message)}</td>"
            "</tr>"
        )
    body = (
        f"<p>Workspace: <code>{escape(principal.tenant_id)}/{escape(principal.workspace_id)}</code></p>"
        "<h2>Incident inbox</h2>"
        "<table><thead><tr><th>ID</th><th>Service</th><th>Env</th><th>Status</th><th>Severity</th><th>Summary</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return _page("OpsCat Operator", body)


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
    action_blocks = []
    for action in incident.actions:
        attempts = "".join(
            f"<li><code>{escape(attempt.id)}</code> #{attempt.attempt_number} {escape(attempt.status)} retry={attempt.retry_eligible}</li>"
            for attempt in action.execution_attempts
        )
        affordance = (
            f"<p><strong>Approve</strong>: POST JSON to <code>/approvals/{escape(action.id)}</code> with decision=approve.</p>"
            if action.status in {"proposed", "approved"}
            else "<span>approval_granted</span>"
        )
        action_blocks.append(
            "<section>"
            f"<h3>{escape(action.action_type)} → {escape(action.target)}</h3>"
            f"<p>Policy: <code>{escape(action.policy_decision)}</code> Risk: <code>{escape(action.risk_level)}</code> Status: <code>{escape(action.status)}</code></p>"
            f"<p>{escape(action.rationale)}</p>{affordance}"
            f"<h4>Execution attempts</h4><ul>{attempts}</ul>"
            "</section>"
        )
    body = f"""
<p><a href="/operator">← Inbox</a></p>
<h2>Incident {escape(incident.id)}</h2>
<p>Status <span class="pill">{escape(incident.status)}</span> Service <code>{escape(incident.service)}</code> Severity <code>{escape(incident.severity)}</code></p>
<p>{escape(incident.summary or '')}</p>
<h2>Evidence</h2><ul>{evidence}</ul>
<h2>Timeline</h2><ul>{timeline}</ul>
<h2>Actions</h2>{''.join(action_blocks)}
<h2>Report</h2><p><a href="/incidents/{escape(incident.id)}/report">Open report JSON</a></p>
"""
    return _page(f"OpsCat Incident {incident.id}", body)
