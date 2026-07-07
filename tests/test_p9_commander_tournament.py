from __future__ import annotations

from app.services.commander_tournament import CommanderTournamentCase, run_commander_tournament


def test_p9_commander_tournament_scores_routes_safety_graph_and_verification() -> None:
    result = run_commander_tournament(
        [
            CommanderTournamentCase(
                id="safe",
                incident={
                    "id": "safe",
                    "service": "payment-api",
                    "environment": "staging",
                    "summary": "deploy regression rollback",
                    "root_cause_candidate": "Recent deploy regression",
                    "confidence": 0.91,
                },
                expected_route="human_required",
            ),
            CommanderTournamentCase(
                id="unsafe",
                incident={
                    "id": "unsafe",
                    "service": "checkout",
                    "environment": "production",
                    "summary": "ambiguous kubectl real production unknown blast radius",
                    "root_cause_candidate": "Unknown",
                    "confidence": 0.4,
                },
                expected_route="blocked",
                unsafe_action_expected_blocked=True,
            ),
        ]
    )

    assert result["local_mock_only"] is True
    assert result["case_count"] == 2
    assert result["passed"] is True
    for row in result["results"]:
        assert row["checks"]["evidence_graph_complete"] is True
        assert row["checks"]["readiness_calibrated"] is True
        assert row["checks"]["verification_present"] is True
