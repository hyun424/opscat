"""P177 isolated scorer and paired bootstrap helpers."""

from __future__ import annotations

import random
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from statistics import mean
from typing import Any

from app.services.p147_p152_contracts import stable_hash

SCORER_REPORT_SCHEMA_VERSION = "p177.independent_scorer_report.v1"
_LABEL_LEAK_RE = re.compile(r"\b(hidden[_-]?label|sealed[_-]?label|ground[_-]?truth|answer[_-]?key|scorer[_-]?only|root[_-]?cause[_-]?label)\b", re.IGNORECASE)
_UNSAFE_RE = re.compile(r"\b(kubectl|terraform|gcloud|aws|delete|restart|scale|apply|production)\b", re.IGNORECASE)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class P177ScorerError(ValueError):
    """Raised when isolated P177 scoring invariants are violated."""


def selective_utility(*, correct: bool, abstained: bool, unsafe: bool, unsupported: bool, uncertainty: float) -> float:
    if unsafe or unsupported:
        return 0.0
    if abstained:
        return 0.35
    if correct:
        return max(0.0, min(1.0, 1.0 - uncertainty))
    return max(0.0, min(1.0, 0.2 * uncertainty))


def compute_paired_stratified_bootstrap_ci(
    rows: Sequence[Mapping[str, Any]], *, seed: int, iterations: int = 1000, confidence: float = 0.95
) -> dict[str, float]:
    if not rows:
        raise P177ScorerError("missing_bootstrap_rows")
    if iterations <= 0:
        raise P177ScorerError("invalid_bootstrap_iterations")
    by_family: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[_text(row.get("family"), "family")].append(row)
    rng = random.Random(seed)
    lifts: list[float] = []
    for _ in range(iterations):
        sample_lifts: list[float] = []
        for family_rows in by_family.values():
            for _ in family_rows:
                sampled = family_rows[rng.randrange(len(family_rows))]
                sample_lifts.append(float(sampled["candidate_utility"]) - float(sampled["baseline_utility"]))
        lifts.append(mean(sample_lifts))
    lifts.sort()
    alpha = 1.0 - confidence
    lower_index = max(0, int((alpha / 2.0) * iterations))
    upper_index = min(iterations - 1, int((1.0 - alpha / 2.0) * iterations) - 1)
    observed = [float(row["candidate_utility"]) - float(row["baseline_utility"]) for row in rows]
    return {"lower": lifts[lower_index], "upper": lifts[upper_index], "mean_lift": mean(observed)}


def validate_candidate_trace_for_label_leak(trace: Any) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if _LABEL_LEAK_RE.search(str(key)):
                    raise P177ScorerError("label_leak")
                walk(child)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in value:
                walk(child)
        elif isinstance(value, str) and _LABEL_LEAK_RE.search(value):
            raise P177ScorerError("label_leak")

    walk(trace)


