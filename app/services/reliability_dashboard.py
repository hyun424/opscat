"""P7 reliability dashboard aggregation over replay/eval outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_reliability_dashboard(eval_report: Mapping[str, Any]) -> dict[str, Any]:
    results = list(eval_report.get("results", []))
    total = len(results) or int(eval_report.get("total", 0) or 0)
    passed = sum(1 for item in results if bool(item.get("passed"))) if results else int(eval_report.get("passed", 0) or 0)
    dangerous = [item for item in results if bool(item.get("dangerous") or item.get("dangerous_action_attempt") or "unsafe_action" in item.get("safety_focus", []))]
    escalated = [item for item in results if str(item.get("actual_route", item.get("route", ""))).startswith("escalated")]
    auto_success = [item for item in results if item.get("expected_route") == "auto_allowed" and item.get("passed")]
    false_positive = [item for item in results if "false_positive" in str(item.get("scenario", "")) or item.get("expected_route") == "false_positive"]
    verification_failures = [item for item in results if item.get("verification_passed") is False]
    overconfidence = [item for item in results if float(item.get("confidence", 0.0) or 0.0) >= 0.85 and item.get("correct", item.get("passed", True)) is False]
    return {
        "local_mock_only": True,
        "accuracy": {"total": total, "passed": passed, "failed": max(0, total - passed), "rate": round(passed / total, 3) if total else 0.0},
        "false_positive_suppression": {"count": false_positive_suppressed},
        "blocked_dangerous_actions": replay_summary.get("blocked_dangerous_actions", {"blocked": 0, "total": 0}),
        "escalation_rate": {"escalated": escalations, "total": total, "rate": round(escalations / total, 3) if total else 0.0},
        "auto_remediation_success": {"succeeded": auto_success, "total": len(auto_candidates), "rate": round(auto_success / len(auto_candidates), 3) if auto_candidates else 0.0},
        "overconfidence": {
            "count": calibration.overconfidence_count,
            "fail_closed_rejections": calibration.fail_closed_rejections,
            "recommended_threshold": calibration.recommended_auto_action_threshold,
        },
        "verification_failure_rate": {"failed": verification_failures, "total": total, "rate": round(verification_failures / total, 3) if total else 0.0},
        "calibration": calibration.to_dict(),
    }


def _rate(value: object, total: int) -> float:
    numerator = int(value) if isinstance(value, int | float | str) else 0
    return round(numerator / total, 3) if total else 0.0
