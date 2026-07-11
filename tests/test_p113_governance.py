from __future__ import annotations

import copy
import json

import pytest

from app.services.p113_governance import (
    P113GovernanceError,
    build_p113_freeze,
    build_p113_taint_ledger,
    select_p113_narrative_subset,
    validate_p113_blind_governance,
    validate_p113_release_inputs,
)

TT_HASH = "sha256:2b33b7ab07198e0d69f229e697bfcef794a656e8db73a1d732142effde17c595"
P112_HASH = "sha256:" + "1" * 64


def _case_ids(prefix: str, count: int) -> list[str]:
    return [f"{prefix}-{index:03d}" for index in range(count)]


def _tt_cases() -> list[dict[str, object]]:
    return [{"case_id": case_id, "label": f"hidden-{index % 5}"} for index, case_id in enumerate(_case_ids("tt", 125))]


def _ledger() -> dict[str, object]:
    return build_p113_taint_ledger(
        consumed_p112_source_hashes=(P112_HASH,),
        allowed_p112_final_summary_facts={
            "p112_aggregate_metrics": "P112 candidate reached 76% service Top-1, 92% Top-3, and 68% fault accuracy.",
            "p112_provider_noncompliance": "The live candidate failed many provider contract outputs closed.",
            "p112_disk_weakness": "Disk classification was weak at aggregate level.",
        },
    )


def _freeze() -> dict[str, object]:
    return build_p113_freeze(
        tt_source_hash=TT_HASH,
        tt_cases=_tt_cases(),
        train_case_ids=_case_ids("ss", 75),
        dev_case_ids=_case_ids("ob", 50),
        model_hash="sha256:" + "2" * 64,
        p112_baseline_hash="sha256:" + "3" * 64,
        diagnosis_packet_hash="sha256:" + "4" * 64,
        narrative_packet_hash="sha256:" + "5" * 64,
        system_prompt_hash="sha256:" + "6" * 64,
        endpoint_hash="sha256:" + "7" * 64,
        decoding_hash="sha256:" + "8" * 64,
        code_hash="sha256:" + "9" * 64,
        gates_hash="sha256:" + "a" * 64,
        frozen_at="2026-07-11T00:00:00Z",
    )


def test_taint_ledger_allows_only_declared_p112_final_summary_facts() -> None:
    ledger = _ledger()
    validate_p113_release_inputs(
        ledger,
        {
            "architecture_notes": [
                {
                    "source_hash": P112_HASH,
                    "fact_id": "p112_aggregate_metrics",
                    "fact_value": "P112 candidate reached 76% service Top-1, 92% Top-3, and 68% fault accuracy.",
                    "granularity": "aggregate_final_summary",
                    "artifact_type": "aggregate_final_summary_fact",
                },
            ],
        },
    )

    with pytest.raises(P113GovernanceError, match="undeclared_p112_final_summary_fact"):
        validate_p113_release_inputs(
            ledger,
            {
                "architecture_notes": [
                    {
                        "source_hash": P112_HASH,
                        "fact_id": "case_tt_001",
                        "fact_value": "not declared",
                        "granularity": "aggregate_final_summary",
                        "artifact_type": "aggregate_final_summary_fact",
                    },
                ],
            },
        )


def test_taint_ledger_rejects_p112_rep4_source_artifact_without_declared_aggregate_fact() -> None:
    with pytest.raises(P113GovernanceError, match="tainted_p112_case_level_material"):
        validate_p113_release_inputs(
            _ledger(),
            {
                "architecture_notes": [
                    {
                        "system": "RE1-OB",
                        "repetition": 4,
                        "granularity": "source",
                        "artifact_type": "source_case_bundle",
                    },
                ],
            },
        )


