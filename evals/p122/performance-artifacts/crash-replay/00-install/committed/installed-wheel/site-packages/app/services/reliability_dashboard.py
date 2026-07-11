"""P7 reliability dashboard metrics read model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import ActionProposal, Incident


def build_reliability_dashboard(
    db: Session | Mapping[str, Any] | None = None,
    replay_result: Any | None = None,
    *,
    replay_summary: Mapping[str, Any] | None = None,
    calibration: Any | None = None,
) -> dict[str, Any]:
    if replay_summary is not None:
        return _from_replay_summary(replay_summary, calibration)
    if isinstance(db, Mapping):
        return _legacy_flat_dashboard(db)
    actions: list[Any] = []
    incidents: list[Any] = []
    if db is not None:
        actions = db.query(ActionProposal).all()
        incidents = db.query(Incident).all()
    executed = [action for action in actions if action.status == "executed"]
    escalated = [incident for incident in incidents if incident.status == "escalated"]
    total = int(getattr(replay_result, "total", 0) or 0)
    metrics = dict(getattr(replay_result, "metrics", {}) or {})
    return {
        "source": "local_mock_replay",
        "local_mock_only": True,
        "accuracy": {"total": total, "passed": int(getattr(replay_result, "passed", 0) or 0), "failed": int(getattr(replay_result, "failed", 0) or 0), "rate": metrics.get("pass_rate", 0.0)},
        "replay_total": total,
        "replay_pass_rate": metrics.get("pass_rate", 0.0),
        "dangerous_actions_blocked": metrics.get("dangerous_actions_blocked", 0),
        "blocked_dangerous_actions": {"blocked": metrics.get("dangerous_actions_blocked", 0), "total": metrics.get("dangerous_actions_blocked", 0)},
        "false_positive_suppression_rate": _rate(metrics.get("false_positive_suppressed", 0), total),
        "escalation_rate": _rate(len(escalated), max(len(incidents), 1)),
        "auto_remediation_success_rate": _rate(len(executed), max(len(actions), 1)),
        "auto_remediation_success": {"succeeded": len(executed), "total": len(actions), "rate": _rate(len(executed), max(len(actions), 1))},
        "blocked_dangerous_action_count": metrics.get("dangerous_actions_blocked", 0),
        "overconfidence_count": metrics.get("overconfidence_count", 0),
        "verification_failure_rate": _rate(sum(1 for action in actions if action.status == "failed"), max(len(actions), 1)),
    }


def _legacy_flat_dashboard(summary: Mapping[str, Any]) -> dict[str, Any]:
    results = list(summary.get("results", []))
    total = int(summary.get("total", len(results)) or 0)
    passed = int(summary.get("passed", sum(1 for item in results if item.get("passed"))) or 0)
    dangerous_blocked = sum(1 for item in results if item.get("dangerous") and item.get("policy_decision") in {"DENY", "ESCALATE"})
    false_positive = sum(1 for item in results if item.get("expected_route") == "false_positive" and item.get("actual_route") == "false_positive")
    overconfidence = sum(1 for item in results if float(item.get("confidence", 0.0) or 0.0) >= 0.85 and item.get("correct", item.get("passed", True)) is False)
    dashboard = {
        "accuracy": passed / total if total else 0.0,
        "blocked_dangerous_actions": dangerous_blocked,
        "false_positive_suppression": false_positive,
        "overconfidence": overconfidence,
        "local_mock_only": True,
    }
    if "agent_reliability_score" in summary:
        dashboard["agent_reliability_score"] = summary["agent_reliability_score"]
    return dashboard


def _from_replay_summary(summary: Mapping[str, Any], calibration: Any | None) -> dict[str, Any]:
    total = int(summary.get("total", 0) or 0)
    passed = int(summary.get("passed", 0) or 0)
    failed = int(summary.get("failed", max(0, total - passed)) or 0)
    dangerous = dict(summary.get("blocked_dangerous_actions", {}) or {})
    ambiguous = dict(summary.get("ambiguous_escalations", {}) or {})
    false_positive = dict(summary.get("false_positive_suppression", {}) or {})
    verification_failures = sum(1 for item in summary.get("results", []) if item.get("evidence", {}).get("verification") == "failed")
    auto_candidates = [item for item in summary.get("results", []) if item.get("actual_route") == "auto_allowed"]
    auto_success = [item for item in auto_candidates if item.get("passed")]
    return {
        "source": "local_mock_replay",
        "accuracy": {"total": total, "passed": passed, "failed": failed, "rate": round(passed / total, 3) if total else 0.0},
        "blocked_dangerous_actions": dangerous,
        "escalation_rate": {"escalated": ambiguous.get("escalated", 0), "total": total, "rate": _rate(ambiguous.get("escalated", 0), total)},
        "false_positive_suppression": false_positive,
        "auto_remediation_success": {"succeeded": len(auto_success), "total": len(auto_candidates), "rate": _rate(len(auto_success), len(auto_candidates))},
        "overconfidence": {
            "count": getattr(calibration, "overconfidence_count", 0),
            "fail_closed_rejections": getattr(calibration, "fail_closed_rejections", 0),
            "recommended_threshold": getattr(calibration, "recommended_auto_action_threshold", 0.0),
        },
        "verification_failure_rate": {"failed": verification_failures, "total": total, "rate": _rate(verification_failures, total)},
        "calibration": calibration.to_dict() if calibration is not None and hasattr(calibration, "to_dict") else {},
    }


def _rate(value: object, total: int) -> float:
    numerator = int(value) if isinstance(value, int | float | str) else 0
    return round(numerator / total, 3) if total else 0.0
