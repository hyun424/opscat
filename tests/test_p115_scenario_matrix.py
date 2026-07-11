from __future__ import annotations

import copy
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p115_scenario_matrix import (
    PARTITION_MANIFEST_SCHEMA_VERSION,
    REQUIRED_EVALUATOR_LABELS,
    ROADMAP_FAMILIES,
    P115ScenarioMatrixError,
    build_p115_scenario_matrix,
    build_partition_manifest,
    validate_p115_scenario_matrix,
)


def test_p115_scenario_matrix_builds_600_cases_with_required_family_label_partition_denominators() -> None:
    matrix = build_p115_scenario_matrix()
    payload = matrix.to_dict()
    validation = validate_p115_scenario_matrix(matrix.cases, matrix.evaluator_labels, matrix.partition_manifest)

    assert payload["schema_version"] == "p115.scenario_matrix.v1"
    assert len(matrix.cases) == 600
    assert validation["case_count"] == 600
    assert validation["family_count"] == 15
    assert set(validation["denominators"]["by_family"]) == set(ROADMAP_FAMILIES)

    labels_by_case = {str(label["case_id"]): str(label["evaluator_label"]) for label in matrix.evaluator_labels}
    for family in ROADMAP_FAMILIES:
        family_cases = [case for case in matrix.cases if case["scenario_family"] == family]
        assert len(family_cases) == 40
        assert {labels_by_case[str(case["case_id"])] for case in family_cases} == REQUIRED_EVALUATOR_LABELS
        for label in REQUIRED_EVALUATOR_LABELS:
            for role in ("development", "holdout"):
                assert validation["denominators"]["by_family_label"][family][label][role] > 0

    assert validation["denominators"]["by_label"]["no_action"]["development"] > 0
    assert validation["denominators"]["by_label"]["investigate_more"]["holdout"] > 0
    assert validation["denominators"]["by_label"]["contraindicated"]["development"] > 0
    assert validation["denominators"]["by_label"]["harmful_or_ineffective"]["holdout"] > 0


def test_p115_scenario_matrix_is_deterministic_and_manifest_hash_bound() -> None:
    first = build_p115_scenario_matrix()
    second = build_p115_scenario_matrix()

    assert first.matrix_hash == second.matrix_hash
    assert first.to_dict() == second.to_dict()
    assert first.partition_manifest["schema_version"] == PARTITION_MANIFEST_SCHEMA_VERSION
    assert first.partition_manifest["matrix_hash"] == first.matrix_hash
    assert first.partition_manifest["manifest_hash"] == stable_hash(
        {key: value for key, value in first.partition_manifest.items() if key != "manifest_hash"}
    )
    assert all(group["release_role"] in {"development", "holdout"} for group in _groups(first.partition_manifest))


def test_p115_partition_manifest_keeps_groups_intact_and_hashes_group_units() -> None:
    matrix = build_p115_scenario_matrix()
    groups = _groups(matrix.partition_manifest)
    case_to_role = {str(case["case_id"]): str(case["release_role"]) for case in matrix.cases}
    case_to_group = {str(case["case_id"]): str(case["partition_group"]) for case in matrix.cases}

    assert len(groups) == 300
    assert all(len(group["case_ids"]) == 2 for group in groups)
    for group in groups:
        group_role = str(group["release_role"])
        assert group["group_hash"] == stable_hash({key: value for key, value in group.items() if key != "group_hash"})
        for case_id in group["case_ids"]:
            assert case_to_role[str(case_id)] == group_role
            assert case_to_group[str(case_id)] == group["group_id"]