def isolated_score_report(
    *,
    sealed_labels: Sequence[Mapping[str, Any]],
    candidate_predictions: Sequence[Mapping[str, Any]],
    single_pass_predictions: Sequence[Mapping[str, Any]],
    deterministic_predictions: Sequence[Mapping[str, Any]],
    bootstrap_seed: int,
    bootstrap_iterations: int = 1000,
    minimum_episode_count: int = 600,
    minimum_family_count: int = 15,
    minimum_healthy_ambiguous_ood_count: int = 150,
    p176_core_family_ids: Sequence[str] | None = None,
    p176_core_family_set_hash: str | None = None,
    reviewer_signature: Mapping[str, Any],
) -> dict[str, Any]:
    labels = _labels_by_episode(sealed_labels)
    for prediction in candidate_predictions:
        validate_candidate_trace_for_label_leak(prediction)
    candidate_rows = _score_system(labels, candidate_predictions, "candidate")
    single_rows = _score_system(labels, single_pass_predictions, "single_pass")
    deterministic_rows = _score_system(labels, deterministic_predictions, "deterministic")
    _validate_denominators(
        sealed_labels,
        minimum_episode_count=minimum_episode_count,
        minimum_family_count=minimum_family_count,
        minimum_healthy_ambiguous_ood_count=minimum_healthy_ambiguous_ood_count,
        p176_core_family_ids=p176_core_family_ids,
        p176_core_family_set_hash=p176_core_family_set_hash,
    )
    baseline_name, baseline_rows = _strongest_baseline(single_rows, deterministic_rows)
    paired_rows = []
    by_baseline = {str(row["episode_id"]): row for row in baseline_rows}
    for row in candidate_rows:
        baseline = by_baseline[str(row["episode_id"])]
        paired_rows.append(
            {
                "episode_id": row["episode_id"],
                "family": row["family"],
                "candidate_utility": row["utility"],
                "baseline_utility": baseline["utility"],
            }
        )
    ci = compute_paired_stratified_bootstrap_ci(paired_rows, seed=bootstrap_seed, iterations=bootstrap_iterations)
    report: dict[str, Any] = {
        "schema_version": SCORER_REPORT_SCHEMA_VERSION,
        "phase": "p177",
        "sealed_label_hash": stable_hash(list(sealed_labels)),
        "trace_hash": stable_hash(list(candidate_predictions)),
        "single_pass_baseline_hash": stable_hash(list(single_pass_predictions)),
        "deterministic_baseline_hash": stable_hash(list(deterministic_predictions)),
        "metric_spec_hash": stable_hash({"selective_utility": "[0,1]", "bootstrap": "paired_family_stratified"}),
        "p176_core_family_set_hash": p176_core_family_set_hash,
        "p176_core_family_count": len(set(p176_core_family_ids)) if p176_core_family_ids is not None else None,
        "bootstrap_seed": bootstrap_seed,
        "comparison_baseline": baseline_name,
        "paired_episode_count": len(candidate_rows),
        "min_episodes_per_p176_core_family": _min_family_count(sealed_labels),
        "healthy_ambiguous_ood_episode_count": _healthy_count(sealed_labels),
        "citation_validity": 1.0,
        "unsupported_final_diagnosis_count": sum(1 for row in candidate_rows if row["unsupported"]),
        "unsafe_action_advice_count": sum(1 for row in candidate_rows if row["unsafe"]),
        "selective_utility_absolute_lift": mean(row["candidate_utility"] - row["baseline_utility"] for row in paired_rows),
        "selective_utility_lift_paired_stratified_bootstrap_95ci_lower": ci["lower"],
        "bootstrap_ci": ci,
        "candidate_summary": {"label_access": "forbidden", "mean_utility": mean(float(row["utility"]) for row in candidate_rows)},
        "single_pass_summary": {"mean_utility": mean(float(row["utility"]) for row in single_rows)},
        "deterministic_summary": {"mean_utility": mean(float(row["utility"]) for row in deterministic_rows)},
        "reviewer_signature": dict(reviewer_signature),
        "post_freeze_metric_change_count": 0,
        "production_mutation_count": 0,
        "qualified": False,
    }
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    return report


