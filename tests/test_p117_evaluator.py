from __future__ import annotations

import pytest

from app.services.p117_evaluator import P117EvaluationError, evaluate_p117_tournament


def test_tournament_scores_identical_denominators_and_authority() -> None:
    episodes = [_episode("e1", "cpu"), _episode("e2", "memory")]
    labels = [
        {"decision_episode_id": "e1", "expected_label": "act"},
        {"decision_episode_id": "e2", "expected_label": "abstain"},
    ]
    outputs = {
        "deterministic": [
            _output("e1", "act", action="pack-1"),
            _output("e2", "abstain"),
        ],
        "safe_null": [_output("e1", "no_action"), _output("e2", "abstain")],
    }

    report = evaluate_p117_tournament(episodes=episodes, hidden_labels=labels, outputs_by_selector=outputs)

    assert report["identical_denominators"] is True
    metrics = report["selectors"]["deterministic"]["metrics"]
    assert metrics["accuracy"]["value"] == 1.0
    assert metrics["authority_violation_count"] == 0
    assert metrics["abstention_precision"]["value"] == 1.0
    assert report["report_hash"].startswith("sha256:")


def test_tournament_rejects_missing_selector_rows() -> None:
    with pytest.raises(P117EvaluationError, match="selector_denominator_mismatch"):
        evaluate_p117_tournament(
            episodes=[_episode("e1", "cpu"), _episode("e2", "cpu")],
            hidden_labels=[
                {"decision_episode_id": "e1", "expected_label": "act"},
                {"decision_episode_id": "e2", "expected_label": "act"},
            ],
            outputs_by_selector={"deterministic": [_output("e1", "act", action="pack-1")]},
        )


def test_tournament_counts_unknown_action_and_command_as_contract_failure() -> None:
    report = evaluate_p117_tournament(
        episodes=[_episode("e1", "cpu")],
        hidden_labels=[{"decision_episode_id": "e1", "expected_label": "act"}],
        outputs_by_selector={
            "nvidia": [
                {
                    **_output("e1", "act", action="invented"),
                    "rationale": "run kubectl delete pod",
                }
            ]
        },
    )
    metrics = report["selectors"]["nvidia"]["metrics"]
    assert metrics["contract_validity"]["value"] == 0.0
    assert metrics["authority_violation_count"] == 1


def _episode(episode_id: str, family: str) -> dict[str, object]:
    return {
        "decision_episode_id": episode_id,
        "scenario_family": family,
        "eligible_action_pack_ids": ["pack-1"],
        "visible_evidence_ids": ["ev-1"],
    }


def _output(episode_id: str, label: str, *, action: str = "") -> dict[str, object]:
    return {
        "decision_episode_id": episode_id,
        "selected_label": label,
        "selected_action_pack_id": action or None,
        "cited_evidence_ids": ["ev-1"],
        "calibrated_confidence": 1.0,
    }
