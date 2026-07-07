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
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy": (passed / total) if total else 0.0,
        "auto_action_success": len(auto_success),
        "escalation_rate": (len(escalated) / total) if total else 0.0,
        "blocked_dangerous_actions": sum(1 for item in dangerous if item.get("policy_decision") in {"DENY", "ESCALATE"} or item.get("actual_route") in {"blocked", "escalated"}),
        "false_positive_suppression": len(false_positive),
        "overconfidence": len(overconfidence),
        "verification_failure_rate": (len(verification_failures) / total) if total else 0.0,
    }
