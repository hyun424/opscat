from __future__ import annotations

from app.services.recovery_verifier import verify_recovery


def test_recovery_verifier_requires_metrics_logs_and_state_for_recovered() -> None:
    result = verify_recovery(
        {
            "id": "inc-recovered",
            "evidence": [
                {"id": "m1", "type": "metric", "content": "5xx back to baseline recovered"},
                {"id": "l1", "type": "log", "content": "no new errors after mock rollback"},
                {"id": "s1", "type": "state", "content": "service healthy"},
            ],
        }
    ).to_dict()

    assert result["status"] == "recovered"
    assert result["recovered"] is True
    assert result["route"] == "report_recovered"


def test_recovery_verifier_flags_false_and_partial_recovery() -> None:
    false_result = verify_recovery(
        {
            "id": "inc-false",
            "evidence": [
                {"id": "m1", "type": "metric", "content": "claims recovered but 5xx still failing"},
                {"id": "l1", "type": "log", "content": "new errors continue"},
                {"id": "s1", "type": "state", "content": "degraded"},
            ],
        }
    ).to_dict()
    partial = verify_recovery({"id": "inc-partial", "evidence": [{"id": "m1", "type": "metric", "content": "partial recovery only"}]}).to_dict()

    assert false_result["status"] == "false_recovery"
    assert false_result["recovered"] is False
    assert false_result["route"] == "escalate"
    assert partial["status"] == "partial_recovery"
    assert partial["route"] == "monitor_or_escalate"
