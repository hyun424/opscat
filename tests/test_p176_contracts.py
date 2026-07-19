from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_contracts import (
    EPISODE_FIELDS,
    HEALTHY_WINDOW_FIELDS,
    P176ContractError,
    validate_campaign_payload,
    validate_episode_mapping,
    validate_healthy_window,
)


def test_episode_mapping_is_exact_key_json_ready_self_hashed_and_truth_sealed() -> None:
    campaign = generate_p176_campaign()
    episode = campaign["episodes"][0]

    assert set(episode) == EPISODE_FIELDS
    assert episode["episode_hash"] == stable_hash({key: value for key, value in episode.items() if key != "episode_hash"})
    assert "truth" not in episode
    assert "evaluator_truth" not in episode
    assert isinstance(episode["agent_visible_evidence_refs"], list)
    assert all(isinstance(ref, str) for ref in episode["agent_visible_evidence_refs"])
    validate_episode_mapping(episode)


def test_episode_mapping_rejects_unknown_missing_bool_as_int_and_non_finite_numeric_values() -> None:
    episode = deepcopy(generate_p176_campaign()["episodes"][0])

    with pytest.raises(P176ContractError, match="unexpected_episode_field"):
        validate_episode_mapping({**episode, "scorer_only_truth": {"root_cause": "hidden"}})

    missing = deepcopy(episode)
    missing.pop("family_id")
    with pytest.raises(P176ContractError, match="missing_episode_field"):
        validate_episode_mapping(missing)

    bool_index = deepcopy(episode)
    bool_index["index"] = True
    with pytest.raises(P176ContractError, match="invalid_episode_int:index"):
        validate_episode_mapping(bool_index)

    nan_index = deepcopy(episode)
    nan_index["index"] = float("nan")
    with pytest.raises(P176ContractError, match="non_finite_episode_number"):
        validate_episode_mapping(nan_index)


def test_healthy_window_mapping_is_exact_key_self_hashed_and_rejects_type_drift() -> None:
    window = generate_p176_campaign()["healthy_windows"][0]

    assert set(window) == HEALTHY_WINDOW_FIELDS
    assert window["window_hash"] == stable_hash({key: value for key, value in window.items() if key != "window_hash"})
    validate_healthy_window(window)

    with pytest.raises(P176ContractError, match="unexpected_healthy_window_field"):
        validate_healthy_window({**window, "unredacted_preview": "secret"})

    bad_noisy: dict[str, Any] = deepcopy(window)
    bad_noisy["noisy"] = 1
    with pytest.raises(P176ContractError, match="invalid_healthy_window_bool:noisy"):
        validate_healthy_window(bad_noisy)


def test_campaign_payload_validator_reconciles_hashes_and_denominators() -> None:
    campaign = generate_p176_campaign()
    assert validate_campaign_payload(campaign) == campaign

    duplicate = deepcopy(campaign)
    duplicate["episodes"][1]["episode_id"] = duplicate["episodes"][0]["episode_id"]
    duplicate["episodes"][1]["episode_hash"] = stable_hash(
        {key: value for key, value in duplicate["episodes"][1].items() if key != "episode_hash"}
    )
    with pytest.raises(P176ContractError, match="duplicate_episode_id"):
        validate_campaign_payload(duplicate)