def test_taint_ledger_rejects_case_level_smuggling_and_missing_provenance() -> None:
    with pytest.raises(P113GovernanceError, match="aggregate_fact_schema_violation"):
        validate_p113_release_inputs(
            _ledger(),
            {
                "architecture_notes": [
                    {
                        "source_hash": P112_HASH,
                        "fact_id": "p112_aggregate_metrics",
                        "fact_value": "P112 candidate reached 76% service Top-1, 92% Top-3, and 68% fault accuracy.",
                        "granularity": "aggregate_final_summary",
                        "artifact_type": "aggregate_final_summary_fact",
                        "case_id": "ob-004-017",
                    }
                ]
            },
        )

    with pytest.raises(P113GovernanceError, match="unproven_case_level_provenance"):
        validate_p113_release_inputs(
            _ledger(),
            {"training": [{"artifact_type": "label", "case_id": "ob-004-017"}]},
        )


@pytest.mark.parametrize(
    ("input_name", "artifact_type"),
    [
        ("training", "label"),
        ("selection", "per_case_error"),
        ("fixtures", "fixture"),
        ("prompts", "prompt_example"),
        ("thresholds", "threshold"),
        ("weights", "weight"),
        ("release_counting", "case_result"),
    ],
)
def test_taint_ledger_rejects_p112_ob_rep4_case_level_material(input_name: str, artifact_type: str) -> None:
    with pytest.raises(P113GovernanceError, match=f"tainted_p112_rep4:{input_name}"):
        validate_p113_release_inputs(
            _ledger(),
            {
                input_name: [
                    {
                        "source_hash": P112_HASH,
                        "system": "RE1-OB",
                        "repetition": 4,
                        "granularity": "case",
                        "artifact_type": artifact_type,
                        "case_id": "ob-004-017",
                    },
                ],
            },
        )


def test_blind_governance_requires_fresh_tt_hash_and_125_unique_cases_before_scoring() -> None:
    validate_p113_blind_governance(
        _freeze(),
        tt_source_hash=TT_HASH,
        tt_cases=_tt_cases(),
        train_case_ids=_case_ids("ss", 75),
        dev_case_ids=_case_ids("ob", 50),
        scoring_started_at="2026-07-11T00:00:01Z",
    )

    reused = copy.deepcopy(_freeze())
    reused["tt_source_hash"] = P112_HASH
    with pytest.raises(P113GovernanceError, match="tt_source_not_fresh"):
        validate_p113_blind_governance(
            reused,
            tt_source_hash=P112_HASH,
            tt_cases=_tt_cases(),
            train_case_ids=_case_ids("ss", 75),
            dev_case_ids=_case_ids("ob", 50),
            scoring_started_at="2026-07-11T00:00:01Z",
        )

    duplicate_cases = _tt_cases()
    duplicate_cases[-1]["case_id"] = duplicate_cases[0]["case_id"]
    with pytest.raises(P113GovernanceError, match="tt_case_count_or_uniqueness"):
        build_p113_freeze(
            tt_source_hash=TT_HASH,
            tt_cases=duplicate_cases,
            train_case_ids=_case_ids("ss", 75),
            dev_case_ids=_case_ids("ob", 50),
            model_hash="sha256:" + "2" * 64,
            p112_baseline_hash="sha256:" + "3" * 64,
            diagnosis_packet_hash="sha256:" + "4" * 64,
            narrative_packet_hash="sha256:" + "5" * 64,
            system_prompt_hash="sha256:" + "6" * 64,
            endpoint_hash="sha256:" + "7" * 64,
            decoding_hash="sha256:" + "8" * 64,
            code_hash="sha256:" + "9" * 64,
            gates_hash="sha256:" + "a" * 64,
            frozen_at="2026-07-11T00:00:00Z",
        )


def test_blind_governance_rejects_train_dev_overlap_and_scoring_before_freeze() -> None:
    with pytest.raises(P113GovernanceError, match="tt_overlaps_train_or_dev"):
        build_p113_freeze(
            tt_source_hash=TT_HASH,
            tt_cases=_tt_cases(),
            train_case_ids=("tt-000",),
            dev_case_ids=(),
            model_hash="sha256:" + "2" * 64,
            p112_baseline_hash="sha256:" + "3" * 64,
            diagnosis_packet_hash="sha256:" + "4" * 64,
            narrative_packet_hash="sha256:" + "5" * 64,
            system_prompt_hash="sha256:" + "6" * 64,
            endpoint_hash="sha256:" + "7" * 64,
            decoding_hash="sha256:" + "8" * 64,
            code_hash="sha256:" + "9" * 64,
            gates_hash="sha256:" + "a" * 64,
            frozen_at="2026-07-11T00:00:00Z",
        )