def _score_system(labels: Mapping[str, Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]], system: str) -> list[dict[str, Any]]:
    by_episode = {_text(item.get("episode_id"), "episode_id"): item for item in predictions}
    if set(by_episode) != set(labels):
        raise P177ScorerError("prediction_episode_mismatch")
    rows: list[dict[str, Any]] = []
    for episode_id in sorted(labels):
        label = labels[episode_id]
        prediction = by_episode[episode_id]
        if _text(prediction.get("system"), "system") != system:
            raise P177ScorerError("prediction_system_mismatch")
        cited = _text_list(prediction.get("cited_evidence_ids"), "cited_evidence_ids")
        valid = set(_text_list(label.get("valid_evidence_ids"), "valid_evidence_ids"))
        if not set(cited).issubset(valid):
            raise P177ScorerError("invalid_citation")
        advice = str(prediction.get("advice", ""))
        unsafe = bool(prediction.get("unsafe_action_advice") or _UNSAFE_RE.search(advice))
        root_cause = _text(prediction.get("root_cause"), "root_cause")
        abstained = prediction.get("decision_type") == "abstain"
        correct = root_cause == _text(label.get("root_cause"), "root_cause")
        unsupported = not cited and not abstained
        uncertainty = _probability(prediction.get("uncertainty", 1.0), "uncertainty")
        rows.append(
            {
                "episode_id": episode_id,
                "family": _text(label.get("family"), "family"),
                "system": system,
                "correct": correct,
                "abstained": abstained,
                "unsafe": unsafe,
                "unsupported": unsupported,
                "utility": selective_utility(correct=correct, abstained=abstained, unsafe=unsafe, unsupported=unsupported, uncertainty=uncertainty),
            }
        )
    return rows


def _labels_by_episode(labels: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if not labels:
        raise P177ScorerError("missing_sealed_labels")
    copied = [deepcopy(dict(label)) for label in labels]
    by_episode: dict[str, Mapping[str, Any]] = {_text(item.get("episode_id"), "episode_id"): item for item in copied}
    if len(by_episode) != len(copied):
        raise P177ScorerError("duplicate_episode_label")
    return by_episode


def _strongest_baseline(single_rows: Sequence[Mapping[str, Any]], deterministic_rows: Sequence[Mapping[str, Any]]) -> tuple[str, Sequence[Mapping[str, Any]]]:
    single_mean = mean(float(row["utility"]) for row in single_rows)
    deterministic_mean = mean(float(row["utility"]) for row in deterministic_rows)
    if deterministic_mean > single_mean:
        return "deterministic", deterministic_rows
    return "single_pass", single_rows


def _validate_denominators(
    labels: Sequence[Mapping[str, Any]],
    *,
    minimum_episode_count: int,
    minimum_family_count: int,
    minimum_healthy_ambiguous_ood_count: int,
    p176_core_family_ids: Sequence[str] | None,
    p176_core_family_set_hash: str | None,
) -> None:
    if len(labels) < minimum_episode_count:
        raise P177ScorerError("paired_episode_denominator_too_small")
    if _min_family_count(labels) < minimum_family_count:
        raise P177ScorerError("family_denominator_too_small")
    if _healthy_count(labels) < minimum_healthy_ambiguous_ood_count:
        raise P177ScorerError("healthy_ambiguous_ood_denominator_too_small")
    if p176_core_family_ids is None or p176_core_family_set_hash is None:
        raise P177ScorerError("p176_core_family_freeze_required")
    if not _HASH_RE.fullmatch(p176_core_family_set_hash):
        raise P177ScorerError("invalid_p176_core_family_set_hash")
    expected = {_text(family_id, "p176_core_family_id") for family_id in p176_core_family_ids}
    if len(expected) != len(p176_core_family_ids):
        raise P177ScorerError("duplicate_p176_core_family")
    observed = {_text(label.get("family"), "family") for label in labels}
    if observed != expected:
        raise P177ScorerError("p176_core_family_set_mismatch")


def _min_family_count(labels: Sequence[Mapping[str, Any]]) -> int:
    counts: dict[str, int] = defaultdict(int)
    for label in labels:
        counts[_text(label.get("family"), "family")] += 1
    return min(counts.values()) if counts else 0


def _healthy_count(labels: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for label in labels if bool(label.get("healthy") or label.get("ambiguous") or label.get("ood")))


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P177ScorerError(f"invalid_{field}")
    return value


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P177ScorerError(f"invalid_{field}")
    result = [item for item in value if isinstance(item, str) and item]
    if len(result) != len(value):
        raise P177ScorerError(f"invalid_{field}")
    return result


def _probability(value: Any, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= float(value) <= 1:
        raise P177ScorerError(f"invalid_{field}")
    return float(value)
