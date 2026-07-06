from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import ActionProposal, Incident
from app.services.risk_engine import get_action_definition


def execute_mock_action(db: Session, incident: Incident, action: ActionProposal) -> dict[str, Any]:
    definition = get_action_definition(action.action_type)
    if action.action_type == "mock.create_rollback_pr":
        result = {
            "ok": True,
            "kind": "mock_pull_request",
            "url": f"mock://github/{incident.service}/pull/rollback-{incident.id[:8]}",
            "title": f"Rollback {incident.service} {action.payload.get('from_version')} -> {action.payload.get('to_version')}",
            "deployed": False,
        }
    elif action.action_type == "mock.create_incident_ticket":
        result = {
            "ok": True,
            "kind": "mock_ticket",
            "url": f"mock://tickets/{incident.id[:8]}",
            "title": f"Incident follow-up for {incident.service}",
        }
    elif action.action_type == "mock.execute_restart_worker":
        result = {
            "ok": True,
            "kind": "mock_worker_restart",
            "target": action.target,
            "restarted_at": datetime.now(UTC).isoformat(),
        }
    else:
        result = {"ok": False, "kind": "unknown", "error": f"No mock executor for {action.action_type}"}
    result["risk"] = definition.base_risk
    result["post_checks"] = list(definition.post_checks or action.post_checks)
    action.execution_result = result
    action.status = "executed" if result["ok"] else "failed"
    db.add(action)
    return result


def verify_recovery(incident: Incident, action: ActionProposal) -> dict[str, Any]:
    if action.status != "executed":
        return {"recovered": False, "error_rate_per_minute": 180, "reason": "action not executed"}
    if incident.service == "worker":
        return {"recovered": True, "queue_latency_p95_seconds": 35, "worker_heartbeat": "healthy"}
    return {"recovered": True, "error_rate_per_minute": 3, "baseline_error_rate_per_minute": 2}
