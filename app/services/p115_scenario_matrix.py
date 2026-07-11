"""Deterministic P115 scenario matrix and grouped partition manifest."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash

SCENARIO_MATRIX_SCHEMA_VERSION = "p115.scenario_matrix.v1"
PARTITION_MANIFEST_SCHEMA_VERSION = "p115.partition_manifest.v1"
ROADMAP_FAMILIES: tuple[str, ...] = (
    "cpu",
    "memory",
    "disk",
    "network_delay",
    "network_loss",
    "socket",
    "deploy",
    "dependency",
    "database_pool",
    "queue",
    "dns",
    "certificate",
    "quota",
    "cache",
    "traffic",
)
REQUIRED_EVALUATOR_LABELS = frozenset(
    {"action", "no_action", "investigate_more", "contraindicated", "harmful_or_ineffective"}
)
RELEASE_ROLES = frozenset({"development", "holdout"})
TRUTH_BEARING_FIELDS = frozenset(
    {
        "answer",
        "answer_key",
        "expected_action",
        "expected_fault",
        "expected_label",
        "expected_outcome",
        "expected_root_cause",
        "ground_truth",
        "hidden_outcome",
        "label",
        "oracle",
        "outcome_truth",
        "root_cause",
        "root_service",
        "scorer_only_truth",
        "truth",
        "truth_hash",
    }
)
EXECUTION_AUTHORITY_FIELDS = frozenset(
    {
        "ansible",
        "argv",
        "cloud_mutation",
        "command",
        "commands",
        "credential",
        "database_mutation",
        "executable",
        "executor",
        "kubectl",
        "network_mutation",
        "production_adapter",
        "shell",
        "subprocess",
    }
)

_SOURCE_FAMILIES = ("controlled_lab", "replay_fixture", "synthetic_counterfactual")
_SERVICES = ("checkout", "payments", "orders", "inventory", "gateway")
_EVIDENCE_CLASSES_BY_LABEL = {
    "action": ("metric", "log", "trace"),
    "no_action": ("metric", "status"),
    "investigate_more": ("metric", "missing_trace"),
    "contraindicated": ("metric", "change_event", "safety_marker"),
    "harmful_or_ineffective": ("metric", "counter_signal", "rollback_marker"),
}


class P115ScenarioMatrixError(ValueError):
    """Raised when the P115 scenario matrix or partition manifest is unsafe."""


@dataclass(frozen=True)
class P115ScenarioMatrix:
    schema_version: str
    cases: tuple[Mapping[str, Any], ...]
    evaluator_labels: tuple[Mapping[str, Any], ...]
    partition_manifest: Mapping[str, Any]
    matrix_hash: str

    def candidate_visible_cases(self) -> list[dict[str, Any]]:
        return [dict(case) for case in self.cases]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "cases": [dict(case) for case in self.cases],
            "evaluator_labels": [dict(label) for label in self.evaluator_labels],
            "partition_manifest": dict(self.partition_manifest),
            "matrix_hash": self.matrix_hash,
        }


def build_p115_scenario_matrix() -> P115ScenarioMatrix:
    """Build the frozen 15-family, 600-case grouped P115 matrix."""

    cases: list[dict[str, Any]] = []
    evaluator_labels: list[dict[str, Any]] = []
    for family_index, family in enumerate(ROADMAP_FAMILIES):
        for label_index, evaluator_label in enumerate(sorted(REQUIRED_EVALUATOR_LABELS)):
            action_family = f"{family}_candidate_response_pack"
            for role_index, release_role in enumerate(("development", "holdout")):
                for group_index in range(2):
                    source_family = _SOURCE_FAMILIES[(family_index + label_index + group_index) % len(_SOURCE_FAMILIES)]
                    service = _SERVICES[(family_index + label_index + role_index + group_index) % len(_SERVICES)]
                    topology_handle = f"topology:p115-{release_role}-{family}-{label_index}-{group_index}"
                    time_bucket = f"2026w{30 + role_index:02d}-{family_index:02d}-{label_index}-{group_index}"
                    partition_group = _partition_group(
                        source_family=source_family,
                        service=service,
                        topology_handle=topology_handle,
                        incident_family=family,
                        time_bucket=time_bucket,
                        action_family=action_family,
                    )
                    for case_index in range(2):
                        case_id = "p115_case_" + stable_hash(
                            {
                                "family": family,
                                "evaluator_partition_key": evaluator_label,
                                "release_role": release_role,
                                "group_index": group_index,
                                "case_index": case_index,
                            }
                        )[7:31]
                        evidence_handle = f"evidence:{case_id}"
                        diagnosis_handle = f"diagnosis:{case_id}"
                        visible_markers = _visible_markers(family, group_index, case_index)
                        cases.append(
                            {
                                "schema_version": "p115.incident_case.v1",
                                "case_id": case_id,
                                "source_family": source_family,
                                "service": service,
                                "scenario_family": family,
                                "topology_handle": topology_handle,
                                "time_bucket": time_bucket,
                                "time_window": _time_window(role_index, family_index, label_index, group_index, case_index),
                                "visible_evidence_handle": evidence_handle,
                                "diagnosis_handle": diagnosis_handle,
                                "visible_evidence_classes": list(_EVIDENCE_CLASSES_BY_LABEL[evaluator_label]),
                                "candidate_context": {
                                    "symptom": f"{family} signal pattern {group_index}-{case_index}",
                                    "observed_markers": visible_markers,
                                    "missing_evidence": ["trace_span"] if evaluator_label == "investigate_more" else [],
                                    "safety_notes": ["executor disabled", "recommendation only"],
                                },
                                "eligible_action_pack_ids": [f"p115_pack_{family}_candidate_response"],
                                "action_pack_family": action_family,
                                "partition_group": partition_group,
                                "release_role": release_role,
                                "authority_level": "L1",
                                "execution_authority": False,
                                "executed_actions": [],
                                "executable_body": None,
                            }
                        )
                        evaluator_labels.append(
                            {
                                "schema_version": "p115.evaluator_label.v1",
                                "case_id": case_id,
                                "evaluator_label": evaluator_label,
                                "scenario_family": family,
                                "release_role": release_role,
                                "partition_group": partition_group,
                            }
                        )
    cases.sort(key=lambda item: str(item["case_id"]))
    evaluator_labels.sort(key=lambda item: str(item["case_id"]))
    matrix_hash = stable_hash({"schema_version": SCENARIO_MATRIX_SCHEMA_VERSION, "cases": cases, "evaluator_labels": evaluator_labels})
    partition_manifest = build_partition_manifest(cases, matrix_hash=matrix_hash)
    validate_p115_scenario_matrix(cases, evaluator_labels, partition_manifest)
    return P115ScenarioMatrix(
        schema_version=SCENARIO_MATRIX_SCHEMA_VERSION,
        cases=tuple(cases),
        evaluator_labels=tuple(evaluator_labels),
        partition_manifest=partition_manifest,
        matrix_hash=matrix_hash,
    )


def build_partition_manifest(cases: Sequence[Mapping[str, Any]], *, matrix_hash: str) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for case in cases:
        group_id = _required_text(case, "partition_group")
        release_role = _required_text(case, "release_role")
        if release_role not in RELEASE_ROLES:
            raise P115ScenarioMatrixError("invalid_release_role")
        group_key = _group_key(case)
        existing = groups.get(group_id)
        if existing is None:
            groups[group_id] = {
                "group_id": group_id,
                "release_role": release_role,
                "source_family": group_key["source_family"],
                "service": group_key["service"],
                "topology_handle": group_key["topology_handle"],
                "incident_family": group_key["incident_family"],
                "time_bucket": group_key["time_bucket"],
                "action_pack_family": group_key["action_pack_family"],
                "case_ids": [],
            }
        elif {key: existing[key] for key in group_key} != group_key or existing["release_role"] != release_role:
            raise P115ScenarioMatrixError(f"row_level_split_or_group_key_mismatch:{group_id}")
        groups[group_id]["case_ids"].append(str(case.get("case_id", "")))

    group_rows = []
    for group in groups.values():
        case_ids = sorted(group["case_ids"])
        row = {**group, "case_ids": case_ids}
        row["group_hash"] = stable_hash({key: value for key, value in row.items() if key != "group_hash"})
        group_rows.append(row)
    group_rows.sort(key=lambda item: str(item["group_id"]))

    payload: dict[str, Any] = {
        "schema_version": PARTITION_MANIFEST_SCHEMA_VERSION,
        "matrix_hash": matrix_hash,
        "split_unit": ["source_family", "service", "topology_handle", "incident_family", "time_bucket", "action_pack_family"],
        "release_roles": ["development", "holdout"],
        "groups": group_rows,
        "frozen": True,
    }
    payload["manifest_hash"] = stable_hash({key: value for key, value in payload.items() if key != "manifest_hash"})
    return payload


def validate_p115_scenario_matrix(
    cases: Sequence[Mapping[str, Any]],
    evaluator_labels: Sequence[Mapping[str, Any]],
    partition_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if len(cases) < 300:
        raise P115ScenarioMatrixError("matrix_case_count_below_300")
    if len({str(case.get("case_id", "")) for case in cases}) != len(cases):
        raise P115ScenarioMatrixError("duplicate_case_id")
    if partition_manifest.get("schema_version") != PARTITION_MANIFEST_SCHEMA_VERSION:
        raise P115ScenarioMatrixError("invalid_partition_manifest_schema")
    if partition_manifest.get("frozen") is not True:
        raise P115ScenarioMatrixError("partition_manifest_not_frozen")
    expected_manifest_hash = stable_hash({key: value for key, value in partition_manifest.items() if key != "manifest_hash"})
    if partition_manifest.get("manifest_hash") != expected_manifest_hash:
        raise P115ScenarioMatrixError("partition_manifest_hash_mismatch")

    labels_by_case = _labels_by_case(evaluator_labels)
    missing_labels = sorted(str(case.get("case_id", "")) for case in cases if str(case.get("case_id", "")) not in labels_by_case)
    if missing_labels:
        raise P115ScenarioMatrixError(f"missing_evaluator_label:{missing_labels[0]}")

    _reject_candidate_visible_truth_and_authority(cases)
    _validate_manifest_groups(cases, partition_manifest)
    _detect_exact_and_near_duplicates(cases)
    _detect_shared_topology_time_leakage(cases)
    denominators = _denominators(cases, labels_by_case)
    _validate_denominators(denominators)
    return {
        "schema_version": "p115.scenario_matrix_validation.v1",
        "case_count": len(cases),
        "family_count": len(denominators["by_family"]),
        "denominators": denominators,
        "partition_manifest_hash": partition_manifest["manifest_hash"],
        "passed": True,
    }


def _validate_manifest_groups(cases: Sequence[Mapping[str, Any]], partition_manifest: Mapping[str, Any]) -> None:
    manifest_groups = {str(group.get("group_id", "")): group for group in _mapping_sequence(partition_manifest.get("groups"))}
    if not manifest_groups:
        raise P115ScenarioMatrixError("missing_partition_groups")
    seen_case_ids: set[str] = set()
    for group_id, group in manifest_groups.items():
        if group.get("group_hash") != stable_hash({key: value for key, value in group.items() if key != "group_hash"}):
            raise P115ScenarioMatrixError(f"group_hash_mismatch:{group_id}")
        seen_case_ids.update(str(case_id) for case_id in _sequence(group.get("case_ids")))

    case_ids = {str(case.get("case_id", "")) for case in cases}
    if seen_case_ids != case_ids:
        raise P115ScenarioMatrixError("manifest_case_set_mismatch")

    groups_by_case: dict[str, str] = {}
    for group_id, group in manifest_groups.items():
        for case_id in _sequence(group.get("case_ids")):
            groups_by_case[str(case_id)] = group_id
    group_role_by_id = {group_id: str(group.get("release_role", "")) for group_id, group in manifest_groups.items()}
    group_key_by_id = {
        group_id: {
            "source_family": str(group.get("source_family", "")),
            "service": str(group.get("service", "")),
            "topology_handle": str(group.get("topology_handle", "")),
            "incident_family": str(group.get("incident_family", "")),
            "time_bucket": str(group.get("time_bucket", "")),
            "action_pack_family": str(group.get("action_pack_family", "")),
        }
        for group_id, group in manifest_groups.items()
    }
    for case in cases:
        case_id = str(case.get("case_id", ""))
        group_id = str(case.get("partition_group", ""))
        if groups_by_case.get(case_id) != group_id:
            raise P115ScenarioMatrixError(f"case_group_not_manifest_bound:{case_id}")
        if group_role_by_id[group_id] != str(case.get("release_role", "")):
            raise P115ScenarioMatrixError(f"row_level_split_leak:{group_id}")
        if group_key_by_id[group_id] != _group_key(case):
            raise P115ScenarioMatrixError(f"group_key_mismatch:{group_id}")


def _detect_exact_and_near_duplicates(cases: Sequence[Mapping[str, Any]]) -> None:
    exact: dict[str, str] = {}
    near: dict[str, str] = {}
    for case in cases:
        case_id = str(case.get("case_id", ""))
        exact_signature = stable_hash(_candidate_duplicate_signature(case, include_variant=True))
        if exact_signature in exact:
            raise P115ScenarioMatrixError(f"exact_duplicate:{exact[exact_signature]}:{case_id}")
        exact[exact_signature] = case_id
        near_signature = stable_hash(_candidate_duplicate_signature(case, include_variant=False))
        if near_signature in near and _partition_of_case(case_id, cases) != _partition_of_case(near[near_signature], cases):
            raise P115ScenarioMatrixError(f"near_duplicate_holdout:{near[near_signature]}:{case_id}")
        near[near_signature] = case_id


def _detect_shared_topology_time_leakage(cases: Sequence[Mapping[str, Any]]) -> None:
    roles_by_topology_time: dict[tuple[str, str], set[str]] = defaultdict(set)
    roles_by_group_key: dict[tuple[str, str, str, str, str, str], set[str]] = defaultdict(set)
    for case in cases:
        role = str(case.get("release_role", ""))
        roles_by_topology_time[(str(case.get("topology_handle", "")), str(case.get("time_bucket", "")))].add(role)
        key = _group_key(case)
        roles_by_group_key[
            (
                key["source_family"],
                key["service"],
                key["topology_handle"],
                key["incident_family"],
                key["time_bucket"],
                key["action_pack_family"],
            )
        ].add(role)
    for roles in roles_by_topology_time.values():
        if len(roles) > 1:
            raise P115ScenarioMatrixError("shared_topology_time_leak")
    for roles in roles_by_group_key.values():
        if len(roles) > 1:
            raise P115ScenarioMatrixError("group_leakage_across_partitions")


def _reject_candidate_visible_truth_and_authority(cases: Sequence[Mapping[str, Any]]) -> None:
    for case in cases:
        _reject_forbidden_candidate_fields(case)
        if case.get("execution_authority") is not False:
            raise P115ScenarioMatrixError("execution_authority_not_disabled")
        if _sequence(case.get("executed_actions")):
            raise P115ScenarioMatrixError("executed_actions_not_empty")
        if case.get("executable_body") is not None:
            raise P115ScenarioMatrixError("executable_body_present")


def _reject_forbidden_candidate_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normalized(key)
            if normalized in TRUTH_BEARING_FIELDS:
                raise P115ScenarioMatrixError(f"candidate_visible_truth_field:{key}")
            if normalized in EXECUTION_AUTHORITY_FIELDS:
                raise P115ScenarioMatrixError(f"candidate_visible_execution_authority:{key}")
            _reject_forbidden_candidate_fields(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_forbidden_candidate_fields(item)


def _denominators(cases: Sequence[Mapping[str, Any]], labels_by_case: Mapping[str, str]) -> dict[str, Any]:
    by_family: dict[str, dict[str, int]] = {family: {"development": 0, "holdout": 0} for family in ROADMAP_FAMILIES}
    by_family_label: dict[str, dict[str, dict[str, int]]] = {
        family: {label: {"development": 0, "holdout": 0} for label in sorted(REQUIRED_EVALUATOR_LABELS)} for family in ROADMAP_FAMILIES
    }
    by_label: dict[str, dict[str, int]] = {label: {"development": 0, "holdout": 0} for label in sorted(REQUIRED_EVALUATOR_LABELS)}
    for case in cases:
        case_id = str(case.get("case_id", ""))
        family = str(case.get("scenario_family", ""))
        role = str(case.get("release_role", ""))
        label = labels_by_case[case_id]
        if family in by_family and role in RELEASE_ROLES:
            by_family[family][role] += 1
            by_family_label[family][label][role] += 1
            by_label[label][role] += 1
    return {"by_family": by_family, "by_family_label": by_family_label, "by_label": by_label}


def _validate_denominators(denominators: Mapping[str, Any]) -> None:
    by_family = _mapping(denominators.get("by_family"))
    if set(by_family) != set(ROADMAP_FAMILIES):
        raise P115ScenarioMatrixError("missing_roadmap_family")
    for family in ROADMAP_FAMILIES:
        family_counts = _mapping(by_family.get(family))
        if int(family_counts.get("development", 0)) <= 0 or int(family_counts.get("holdout", 0)) <= 0:
            raise P115ScenarioMatrixError(f"missing_family_denominator:{family}")
        label_counts = _mapping(_mapping(denominators.get("by_family_label")).get(family))
        for label in REQUIRED_EVALUATOR_LABELS:
            counts = _mapping(label_counts.get(label))
            if int(counts.get("development", 0)) <= 0 or int(counts.get("holdout", 0)) <= 0:
                raise P115ScenarioMatrixError(f"missing_family_label_denominator:{family}:{label}")
    by_label = _mapping(denominators.get("by_label"))
    for label in REQUIRED_EVALUATOR_LABELS:
        counts = _mapping(by_label.get(label))
        if int(counts.get("development", 0)) <= 0 or int(counts.get("holdout", 0)) <= 0:
            raise P115ScenarioMatrixError(f"missing_label_denominator:{label}")


def _labels_by_case(evaluator_labels: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for label in evaluator_labels:
        case_id = str(label.get("case_id", ""))
        evaluator_label = str(label.get("evaluator_label", ""))
        if evaluator_label not in REQUIRED_EVALUATOR_LABELS:
            raise P115ScenarioMatrixError(f"invalid_evaluator_label:{evaluator_label}")
        if case_id in labels:
            raise P115ScenarioMatrixError(f"duplicate_evaluator_label:{case_id}")
        labels[case_id] = evaluator_label
    return labels


def _candidate_duplicate_signature(case: Mapping[str, Any], *, include_variant: bool) -> dict[str, Any]:
    context = _mapping(case.get("candidate_context"))
    signature: dict[str, Any] = {
        "source_family": case.get("source_family"),
        "service": case.get("service"),
        "scenario_family": case.get("scenario_family"),
        "visible_evidence_classes": sorted(str(item) for item in _sequence(case.get("visible_evidence_classes"))),
        "eligible_action_pack_ids": sorted(str(item) for item in _sequence(case.get("eligible_action_pack_ids"))),
        "symptom_family": _normalized(str(context.get("symptom", "")).rsplit(" ", 1)[0]),
        "missing_evidence": sorted(str(item) for item in _sequence(context.get("missing_evidence"))),
    }
    if include_variant:
        signature.update(
            {
                "topology_handle": case.get("topology_handle"),
                "time_bucket": case.get("time_bucket"),
                "observed_markers": sorted(str(item) for item in _sequence(context.get("observed_markers"))),
            }
        )
    return signature


def _partition_of_case(case_id: str, cases: Sequence[Mapping[str, Any]]) -> str:
    for case in cases:
        if str(case.get("case_id", "")) == case_id:
            return str(case.get("release_role", ""))
    return ""


def _partition_group(
    *,
    source_family: str,
    service: str,
    topology_handle: str,
    incident_family: str,
    time_bucket: str,
    action_family: str,
) -> str:
    suffix = stable_hash(
        {
            "source_family": source_family,
            "service": service,
            "topology_handle": topology_handle,
            "incident_family": incident_family,
            "time_bucket": time_bucket,
            "action_family": action_family,
        }
    )[7:19]
    return f"p115_group_{incident_family}_{action_family}_{suffix}"


def _group_key(case: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_family": _required_text(case, "source_family"),
        "service": _required_text(case, "service"),
        "topology_handle": _required_text(case, "topology_handle"),
        "incident_family": _required_text(case, "scenario_family"),
        "time_bucket": _required_text(case, "time_bucket"),
        "action_pack_family": _required_text(case, "action_pack_family"),
    }


def _time_window(role_index: int, family_index: int, label_index: int, group_index: int, case_index: int) -> dict[str, str]:
    day = 1 + family_index
    hour = label_index * 2 + group_index
    minute = case_index * 10
    return {
        "start": f"2026-08-{day:02d}T{hour:02d}:{minute:02d}:00Z",
        "end": f"2026-08-{day:02d}T{hour:02d}:{minute + 5:02d}:00Z",
        "partition_epoch": "development" if role_index == 0 else "holdout",
    }


def _visible_markers(family: str, group_index: int, case_index: int) -> list[str]:
    return [
        f"{family}_primary_signal_{group_index}",
        f"{family}_secondary_signal_{case_index}",
        f"{family}_candidate_context_{group_index}_{case_index}",
    ]


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise P115ScenarioMatrixError(f"missing_{key}")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _normalized(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")
