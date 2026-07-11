"""P120 system-level split manifests and near-duplicate prevention."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash

SPLIT_MANIFEST_SCHEMA_VERSION = "p120.system_split_manifest.v1"
NEAR_DUPLICATE_REPORT_SCHEMA_VERSION = "p120.near_duplicate_report.v1"
SPLITS = frozenset({"development", "calibration", "frozen_holdout"})
TUNING_INPUTS = frozenset({"calibration", "thresholds", "prompt_tuning", "parser_tuning", "ontology_tuning", "ood_cutoff_fitting", "connector_normalization_tuning"})
REQUIRED_AXES = (
    "system_id",
    "dataset_origin",
    "source_origin",
    "service_architecture_class",
    "topology_graph_family",
    "telemetry_source_combination",
    "incident_scenario_family",
    "action_family",
    "time_window",
    "generated_vs_observed_lineage",
    "ontology_mapping_version",
)
DUPLICATE_AXES = (
    "incident_text",
    "telemetry_window_fingerprint",
    "log_template_signature",
    "trace_structure_fingerprint",
    "topology_graph_fingerprint",
    "deploy_config_marker_sequence",
    "root_cause_label",
    "ontology_path",
    "action_pack_id",
    "validation_probe",
    "rollback_probe",
    "outcome_window_fingerprint",
    "generated_prompt_lineage",
    "seed_lineage",
)


class P120SplitError(ValueError):
    """Raised when P120 split governance or leakage checks fail."""


def build_split_manifest(records: Sequence[Mapping[str, Any]], *, frozen_at: str, freeze_inputs: Mapping[str, str]) -> dict[str, Any]:
    """Build and freeze a system-first split manifest."""

    if not records:
        raise P120SplitError("missing_split_records")
    if not frozen_at:
        raise P120SplitError("missing_frozen_at")
    _validate_freeze_inputs(freeze_inputs)
    normalized_records = [_normalize_record(record) for record in records]
    _validate_system_exclusivity(normalized_records)
    payload: dict[str, Any] = {
        "schema_version": SPLIT_MANIFEST_SCHEMA_VERSION,
        "status": "frozen",
        "frozen_at": frozen_at,
        "freeze_inputs": dict(sorted((str(key), str(value)) for key, value in freeze_inputs.items())),
        "records": sorted(normalized_records, key=lambda item: (str(item["split"]), str(item["system_id"]), str(item["case_id"]))),
    }
    payload["manifest_hash"] = stable_hash(payload)
    return payload


def validate_split_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a frozen split manifest and reject tampering."""

    if manifest.get("schema_version") != SPLIT_MANIFEST_SCHEMA_VERSION or manifest.get("status") != "frozen":
        raise P120SplitError("invalid_split_manifest")
    records = manifest.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)) or not records:
        raise P120SplitError("missing_split_records")
    normalized_records = [_normalize_record(record) for record in records if isinstance(record, Mapping)]
    if len(normalized_records) != len(records):
        raise P120SplitError("invalid_split_record")
    _validate_system_exclusivity(normalized_records)
    _validate_freeze_inputs(_mapping(manifest.get("freeze_inputs")))
    submitted = str(manifest.get("manifest_hash", ""))
    unhashed = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if submitted and submitted != stable_hash(unhashed):
        raise P120SplitError("split_manifest_tampered")


def validate_no_holdout_tuning(manifest: Mapping[str, Any], tuning_usage: Mapping[str, Sequence[str]]) -> None:
    """Reject calibration, prompt, parser, ontology, OOD, or normalization tuning on holdout systems."""

    validate_split_manifest(manifest)
    holdout_systems = {str(record["system_id"]) for record in _records(manifest) if record["split"] == "frozen_holdout"}
    for usage_name, system_ids in tuning_usage.items():
        if str(usage_name) not in TUNING_INPUTS:
            continue
        overlap = holdout_systems & {str(system_id) for system_id in system_ids}
        if overlap:
            raise P120SplitError(f"holdout_tuning:{sorted(overlap)[0]}")


