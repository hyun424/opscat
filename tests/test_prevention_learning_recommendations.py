from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.prevention_learning_recommendations import (
    build_prevention_learning_recommendation_manifest,
)


def test_recommendations_are_data_only_unapplied_hashed_and_rollbackable() -> None:
    base_version = {
        "version_id": "policy-v17",
        "content_hash": "a" * 64,
        "rollback_target": "policy-v16",
    }
    feedback = [
        {
            "episode_id": "L05",
            "family": "forecast",
            "outcome_label": "harmful_guardrail_breach",
            "failure_mode": "harmful_intervention",
            "metric": "harmful_intervention_rate",
            "recommended_direction": "tighten_threshold",
            "rationale": "Candidate intervention increased harm.",
            "evidence_hash": "b" * 64,
        },
        {
            "episode_id": "L08",
            "family": "runbook",
            "outcome_label": "false_positive_intervention",
            "failure_mode": "unnecessary_intervention",
            "metric": "unnecessary_intervention_rate",
            "recommended_direction": "narrow_cohort",
            "rationale": "False positive indicates overly broad targeting.",
            "evidence_hash": "c" * 64,
        },
        {
            "episode_id": "L14",
            "family": "thresholds",
            "outcome_label": "near_miss",
            "failure_mode": "missed_prevention",
            "metric": "prevented_precision",
            "recommended_direction": "broaden_threshold",
            "rationale": "Potential improvement needs independent review.",
            "evidence_hash": "d" * 64,
        },
    ]
    original_base = deepcopy(base_version)
    original_feedback = deepcopy(feedback)

    first = build_prevention_learning_recommendation_manifest(
        base_version=base_version,
        feedback_items=feedback,
        producer_id="p108-learner",
    )
    second = build_prevention_learning_recommendation_manifest(
        base_version=base_version,
        feedback_items=feedback,
        producer_id="p108-learner",
    )

    assert base_version == original_base
    assert feedback == original_feedback
    assert first == second
    assert first["schema_version"] == "p108.recommendation_manifest.v1"
    assert first["summary"]["recommendation_count"] == 3
    assert first["summary"]["applied_count"] == 0
    assert first["summary"]["conservative_automatic_count"] == 2
    assert first["base_version"] == {
        "version_id": "policy-v17",
        "content_hash": "a" * 64,
        "rollback_target": "policy-v16",
    }
    assert first["rollback"]["base_version_id"] == "policy-v17"
    assert first["rollback"]["base_content_hash_sha256"] == "a" * 64
    assert first["rollback"]["target_version_id"] == "policy-v16"
    assert len(first["manifest_hash_sha256"]) == 64

    recommendations = first["recommendations"]
    assert all(item["applied"] is False for item in recommendations)
    assert all(len(item["recommendation_hash_sha256"]) == 64 for item in recommendations)
    assert all(item["file_mutation_enabled"] is False for item in recommendations)
    assert all(item["review_binding"]["producer_id"] == "p108-learner" for item in recommendations)
    assert all(item["review_binding"]["required_before_apply"] is True for item in recommendations)
    assert all(item["rollback"]["base_version_id"] == "policy-v17" for item in recommendations)
    assert all(item["rollback"]["base_content_hash_sha256"] == "a" * 64 for item in recommendations)
    assert all(item["rollback"]["target_version_id"] == "policy-v16" for item in recommendations)

    conservative = [item for item in recommendations if item["review_binding"]["automatic_direction_allowed"]]
    broader = [item for item in recommendations if not item["review_binding"]["automatic_direction_allowed"]]
    assert {item["source_episode_id"] for item in conservative} == {"L05", "L08"}
    assert all(item["direction_class"] == "conservative" for item in conservative)
    assert all(item["direction_class"] == "broader_review_required" for item in broader)
    assert all(item["review_binding"]["independent_review_required"] is True for item in broader)


def test_non_conservative_harm_or_false_positive_direction_fails_closed() -> None:
    payload = build_prevention_learning_recommendation_manifest(
        base_version={"version_id": "policy-v17", "content_hash": "a" * 64, "rollback_target": "policy-v16"},
        feedback_items=[
            {
                "episode_id": "L05",
                "family": "forecast",
                "outcome_label": "harmful_guardrail_breach",
                "failure_mode": "harmful_intervention",
                "metric": "harmful_intervention_rate",
                "recommended_direction": "broaden_threshold",
                "rationale": "Unsafe widening must not be automatic.",
                "evidence_hash": "b" * 64,
            }
        ],
        producer_id="p108-learner",
    )

    assert payload["summary"]["passed"] is False
    assert payload["summary"]["blocked_count"] == 1
    assert payload["recommendations"][0]["applied"] is False
    assert payload["recommendations"][0]["blocked"] is True
    assert "non_conservative_direction_for_harm_or_false_positive" in payload["recommendations"][0]["block_reasons"]
    assert payload["recommendations"][0]["review_binding"]["automatic_direction_allowed"] is False


@pytest.mark.parametrize(
    ("base_version", "expected_reason"),
    [
        ({"content_hash": "a" * 64, "rollback_target": "policy-v16"}, "invalid_base_version_id"),
        ({"version_id": "", "content_hash": "a" * 64, "rollback_target": "policy-v16"}, "invalid_base_version_id"),
        ({"version_id": "   ", "content_hash": "a" * 64, "rollback_target": "policy-v16"}, "invalid_base_version_id"),
        ({"version_id": "policy v17", "content_hash": "a" * 64, "rollback_target": "policy-v16"}, "invalid_base_version_id"),
        ({"version_id": "policy-v17", "rollback_target": "policy-v16"}, "invalid_base_content_hash_sha256"),
        ({"version_id": "policy-v17", "content_hash": "", "rollback_target": "policy-v16"}, "invalid_base_content_hash_sha256"),
        ({"version_id": "policy-v17", "content_hash": "not-sha256", "rollback_target": "policy-v16"}, "invalid_base_content_hash_sha256"),
        ({"version_id": "policy-v17", "content_hash": "g" * 64, "rollback_target": "policy-v16"}, "invalid_base_content_hash_sha256"),
        ({"version_id": "policy-v17", "content_hash": "a" * 64}, "missing_rollback_pointer"),
        ({"version_id": "policy-v17", "content_hash": "a" * 64, "rollback_target": ""}, "missing_rollback_pointer"),
        ({"version_id": "policy-v17", "content_hash": "a" * 64, "rollback_target": "policy v16"}, "invalid_rollback_target"),
        ({"version_id": "policy-v17", "content_hash": "a" * 64, "rollback_target": "policy-v17"}, "rollback_target_matches_base_version"),
    ],
)
def test_manifest_rejects_missing_empty_invalid_base_hash_and_rollback_fields(
    base_version: dict[str, object], expected_reason: str
) -> None:
    payload = build_prevention_learning_recommendation_manifest(
        base_version=base_version,
        feedback_items=[
            {
                "episode_id": "L05",
                "family": "forecast",
                "outcome_label": "harmful_guardrail_breach",
                "failure_mode": "harmful_intervention",
                "metric": "harmful_intervention_rate",
                "recommended_direction": "tighten_threshold",
                "rationale": "Candidate intervention increased harm.",
                "evidence_hash": "b" * 64,
            }
        ],
        producer_id="p108-learner",
    )

    assert payload["summary"]["passed"] is False
    assert expected_reason in payload["summary"]["version_block_reasons"]
    assert payload["recommendations"][0]["blocked"] is True
    assert expected_reason in payload["recommendations"][0]["block_reasons"]
