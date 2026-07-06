"""Safe mock action execution for OpsCat MVP.

This module intentionally performs no external network calls, production mutations, or
shell execution. It returns deterministic artifacts for demos and tests.
"""

from __future__ import annotations

from hashlib import sha1
from typing import Any

from app.models.action import ActionExecutionResult, ActionRequest, ActionStatus


class MockActionExecutor:
    def execute(self, request: ActionRequest) -> ActionExecutionResult:
        handlers = {
            "mock.create_incident_ticket": self._create_incident_ticket,
            "mock.create_rollback_pr": self._create_rollback_pr,
            "mock.execute_restart_worker": self._restart_worker,
            "mock.verify_recovery": self._verify_recovery,
            "report.generate": self._generate_report,
            "timeline.add_note": self._add_timeline_note,
        }
        handler = handlers.get(request.action_type)
        if handler is None:
            return ActionExecutionResult(
                action_type=request.action_type,
                target=request.target,
                status=ActionStatus.FAILED,
                message="No mock executor registered for action.",
            )
        return handler(request)

    def _create_incident_ticket(self, request: ActionRequest) -> ActionExecutionResult:
        ticket_id = "OPSCAT-" + _stable_suffix(request)
        return ActionExecutionResult(
            action_type=request.action_type,
            target=request.target,
            status=ActionStatus.EXECUTED,
            message="Mock incident ticket created.",
            output={
                "ticket_id": ticket_id,
                "title": request.payload.get("title", "OpsCat incident"),
            },
            verification={"ticket_id_recorded": True},
        )

    def _create_rollback_pr(self, request: ActionRequest) -> ActionExecutionResult:
        pr_number = int(_stable_suffix(request), 16) % 9000 + 1000
        return ActionExecutionResult(
            action_type=request.action_type,
            target=request.target,
            status=ActionStatus.EXECUTED,
            message="Mock rollback PR draft created.",
            output={
                "pr_url": f"https://mock.local/pr/{pr_number}",
                "base": request.payload.get("base", "main"),
                "rollback_to": request.payload.get("rollback_to", "previous-good-deploy"),
            },
            verification={"pr_url_recorded": True, "verify_recovery_after_merge": "pending"},
        )

    def _restart_worker(self, request: ActionRequest) -> ActionExecutionResult:
        return ActionExecutionResult(
            action_type=request.action_type,
            target=request.target,
            status=ActionStatus.EXECUTED,
            message="Mock non-production worker restart simulated.",
            output={
                "worker": request.target,
                "environment": request.environment,
                "restart": "simulated",
            },
            verification={"mock.verify_recovery": "required"},
        )

    def _verify_recovery(self, request: ActionRequest) -> ActionExecutionResult:
        return ActionExecutionResult(
            action_type=request.action_type,
            target=request.target,
            status=ActionStatus.EXECUTED,
            message="Mock recovery verified: error rate below threshold.",
            output={"recovered": True, "error_rate_delta": "-92%"},
            verification={"recovery_signal": "pass"},
        )

    def _generate_report(self, request: ActionRequest) -> ActionExecutionResult:
        incident_id = request.incident_id or "unknown"
        return ActionExecutionResult(
            action_type=request.action_type,
            target=request.target,
            status=ActionStatus.EXECUTED,
            message="Mock incident report generated.",
            output={"report_path": f"reports/incident-{incident_id}.md"},
            verification={"report_contains_evidence": bool(request.payload.get("evidence_ids"))},
        )

    def _add_timeline_note(self, request: ActionRequest) -> ActionExecutionResult:
        return ActionExecutionResult(
            action_type=request.action_type,
            target=request.target,
            status=ActionStatus.EXECUTED,
            message="Timeline note recorded in mock incident timeline.",
            output={"note": request.payload.get("note", "OpsCat action note")},
        )


def _stable_suffix(request: ActionRequest) -> str:
    payload_items = sorted(request.payload.items())
    raw = f"{request.incident_id}|{request.action_type}|{request.target}|{payload_items}"
    return sha1(raw.encode("utf-8")).hexdigest()[:6].upper()


def execute_mock_action(db: Any, incident: Any, action: Any) -> dict[str, object]:
    """Compatibility wrapper for the persisted incident service flow."""

    request = ActionRequest(
        action_type=action.action_type,
        target=action.target,
        environment=action.environment,
        payload=action.payload,
        incident_id=action.incident_id,
        approved=True,
    )
    result = MockActionExecutor().execute(request)
    output = {
        "ok": result.status == ActionStatus.EXECUTED,
        "kind": result.action_type,
        "message": result.message,
        "output": dict(result.output),
        "verification": dict(result.verification),
        "post_checks": list(getattr(action, "post_checks", [])),
    }
    action.execution_result = output
    action.status = "executed" if output["ok"] else "failed"
    if hasattr(db, "add"):
        db.add(action)
    return output


def verify_recovery(incident: object, action: object) -> dict[str, object]:
    if getattr(action, "status", "") != "executed":
        return {"recovered": False, "reason": "action not executed"}
    if getattr(incident, "service", "") == "worker":
        return {"recovered": True, "queue_latency_p95_seconds": 35, "worker_heartbeat": "healthy"}
    return {"recovered": True, "error_rate_per_minute": 3, "baseline_error_rate_per_minute": 2}
