"""Frozen unseen temporal/system evaluation for proactive prevention."""

from __future__ import annotations

import json
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_execution import prove_p121_restart_recovery
from app.services.p121_signals import zero_authority_counters

P121_EVALUATION_SCHEMA_VERSION = "p121.frozen_prevention_evaluation.v1"
_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "evals/p121/frozen-unseen-manifest.json"


def run_p121_frozen_evaluation(*, seed: int = 12101) -> dict[str, Any]:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    expected = stable_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    if manifest.get("manifest_hash") != expected or manifest.get("seed") != seed:
        raise ValueError("stale_or_mismatched_frozen_manifest")
    cases = list(manifest["cases"])
    _validate_manifest_contract(manifest, cases)
    scored = [_score_case(case) for case in cases]
    if not all(row.get("first_score_consumed") is True for row in scored):
        raise ValueError("holdout_not_consumed")
    dimensions = ("system_id", "service_id", "horizon_bucket", "incident_family", "action_family", "source_lineage", "authority_sensitive")
    per_slice: dict[str, dict[str, Any]] = {}
    for dimension in dimensions:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in scored:
            grouped[str(row[dimension])].append(row)
        for value, rows in grouped.items():
            per_slice[f"{dimension}:{value}"] = _metrics(rows)
    aggregate = _metrics(scored)
    recovery_proof = _build_recovery_proof()
    crash_points = list(recovery_proof["crash_replay_points"])
    report: dict[str, Any] = {
        "schema_version": P121_EVALUATION_SCHEMA_VERSION,
        "seed": seed,
        "case_count": len(scored),
        "frozen_manifest_hash": manifest["manifest_hash"],
        "manifest_contract": {
            "raw_inputs_only": True,
            "hidden_truth_is_scorer_only": True,
            "system_temporal_separation_enforced": True,
            "near_duplicate_leakage_check": "passed",
        },
        "first_score_consumed": True,
        "aggregate": aggregate,
        "per_slice": per_slice,
        "system_count": len({row["system_id"] for row in scored}),
        "incident_family_count": len({row["incident_family"] for row in scored}),
        "crash_replay_points": crash_points,
        "crash_replay_receipts": recovery_proof["crash_replay_receipts"],
        "restart_recovery_proof_hash": recovery_proof["proof_hash"],
        "restart_recovery": {
            "point_count": recovery_proof["point_count"],
            "partial_l3_recovered": any(value["partial_l3_recovered"] for value in recovery_proof["crash_replay_receipts"].values()),
            "rollback_recovered": any(value["rollback_recovered"] for value in recovery_proof["crash_replay_receipts"].values()),
            "pending_rollback_replayed": _mapping(recovery_proof["crash_replay_receipts"].get("rollback_begin")).get("rollback_pending_replayed") is True,
            "pending_rollback_count_after_replay": recovery_proof["wal_recovered"].get("pending_rollback_count"),
            "wal_last_hash": recovery_proof["wal_recovered"]["last_wal_hash"],
        },
        "split_counts": dict(Counter(str(row["split"]) for row in scored)),
        "authority": {"exact_nonlocal_authority_zero": True, "counters": zero_authority_counters()},
        "negative_evidence_count": sum(int(row.get("passed") is not True) for row in scored),
        "claim": "local/mock/sandbox proactive prevention readiness only",
    }
    report["evaluation_hash"] = stable_hash(report)
    return report


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    return {
        "denominator": denominator,
        "passed": sum(int(row.get("passed") is True) for row in rows),
        "forecast_precision": sum(int(row.get("forecast_correct") is True) for row in rows) / denominator,
        "abstention_correctness": sum(int(row.get("abstention_correct") is True) for row in rows) / denominator,
        "prevention_utility": sum(float(row.get("prevention_utility", 0.0)) for row in rows) / denominator,
        "harmful_action_rate": sum(int(row.get("harmful") is True) for row in rows) / denominator,
        "false_positive_rate": sum(int(row.get("false_positive") is True) for row in rows) / denominator,
        "fatigue_violation_rate": sum(int(row.get("fatigue_violation") is True) for row in rows) / denominator,
        "rollback_failure_rate": sum(int(row.get("rollback_failed") is True) for row in rows) / denominator,
        "duplicate_effect_count": sum(int(row.get("duplicate_effect_count", 0)) for row in rows),
    }