def build_near_duplicate_report(records: Sequence[Mapping[str, Any]], *, threshold: float = 0.86, manual_adjudications: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Detect exact and near duplicates across P120 leakage axes."""

    if not 0.0 <= threshold <= 1.0:
        raise P120SplitError("invalid_duplicate_threshold")
    normalized_records = [_normalize_record(record) for record in records]
    adjudicated = {_pair_key(str(item.get("left_case_id", "")), str(item.get("right_case_id", ""))) for item in manual_adjudications}
    blocked_pairs: list[dict[str, Any]] = []
    unresolved_pairs: list[dict[str, Any]] = []
    denominator = 0
    for left_index, left in enumerate(normalized_records):
        for right in normalized_records[left_index + 1 :]:
            denominator += 1
            score, reasons = _duplicate_score(left, right)
            if score < threshold:
                continue
            pair = {
                "left_case_id": left["case_id"],
                "right_case_id": right["case_id"],
                "left_system_id": left["system_id"],
                "right_system_id": right["system_id"],
                "left_split": left["split"],
                "right_split": right["split"],
                "score": score,
                "reasons": reasons,
            }
            if left["split"] == right["split"]:
                blocked_pairs.append(pair)
            elif _pair_key(str(left["case_id"]), str(right["case_id"])) in adjudicated:
                blocked_pairs.append({**pair, "manual_adjudication": "accepted"})
            else:
                unresolved_pairs.append(pair)
    payload: dict[str, Any] = {
        "schema_version": NEAR_DUPLICATE_REPORT_SCHEMA_VERSION,
        "method": "p120_axis_exact_plus_token_jaccard_v1",
        "threshold": threshold,
        "denominator": denominator,
        "numerator": len(blocked_pairs) + len(unresolved_pairs),
        "blocked_pairs": blocked_pairs,
        "manually_adjudicated_pairs": [dict(item) for item in manual_adjudications],
        "unresolved_pairs": unresolved_pairs,
    }
    payload["report_hash"] = stable_hash(payload)
    return payload


def validate_near_duplicate_report(report: Mapping[str, Any]) -> None:
    """Block release when unresolved near duplicates touch holdout systems."""

    if report.get("schema_version") != NEAR_DUPLICATE_REPORT_SCHEMA_VERSION:
        raise P120SplitError("invalid_duplicate_report")
    unresolved = report.get("unresolved_pairs")
    if not isinstance(unresolved, Sequence) or isinstance(unresolved, (str, bytes, bytearray)):
        raise P120SplitError("invalid_unresolved_pairs")
    for pair in unresolved:
        if not isinstance(pair, Mapping):
            raise P120SplitError("invalid_unresolved_pair")
        if "frozen_holdout" in {str(pair.get("left_split")), str(pair.get("right_split"))}:
            raise P120SplitError("unresolved_holdout_duplicate")
    submitted = str(report.get("report_hash", ""))
    unhashed = {key: value for key, value in report.items() if key != "report_hash"}
    if submitted and submitted != stable_hash(unhashed):
        raise P120SplitError("duplicate_report_tampered")


def consume_first_unseen_score(manifest: Mapping[str, Any], *, system_id: str, score_receipt_hash: str) -> dict[str, Any]:
    """Record that the first frozen holdout score consumed an unseen system split."""

    validate_split_manifest(manifest)
    holdout_systems = {str(record["system_id"]) for record in _records(manifest) if record["split"] == "frozen_holdout"}
    if system_id not in holdout_systems:
        raise P120SplitError("system_not_frozen_holdout")
    if not score_receipt_hash.startswith("sha256:"):
        raise P120SplitError("invalid_score_receipt_hash")
    consumed = dict(manifest)
    consumed_systems = set(str(item) for item in consumed.get("consumed_holdout_systems", ()))
    if system_id in consumed_systems:
        raise P120SplitError("consumed_holdout_rescored_as_pass")
    consumed_systems.add(system_id)
    consumed["consumed_holdout_systems"] = sorted(consumed_systems)
    consumed["first_score_receipts"] = [*list(consumed.get("first_score_receipts", ())), {"system_id": system_id, "score_receipt_hash": score_receipt_hash}]
    consumed["manifest_hash"] = stable_hash({key: value for key, value in consumed.items() if key != "manifest_hash"})
    return consumed


def _normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {str(key): value for key, value in record.items()}
    for key in ("case_id", "split", *REQUIRED_AXES):
        value = normalized.get(key)
        if not isinstance(value, str) or not value.strip():
            raise P120SplitError(f"missing_split_axis:{key}")
        normalized[key] = value.strip()
    if normalized["split"] not in SPLITS:
        raise P120SplitError("invalid_split")
    if not isinstance(normalized.get("time_window"), str) or ".." not in str(normalized["time_window"]):
        raise P120SplitError("invalid_time_window_axis")
    for key in DUPLICATE_AXES:
        value = normalized.get(key)
        if value is not None:
            normalized[key] = str(value).strip()
    return normalized


def _validate_system_exclusivity(records: Sequence[Mapping[str, Any]]) -> None:
    splits_by_system: dict[str, set[str]] = {}
    case_ids: set[str] = set()
    for record in records:
        case_id = str(record["case_id"])
        if case_id in case_ids:
            raise P120SplitError("duplicate_case_id")
        case_ids.add(case_id)
        splits_by_system.setdefault(str(record["system_id"]), set()).add(str(record["split"]))
    for system_id, splits in splits_by_system.items():
        if len(splits) > 1:
            raise P120SplitError(f"system_id_crosses_splits:{system_id}")


def _validate_freeze_inputs(freeze_inputs: Mapping[str, Any]) -> None:
    required = {
        "source_manifest_hash",
        "normalization_version",
        "ontology_version",
        "ood_threshold_hash",
        "calibration_method_hash",
        "selector_hash",
        "prompt_hash",
        "parser_rules_hash",
        "baseline_config_hash",
        "seed_hash",
        "evaluator_hash",
        "release_threshold_hash",
    }
    missing = sorted(required - set(str(key) for key in freeze_inputs))
    if missing:
        raise P120SplitError(f"missing_freeze_input:{missing[0]}")
    for key in required:
        if not str(freeze_inputs[key]).startswith("sha256:"):
            raise P120SplitError(f"invalid_freeze_hash:{key}")


def _duplicate_score(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    exact_matches = 0
    comparable = 0
    for key in DUPLICATE_AXES:
        left_value = str(left.get(key, ""))
        right_value = str(right.get(key, ""))
        if not left_value or not right_value:
            continue
        comparable += 1
        if _normalize_text(left_value) == _normalize_text(right_value):
            exact_matches += 1
            reasons.append(key)
    text_score = _jaccard(str(left.get("incident_text", "")), str(right.get("incident_text", "")))
    if text_score >= 0.8 and "incident_text" not in reasons:
        reasons.append("incident_text_near")
    axis_score = exact_matches / comparable if comparable else 0.0
    return max(axis_score, text_score), reasons


def _jaccard(left: str, right: str) -> float:
    left_tokens = set(_normalize_text(left).split())
    right_tokens = set(_normalize_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    records = manifest.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return []
    return [record for record in records if isinstance(record, Mapping)]


__all__ = [
    "NEAR_DUPLICATE_REPORT_SCHEMA_VERSION",
    "P120SplitError",
    "SPLIT_MANIFEST_SCHEMA_VERSION",
    "build_near_duplicate_report",
    "build_split_manifest",
    "consume_first_unseen_score",
    "validate_near_duplicate_report",
    "validate_no_holdout_tuning",
    "validate_split_manifest",
]
