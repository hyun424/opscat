"""P7 deterministic reliability dashboard metrics."""

from __future__ import annotations

from typing import Any

from app.services.confidence_calibration import CalibrationReport, calibrate_replay_results


def build_reliability_dashboard(*, replay_summary: dict[str, Any] | None = None, calibration: CalibrationReport | None = None) -> dict[str, Any]:
    if replay_summary is None:
        try:
            from scripts.run_replay_evals import run_replay_evals

            replay_summary = run_replay_evals()
        except Exception:
            replay_summary = {"total": 0, "passed": 0, "failed": 0, "results": [], "blocked_dangerous_actions": {"blocked": 0, "total": 0}}
    results = list(replay_summary.get("results", []))
    calibration = calibration or calibrate_replay_results(results)
    total = int(replay_summary.get("total", len(results)))
    passed = int(replay_summary.get("passed", sum(1 for item in results if item.get("passed"))))
    auto_candidates = [item for item in results if item.get("auto_action_eligible")]
    auto_success = sum(1 for item in auto_candidates if item.get("passed"))
    escalations = sum(1 for item in results if item.get("policy_decision") == "ESCALATE")
    false_positive_suppressed = sum(1 for item in results if item.get("false_positive_suppressed"))
    verification_failures = sum(1 for item in results if item.get("verification_outcome") == "failed")
    return {
        "local_mock_only": True,
        "accuracy": {"total": total, "passed": passed, "failed": max(0, total - passed), "rate": round(passed / total, 3) if total else 0.0},
        "false_positive_suppression": {"count": false_positive_suppressed},
        "blocked_dangerous_actions": replay_summary.get("blocked_dangerous_actions", {"blocked": 0, "total": 0}),
        "escalation_rate": {"escalated": escalations, "total": total, "rate": round(escalations / total, 3) if total else 0.0},
        "auto_remediation_success": {"succeeded": auto_success, "total": len(auto_candidates), "rate": round(auto_success / len(auto_candidates), 3) if auto_candidates else 0.0},
        "overconfidence": {"count": calibration.overconfidence_count, "fail_closed_rejections": calibration.fail_closed_rejections, "recommended_threshold": calibration.recommended_auto_action_threshold},
        "verification_failure_rate": {"failed": verification_failures, "total": total, "rate": round(verification_failures / total, 3) if total else 0.0},
        "calibration": calibration.to_dict(),
    }