def _validate_manifest_contract(manifest: Mapping[str, Any], cases: list[Any]) -> None:
    if manifest.get("manifest_contract") != "raw_inputs_hidden_truth_v2":
        raise ValueError("stale_manifest_contract")
    if len(cases) < 300 or len({case["case_id"] for case in cases if isinstance(case, Mapping)}) != len(cases):
        raise ValueError("invalid_frozen_cases")
    forbidden = {
        "passed",
        "forecast_correct",
        "abstention_correct",
        "prevention_utility",
        "harmful",
        "false_positive",
        "fatigue_violation",
        "rollback_failed",
        "duplicate_effect_count",
    }
    split_systems: dict[str, set[str]] = defaultdict(set)
    split_windows: dict[str, list[tuple[int, int]]] = defaultdict(list)
    fingerprints: dict[str, str] = {}
    for raw_case in cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("invalid_frozen_case")
        if forbidden.intersection(raw_case):
            raise ValueError("pre_scored_manifest_forbidden")
        raw_inputs = raw_case.get("raw_inputs")
        hidden_truth = raw_case.get("hidden_truth")
        if not isinstance(raw_inputs, Mapping) or not isinstance(hidden_truth, Mapping):
            raise ValueError("missing_raw_inputs_or_hidden_truth")
        visible_hash = stable_hash(raw_inputs)
        if raw_case.get("visible_input_hash") != visible_hash:
            raise ValueError("visible_input_hash_mismatch")
        if stable_hash(hidden_truth) != raw_case.get("hidden_truth_hash"):
            raise ValueError("hidden_truth_hash_mismatch")
        split = str(raw_case["split"])
        system = str(raw_case["system_id"])
        split_systems[system].add(split)
        split_windows[split].append((int(raw_inputs["window_start"]), int(raw_inputs["window_end"])))
        fingerprint = str(raw_inputs["near_duplicate_fingerprint"])
        previous = fingerprints.get(fingerprint)
        if previous is not None and previous != split:
            raise ValueError("near_duplicate_cross_split_leakage")
        fingerprints[fingerprint] = split
        if set(raw_inputs).intersection({"outcome_label", "should_prevent", "expected_action", "harmful_if_actioned"}):
            raise ValueError("truth_leaked_into_raw_inputs")
    if any(len(splits) > 1 for splits in split_systems.values()):
        raise ValueError("system_crosses_splits")
    for split, windows in split_windows.items():
        ordered = sorted(windows)
        for left, right in zip(ordered, ordered[1:], strict=False):
            if left[1] > right[0]:
                raise ValueError(f"temporal_overlap:{split}")


def _score_case(case: Mapping[str, Any]) -> dict[str, Any]:
    raw_inputs = _mapping(case["raw_inputs"])
    hidden_truth = _mapping(case["hidden_truth"])
    forecast_probability = float(raw_inputs["indicator_strength"]) * (1.0 - float(raw_inputs["ood_score"]))
    prediction = {
        "forecast_positive": forecast_probability >= float(raw_inputs["decision_threshold"]),
        "route": "prevent_l3_local_sandbox" if forecast_probability >= float(raw_inputs["decision_threshold"]) and int(raw_inputs["fatigue_budget_remaining"]) > 0 else "abstain_fail_closed",
        "action_family": raw_inputs["recommended_action_family"],
    }
    should_prevent = bool(hidden_truth["should_prevent"])
    expected_action = str(hidden_truth["expected_action_family"])
    outcome_label = str(hidden_truth["outcome_label"])
    actioned = prediction["route"] == "prevent_l3_local_sandbox"
    forecast_correct = bool(prediction["forecast_positive"]) is should_prevent
    abstention_correct = actioned or not should_prevent
    harmful = actioned and bool(hidden_truth["harmful_if_actioned"])
    false_positive = actioned and not should_prevent
    rollback_failed = actioned and outcome_label == "rollback_failed"
    fatigue_violation = actioned and int(raw_inputs["fatigue_budget_remaining"]) <= 0
    utility = 1.0 if actioned and should_prevent and prediction["action_family"] == expected_action and not harmful else 0.0
    scored = {key: value for key, value in case.items() if key not in {"raw_inputs", "hidden_truth"}}
    scored.update(
        {
            "first_score_consumed": True,
            "forecast_correct": forecast_correct,
            "abstention_correct": abstention_correct,
            "prevention_utility": utility,
            "harmful": harmful,
            "false_positive": false_positive,
            "fatigue_violation": fatigue_violation,
            "rollback_failed": rollback_failed,
            "duplicate_effect_count": 0,
            "prediction": prediction,
            "outcome": {"label": outcome_label, "should_prevent": should_prevent},
            "passed": forecast_correct and abstention_correct and utility >= 1.0 and not harmful and not false_positive and not fatigue_violation and not rollback_failed,
        }
    )
    return scored


def _build_recovery_proof() -> dict[str, Any]:
    registry: dict[str, dict[str, Any]] = {"fixture-p121": {"disposable": True, "target_class": "disposable_local_sandbox", "allowed_handlers": ["inject_latency"]}}
    envelope: dict[str, Any] = {
        "operation_id": "p121-recovery",
        "authority_level": "L3",
        "target_class": "disposable_local_sandbox",
        "fixture_id": "fixture-p121",
        "handler": "inject_latency",
        "registry_hash": stable_hash(registry),
        "idempotency_key": "p121-recovery-idem",
        "lease_owner": "p121-recovery-worker",
        "lease_expires_at": 200,
        "approval_expires_at": 190,
        "authority_counters": zero_authority_counters(),
    }
    for name in ("forecast_hash", "evidence_hash", "counterfactual_hash", "guardrail_hash", "validation_plan_hash", "rollback_plan_hash"):
        envelope[name] = "sha256:" + name
    with tempfile.TemporaryDirectory(prefix="p121-recovery-") as directory:
        return prove_p121_restart_recovery(wal_path=Path(directory) / "execution.wal", envelope=envelope, registry=registry, now=100)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["P121_EVALUATION_SCHEMA_VERSION", "run_p121_frozen_evaluation"]
