from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any, cast

import pytest

from app.services.p117_nvidia_proposal import replay_p117_nvidia_proposal
from app.services.p117_selector import select_p117_decision
from tests.test_p117_selector import _episode


def test_valid_nvidia_json_is_proposal_only_and_preserves_exact_zero_authority() -> None:
    episode = _episode()
    deterministic = select_p117_decision(episode).to_dict()
    raw = {
        "selected_label": "act",
        "selected_action_pack_id": "act_restart_worker",
        "ranked_action_pack_ids": ["act_restart_worker", "act_shed_load"],
        "cited_evidence_ids": ["ev-cpu", "ev-error"],
        "expected_utility": 0.42,
        "utility_interval": [0.18, 0.55],
        "calibrated_confidence": 0.81,
        "abstention_reason": None,
    }

    result = replay_p117_nvidia_proposal(episode, raw, deterministic_decision=deterministic).to_dict()

    assert result["schema_version"] == "p117.nvidia_proposal_replay.v1"
    assert result["status"] == "valid"
    assert result["selection_source"] == "nvidia_proposal"
    assert result["fallback_reason"] is None
    assert result["proposal"]["selected_action_pack_id"] == "act_restart_worker"
    assert result["proposal"]["cited_evidence_ids"] == ["ev-cpu", "ev-error"]
    assert result["final_decision"] == result["proposal"]
    assert result["execution_authority"] == "none"
    assert result["llm_authority"] == "proposal_only"
    assert result["production_authority"] is False
    assert result["credential_scope"] is False
    assert result["p118_required_for_execution"] is True


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("not-json", "malformed_provider_json"),
        (["not", "object"], "provider_json_not_object"),
        ({"selected_label": "act", "selected_action_pack_id": "invented", "ranked_action_pack_ids": ["invented"], "cited_evidence_ids": ["ev-cpu"]}, "unknown_action_pack_id"),
        ({"selected_label": "act", "selected_action_pack_id": "act_restart_worker", "ranked_action_pack_ids": ["act_restart_worker"], "cited_evidence_ids": ["ev-secret"]}, "invented_evidence_id"),
        (
            {
                "selected_label": "act",
                "selected_action_pack_id": "act_restart_worker",
                "ranked_action_pack_ids": ["act_restart_worker"],
                "cited_evidence_ids": ["ev-cpu"],
                "command": "kubectl delete pod",
            },
            "unknown_output_field",
        ),
        (
            {
                "selected_label": "act",
                "selected_action_pack_id": "act_restart_worker",
                "ranked_action_pack_ids": ["act_restart_worker"],
                "cited_evidence_ids": ["ev-cpu"],
                "rationale": "use AWS creds and run rm -rf /",
            },
            "forbidden_authority_text",
        ),
        ({"selected_label": "restart", "selected_action_pack_id": "act_restart_worker", "ranked_action_pack_ids": ["act_restart_worker"], "cited_evidence_ids": ["ev-cpu"]}, "unknown_selected_label"),
        ({"selected_label": "act", "selected_action_pack_id": "act_restart_worker", "ranked_action_pack_ids": ["act_restart_worker"], "cited_evidence_ids": []}, "missing_cited_evidence_ids"),
    ],
)
def test_untrusted_nvidia_json_rejects_unknown_ids_evidence_commands_credentials_mutation_and_falls_back(raw: Any, reason: str) -> None:
    episode = _episode()
    deterministic = select_p117_decision(episode).to_dict()

    result = replay_p117_nvidia_proposal(episode, raw, deterministic_decision=deterministic).to_dict()

    assert result["status"] == "fail_closed"
    assert result["selection_source"] == "deterministic_fallback"
    assert reason in result["validation_errors"][0]
    assert result["fallback_reason"] == result["validation_errors"][0]
    assert result["final_decision"] == deterministic
    assert result["execution_authority"] == "none"


def test_repeat_replay_is_exact_for_json_string_input_and_records_disagreement_without_override() -> None:
    episode = _episode()
    deterministic = select_p117_decision(episode).to_dict()
    raw = json.dumps(
        {
            "selected_label": "no_action",
            "selected_action_pack_id": None,
            "ranked_action_pack_ids": ["act_shed_load", "act_restart_worker"],
            "cited_evidence_ids": ["ev-cpu"],
            "expected_utility": 0.0,
            "utility_interval": [0.0, 0.0],
            "calibrated_confidence": 0.74,
            "abstention_reason": "measured no-action dominates",
        },
        sort_keys=True,
    )

    first = replay_p117_nvidia_proposal(episode, raw, deterministic_decision=deterministic).to_dict()
    second = replay_p117_nvidia_proposal(episode, raw, deterministic_decision=deterministic).to_dict()

    assert first == second
    assert first["status"] == "valid"
    assert first["disagreement_with_deterministic"] is True
    assert first["final_decision"]["selected_label"] == "no_action"


def test_nvidia_cannot_turn_deterministic_abstention_into_action() -> None:
    episode = _episode()
    receipt = cast(MutableMapping[str, Any], episode["authority_boundary_receipt"])
    counters = cast(MutableMapping[str, int], receipt["authority_counters"])
    counters["credential_access_count"] = 1
    deterministic = select_p117_decision(episode).to_dict()
    raw = {
        "selected_label": "act",
        "selected_action_pack_id": "act_restart_worker",
        "ranked_action_pack_ids": ["act_restart_worker"],
        "cited_evidence_ids": ["ev-cpu"],
    }

    result = replay_p117_nvidia_proposal(episode, raw, deterministic_decision=deterministic).to_dict()

    assert result["status"] == "fail_closed"
    assert "deterministic_safety_gate_override" in result["validation_errors"]
    assert result["final_decision"] == deterministic
