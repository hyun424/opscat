from __future__ import annotations

from app.services.reliability_dashboard import build_reliability_dashboard


def test_reliability_dashboard_aggregates_eval_outputs() -> None:
    dashboard = build_reliability_dashboard(
        {
            "total": 3,
            "passed": 2,
            "failed": 1,
            "results": [
                {"passed": True, "expected_route": "auto_allowed", "actual_route": "auto_allowed", "dangerous": False, "policy_decision": "ALLOW", "verification_passed": True, "confidence": 0.9},
                {"passed": True, "expected_route": "escalated", "actual_route": "escalated", "dangerous": True, "policy_decision": "DENY", "verification_passed": False, "confidence": 0.4},
                {"passed": False, "expected_route": "false_positive", "actual_route": "false_positive", "dangerous": False, "policy_decision": "ALLOW", "verification_passed": False, "confidence": 0.95, "correct": False},
            ],
        }
    )

    assert dashboard["accuracy"] == 2 / 3
    assert dashboard["blocked_dangerous_actions"] == 1
    assert dashboard["false_positive_suppression"] == 1
    assert dashboard["overconfidence"] == 1
