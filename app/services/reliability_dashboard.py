"""P7 reliability dashboard metrics read model."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import ActionProposal, Incident
from app.services.replay_service import ReplayRunResult


def build_reliability_dashboard(db: Session, replay_result: ReplayRunResult | None = None) -> dict[str, Any]:
    actions = db.query(ActionProposal).all()
    incidents = db.query(Incident).all()
    executed = [action for action in actions if action.status == "executed"]
    escalated = [incident for incident in incidents if incident.status == "escalated"]
    total = replay_result.total if replay_result else 0
    metrics = dict(replay_result.metrics) if replay_result else {}
    return {
        "source": "local_mock_replay",
        "replay_total": total,
        "replay_pass_rate": metrics.get("pass_rate", 0.0),
        "dangerous_actions_blocked": metrics.get("dangerous_actions_blocked", 0),
        "false_positive_suppression_rate": _rate(metrics.get("false_positive_suppressed", 0), total),
        "escalation_rate": _rate(len(escalated), max(len(incidents), 1)),
        "auto_remediation_success_rate": _rate(len(executed), max(len(actions), 1)),
        "blocked_dangerous_action_count": metrics.get("dangerous_actions_blocked", 0),
        "overconfidence_count": metrics.get("overconfidence_count", 0),
        "verification_failure_rate": _rate(sum(1 for action in actions if action.status == "failed"), max(len(actions), 1)),
    }


def _rate(value: object, total: int) -> float:
    numerator = int(value or 0)
    return round(numerator / total, 3) if total else 0.0
