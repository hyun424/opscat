from __future__ import annotations

from app.services.autonomy_readiness import score_autonomy_readiness


def test_autonomy_readiness_decomposes_score_and_blocks_hard_gates() -> None:
    readiness = score_autonomy_readiness(
        {
            "evidence_count": 5,
            "confidence": 0.94,
            "blast_radius_scope": "prohibited",
            "reversible": True,
            "simulation_status": "passed",
            "policy_decision": "ALLOW",
            "memory_outcome": "success",
            "verification_status": "passed",
        }
    ).to_dict()

    assert readiness["local_mock_only"] is True
    assert readiness["route"] == "blocked"
    assert readiness["hard_blocked"] is True
    assert readiness["score"] < 80
    assert "blast_radius" in readiness["components_by_name"]
    assert readiness["blockers"]


def test_autonomy_readiness_allows_only_fully_gated_local_mock_path() -> None:
    readiness = score_autonomy_readiness(
        {
            "evidence_count": 5,
            "confidence": 0.91,
            "blast_radius_scope": "local",
            "reversible": True,
            "simulation_status": "passed",
            "policy_decision": "ALLOW",
            "memory_outcome": "success",
            "verification_status": "passed",
        }
    ).to_dict()

    assert readiness["route"] == "local_mock_auto_allowed"
    assert readiness["score"] >= 80
    assert readiness["required_human_answers"] == []
