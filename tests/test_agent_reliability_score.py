from __future__ import annotations

from app.services.agent_reliability_score import score_agent_reliability
from app.services.reliability_dashboard import build_reliability_dashboard


def test_agent_reliability_score_is_deterministic_explainable_and_decomposed() -> None:
    score = score_agent_reliability(
        {
            "replay_pass_rate": 0.96,
            "dangerous_action_block_rate": 1.0,
            "confidence": 0.91,
            "evidence_count": 4,
            "conflicting_signals": False,
            "known_ambiguity": False,
            "blast_radius_scope": "service",
            "simulation_status": "passed",
            "memory_prior_outcome": "success",
            "post_action_verification": "passed",
            "policy_decision": "ALLOW",
        }
    )

    assert score.to_dict() == score_agent_reliability(score.inputs).to_dict()
    assert score.score >= 85
    assert score.band == "high"
    assert score.hard_policy_blocked is False
    assert score.action_route == "eligible_for_action_gate"
    assert {component["name"] for component in score.to_dict()["components"]} == {
        "replay_pass_rate",
        "dangerous_action_block_rate",
        "confidence_calibration",
        "evidence_count",
        "signal_clarity",
        "blast_radius",
        "simulation",
        "memory_prior_outcome",
        "post_action_verification",
    }


def test_high_score_cannot_override_prohibited_or_unknown_blast_radius() -> None:
    score = score_agent_reliability(
        {
            "replay_pass_rate": 1.0,
            "dangerous_action_block_rate": 1.0,
            "confidence": 0.99,
            "evidence_count": 9,
            "conflicting_signals": False,
            "known_ambiguity": False,
            "blast_radius_scope": "prohibited",
            "simulation_status": "passed",
            "memory_prior_outcome": "success",
            "post_action_verification": "passed",
            "policy_decision": "ALLOW",
        }
    )

    assert score.hard_policy_blocked is True
    assert score.action_route == "blocked_by_policy"
    assert score.band == "blocked"
    assert score.human_on_exception_reason is not None
    assert "blast radius" in score.human_on_exception_reason.lower()


def test_missing_evidence_conflicts_failed_memory_and_failed_post_check_lower_score() -> None:
    score = score_agent_reliability(
        {
            "replay_pass_rate": 0.68,
            "dangerous_action_block_rate": 0.7,
            "confidence": 0.88,
            "evidence_count": 1,
            "conflicting_signals": True,
            "known_ambiguity": True,
            "blast_radius_scope": "workspace",
            "simulation_status": "blocked",
            "memory_prior_outcome": "failed",
            "post_action_verification": "failed",
            "policy_decision": "REQUIRE_APPROVAL",
        }
    )

    payload = score.to_dict()
    assert score.score < 60
    assert score.band == "low"
    assert score.action_route == "human_required"
    assert "human" in (score.human_on_exception_reason or "").lower()
    assert payload["components_by_name"]["evidence_count"]["points"] < payload["components_by_name"]["evidence_count"]["weight"]
    assert payload["components_by_name"]["memory_prior_outcome"]["points"] == 0
    assert payload["components_by_name"]["post_action_verification"]["points"] == 0


def test_reliability_dashboard_can_include_p8_agent_score_without_breaking_existing_keys() -> None:
    agent_score = score_agent_reliability({"replay_pass_rate": 1.0, "dangerous_action_block_rate": 1.0, "evidence_count": 3, "blast_radius_scope": "service", "simulation_status": "passed"}).to_dict()

    dashboard = build_reliability_dashboard(
        {
            "total": 1,
            "passed": 1,
            "results": [{"passed": True, "dangerous": False, "expected_route": "auto_allowed", "actual_route": "auto_allowed"}],
            "agent_reliability_score": agent_score,
        }
    )

    assert dashboard["accuracy"] == 1.0
    assert dashboard["agent_reliability_score"] == agent_score
    assert dashboard["local_mock_only"] is True
