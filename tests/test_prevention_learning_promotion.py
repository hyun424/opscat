from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from app.services.prevention_learning_promotion import evaluate_prevention_learning_promotion


def _manifest(*, applied: bool = False, rollback_target: str | None = "policy-v16") -> dict[str, object]:
    recommendation: dict[str, object] = {
        "recommendation_id": "rec-L05-forecast",
        "applied": applied,
        "review_binding": {
            "base_version_id": "policy-v17",
            "base_content_hash_sha256": "a" * 64,
            "rollback_target": rollback_target,
        },
        "rollback": {
            "base_version_id": "policy-v17",
            "base_content_hash_sha256": "a" * 64,
            "target_version_id": rollback_target,
        },
    }
    recommendation["recommendation_hash_sha256"] = _sha256_json(recommendation)
    manifest: dict[str, object] = {
        "schema_version": "p108.recommendation_manifest.v1",
        "base_version": {"version_id": "policy-v17", "content_hash": "a" * 64, "rollback_target": rollback_target},
        "rollback": {"base_version_id": "policy-v17", "base_content_hash_sha256": "a" * 64, "target_version_id": rollback_target},
        "recommendations": [recommendation],
    }
    manifest["manifest_hash_sha256"] = _sha256_json(manifest)
    return manifest


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row(
    *,
    family: str,
    seed: int,
    time_split: str,
    episode_index: int,
    role: str,
    baseline_precision: float = 0.70,
    candidate_precision: float = 0.74,
    baseline_unnecessary: float = 0.12,
    candidate_unnecessary: float = 0.10,
    baseline_natural: float = 0.03,
    candidate_natural: float = 0.02,
    baseline_harmful: float = 0.0,
    candidate_harmful: float = 0.0,
    baseline_calibration_drift: float = 0.04,
    candidate_calibration_drift: float = 0.04,
    family_drift: float = 0.02,
) -> dict[str, object]:
    return {
        "family": family,
        "seed": seed,
        "time_split": time_split,
        "episode_id": f"{role}-{family}-{time_split}-{seed}-{episode_index}",
        "incident_group": f"{role}-{family}-{time_split}-{seed}-{episode_index}",
        "role": role,
        "baseline": {
            "prevented_precision": baseline_precision,
            "unnecessary_intervention_rate": baseline_unnecessary,
            "natural_recovery_miscredit_rate": baseline_natural,
            "harmful_intervention_rate": baseline_harmful,
            "forecast_calibration_drift": baseline_calibration_drift,
            "hard_safety_counter_total": 0,
            "net_avoided_impact": 0.20,
        },
        "candidate": {
            "prevented_precision": candidate_precision,
            "unnecessary_intervention_rate": candidate_unnecessary,
            "natural_recovery_miscredit_rate": candidate_natural,
            "harmful_intervention_rate": candidate_harmful,
            "forecast_calibration_drift": candidate_calibration_drift,
            "hard_safety_counter_total": 0,
            "net_avoided_impact": 0.25,
        },
        "family_drift": family_drift,
        "family_drift_threshold": 0.10,
    }


def _valid_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for family in ("forecast", "runbook"):
        for seed in (101, 202, 303):
            for time_split in ("2026w01", "2026w02"):
                rows.append(_row(family=family, seed=seed, time_split=time_split, episode_index=0, role="train"))
                rows.append(_row(family=family, seed=seed, time_split=time_split, episode_index=1, role="candidate"))
                rows.append(_row(family=family, seed=seed, time_split=time_split, episode_index=2, role="holdout"))
    return rows


