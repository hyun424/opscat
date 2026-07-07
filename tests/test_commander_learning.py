from __future__ import annotations

from app.services.commander_learning import summarize_learning_signals


def test_commander_learning_classifies_success_failure_rejected_stale_and_poisoned_memory() -> None:
    summary = summarize_learning_signals(
        [
            {"incident_id": "s", "outcome": "success", "score": 0.9},
            {"incident_id": "f", "outcome": "failed", "warnings": ["prior_failed_remediation"]},
            {"incident_id": "r", "outcome": "rejected"},
            {"incident_id": "st", "outcome": "stale"},
            {"incident_id": "p", "outcome": "poisoned"},
        ]
    ).to_dict()

    assert summary["local_mock_only"] is True
    assert summary["counts"] == {"success": 1, "failed": 1, "rejected": 1, "stale": 1, "poisoned": 1, "unknown": 0}
    assert summary["route"] == "human_required"
    assert "prior_failed_remediation" in summary["warnings"]
    assert "poisoned_memory" in summary["warnings"]
