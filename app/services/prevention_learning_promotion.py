"""P108 offline recommendation promotion gates."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

_SCHEMA_VERSION = "p108.promotion_report.v1"
_REQUIRED_PARTITION_ROLES = frozenset({"train", "candidate", "holdout"})
_REQUIRED_ROW_FIELDS = ("role", "incident_group", "episode_id", "time_split")
_VERSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_SHA256_PATTERN = re.compile(r"^[A-Fa-f0-9]{64}$")
_MIN_SEEDS = 3
_MIN_TIME_SPLITS = 2
_REQUIRED_CELL_COUNT = 6
_MIN_CELL_DELTA = 0.0
_MIN_MEDIAN_DELTA = 0.03
_NONINFERIORITY_MARGIN = -0.01
_MAX_CALIBRATION_DRIFT_INCREASE = 0.01


def evaluate_prevention_learning_promotion(recommendation_manifest: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Evaluate a rollbackable, unapplied recommendation candidate on offline holdout rows."""

    row_list = [dict(row) for row in rows]
    paired_cells = _paired_cells(row_list)
    per_family = _per_family_metrics(row_list)
    holdout = _holdout_disjointness(row_list)
    drift = _drift_report(per_family)
    version_manifest = _version_manifest(recommendation_manifest)
    gates = _gates(recommendation_manifest, row_list, paired_cells, per_family, holdout, drift, version_manifest)
    failed_gate_ids = [str(gate["gate_id"]) for gate in gates if not gate["passed"]]
    passed = not failed_gate_ids
    report_without_hash = {
        "schema_version": _SCHEMA_VERSION,
        "summary": {
            "passed": passed,
            "promotion_status": "candidate_ready" if passed else "blocked",
            "failed_gate_ids": failed_gate_ids,
            "seed_count": len({cell["seed"] for cell in paired_cells}),
            "time_split_count": len({cell["time_split"] for cell in paired_cells}),
            "paired_cell_count": len(paired_cells),
            "median_utility_delta": round(median([cell["utility_delta"] for cell in paired_cells]) if paired_cells else 0.0, 6),
            "sign_probability_floor": "1/64",
            "applied": _manifest_applied(recommendation_manifest),
            "rollback_target": _rollback_target(recommendation_manifest),
        },
        "version_manifest": version_manifest,
        "holdout": holdout,
        "paired_cells": paired_cells,
        "per_family_metrics": per_family,
        "drift": drift,
        "promotion_gates": gates,
    }
    report_hash = _sha256_json(report_without_hash)
    report: dict[str, Any] = dict(report_without_hash)
    report["version_manifest"] = {**version_manifest, "promotion_report_hash_sha256": report_hash}
    return report