def test_promotion_requires_six_seed_time_cells_and_reports_per_family_metrics() -> None:
    manifest = _manifest()
    rows = _valid_rows()
    original_manifest = deepcopy(manifest)
    original_rows = deepcopy(rows)

    payload = evaluate_prevention_learning_promotion(manifest, rows)

    assert manifest == original_manifest
    assert rows == original_rows
    assert payload["schema_version"] == "p108.promotion_report.v1"
    assert payload["summary"]["promotion_status"] == "candidate_ready"
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["seed_count"] == 3
    assert payload["summary"]["time_split_count"] == 2
    assert payload["summary"]["paired_cell_count"] == 6
    assert payload["summary"]["sign_probability_floor"] == "1/64"
    assert payload["summary"]["applied"] is False
    assert payload["summary"]["rollback_target"] == "policy-v16"
    assert len(payload["version_manifest"]["base_hash_sha256"]) == 64
    assert len(payload["version_manifest"]["candidate_hash_sha256"]) == 64
    assert len(payload["version_manifest"]["rollback_hash_sha256"]) == 64
    assert len(payload["version_manifest"]["promotion_report_hash_sha256"]) == 64
    assert payload["holdout"]["disjoint"] is True
    assert payload["holdout"]["overlap_count"] == 0
    assert all(cell["utility_delta"] > 0 for cell in payload["paired_cells"])
    assert len(payload["paired_cells"]) == 6
    assert set(payload["per_family_metrics"]) == {"forecast", "runbook"}
    assert all(metrics["evaluated_row_count"] == 18 for metrics in payload["per_family_metrics"].values())
    assert all(metrics["distinct_episode_count"] == 18 for metrics in payload["per_family_metrics"].values())
    assert all(metrics["positive_seed_time_cell_count"] == 6 for metrics in payload["per_family_metrics"].values())
    assert all(metrics["failed_seed_time_cells"] == [] for metrics in payload["per_family_metrics"].values())
    assert all(metrics["promotion_eligible"] is True for metrics in payload["per_family_metrics"].values())
    assert all(gate["passed"] is True for gate in payload["promotion_gates"])
    assert payload["drift"]["blocked"] is False


def test_promotion_blocks_drift_and_any_failing_family_despite_aggregate_gain() -> None:
    rows = _valid_rows()
    for row in rows:
        if row["family"] == "runbook":
            row["family_drift"] = 0.20
            candidate = row["candidate"]
            assert isinstance(candidate, dict)
            candidate["prevented_precision"] = 0.68

    payload = evaluate_prevention_learning_promotion(_manifest(), rows)

    assert payload["summary"]["passed"] is False
    assert payload["summary"]["promotion_status"] == "blocked"
    assert payload["per_family_metrics"]["forecast"]["promotion_eligible"] is True
    assert payload["per_family_metrics"]["runbook"]["promotion_eligible"] is False
    assert payload["per_family_metrics"]["runbook"]["noninferiority_passed"] is False
    assert payload["drift"]["blocked"] is True
    assert payload["drift"]["blocked_families"] == ["runbook"]
    assert "family-noninferiority" in payload["summary"]["failed_gate_ids"]
    assert "family-drift" in payload["summary"]["failed_gate_ids"]


def test_promotion_rejects_missing_cells_overlap_applied_or_missing_rollback() -> None:
    missing_cell = [row for row in _valid_rows() if not (row["seed"] == 303 and row["time_split"] == "2026w02")]
    overlapping = _valid_rows()
    overlapping[0]["incident_group"] = overlapping[1]["incident_group"]

    cases = [
        (_manifest(), missing_cell, "seed-time-cells"),
        (_manifest(), overlapping, "holdout-disjointness"),
        (_manifest(applied=True), _valid_rows(), "recommendations-unapplied"),
        (_manifest(rollback_target=None), _valid_rows(), "rollback-pointer"),
    ]

    for manifest, rows, failed_gate in cases:
        payload = evaluate_prevention_learning_promotion(manifest, rows)
        assert payload["summary"]["passed"] is False
        assert payload["summary"]["promotion_status"] == "blocked"
        assert failed_gate in payload["summary"]["failed_gate_ids"]


def test_promotion_requires_explicit_nonempty_train_candidate_and_holdout_roles() -> None:
    for missing_role in ("train", "candidate", "holdout"):
        rows = [row for row in _valid_rows() if row["role"] != missing_role]

        payload = evaluate_prevention_learning_promotion(_manifest(), rows)

        assert payload["summary"]["passed"] is False
        assert payload["summary"]["promotion_status"] == "blocked"
        assert "partition-contract" in payload["summary"]["failed_gate_ids"]
        assert missing_role in payload["holdout"]["missing_roles"]


