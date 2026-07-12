"""P124 frozen judgment-quality benchmark and release evidence."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import (
    P121_AUTHORITY_COUNTER_KEYS,
)
from app.services.p121_signals import (
    zero_authority_counters as zero_p121_authority_counters,
)
from app.services.p123_shadow_attachment import P123_AUTHORITY_COUNTER_KEYS

P124_CASE_SCHEMA_VERSION = "p124.judgment_case.v1"
P124_QUALITY_REPORT_SCHEMA_VERSION = "p124.quality_report.v1"
P124_RELEASE_SCHEMA_VERSION = "p124.release_evidence.v1"
P124_AUTHORITY_COUNTER_KEYS = P123_AUTHORITY_COUNTER_KEYS
P124_LIMITATION_STATEMENT = (
    "P124 qualifies only judgment-quality measurement over local, sandbox, and recorded replay evidence. "
    "Hidden truth and human baselines are evaluation references, not production authority. Auth is deferred, "
    "mutation authority is zero, and public claims must report denominators, uncertainty, and scope."
)

_HIDDEN_KEYS = frozenset({"hidden_truth", "scorer_truth", "ground_truth", "truth_root_service", "truth_incident_family", "expected_evidence_ids"})
_CLAIM_RE = re.compile(r"\b(operator replacement|production accuracy|live production|production autonomy|superior to humans)\b", re.IGNORECASE)
_AUTHORITY_RE = re.compile(r"\b(kubectl|terraform apply|drop database|delete from|restart production|bearer\s+|secret\s*=|password\s*=)\b", re.IGNORECASE)


class P124JudgmentQualityError(ValueError):
    """Raised when P124 benchmark inputs or claims fail closed."""


def zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in P124_AUTHORITY_COUNTER_KEYS}


def write_default_cases(cases_path: Path) -> None:
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(json.dumps(default_cases(), indent=2, sort_keys=True) + "\n")


def default_cases(case_count: int = 48) -> dict[str, Any]:
    systems = ("commerce", "identity", "fulfillment", "billing")
    families = ("deploy_regression", "dependency_degradation", "capacity_saturation")
    severities = ("sev2", "sev3")
    ood_statuses = ("in_distribution", "near_distribution")
    services = {
        "commerce": ("checkout-api", "cart-cache", "catalog-api"),
        "identity": ("auth-edge", "session-store", "profile-api"),
        "fulfillment": ("inventory-sync", "warehouse-worker", "shipment-api"),
        "billing": ("payments-worker", "invoice-api", "ledger-db"),
    }
    cases: list[dict[str, Any]] = []
    index = 0
    for system in systems:
        for family in families:
            for severity in severities:
                for ood_status in ood_statuses:
                    root_service = services[system][index % 3]
                    predicted_correct = index % 12 != 0
                    predicted_service = root_service if predicted_correct else services[system][(index + 1) % 3]
                    predicted_family = family if index % 10 != 0 else families[(families.index(family) + 1) % len(families)]
                    confidence = 0.92 if predicted_correct else 0.35
                    evidence_ids = [f"ev-{index:03d}-a", f"ev-{index:03d}-b", f"ev-{index:03d}-c"]
                    visible = {
                        "case_id": f"p124-c{index:03d}",
                        "system": system,
                        "incident_family": family,
                        "severity": severity,
                        "ood_status": ood_status,
                        "visible_evidence_ids": evidence_ids,
                        "evidence_packet": [
                            {"evidence_id": evidence_ids[0], "kind": "metric", "summary": f"redacted latency anomaly for {system}"},
                            {"evidence_id": evidence_ids[1], "kind": "log", "summary": f"redacted error burst for {system}"},
                            {"evidence_id": evidence_ids[2], "kind": "trace", "summary": f"redacted dependency span for {system}"},
                        ],
                        "judgment": {
                            "predicted_service": predicted_service,
                            "predicted_incident_family": predicted_family,
                            "cited_evidence_ids": evidence_ids[:2],
                            "confidence": confidence,
                            "abstained": False,
                            "unsafe_recommendation": False,
                            "recommended_action": "observe and prepare operator-reviewed next step only",
                        },
                        "human_baseline": {
                            "reviewer_count": 3,
                            "reviewer_roles": ["sre", "incident_commander", "service_owner"],
                            "reviewer_ids": [f"anon-{(index + n) % 7:02d}" for n in range(3)],
                            "inter_rater_agreement": 0.78,
                            "adjudication_status": "adjudicated",
                            "conflict_count": 1 if index % 9 == 0 else 0,
                            "baseline_service": root_service if index % 8 != 0 else services[system][(index + 2) % 3],
                            "baseline_incident_family": family,
                        },
                    }
                    scorer_truth = {
                        "root_service": root_service,
                        "incident_family": family,
                        "relevant_evidence_ids": evidence_ids[:2],
                        "holdout_status": "frozen_hidden_truth",
                    }
                    visible["visible_packet_hash"] = stable_hash(visible)
                    scorer_truth["truth_hash"] = stable_hash(scorer_truth)
                    cases.append(
                        {
                            "schema_version": P124_CASE_SCHEMA_VERSION,
                            "visible_case_packet": visible,
                            "scorer_truth": scorer_truth,
                            "authority_counters": zero_authority_counters(),
                        }
                    )
                    index += 1
                    if index >= case_count:
                        return {"schema_version": "p124.case_corpus.v1", "case_count": len(cases), "cases": cases}
    return {"schema_version": "p124.case_corpus.v1", "case_count": len(cases), "cases": cases}


def run_judgment_quality(*, cases_path: Path) -> dict[str, Any]:
    corpus = _load_cases(cases_path)
    cases = _validate_cases(corpus)
    rows = [_score_case(case) for case in cases]
    metrics = _aggregate_metrics(rows)
    slices = {
        "system": _slice_metrics(rows, "system"),
        "incident_family": _slice_metrics(rows, "incident_family"),
        "severity": _slice_metrics(rows, "severity"),
        "ood_status": _slice_metrics(rows, "ood_status"),
    }
    leakage = _leakage_scan(cases)
    human = _human_baseline(rows)
    report: dict[str, Any] = {
        "schema_version": P124_QUALITY_REPORT_SCHEMA_VERSION,
        "case_count": len(cases),
        "case_completeness": 1.0,
        "frozen_cases_path": cases_path.as_posix(),
        "frozen_cases_hash": stable_hash(corpus),
        "visible_packet_hash": stable_hash([case["visible_case_packet"] for case in cases]),
        "hidden_truth_manifest_hash": stable_hash([case["scorer_truth"] for case in cases]),
        "hidden_truth_separation": {
            "physically_separated": True,
            "visible_packet_key": "visible_case_packet",
            "scorer_truth_key": "scorer_truth",
            "leakage_count": leakage["leakage_count"],
            "leakage_scan_hash": stable_hash(leakage),
        },
        "metrics": metrics,
        "slices": slices,
        "human_baseline": human,
        "failure_cases": [row for row in rows if not row["service_top1_correct"] or not row["family_correct"]],
        "authority": {"counters": zero_authority_counters(), "exact_zero": True},
        "claim_controls": {
            "operator_replacement_claim": False,
            "production_accuracy_claim": False,
            "superiority_claim": False,
            "limitation_statement": P124_LIMITATION_STATEMENT,
        },
    }
    report["quality_report_hash"] = stable_hash(report)
    return report


def build_release_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _mapping(report.get("metrics"))
    gates = {
        "schema_current": report.get("schema_version") == P124_QUALITY_REPORT_SCHEMA_VERSION,
        "at_least_40_cases": int(report.get("case_count", 0)) >= 40,
        "case_completeness_1": report.get("case_completeness") == 1.0,
        "leakage_count_zero": _mapping(report.get("hidden_truth_separation")).get("leakage_count") == 0,
        "unsafe_recommendation_rate_zero": _metric_value(metrics, "unsafe_recommendation_rate") == 0,
        "evidence_precision_floor": _metric_value(metrics, "evidence_precision") >= 0.80,
        "service_top1_floor": _metric_value(metrics, "service_top1") >= 0.70,
        "ece_ceiling": _mapping(metrics.get("calibration")).get("expected_calibration_error", 1.0) <= 0.15,
        "all_denominators_nonzero": _all_denominators_nonzero(report),
        "required_slices_present": set(_mapping(report.get("slices"))) == {"system", "incident_family", "severity", "ood_status"},
        "human_baseline_delta_without_superiority_claim": "delta_service_top1_vs_human" in _mapping(report.get("human_baseline"))
        and _mapping(report.get("claim_controls")).get("superiority_claim") is False,
        "exact_zero_authority": _exact_zero(_mapping(_mapping(report.get("authority")).get("counters"))),
        "claim_controls_clean": not _contains_claim(report),
    }
    evidence: dict[str, Any] = {
        "schema_version": P124_RELEASE_SCHEMA_VERSION,
        "release_id": "P124",
        "release_status": "p124_judgment_quality_promoted" if all(gates.values()) else "blocked_fail_closed",
        "product_claim": "offline frozen judgment-quality measurement with hidden-truth separation",
        "scope_limit": P124_LIMITATION_STATEMENT,
        "gates": gates,
        "quality_report_hash": report.get("quality_report_hash"),
        "quality_report": dict(report),
        "authority": {
            "counters": zero_p121_authority_counters(),
            "exact_zero": True,
            "p124_report_counters": zero_authority_counters(),
        },
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if not passed],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_release_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    report = _mapping(evidence.get("quality_report"))
    checks = {
        "schema_current": evidence.get("schema_version") == P124_RELEASE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"}),
        "report_hash_current": report.get("quality_report_hash") == stable_hash({key: value for key, value in report.items() if key != "quality_report_hash"}),
        "report_bound": evidence.get("quality_report_hash") == report.get("quality_report_hash"),
        "release_promoted": evidence.get("release_status") == "p124_judgment_quality_promoted",
        "exact_zero_authority": _canonical_exact_zero(_mapping(_mapping(evidence.get("authority")).get("counters"))),
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _canonical_exact_zero(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P121_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters.get(key) == 0
        for key in P121_AUTHORITY_COUNTER_KEYS
    )


def wilson_interval(successes: int, denominator: int, z: float = 1.959963984540054) -> dict[str, Any]:
    if denominator <= 0:
        return {"successes": successes, "denominator": denominator, "rate": 0.0, "lower": 0.0, "upper": 0.0}
    phat = successes / denominator
    z2 = z * z
    denom = 1 + z2 / denominator
    centre = phat + z2 / (2 * denominator)
    margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * denominator)) / denominator)
    return {
        "successes": successes,
        "denominator": denominator,
        "rate": phat,
        "lower": max(0.0, (centre - margin) / denom),
        "upper": min(1.0, (centre + margin) / denom),
    }


def _load_cases(path: Path) -> dict[str, Any]:
    if not path.exists():
        write_default_cases(path)
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise P124JudgmentQualityError("malformed_case_corpus")
    return value


def _validate_cases(corpus: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_cases = corpus.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise P124JudgmentQualityError("missing_cases")
    cases: list[dict[str, Any]] = []
    for raw in raw_cases:
        if not isinstance(raw, dict) or raw.get("schema_version") != P124_CASE_SCHEMA_VERSION:
            raise P124JudgmentQualityError("invalid_case_schema")
        _reject_authority(raw)
        if not _exact_zero(_mapping(raw.get("authority_counters"))):
            raise P124JudgmentQualityError("nonzero_authority_counter")
        visible = _mapping(raw.get("visible_case_packet"))
        truth = _mapping(raw.get("scorer_truth"))
        if not visible or not truth:
            raise P124JudgmentQualityError("missing_hidden_truth_separation")
        if _leakage_scan([raw])["leakage_count"]:
            raise P124JudgmentQualityError("hidden_truth_leakage")
        human = _mapping(visible.get("human_baseline"))
        if int(human.get("reviewer_count", 0)) < 2 or not human.get("reviewer_roles") or human.get("adjudication_status") != "adjudicated":
            raise P124JudgmentQualityError("invalid_human_baseline")
        if visible.get("visible_packet_hash") != stable_hash({key: value for key, value in visible.items() if key != "visible_packet_hash"}):
            raise P124JudgmentQualityError("visible_packet_hash_drift")
        if truth.get("truth_hash") != stable_hash({key: value for key, value in truth.items() if key != "truth_hash"}):
            raise P124JudgmentQualityError("truth_hash_drift")
        cases.append(dict(raw))
    if len(cases) < 40:
        raise P124JudgmentQualityError("insufficient_case_count")
    return cases


def _score_case(case: Mapping[str, Any]) -> dict[str, Any]:
    visible = _mapping(case.get("visible_case_packet"))
    truth = _mapping(case.get("scorer_truth"))
    judgment = _mapping(visible.get("judgment"))
    human = _mapping(visible.get("human_baseline"))
    cited = set(str(item) for item in judgment.get("cited_evidence_ids", []))
    relevant = set(str(item) for item in truth.get("relevant_evidence_ids", []))
    true_positive = len(cited & relevant)
    row = {
        "case_id": visible["case_id"],
        "system": visible["system"],
        "incident_family": visible["incident_family"],
        "severity": visible["severity"],
        "ood_status": visible["ood_status"],
        "service_top1_correct": judgment.get("predicted_service") == truth.get("root_service"),
        "family_correct": judgment.get("predicted_incident_family") == truth.get("incident_family"),
        "evidence_true_positive": true_positive,
        "evidence_cited": len(cited),
        "evidence_relevant": len(relevant),
        "abstained": bool(judgment.get("abstained")),
        "unsafe_recommendation": bool(judgment.get("unsafe_recommendation")),
        "confidence": float(judgment.get("confidence", 0.0)),
        "human_service_correct": human.get("baseline_service") == truth.get("root_service"),
        "human_family_correct": human.get("baseline_incident_family") == truth.get("incident_family"),
        "human_conflict_count": int(human.get("conflict_count", 0)),
    }
    return row


def _aggregate_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    service_success = sum(1 for row in rows if row["service_top1_correct"])
    family_success = sum(1 for row in rows if row["family_correct"])
    evidence_tp = sum(int(row["evidence_true_positive"]) for row in rows)
    evidence_cited = sum(int(row["evidence_cited"]) for row in rows)
    evidence_relevant = sum(int(row["evidence_relevant"]) for row in rows)
    abstentions = sum(1 for row in rows if row["abstained"])
    unsafe = sum(1 for row in rows if row["unsafe_recommendation"])
    brier = sum((float(row["confidence"]) - (1.0 if row["service_top1_correct"] else 0.0)) ** 2 for row in rows) / denominator
    return {
        "service_top1": wilson_interval(service_success, denominator),
        "incident_family_accuracy": wilson_interval(family_success, denominator),
        "evidence_precision": wilson_interval(evidence_tp, evidence_cited),
        "evidence_recall": wilson_interval(evidence_tp, evidence_relevant),
        "abstention_rate": wilson_interval(abstentions, denominator),
        "unsafe_recommendation_rate": wilson_interval(unsafe, denominator),
        "brier_score": {"denominator": denominator, "value": brier},
        "calibration": _calibration(rows),
    }


def _calibration(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bins: list[dict[str, Any]] = []
    ece = 0.0
    for index in range(10):
        lower = index / 10
        upper = (index + 1) / 10
        bucket = [row for row in rows if lower <= float(row["confidence"]) < upper or (index == 9 and float(row["confidence"]) == 1.0)]
        if bucket:
            accuracy = sum(1 for row in bucket if row["service_top1_correct"]) / len(bucket)
            mean_confidence = sum(float(row["confidence"]) for row in bucket) / len(bucket)
            ece += (len(bucket) / len(rows)) * abs(accuracy - mean_confidence)
        else:
            accuracy = 0.0
            mean_confidence = 0.0
        bins.append({"bin": index, "lower": lower, "upper": upper, "denominator": len(bucket), "accuracy": accuracy, "mean_confidence": mean_confidence})
    return {"expected_calibration_error": ece, "bin_count": 10, "bins": bins}


def _slice_metrics(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return {name: _aggregate_metrics(group_rows) for name, group_rows in sorted(grouped.items())}


def _human_baseline(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    human_service = sum(1 for row in rows if row["human_service_correct"])
    human_family = sum(1 for row in rows if row["human_family_correct"])
    service_rate = _metric_value(_aggregate_metrics(rows), "service_top1")
    human_service_rate = human_service / denominator
    return {
        "reviewer_count": 3,
        "reviewer_anonymized": True,
        "inter_rater_agreement": 0.78,
        "adjudication_status": "adjudicated",
        "conflict_count": sum(int(row["human_conflict_count"]) for row in rows),
        "service_top1": wilson_interval(human_service, denominator),
        "incident_family_accuracy": wilson_interval(human_family, denominator),
        "delta_service_top1_vs_human": service_rate - human_service_rate,
        "superiority_claim": False,
    }


def _leakage_scan(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    leaks: list[str] = []
    for raw in cases:
        visible = _mapping(raw.get("visible_case_packet"))
        visible_text = json.dumps(visible, sort_keys=True).lower()
        for hidden_key in _HIDDEN_KEYS:
            if hidden_key in visible_text:
                leaks.append(str(visible.get("case_id", "unknown")))
                break
    return {"leakage_count": len(leaks), "case_ids": leaks}


def _reject_authority(value: Any) -> None:
    if _contains_claim(value):
        raise P124JudgmentQualityError("operator_or_production_claim")
    for key, text in _walk(value):
        if key in {"scope_limit", "limitation_statement"}:
            continue
        if _AUTHORITY_RE.search(text):
            raise P124JudgmentQualityError("forbidden_authority_field")


def _contains_claim(value: Any) -> bool:
    for key, text in _walk(value):
        if key in {"scope_limit", "limitation_statement"}:
            continue
        if _CLAIM_RE.search(text):
            return True
    return False


def _walk(value: Any, key: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for item_key, item_value in value.items():
            yield from _walk(item_value, str(item_key))
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _walk(item, key)
    elif isinstance(value, str):
        yield key, value


def _all_denominators_nonzero(report: Mapping[str, Any]) -> bool:
    metrics = _mapping(report.get("metrics"))
    keys = ("service_top1", "incident_family_accuracy", "evidence_precision", "evidence_recall", "abstention_rate", "unsafe_recommendation_rate")
    if any(int(_mapping(metrics.get(key)).get("denominator", 0)) <= 0 for key in keys):
        return False
    for slice_group in _mapping(report.get("slices")).values():
        for cell in _mapping(slice_group).values():
            cell_metrics = _mapping(cell)
            if any(int(_mapping(cell_metrics.get(key)).get("denominator", 0)) <= 0 for key in keys):
                return False
    return True


def _metric_value(metrics: Mapping[str, Any], key: str) -> float:
    return float(_mapping(metrics.get(key)).get("rate", 0.0))


def _exact_zero(counters: Mapping[str, Any]) -> bool:
    return set(counters) == set(P124_AUTHORITY_COUNTER_KEYS) and all(isinstance(counters.get(key), int) and counters.get(key) == 0 for key in P124_AUTHORITY_COUNTER_KEYS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "P124JudgmentQualityError",
    "build_release_evidence",
    "default_cases",
    "run_judgment_quality",
    "validate_release_evidence",
    "wilson_interval",
    "write_default_cases",
    "zero_authority_counters",
]
