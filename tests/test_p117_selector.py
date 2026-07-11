from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p117_selector import P117SelectorError, select_p117_decision


def test_selector_is_byte_stable_and_ranks_only_frozen_ids_by_measured_utility() -> None:
    episode = _episode()

    first = select_p117_decision(episode)
    second = select_p117_decision(_episode())

    assert first.to_dict() == second.to_dict()
    payload = first.to_dict()
    assert payload["schema_version"] == "p117.deterministic_decision.v1"
    assert payload["decision_episode_id"] == "episode-1"
    assert payload["selected_label"] == "act"
    assert payload["selected_action_pack_id"] == "act_restart_worker"
    assert payload["ranked_action_pack_ids"] == ["act_restart_worker", "act_shed_load"]
    assert payload["cited_evidence_ids"] == ["ev-cpu", "ev-error"]
    assert payload["expected_utility"] == 0.42
    assert payload["utility_interval"] == [0.18, 0.55]
    assert payload["execution_authority"] == "none"
    assert payload["llm_authority"] == "proposal_only"
    assert payload["production_authority"] is False
    assert payload["credential_scope"] is False
    assert payload["p118_required_for_execution"] is True
    assert payload["authority_boundary_receipt"] == {"authority_counters": _zero_authority_counters(), "receipt_hash": "sha256:" + "a" * 64}
    assert payload["decision_hash"] == stable_hash({key: value for key, value in payload.items() if key != "decision_hash"})

    with pytest.raises(FrozenInstanceError):
        first.selected_label = "no_action"  # type: ignore[misc]


def test_selector_escalates_permanently_human_authorized_operation() -> None:
    episode = _episode()
    episode["human_authorization_required"] = True

    decision = select_p117_decision(episode).to_dict()

    assert decision["selected_label"] == "escalate"
    assert decision["selected_action_pack_id"] is None
    assert decision["cited_evidence_ids"] == ["ev-cpu", "ev-error"]
    assert decision["deterministic_fallback_reason"] == "human_authorization_required"


@pytest.mark.parametrize(
    ("mutate", "label", "reason"),
    [
        (lambda episode: episode["authority_boundary_receipt"]["authority_counters"].__setitem__("credential_access_count", 1), "abstain", "authority_boundary_nonzero"),
        (lambda episode: episode.__setitem__("missing_evidence_markers", ["missing_metric_window"]), "investigate_more", "missing_required_evidence"),
        (lambda episode: episode.__setitem__("visible_evidence_ids", ["ev-cpu", "ev-rollback-risk"]), "abstain", "contraindication_present"),
        (lambda episode: episode["calibration_profile_ref"].__setitem__("calibrated_confidence", 0.5), "abstain", "calibration_below_threshold"),
        (lambda episode: episode["p116_measured_outcome_refs"][0].__setitem__("utility_interval", [-0.01, 0.55]), "no_action", "utility_interval_crosses_zero"),
        (lambda episode: episode["p116_measured_outcome_refs"][0].__setitem__("measurement_status", "inconclusive"), "no_action", "outcome_not_comparable"),
    ],
)
def test_selector_fails_closed_for_incomplete_evidence_calibration_utility_or_authority(
    mutate: object,
    label: str,
    reason: str,
) -> None:
    episode = _episode()
    mutate(episode)  # type: ignore[operator]

    decision = select_p117_decision(episode).to_dict()

    assert decision["selected_label"] == label
    assert decision["selected_action_pack_id"] is None
    assert decision["deterministic_fallback_reason"] == reason
    assert decision["execution_authority"] == "none"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda episode: episode.__setitem__("schema_version", "p117.decision_episode.v2"), "invalid_episode_schema"),
        (lambda episode: episode["p115_signed_action_pack_refs"][0].__setitem__("action_pack_id", "invented"), "unknown_outcome_action_pack_id"),
        (lambda episode: episode["p115_signed_action_pack_refs"][0].__setitem__("signed", False), "unsigned_action_pack"),
        (lambda episode: episode["p115_signed_action_pack_refs"][0].__setitem__("executor_disabled", False), "action_authority_enabled"),
        (lambda episode: episode["p115_signed_action_pack_refs"][0].__setitem__("validation_plan", {"command": "kubectl delete pod"}), "forbidden_authority_text"),
        (lambda episode: episode["p116_measured_outcome_refs"][0].__setitem__("denominator", 0), "missing_outcome_denominator"),
    ],
)
def test_selector_rejects_unknown_ids_unsigned_packs_authority_text_and_missing_denominators(mutate: object, message: str) -> None:
    episode = _episode()
    mutate(episode)  # type: ignore[operator]

    with pytest.raises(P117SelectorError, match=message):
        select_p117_decision(episode)


def _episode() -> dict[str, object]:
    return {
        "schema_version": "p117.decision_episode.v1",
        "decision_episode_id": "episode-1",
        "visible_evidence_ids": ["ev-cpu", "ev-error"],
        "missing_evidence_markers": [],
        "p115_signed_action_pack_refs": [
            _action_pack("act_restart_worker", required=("ev-cpu", "ev-error"), contraindications=("ev-rollback-risk",)),
            _action_pack("act_shed_load", required=("ev-cpu",), contraindications=()),
        ],
        "p116_measured_outcome_refs": [
            _outcome("act_restart_worker", utility=0.42, interval=(0.18, 0.55)),
            _outcome("act_shed_load", utility=0.20, interval=(0.05, 0.32)),
        ],
        "calibration_profile_ref": {"calibrated_confidence": 0.82, "acceptance_threshold": 0.7, "profile_hash": "sha256:" + "b" * 64},
        "utility_profile_ref": {"utility_threshold": 0.0, "profile_hash": "sha256:" + "c" * 64},
        "evaluation_split": "development",
        "frozen_seed": 117,
        "authority_boundary_receipt": {"authority_counters": _zero_authority_counters(), "receipt_hash": "sha256:" + "a" * 64},
    }


def _action_pack(action_pack_id: str, *, required: tuple[str, ...], contraindications: tuple[str, ...]) -> dict[str, object]:
    return {
        "action_pack_id": action_pack_id,
        "signed": True,
        "signer_id": "p115-catalog",
        "pack_hash": "sha256:" + action_pack_id[-1] * 64,
        "required_evidence_ids": list(required),
        "required_evidence_classes": ["metric_window"],
        "contraindication_evidence_ids": list(contraindications),
        "authority_level": "L1",
        "executor_disabled": True,
        "validation_plan": {"checks": ["post_window_slo"]},
        "rollback_plan": {"metadata_only": True},
    }


def _outcome(action_pack_id: str, *, utility: float, interval: tuple[float, float]) -> dict[str, object]:
    return {
        "action_pack_id": action_pack_id,
        "measurement_status": "comparable",
        "outcome_label": "verified_helpful",
        "utility_delta": utility,
        "utility_interval": list(interval),
        "denominator": 12,
        "controls_comparable": True,
        "natural_recovery_dominates": False,
        "source_hash": "sha256:" + "d" * 64,
    }


def _zero_authority_counters() -> dict[str, int]:
    return {
        "auth_count": 0,
        "credential_access_count": 0,
        "executor_call_count": 0,
        "shell_count": 0,
        "subprocess_count": 0,
        "kubernetes_mutation_count": 0,
        "cloud_mutation_count": 0,
        "database_mutation_count": 0,
        "production_adapter_call_count": 0,
        "network_mutation_count": 0,
        "online_policy_write_count": 0,
        "production_mutation_count": 0,
    }
