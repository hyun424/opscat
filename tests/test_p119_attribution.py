from __future__ import annotations

from app.services.p119_attribution import attribute_p119_outcome, build_p119_learning_record


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def test_action_help_requires_incremental_effect_and_no_recurrence() -> None:
    helped = attribute_p119_outcome(
        windows={"action": 0.8, "no_action": 0.1, "natural_recovery": 0.2}, controls_comparable=True, contaminated=False, guardrail_breach=False, rollback_performed=False, recurrence_detected=False
    )
    recurring = attribute_p119_outcome(
        windows={"action": 0.8, "no_action": 0.1, "natural_recovery": 0.2}, controls_comparable=True, contaminated=False, guardrail_breach=False, rollback_performed=False, recurrence_detected=True
    )
    assert helped.label == "action_helped" and helped.recovery_eligible is True
    assert recurring.label == "action_helped" and recurring.recovery_eligible is False


def test_natural_and_rollback_recovery_are_not_action_success() -> None:
    natural = attribute_p119_outcome(
        windows={"action": 0.3, "no_action": 0.1, "natural_recovery": 0.4}, controls_comparable=True, contaminated=False, guardrail_breach=False, rollback_performed=False, recurrence_detected=False
    )
    rollback = attribute_p119_outcome(
        windows={"action": 0.8, "no_action": 0.1, "natural_recovery": 0.2}, controls_comparable=True, contaminated=False, guardrail_breach=False, rollback_performed=True, recurrence_detected=False
    )
    assert natural.label == "natural_recovery"
    assert rollback.label == "rollback_recovered"
    assert not natural.recovery_eligible and not rollback.recovery_eligible


def test_learning_record_is_offline_hash_bound_and_exact_zero_authority() -> None:
    attribution = attribute_p119_outcome(
        windows={"action": 0.8, "no_action": 0.1, "natural_recovery": 0.2}, controls_comparable=True, contaminated=False, guardrail_breach=False, rollback_performed=False, recurrence_detected=False
    )
    record = build_p119_learning_record(incident_id="incident-001", attribution=attribution, denominator=3, split="holdout", fixture_version="v1", seed=11901, replay_ref=_hash("1"))
    assert record["online_policy_write"] is False
    assert record["authority_counter_snapshot"]["online_policy_write"] == 0
    assert str(record["record_hash"]).startswith("sha256:")