def _paired_cells(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for seed, time_split in sorted({(int(row.get("seed", -1)), str(row.get("time_split", ""))) for row in rows}):
        cell_rows = [row for row in rows if int(row.get("seed", -1)) == seed and str(row.get("time_split", "")) == time_split]
        if not cell_rows:
            continue
        baseline_utility = _average(_learning_utility(_mapping(row.get("baseline"))) for row in cell_rows)
        candidate_utility = _average(_learning_utility(_mapping(row.get("candidate"))) for row in cell_rows)
        cells.append(
            {
                "seed": seed,
                "time_split": time_split,
                "row_count": len(cell_rows),
                "baseline_utility": round(baseline_utility, 6),
                "candidate_utility": round(candidate_utility, 6),
                "utility_delta": round(candidate_utility - baseline_utility, 6),
            }
        )
    return cells


def _per_family_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for family in sorted({str(row.get("family", "")) for row in rows if row.get("family")}):
        family_rows = [row for row in rows if str(row.get("family", "")) == family]
        baseline_precision = _metric_average(family_rows, "baseline", "prevented_precision")
        candidate_precision = _metric_average(family_rows, "candidate", "prevented_precision")
        baseline_unnecessary = _metric_average(family_rows, "baseline", "unnecessary_intervention_rate")
        candidate_unnecessary = _metric_average(family_rows, "candidate", "unnecessary_intervention_rate")
        baseline_natural = _metric_average(family_rows, "baseline", "natural_recovery_miscredit_rate")
        candidate_natural = _metric_average(family_rows, "candidate", "natural_recovery_miscredit_rate")
        baseline_harmful = _metric_average(family_rows, "baseline", "harmful_intervention_rate")
        candidate_harmful = _metric_average(family_rows, "candidate", "harmful_intervention_rate")
        baseline_calibration = _metric_average(family_rows, "baseline", "forecast_calibration_drift")
        candidate_calibration = _metric_average(family_rows, "candidate", "forecast_calibration_drift")
        safety_total = sum(
            int(_mapping(row.get("baseline")).get("hard_safety_counter_total", 0))
            + int(_mapping(row.get("candidate")).get("hard_safety_counter_total", 0))
            for row in family_rows
        )
        drift_values = [float(row.get("family_drift", 0.0)) for row in family_rows]
        drift_thresholds = [float(row.get("family_drift_threshold", 0.0)) for row in family_rows]
        distinct_episodes = {str(row.get("episode_id", "")) for row in family_rows if row.get("episode_id")}
        seed_time_cells = _seed_time_cells(family_rows)
        failed_seed_time_cells = [
            {"seed": cell["seed"], "time_split": cell["time_split"], "utility_delta": cell["utility_delta"]}
            for cell in seed_time_cells
            if float(cell["utility_delta"]) <= _MIN_CELL_DELTA
        ]
        positive_seed_time_cell_count = len(seed_time_cells) - len(failed_seed_time_cells)
        noninferiority_passed = (
            candidate_precision - baseline_precision >= _NONINFERIORITY_MARGIN
            and candidate_unnecessary - baseline_unnecessary <= abs(_NONINFERIORITY_MARGIN)
            and candidate_natural - baseline_natural <= abs(_NONINFERIORITY_MARGIN)
            and candidate_harmful - baseline_harmful <= abs(_NONINFERIORITY_MARGIN)
        )
        calibration_passed = candidate_calibration - baseline_calibration <= _MAX_CALIBRATION_DRIFT_INCREASE
        safety_passed = safety_total == 0 and candidate_harmful == 0.0
        denominator_passed = len(family_rows) >= 12 and len(distinct_episodes) >= 6
        drift_blocked = bool(drift_values) and max(drift_values) > min(drift_thresholds or [0.0])
        result[family] = {
            "evaluated_row_count": len(family_rows),
            "distinct_episode_count": len(distinct_episodes),
            "baseline_prevented_precision": round(baseline_precision, 6),
            "candidate_prevented_precision": round(candidate_precision, 6),
            "prevented_precision_delta": round(candidate_precision - baseline_precision, 6),
            "baseline_unnecessary_intervention_rate": round(baseline_unnecessary, 6),
            "candidate_unnecessary_intervention_rate": round(candidate_unnecessary, 6),
            "unnecessary_intervention_delta": round(candidate_unnecessary - baseline_unnecessary, 6),
            "baseline_harmful_intervention_rate": round(baseline_harmful, 6),
            "candidate_harmful_intervention_rate": round(candidate_harmful, 6),
            "baseline_natural_recovery_miscredit_rate": round(baseline_natural, 6),
            "candidate_natural_recovery_miscredit_rate": round(candidate_natural, 6),
            "baseline_forecast_calibration_drift": round(baseline_calibration, 6),
            "candidate_forecast_calibration_drift": round(candidate_calibration, 6),
            "calibration_drift_delta": round(candidate_calibration - baseline_calibration, 6),
            "net_avoided_impact_delta": round(
                _metric_average(family_rows, "candidate", "net_avoided_impact")
                - _metric_average(family_rows, "baseline", "net_avoided_impact"),
                6,
            ),
            "hard_safety_counter_total": safety_total,
            "family_drift": round(max(drift_values) if drift_values else 0.0, 6),
            "family_drift_threshold": round(min(drift_thresholds) if drift_thresholds else 0.0, 6),
            "positive_seed_time_cell_count": positive_seed_time_cell_count,
            "failed_seed_time_cells": failed_seed_time_cells,
            "denominator_passed": denominator_passed,
            "seed_time_cells_passed": len(seed_time_cells) == _REQUIRED_CELL_COUNT and not failed_seed_time_cells,
            "noninferiority_passed": noninferiority_passed,
            "calibration_passed": calibration_passed,
            "safety_passed": safety_passed,
            "drift_passed": not drift_blocked,
            "promotion_eligible": denominator_passed
            and len(seed_time_cells) == _REQUIRED_CELL_COUNT
            and not failed_seed_time_cells
            and noninferiority_passed
            and calibration_passed
            and safety_passed
            and not drift_blocked,
        }
    return result


def _holdout_disjointness(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    roles = {str(row.get("role", "")) for row in rows if str(row.get("role", ""))}
    missing_roles = sorted(_REQUIRED_PARTITION_ROLES - roles)
    role_counts = {role: sum(1 for row in rows if str(row.get("role", "")) == role) for role in sorted(_REQUIRED_PARTITION_ROLES)}
    missing_required_fields = [
        {"row_index": index, "fields": [field for field in _REQUIRED_ROW_FIELDS if not str(row.get(field, "")).strip()]}
        for index, row in enumerate(rows)
        if any(not str(row.get(field, "")).strip() for field in _REQUIRED_ROW_FIELDS)
    ]
    incident_group_overlap = _cross_role_overlap(rows, "incident_group")
    episode_overlap = _cross_role_overlap(rows, "episode_id")
    incident_time_overlap = _cross_role_overlap(rows, "incident_group", "episode_id", "time_split")
    disjoint = not incident_group_overlap and not episode_overlap and not incident_time_overlap
    partition_contract_passed = (
        not missing_roles
        and all(role_counts[role] > 0 for role in _REQUIRED_PARTITION_ROLES)
        and not missing_required_fields
        and disjoint
    )
    return {
        "partition_contract_passed": partition_contract_passed,
        "roles": sorted(roles),
        "role_counts": role_counts,
        "missing_roles": missing_roles,
        "missing_required_fields": missing_required_fields,
        "disjoint": disjoint,
        "overlap_count": len(incident_group_overlap),
        "overlap_incident_groups": [item["value"] for item in incident_group_overlap],
        "cross_role_incident_group_overlap": incident_group_overlap,
        "cross_role_episode_overlap": episode_overlap,
        "cross_role_incident_time_overlap": incident_time_overlap,
    }


def _drift_report(per_family: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    blocked = sorted(family for family, metrics in per_family.items() if not bool(metrics.get("drift_passed")))
    return {
        "blocked": bool(blocked),
        "blocked_families": blocked,
        "family_drift": {
            family: {
                "observed": metrics.get("family_drift"),
                "threshold": metrics.get("family_drift_threshold"),
                "passed": metrics.get("drift_passed"),
            }
            for family, metrics in per_family.items()
        },
    }


def _version_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    base = _mapping(manifest.get("base_version"))
    rollback = _mapping(manifest.get("rollback"))
    recommendations = [item for item in _sequence(manifest.get("recommendations")) if isinstance(item, Mapping)]
    candidate_body = {
        "manifest_hash_sha256": manifest.get("manifest_hash_sha256"),
        "recommendation_hashes": [
            str(item.get("recommendation_hash_sha256", "")) for item in recommendations
        ],
    }
    recomputed_manifest_hash = _manifest_hash(manifest)
    recomputed_recommendation_hashes = [_recommendation_hash(item) for item in recommendations]
    validation_errors = _version_manifest_errors(
        manifest=manifest,
        base=base,
        rollback=rollback,
        recommendations=recommendations,
        recomputed_manifest_hash=recomputed_manifest_hash,
        recomputed_recommendation_hashes=recomputed_recommendation_hashes,
    )
    return {
        "base_version_id": base.get("version_id"),
        "rollback_target": rollback.get("target_version_id") or base.get("rollback_target"),
        "base_hash_sha256": _sha256_json(base),
        "candidate_hash_sha256": _sha256_json(candidate_body),
        "evidence_hash_sha256": str(manifest.get("manifest_hash_sha256", "")),
        "recomputed_evidence_hash_sha256": recomputed_manifest_hash,
        "recomputed_recommendation_hashes_sha256": recomputed_recommendation_hashes,
        "rollback_hash_sha256": _sha256_json(rollback),
        "promotion_report_hash_sha256": "",
        "validation_errors": validation_errors,
        "applied": False,
    }


def _gates(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    paired_cells: Sequence[Mapping[str, Any]],
    per_family: Mapping[str, Mapping[str, Any]],
    holdout: Mapping[str, Any],
    drift: Mapping[str, Any],
    version_manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    utility_deltas = [float(cell.get("utility_delta", 0.0)) for cell in paired_cells]
    seeds = {cell.get("seed") for cell in paired_cells}
    time_splits = {cell.get("time_split") for cell in paired_cells}
    all_families_evaluable = bool(per_family) and all(bool(metrics.get("denominator_passed")) for metrics in per_family.values())
    all_family_cells_positive = bool(per_family) and all(bool(metrics.get("seed_time_cells_passed")) for metrics in per_family.values())
    all_families_noninferior = bool(per_family) and all(bool(metrics.get("noninferiority_passed")) for metrics in per_family.values())
    all_calibrated = bool(per_family) and all(bool(metrics.get("calibration_passed")) for metrics in per_family.values())
    all_safety_zero = bool(per_family) and all(bool(metrics.get("safety_passed")) for metrics in per_family.values())
    return [
        {
            "gate_id": "rollback-pointer",
            "passed": bool(version_manifest.get("rollback_target")),
            "reason": "Promotion requires a rollback target bound to the base version.",
        },
        {
            "gate_id": "version-manifest",
            "passed": not bool(version_manifest.get("validation_errors")),
            "reason": "Promotion requires valid base, candidate, evidence, and rollback hashes with rollback bound to the base version.",
        },
        {
            "gate_id": "recommendations-unapplied",
            "passed": not _manifest_applied(manifest),
            "reason": "Recommendation manifests must remain data-only and unapplied.",
        },
        {
            "gate_id": "seed-time-cells",
            "passed": len(seeds) >= _MIN_SEEDS and len(time_splits) >= _MIN_TIME_SPLITS and len(paired_cells) == _REQUIRED_CELL_COUNT,
            "reason": "Promotion requires three seeds across two time splits: six predeclared paired cells.",
        },
        {
            "gate_id": "holdout-disjointness",
            "passed": bool(holdout.get("disjoint")),
            "reason": "Candidate/train and holdout incident groups must be disjoint.",
        },
        {
            "gate_id": "partition-contract",
            "passed": bool(holdout.get("partition_contract_passed")),
            "reason": "Promotion requires explicit nonempty train, candidate, and holdout rows with role, incident group, episode, and time-split isolation.",
        },
        {
            "gate_id": "family-denominators",
            "passed": all_families_evaluable and len(rows) >= 12 * len(per_family),
            "reason": "Every family must report nonzero denominators with at least six episodes and twelve evaluated rows.",
        },
        {
            "gate_id": "utility-effect",
            "passed": bool(utility_deltas)
            and all(delta > _MIN_CELL_DELTA for delta in utility_deltas)
            and median(utility_deltas) >= _MIN_MEDIAN_DELTA,
            "reason": "Every seed-time cell needs positive learning utility and median delta at least 0.03.",
        },
        {
            "gate_id": "family-seed-time-cells",
            "passed": all_family_cells_positive,
            "reason": "Every evaluated family needs exactly six positive seed-time learning utility cells.",
        },
        {
            "gate_id": "family-noninferiority",
            "passed": all_families_noninferior,
            "reason": "No evaluated family may regress beyond the -0.01 noninferiority margin.",
        },
        {
            "gate_id": "calibration",
            "passed": all_calibrated,
            "reason": "Forecast calibration drift increase may not exceed 0.01 in any family.",
        },
        {
            "gate_id": "safety-zero",
            "passed": all_safety_zero,
            "reason": "Harmful interventions and hard safety counters must remain exactly zero.",
        },
        {"gate_id": "family-drift", "passed": not bool(drift.get("blocked")), "reason": "Family drift above threshold blocks promotion."},
    ]


def _learning_utility(metrics: Mapping[str, Any]) -> float:
    return (
        float(metrics.get("prevented_precision", 0.0))
        - float(metrics.get("unnecessary_intervention_rate", 0.0))
        - float(metrics.get("natural_recovery_miscredit_rate", 0.0))
        - 4 * float(metrics.get("harmful_intervention_rate", 0.0))
    )


def _seed_time_cells(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for seed, time_split in sorted({(int(row.get("seed", -1)), str(row.get("time_split", ""))) for row in rows}):
        cell_rows = [row for row in rows if int(row.get("seed", -1)) == seed and str(row.get("time_split", "")) == time_split]
        if not cell_rows:
            continue
        baseline_utility = _average(_learning_utility(_mapping(row.get("baseline"))) for row in cell_rows)
        candidate_utility = _average(_learning_utility(_mapping(row.get("candidate"))) for row in cell_rows)
        cells.append({"seed": seed, "time_split": time_split, "utility_delta": round(candidate_utility - baseline_utility, 6)})
    return cells


def _cross_role_overlap(rows: Sequence[Mapping[str, Any]], *fields: str) -> list[dict[str, Any]]:
    owners: dict[tuple[str, ...], set[str]] = {}
    for row in rows:
        role = str(row.get("role", "")).strip()
        values = tuple(str(row.get(field, "")).strip() for field in fields)
        if not role or any(not value for value in values):
            continue
        owners.setdefault(values, set()).add(role)
    overlaps = [
        {"value": "|".join(values), "roles": sorted(roles)}
        for values, roles in sorted(owners.items())
        if len(roles) > 1
    ]
    return overlaps


def _version_manifest_errors(
    *,
    manifest: Mapping[str, Any],
    base: Mapping[str, Any],
    rollback: Mapping[str, Any],
    recommendations: Sequence[Mapping[str, Any]],
    recomputed_manifest_hash: str,
    recomputed_recommendation_hashes: Sequence[str],
) -> list[str]:
    errors: list[str] = []
    base_version_id = base.get("version_id")
    base_content_hash = base.get("content_hash")
    rollback_base_version_id = rollback.get("base_version_id")
    rollback_base_content_hash = rollback.get("base_content_hash_sha256")
    rollback_target = rollback.get("target_version_id") or base.get("rollback_target")
    if not _valid_version_id(base_version_id):
        errors.append("invalid_base_version_id")
    if not _valid_sha256(base_content_hash):
        errors.append("invalid_base_content_hash_sha256")
    if not rollback_target:
        errors.append("missing_rollback_target")
    elif not _valid_version_id(rollback_target):
        errors.append("invalid_rollback_target")
    elif rollback_target == base_version_id:
        errors.append("rollback_target_matches_base_version")
    if rollback_base_version_id != base_version_id:
        errors.append("rollback_base_version_mismatch")
    if rollback_base_content_hash != base_content_hash:
        errors.append("rollback_base_content_hash_mismatch")
    if rollback.get("target_version_id") != base.get("rollback_target"):
        errors.append("rollback_target_mismatch")
    if not _valid_sha256(manifest.get("manifest_hash_sha256")):
        errors.append("invalid_manifest_hash_sha256")
    elif manifest.get("manifest_hash_sha256") != recomputed_manifest_hash:
        errors.append("manifest_hash_mismatch")
    if not recommendations:
        errors.append("missing_recommendations")
    if any(not _valid_sha256(item.get("recommendation_hash_sha256")) for item in recommendations):
        errors.append("invalid_recommendation_hash_sha256")
    if any(item.get("recommendation_hash_sha256") != recomputed_hash for item, recomputed_hash in zip(recommendations, recomputed_recommendation_hashes, strict=True)):
        errors.append("recommendation_hash_mismatch")
    if any(_mapping(item.get("rollback")).get("base_version_id") != base_version_id for item in recommendations):
        errors.append("recommendation_rollback_base_version_mismatch")
    if any(_mapping(item.get("rollback")).get("base_content_hash_sha256") != base_content_hash for item in recommendations):
        errors.append("recommendation_rollback_base_content_hash_mismatch")
    if any(_mapping(item.get("rollback")).get("target_version_id") != rollback_target for item in recommendations):
        errors.append("recommendation_rollback_target_mismatch")
    if any(_mapping(item.get("review_binding")).get("base_version_id") != base_version_id for item in recommendations):
        errors.append("recommendation_review_base_version_mismatch")
    if any(_mapping(item.get("review_binding")).get("base_content_hash_sha256") != base_content_hash for item in recommendations):
        errors.append("recommendation_review_base_content_hash_mismatch")
    if any(_mapping(item.get("review_binding")).get("rollback_target") != rollback_target for item in recommendations):
        errors.append("recommendation_review_rollback_target_mismatch")
    return errors


def _valid_version_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_VERSION_ID_PATTERN.fullmatch(value))


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_PATTERN.fullmatch(value))


def _metric_average(rows: Sequence[Mapping[str, Any]], side: str, metric: str) -> float:
    return _average(float(_mapping(row.get(side)).get(metric, 0.0)) for row in rows)


def _average(values: Sequence[float] | Any) -> float:
    collected = list(values)
    return sum(collected) / len(collected) if collected else 0.0


def _manifest_applied(manifest: Mapping[str, Any]) -> bool:
    if bool(_mapping(manifest.get("summary")).get("applied")):
        return True
    return any(bool(item.get("applied")) for item in _sequence(manifest.get("recommendations")) if isinstance(item, Mapping))


def _rollback_target(manifest: Mapping[str, Any]) -> Any:
    rollback = _mapping(manifest.get("rollback"))
    base = _mapping(manifest.get("base_version"))
    return rollback.get("target_version_id") or base.get("rollback_target")


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    body = dict(manifest)
    body.pop("manifest_hash_sha256", None)
    return _sha256_json(body)


def _recommendation_hash(recommendation: Mapping[str, Any]) -> str:
    body = dict(recommendation)
    body.pop("recommendation_hash_sha256", None)
    return _sha256_json(body)