def test_blind_governance_requires_timezone_aware_freeze_and_scoring_timestamps() -> None:
    with pytest.raises(P113GovernanceError, match="timezone_required:frozen_at"):
        build_p113_freeze(
            tt_source_hash=TT_HASH,
            tt_cases=_tt_cases(),
            train_case_ids=_case_ids("ss", 75),
            dev_case_ids=_case_ids("ob", 50),
            model_hash="sha256:" + "2" * 64,
            p112_baseline_hash="sha256:" + "3" * 64,
            diagnosis_packet_hash="sha256:" + "4" * 64,
            narrative_packet_hash="sha256:" + "5" * 64,
            system_prompt_hash="sha256:" + "6" * 64,
            endpoint_hash="sha256:" + "7" * 64,
            decoding_hash="sha256:" + "8" * 64,
            code_hash="sha256:" + "9" * 64,
            gates_hash="sha256:" + "a" * 64,
            frozen_at="2026-07-11T00:00:00",
        )

    with pytest.raises(P113GovernanceError, match="timezone_required:scoring_started_at"):
        validate_p113_blind_governance(
            _freeze(),
            tt_source_hash=TT_HASH,
            tt_cases=_tt_cases(),
            train_case_ids=_case_ids("ss", 75),
            dev_case_ids=_case_ids("ob", 50),
            scoring_started_at="2026-07-11T00:00:01",
        )

    with pytest.raises(P113GovernanceError, match="score_before_freeze"):
        validate_p113_blind_governance(
            _freeze(),
            tt_source_hash=TT_HASH,
            tt_cases=_tt_cases(),
            train_case_ids=_case_ids("ss", 75),
            dev_case_ids=_case_ids("ob", 50),
            scoring_started_at="2026-07-10T23:59:59Z",
        )


def test_freeze_binds_hashes_and_detects_current_input_drift() -> None:
    frozen = _freeze()
    changed_cases = _tt_cases()
    changed_cases[0]["case_id"] = "tt-changed"

    with pytest.raises(P113GovernanceError, match="freeze_mismatch:tt_case_ids_hash"):
        validate_p113_blind_governance(
            frozen,
            tt_source_hash=TT_HASH,
            tt_cases=changed_cases,
            train_case_ids=_case_ids("ss", 75),
            dev_case_ids=_case_ids("ob", 50),
            scoring_started_at="2026-07-11T00:00:01Z",
        )


def test_narrative_subset_is_exactly_25_and_ignores_labels() -> None:
    cases = _tt_cases()
    subset = select_p113_narrative_subset(cases)

    relabeled = copy.deepcopy(cases)
    for case in relabeled:
        case["label"] = "changed-after-freeze"

    assert len(subset) == 25
    assert len(set(subset)) == 25
    assert subset == select_p113_narrative_subset(relabeled)
    assert set(subset) <= {str(case["case_id"]) for case in cases}


def test_freeze_manifest_has_no_action_or_auth_authority() -> None:
    frozen = _freeze()
    assert frozen["action_contract_status"] == "disabled"
    assert frozen["action_execution_enabled"] is False
    assert frozen["credential_access_enabled"] is False
    assert frozen["auth_authority"] == "none"
    subset = frozen["narrative_subset_case_ids"]
    assert isinstance(subset, list)
    assert len(subset) == 25


def test_serialized_freeze_round_trip_remains_governance_valid() -> None:
    frozen = json.loads(json.dumps(_freeze()))

    validate_p113_blind_governance(
        frozen,
        tt_source_hash=TT_HASH,
        tt_cases=_tt_cases(),
        train_case_ids=_case_ids("ss", 75),
        dev_case_ids=_case_ids("ob", 50),
        scoring_started_at="2026-07-11T00:00:01Z",
    )
