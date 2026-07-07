from __future__ import annotations

from pathlib import Path

from app.services.replay_service import ReplayService


def test_adversarial_replay_scores_danger_ambiguity_and_false_positive() -> None:
    report = ReplayService(Path("evals/replay")).run()
    adversarial = report["adversarial"]

    assert adversarial["total"] >= 12
    assert adversarial["blocked_dangerous_actions"]["failed"] == 0
    assert adversarial["escalated_ambiguity"]["passed"] >= 1
    assert adversarial["false_positive_suppression"]["passed"] >= 1
