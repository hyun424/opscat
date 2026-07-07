"""Immutable action execution attempt recording."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from app.models import ActionExecutionAttempt, ActionProposal, Incident
from app.models.action import ActionRequest
from app.services.action_simulator import ActionSimulator
from app.services.redaction import redact_text, redact_value


def start_action_attempt(db: Session, incident: Incident, action: ActionProposal, *, idempotency_key: str | None = None) -> ActionExecutionAttempt:
    existing_count = db.query(ActionExecutionAttempt).filter(ActionExecutionAttempt.action_id == action.id).count()
    attempt = ActionExecutionAttempt(
        action_id=action.id,
        incident_id=incident.id,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        attempt_number=existing_count + 1,
        idempotency_key=idempotency_key or f"{action.id}:{existing_count + 1}",
        status="running",
        precondition_result={
            "ok": True,
            "checks": list(action.preconditions or []),
            "dry_run_payload": dict(action.payload or {}),
            "rollback_metadata": _rollback_metadata(action),
            "simulation": _simulation_metadata(incident, action),
            "policy_decision_id": f"{action.policy_decision}:{action.id}",
        },
    )
    db.add(attempt)
    db.flush()
    return attempt


def record_execution_result(db: Session, attempt: ActionExecutionAttempt, result: dict[str, Any]) -> None:
    redacted = cast(dict[str, Any], redact_value(result))
    attempt.execution_result = redacted
    if not bool(result.get("ok")):
        attempt.status = "execution_failed"
        attempt.retry_eligible = True
        attempt.failure_class = "execution_failed"
        attempt.error = redact_text(str(result.get("message") or "execution failed"))
        attempt.finished_at = datetime.now(UTC)
    db.add(attempt)


def record_post_check_result(db: Session, attempt: ActionExecutionAttempt, verification: dict[str, Any]) -> None:
    redacted = cast(dict[str, Any], redact_value(verification))
    attempt.post_check_result = redacted
    if bool(verification.get("recovered")):
        attempt.status = "succeeded"
        attempt.retry_eligible = False
        attempt.failure_class = None
        attempt.error = None
    else:
        attempt.status = "post_check_failed"
        attempt.retry_eligible = True
        attempt.failure_class = "post_check_failed"
        attempt.error = redact_text(str(verification.get("message") or "post-check failed"))
    attempt.finished_at = datetime.now(UTC)
    db.add(attempt)


def _rollback_metadata(action: ActionProposal) -> dict[str, Any]:
    if not any(token in action.action_type for token in ("rollback", "restart", "ticket")):
        return {"required": False}
    expectation = "mock/local only; no external mutation"
    if "rollback" in action.action_type:
        expectation = "rollback artifact is a draft/mock PR until approved and verified"
    elif "restart" in action.action_type:
        expectation = "restart is simulated for a single non-production worker"
    return {"required": True, "expectation": expectation, "post_checks": list(action.post_checks or [])}


def _simulation_metadata(incident: Incident, action: ActionProposal) -> dict[str, Any]:
    request = ActionRequest(
        action_type=action.action_type,
        target=action.target,
        environment=action.environment or incident.environment,
        tenant_id=incident.tenant_id,
        workspace_id=incident.workspace_id,
        payload=action.payload or {},
        incident_id=incident.id,
        approved=True,
    )
    return ActionSimulator().simulate(request).to_dict()