def test_promotion_requires_partition_identity_fields_and_role_disjointness() -> None:
    missing_field_rows = _valid_rows()
    del missing_field_rows[0]["episode_id"]
    duplicate_identity_rows = _valid_rows()
    duplicate_identity_rows[0]["episode_id"] = duplicate_identity_rows[1]["episode_id"]
    duplicate_identity_rows[2]["incident_group"] = duplicate_identity_rows[3]["incident_group"]
    duplicate_identity_rows[4]["time_split"] = duplicate_identity_rows[5]["time_split"]
    duplicate_identity_rows[4]["episode_id"] = duplicate_identity_rows[5]["episode_id"]
    duplicate_identity_rows[4]["incident_group"] = duplicate_identity_rows[5]["incident_group"]

    cases = [
        (missing_field_rows, "missing_required_fields"),
        (duplicate_identity_rows, "cross_role_episode_overlap"),
        (duplicate_identity_rows, "cross_role_incident_group_overlap"),
        (duplicate_identity_rows, "cross_role_incident_time_overlap"),
    ]

    for rows, expected_key in cases:
        payload = evaluate_prevention_learning_promotion(_manifest(), rows)
        assert payload["summary"]["passed"] is False
        assert "partition-contract" in payload["summary"]["failed_gate_ids"]
        assert payload["holdout"][expected_key]


def test_promotion_rejects_broken_version_manifest_linkage_and_invalid_hashes() -> None:
    broken_base = _manifest()
    rollback = broken_base["rollback"]
    assert isinstance(rollback, dict)
    rollback["base_version_id"] = "policy-v15"
    invalid_hash = _manifest()
    base_version = invalid_hash["base_version"]
    assert isinstance(base_version, dict)
    base_version["content_hash"] = "not-sha256"
    missing_candidate_hash = _manifest()
    recommendation = missing_candidate_hash["recommendations"]
    assert isinstance(recommendation, list)
    recommendation[0]["recommendation_hash_sha256"] = ""
    broken_rollback_hash_linkage = _manifest()
    rollback_hash = broken_rollback_hash_linkage["rollback"]
    assert isinstance(rollback_hash, dict)
    rollback_hash["base_content_hash_sha256"] = "c" * 64
    broken_recommendation_linkage = _manifest()
    recommendations = broken_recommendation_linkage["recommendations"]
    assert isinstance(recommendations, list)
    recommendation_rollback = recommendations[0]["rollback"]
    assert isinstance(recommendation_rollback, dict)
    recommendation_rollback["target_version_id"] = "policy-v15"
    forged_manifest_hash = _manifest()
    forged_manifest_hash["manifest_hash_sha256"] = "f" * 64
    forged_recommendation_hash = _manifest()
    forged_recommendations = forged_recommendation_hash["recommendations"]
    assert isinstance(forged_recommendations, list)
    forged_recommendations[0]["recommendation_hash_sha256"] = "c" * 64

    cases = [
        (broken_base, "version-manifest"),
        (invalid_hash, "version-manifest"),
        (missing_candidate_hash, "version-manifest"),
        (broken_rollback_hash_linkage, "version-manifest"),
        (broken_recommendation_linkage, "version-manifest"),
        (forged_manifest_hash, "version-manifest"),
        (forged_recommendation_hash, "version-manifest"),
    ]

    for manifest, failed_gate in cases:
        payload = evaluate_prevention_learning_promotion(manifest, _valid_rows())
        assert payload["summary"]["passed"] is False
        assert payload["summary"]["promotion_status"] == "blocked"
        assert failed_gate in payload["summary"]["failed_gate_ids"]
        assert payload["version_manifest"]["validation_errors"]


def test_promotion_requires_six_positive_seed_time_cells_per_family_without_aggregate_offset() -> None:
    rows = _valid_rows()
    for row in rows:
        if row["family"] == "forecast":
            candidate = row["candidate"]
            assert isinstance(candidate, dict)
            candidate["prevented_precision"] = 0.92
        if row["family"] == "runbook" and row["seed"] == 303 and row["time_split"] == "2026w02":
            candidate = row["candidate"]
            assert isinstance(candidate, dict)
            candidate["prevented_precision"] = 0.63

    payload = evaluate_prevention_learning_promotion(_manifest(), rows)

    assert payload["summary"]["passed"] is False
    assert payload["summary"]["promotion_status"] == "blocked"
    assert payload["summary"]["median_utility_delta"] >= 0.03
    assert "family-seed-time-cells" in payload["summary"]["failed_gate_ids"]
    assert payload["per_family_metrics"]["forecast"]["positive_seed_time_cell_count"] == 6
    assert payload["per_family_metrics"]["runbook"]["positive_seed_time_cell_count"] == 5
    assert payload["per_family_metrics"]["runbook"]["failed_seed_time_cells"] == [
        {"seed": 303, "time_split": "2026w02", "utility_delta": -0.04}
    ]