def test_p115_candidate_visible_cases_have_no_outcome_truth_or_execution_authority() -> None:
    matrix = build_p115_scenario_matrix()
    candidate_cases = matrix.candidate_visible_cases()

    assert candidate_cases
    assert all("evaluator_label" not in case for case in candidate_cases)
    assert all("hidden_outcome" not in str(case) for case in candidate_cases)
    assert all(case["execution_authority"] is False for case in candidate_cases)
    assert all(case["executed_actions"] == [] for case in candidate_cases)
    assert all(case["executable_body"] is None for case in candidate_cases)
    assert {str(label["evaluator_label"]) for label in matrix.evaluator_labels} == REQUIRED_EVALUATOR_LABELS


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        ("truth_field", "candidate_visible_truth_field"),
        ("execution_field", "candidate_visible_execution_authority"),
        ("manifest_hash", "partition_manifest_hash_mismatch"),
        ("row_split", "row_level_split_leak"),
        ("exact_duplicate", "exact_duplicate"),
        ("near_duplicate", "near_duplicate_holdout"),
        ("topology_time", "shared_topology_time_leak"),
        ("missing_family_denominator", "matrix_case_count_below_300|missing_roadmap_family|missing_family_denominator"),
    ],
)
def test_p115_scenario_matrix_fails_closed_on_contamination(mutator: str, error: str) -> None:
    matrix = build_p115_scenario_matrix()
    cases = [dict(case) for case in matrix.cases]
    labels = [dict(label) for label in matrix.evaluator_labels]
    manifest = copy.deepcopy(matrix.partition_manifest)

    if mutator == "truth_field":
        cases[0]["groundTruth"] = "do-not-show"
    elif mutator == "execution_field":
        cases[0]["candidate_context"] = {**_mapping(cases[0]["candidate_context"]), "command": "kubectl delete pod"}
    elif mutator == "manifest_hash":
        manifest["groups"][0]["case_ids"] = list(manifest["groups"][0]["case_ids"]) + ["p115-forged"]
    elif mutator == "row_split":
        case_id = str(manifest["groups"][0]["case_ids"][0])
        target = next(case for case in cases if case["case_id"] == case_id)
        target["release_role"] = "holdout" if target["release_role"] == "development" else "development"
    elif mutator == "exact_duplicate":
        cases[1] = {**cases[0], "case_id": "p115-exact-duplicate"}
        labels[1] = {**labels[0], "case_id": "p115-exact-duplicate"}
        manifest = build_partition_manifest(cases, matrix_hash=stable_hash(cases))
    elif mutator == "near_duplicate":
        dev_case = next(case for case in cases if case["release_role"] == "development")
        holdout_index, holdout_case = next((index, case) for index, case in enumerate(cases) if case["release_role"] == "holdout")
        copied = {
            **holdout_case,
            "source_family": dev_case["source_family"],
            "service": dev_case["service"],
            "scenario_family": dev_case["scenario_family"],
            "visible_evidence_classes": list(dev_case["visible_evidence_classes"]),
            "eligible_action_pack_ids": list(dev_case["eligible_action_pack_ids"]),
            "candidate_context": {
                **_mapping(dev_case["candidate_context"]),
                "observed_markers": ["holdout_specific_marker"],
            },
            "action_pack_family": dev_case["action_pack_family"],
            "partition_group": "p115_near_duplicate_holdout_group",
        }
        cases[holdout_index] = copied
        labels_by_case = {str(label["case_id"]): label for label in labels}
        labels_by_case[str(holdout_case["case_id"])]["evaluator_label"] = next(
            str(label["evaluator_label"]) for label in labels if label["case_id"] == dev_case["case_id"]
        )
        manifest = build_partition_manifest(cases, matrix_hash=stable_hash(cases))
    elif mutator == "topology_time":
        dev_case = next(case for case in cases if case["release_role"] == "development")
        holdout_case = next(case for case in cases if case["release_role"] == "holdout")
        holdout_case["topology_handle"] = dev_case["topology_handle"]
        holdout_case["time_bucket"] = dev_case["time_bucket"]
        holdout_case["partition_group"] = "p115_shared_topology_time_group"
        manifest = build_partition_manifest(cases, matrix_hash=stable_hash(cases))
    elif mutator == "missing_family_denominator":
        cases = [case for case in cases if case["scenario_family"] != ROADMAP_FAMILIES[0]]
        labels = [label for label in labels if label["scenario_family"] != ROADMAP_FAMILIES[0]]
        manifest = build_partition_manifest(cases, matrix_hash=stable_hash(cases))

    with pytest.raises(P115ScenarioMatrixError, match=error):
        validate_p115_scenario_matrix(cases, labels, manifest)


def test_p115_generated_matrix_has_no_row_level_or_group_leakage() -> None:
    matrix = build_p115_scenario_matrix()
    roles_by_group = defaultdict_set()
    roles_by_topology_time = defaultdict_set()
    roles_by_group_key = defaultdict_set()

    for case in matrix.cases:
        roles_by_group[str(case["partition_group"])].add(str(case["release_role"]))
        roles_by_topology_time[(str(case["topology_handle"]), str(case["time_bucket"]))].add(str(case["release_role"]))
        roles_by_group_key[
            (
                str(case["source_family"]),
                str(case["service"]),
                str(case["topology_handle"]),
                str(case["scenario_family"]),
                str(case["time_bucket"]),
                str(case["action_pack_family"]),
            )
        ].add(str(case["release_role"]))

    assert Counter(len(roles) for roles in roles_by_group.values()) == {1: 300}
    assert all(len(roles) == 1 for roles in roles_by_topology_time.values())
    assert all(len(roles) == 1 for roles in roles_by_group_key.values())


def test_candidate_case_ids_and_order_do_not_encode_evaluator_labels() -> None:
    matrix = build_p115_scenario_matrix()
    forbidden = {label.replace("_", "-") for label in REQUIRED_EVALUATOR_LABELS} | set(REQUIRED_EVALUATOR_LABELS)

    for case in matrix.candidate_visible_cases():
        case_id = str(case["case_id"])
        assert case_id.startswith("p115_case_")
        assert not any(token in case_id for token in forbidden)
        assert "row_ordinal" not in case


def _groups(manifest: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    groups = manifest["groups"]
    assert isinstance(groups, Sequence)
    return [group for group in groups if isinstance(group, Mapping)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def defaultdict_set() -> dict[Any, set[str]]:
    return defaultdict(set)
