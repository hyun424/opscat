"""P108 fixture, release evidence, and independent review contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

CANONICAL_FIXTURE_PATH = Path("evals/prevention/p108_learning_cases.json")
FIXTURE_SCHEMA_VERSION = "p108.learning_fixture_matrix.v1"
RELEASE_EVIDENCE_SCHEMA_VERSION = "p108.release_evidence.v1"
INDEPENDENT_REVIEW_SCHEMA_VERSION = "p108.independent_review.v1"
P108_RELEASE_PROFILE = "p108-release"
DEFAULT_TRUSTED_NOW = "2026-07-10T04:00:00Z"

REQUIRED_FIXTURE_IDENTITIES = (
    ("L01", "valid_prevented", "prevented"),
    ("L02", "valid_delayed", "delayed"),
    ("L03", "unaffected", "unaffected"),
    ("L04", "natural_recovery", "naturally_recovered"),
    ("L05", "harmful_guardrail_breach", "harmful"),
    ("L06", "inconclusive_missing_control", "inconclusive"),
    ("L07", "censored_horizon", "censored"),
    ("L08", "false_positive_intervention", "unaffected"),
    ("L09", "near_miss_abstention", "unaffected"),
    ("L10", "conflicting_evidence", "inconclusive"),
    ("L11", "telemetry_loss", "inconclusive"),
    ("L12", "family_level_drift", "delayed"),
    ("L13", "candidate_safety_regression", "harmful"),
    ("L14", "valid_conservative_recommendation", "prevented"),
    ("L15", "forged_p107_handoff", "rejected"),
    ("L16", "online_mutation_attempt", "rejected"),
)
REQUIRED_FIXTURE_IDS = tuple(fixture_id for fixture_id, _, _ in REQUIRED_FIXTURE_IDENTITIES)
REQUIRED_EVIDENCE_GATES = frozenset(
    {
        "ingress_recomputed",
        "ledger_content_bound",
        "temporal_cutoff_enforced",
        "counterfactual_identifiable_or_abstained",
        "recommendation_unapplied",
        "holdout_disjoint",
        "authority_zero",
    }
)
ZERO_AUTHORITY_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "subprocess_calls": 0,
    "cloud_calls": 0,
    "db_access": 0,
    "production_adapter_calls": 0,
    "production_mutation": 0,
    "live_calls": 0,
    "executor_calls": 0,
    "online_policy_writes": 0,
}
REQUIRED_METRICS = {
    "prevented_precision",
    "unnecessary_intervention_rate",
    "harmful_intervention_rate",
    "natural_recovery_miscredit_rate",
    "inconclusive_rate",
    "censored_rate",
    "net_avoided_impact",
    "forecast_calibration_drift",
    "median_learning_utility_delta",
    "one_sided_exact_sign_probability",
}
SIX_RELEASE_GATE_KEYS = (
    "p107_ingress_ready",
    "immutable_ledger_ready",
    "benchmark_metrics_ready",
    "recommendation_manifest_ready",
    "promotion_ready",
    "authority_boundary_ready",
)
REVIEW_HASH_KEYS = (
    "ingress_hash",
    "ledger_head_hash",
    "benchmark_hash",
    "release_evidence_hash",
    "fixture_matrix_hash",
    "holdout_report_hash",
    "promotion_report_hash",
    "recommendation_manifest_hash",
    "authority_scan_hash",
    "docs_scan_hash",
    "release_profile_hash",
)
APPROVED_REVIEWER_ROLES = frozenset({"code-reviewer", "architect", "verifier", "independent-reviewer"})
RFC3339_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")
CANONICAL_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
FORBIDDEN_AUTHORITY_REQUEST_KINDS = frozenset({"db_session_query", "db_query", "session_query", "online_policy_mutation", "production_mutation"})


def zero_authority_counters() -> dict[str, int]:
    return dict(ZERO_AUTHORITY_COUNTERS)


def load_prevention_learning_fixture_matrix(path: str | Path = CANONICAL_FIXTURE_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_prevention_learning_fixture_matrix(matrix: Mapping[str, Any]) -> dict[str, Any]:
    fixtures = list(matrix.get("fixtures", [])) if isinstance(matrix.get("fixtures"), list) else []
    fixture_identities: list[tuple[str, str, str]] = []
    evidence_gate_failures: dict[str, list[str]] = {}
    authority_counter_failures: dict[str, dict[str, Any]] = {}
    recommendation_failures: dict[str, list[str]] = {}
    episode_evaluation_failures: dict[str, dict[str, Any]] = {}
    negative_case_results: dict[str, dict[str, Any]] = {}
    negative_case_failures: dict[str, str] = {}
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            continue
        fixture_id = str(fixture.get("fixture_id", ""))
        episode_result = _evaluate_fixture_episode(fixture)
        fixture_identities.append((fixture_id, str(fixture.get("scenario", "")), str(episode_result["actual_label"])))
        expected_evaluation = fixture.get("expected_evaluation")
        expected_failed_before_ledger = expected_evaluation.get("failed_before_ledger") if isinstance(expected_evaluation, Mapping) else None
        expected_negative_rejection = expected_failed_before_ledger is True and episode_result["actual_label"] == "rejected" and episode_result["failed_before_ledger"] is True
        failed_gates = [] if expected_negative_rejection else [gate for gate, passed in episode_result["computed_gates"].items() if not passed]
        if failed_gates:
            evidence_gate_failures[fixture_id] = failed_gates
        counter_failures = _authority_counter_failures(fixture.get("authority_counters"))
        if counter_failures:
            authority_counter_failures[fixture_id] = counter_failures
        recommendation_errors = _recommendation_errors(fixture.get("recommendation"))
        if recommendation_errors:
            recommendation_failures[fixture_id] = recommendation_errors
        expected_label = expected_evaluation.get("label") if isinstance(expected_evaluation, Mapping) else fixture.get("expected_label")
        expected_ledger_admitted = expected_evaluation.get("ledger_admitted") if isinstance(expected_evaluation, Mapping) else None
        if (
            episode_result["actual_label"] != expected_label
            or (isinstance(expected_ledger_admitted, bool) and episode_result["ledger_admitted"] is not expected_ledger_admitted)
            or (isinstance(expected_failed_before_ledger, bool) and episode_result["failed_before_ledger"] is not expected_failed_before_ledger)
        ):
            episode_evaluation_failures[fixture_id] = {
                "actual_label": episode_result["actual_label"],
                "expected_label": expected_label,
                "ledger_admitted": episode_result["ledger_admitted"],
                "failed_before_ledger": episode_result["failed_before_ledger"],
            }
        if fixture_id in {"L15", "L16"}:
            negative_case_results[fixture_id] = {
                "actual_label": episode_result["actual_label"],
                "failed_before_ledger": episode_result["failed_before_ledger"],
                "ledger_admitted": episode_result["ledger_admitted"],
            }
            if negative_case_results[fixture_id] != {"actual_label": "rejected", "failed_before_ledger": True, "ledger_admitted": False}:
                negative_case_failures[fixture_id] = "negative case must reject before ledger"

    fixture_ids = [fixture_id for fixture_id, _, _ in fixture_identities]
    missing_fixture_ids = [fixture_id for fixture_id in REQUIRED_FIXTURE_IDS if fixture_id not in fixture_ids]
    unexpected_fixture_ids = [fixture_id for fixture_id in fixture_ids if fixture_id not in REQUIRED_FIXTURE_IDS]
    duplicate_fixture_ids = sorted({fixture_id for fixture_id in fixture_ids if fixture_ids.count(fixture_id) > 1})
    identity_mismatches = {
        expected[0]: {"expected": expected, "actual": actual}
        for expected, actual in zip(REQUIRED_FIXTURE_IDENTITIES, fixture_identities, strict=False)
        if actual != expected
    }

    statistical_support = _statistical_support(matrix.get("paired_learning_utility_deltas"))
    metric_failures = _metric_failures(matrix.get("metrics"), computed_median_delta=statistical_support.get("computed_median_delta"))
    family_failures = _family_failures(matrix.get("family_results"))
    schema_valid = matrix.get("schema_version") == FIXTURE_SCHEMA_VERSION
    exact_identity = fixture_identities == list(REQUIRED_FIXTURE_IDENTITIES)
    accepted = (
        schema_valid
        and exact_identity
        and not missing_fixture_ids
        and not unexpected_fixture_ids
        and not duplicate_fixture_ids
        and not identity_mismatches
        and not evidence_gate_failures
        and not authority_counter_failures
        and not recommendation_failures
        and not episode_evaluation_failures
        and not negative_case_failures
        and not metric_failures
        and statistical_support["accepted"]
        and not family_failures
    )
    return {
        "accepted": accepted,
        "schema_version": matrix.get("schema_version"),
        "fixture_ids": fixture_ids,
        "fixture_identities": fixture_identities,
        "required_fixture_identities": list(REQUIRED_FIXTURE_IDENTITIES),
        "missing_fixture_ids": missing_fixture_ids,
        "unexpected_fixture_ids": unexpected_fixture_ids,
        "duplicate_fixture_ids": duplicate_fixture_ids,
        "identity_mismatches": identity_mismatches,
        "evidence_gate_failures": evidence_gate_failures,
        "authority_counter_failures": authority_counter_failures,
        "recommendation_failures": recommendation_failures,
        "episode_evaluation_failures": episode_evaluation_failures,
        "negative_case_results": negative_case_results,
        "negative_case_failures": negative_case_failures,
        "metric_failures": metric_failures,
        "statistical_support": statistical_support,
        "family_failures": family_failures,
        "matrix_hash": stable_hash(matrix),
        "matrix_source_path": str(matrix.get("source_path") or CANONICAL_FIXTURE_PATH),
        "required_metrics": sorted(REQUIRED_METRICS),
        "six_release_gates": {key: accepted for key in SIX_RELEASE_GATE_KEYS},
    }


def build_prevention_learning_evidence(matrix: Mapping[str, Any], *, trusted_now: str = DEFAULT_TRUSTED_NOW) -> dict[str, Any]:
    result = evaluate_prevention_learning_fixture_matrix(matrix)
    return {
        "schema_version": "p108.learning_evidence.v1",
        "release_schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "fixture_path": str(result["matrix_source_path"]),
        "trusted_now": trusted_now,
        "fixture_ids": result["fixture_ids"],
        "fixture_identities": result["fixture_identities"],
        "accepted": result["accepted"],
        "matrix_hash": result["matrix_hash"],
        "six_release_gates": result["six_release_gates"],
        "metric_failures": result["metric_failures"],
        "statistical_support": result["statistical_support"],
        "authority_counter_failures": result["authority_counter_failures"],
        "result": result,
    }


def produce_p108_release_evidence(
    *,
    producer_id: str,
    fixture_matrix_result: Mapping[str, Any],
    ingress_result: Mapping[str, Any],
    ledger_result: Mapping[str, Any],
    benchmark_result: Mapping[str, Any],
    recommendation_manifest: Mapping[str, Any],
    promotion_report: Mapping[str, Any],
    authority_scan: Mapping[str, Any],
    docs_scan: Mapping[str, Any],
    verify_profile: Mapping[str, Any],
    independent_review: Mapping[str, Any] | None,
    trusted_now: str = DEFAULT_TRUSTED_NOW,
) -> dict[str, Any]:
    fixture_recomputed = _recompute_fixture_matrix_result(fixture_matrix_result)
    benchmark_recomputed = _recompute_benchmark_result(benchmark_result)
    six_gates = {
        "p107_ingress_ready": _section_accepted_with_hash(ingress_result, "ingress_hash"),
        "immutable_ledger_ready": _section_accepted_with_hash(ledger_result, "ledger_head_hash"),
        "benchmark_metrics_ready": benchmark_recomputed["accepted"],
        "recommendation_manifest_ready": recommendation_manifest.get("accepted") is True
        and recommendation_manifest.get("applied") is False
        and bool(recommendation_manifest.get("rollback_to_version")),
        "promotion_ready": _section_accepted_with_hash(promotion_report, "holdout_report_hash")
        and _canonical_sha256(promotion_report.get("promotion_report_hash"))
        and promotion_report.get("holdout_disjoint") is True
        and promotion_report.get("promotion_ready") is True,
        "authority_boundary_ready": _section_accepted_with_hash(authority_scan, "authority_scan_hash")
        and _authority_counter_failures(authority_scan.get("authority_counters")) == {},
    }
    reasons = [f"{gate} failed closed" for gate, passed in six_gates.items() if not passed]

    fixture_ids = list(fixture_recomputed.get("fixture_ids", []))
    supplied_fixture_ids = fixture_matrix_result.get("fixture_ids")
    if fixture_recomputed.get("accepted") is not True:
        reasons.append("fixture matrix did not pass recomputation")
    if fixture_ids != list(REQUIRED_FIXTURE_IDS):
        reasons.append("fixture matrix must contain exact L01-L16 identity")
    if isinstance(supplied_fixture_ids, list) and supplied_fixture_ids != fixture_ids:
        reasons.append("fixture matrix supplied fixture_ids must match recomputed L01-L16 identity")
    if not _section_accepted_with_hash(docs_scan, "docs_scan_hash") or docs_scan.get("overclaiming_phrases"):
        reasons.append("docs scan did not pass")
    if (
        verify_profile.get("profile") != P108_RELEASE_PROFILE
        or verify_profile.get("passed") is not True
        or verify_profile.get("fresh") is not True
        or not _canonical_sha256(verify_profile.get("release_profile_hash"))
    ):
        reasons.append("p108-release verify profile did not pass fresh")
    if not _recommendation_manifest_valid(recommendation_manifest):
        reasons.append("recommendation manifest did not pass structural validation")

    expected_hashes = {
        "ingress_hash": ingress_result.get("ingress_hash"),
        "ledger_head_hash": ledger_result.get("ledger_head_hash"),
        "benchmark_hash": benchmark_result.get("benchmark_hash"),
        "fixture_matrix_hash": fixture_recomputed.get("matrix_hash"),
        "holdout_report_hash": promotion_report.get("holdout_report_hash"),
        "promotion_report_hash": promotion_report.get("promotion_report_hash"),
        "recommendation_manifest_hash": recommendation_manifest.get("recommendation_manifest_hash") or recommendation_manifest.get("manifest_hash"),
        "authority_scan_hash": authority_scan.get("authority_scan_hash"),
        "docs_scan_hash": docs_scan.get("docs_scan_hash"),
        "release_profile_hash": verify_profile.get("release_profile_hash"),
    }
    core_payload = {
        "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "producer_id": producer_id,
        "fixture_matrix_hash": expected_hashes["fixture_matrix_hash"],
        "fixture_ids": fixture_ids,
        "ingress_hash": expected_hashes["ingress_hash"],
        "ledger_head_hash": expected_hashes["ledger_head_hash"],
        "benchmark_hash": expected_hashes["benchmark_hash"],
        "holdout_report_hash": expected_hashes["holdout_report_hash"],
        "promotion_report_hash": expected_hashes["promotion_report_hash"],
        "recommendation_manifest_hash": expected_hashes["recommendation_manifest_hash"],
        "authority_scan_hash": expected_hashes["authority_scan_hash"],
        "docs_scan_hash": expected_hashes["docs_scan_hash"],
        "release_profile_hash": expected_hashes["release_profile_hash"],
        "six_release_gates": six_gates,
        "trusted_now": trusted_now,
    }
    release_evidence_hash = stable_hash(core_payload)
    expected_hashes["release_evidence_hash"] = release_evidence_hash
    review_result = validate_p108_independent_review(
        independent_review,
        expected_hashes=expected_hashes,
        producer_id=producer_id,
        trusted_now=trusted_now,
    )
    if not review_result["accepted"]:
        reasons.append("P108 independent review contract did not pass")

    release_qualified = not reasons and all(six_gates.values()) and review_result["accepted"]
    return {
        **core_payload,
        "release_evidence_hash": release_evidence_hash,
        "release_qualified": release_qualified,
        "reasons": reasons,
        "independent_review": review_result,
        "fixture_recomputed": fixture_recomputed,
        "benchmark_recomputed": benchmark_recomputed,
    }


def validate_p108_independent_review(
    review: Mapping[str, Any] | None,
    *,
    expected_hashes: Mapping[str, Any],
    producer_id: str,
    trusted_now: str = DEFAULT_TRUSTED_NOW,
) -> dict[str, Any]:
    if not isinstance(review, Mapping):
        return {
            "accepted": False,
            "fresh": False,
            "reviewed_artifact_hashes_match": False,
            "reasons": ["missing independent review"],
            "schema_version": None,
            "reviewer": None,
            "verdict": None,
            "review_id": None,
        }
    reasons: list[str] = []
    if review.get("schema_version") != INDEPENDENT_REVIEW_SCHEMA_VERSION:
        reasons.append("schema_version must be p108.independent_review.v1")
    review_id = review.get("review_id")
    if not isinstance(review_id, str) or not review_id.strip():
        reasons.append("review_id must be non-empty")
    verdict = review.get("verdict")
    if verdict != "pass":
        reasons.append("independent review verdict must be lowercase pass")
    reviewer = review.get("reviewer")
    reviewer_id = reviewer.get("id") if isinstance(reviewer, Mapping) else None
    reviewer_role = reviewer.get("role") if isinstance(reviewer, Mapping) else None
    if not isinstance(reviewer, Mapping) or reviewer_role not in APPROVED_REVIEWER_ROLES or not isinstance(reviewer_id, str) or not reviewer_id:
        reasons.append("reviewer must use an approved independent role and non-empty id")
    if review.get("producer_id") != producer_id:
        reasons.append("producer_id must match release producer")
    if reviewer_id == producer_id or review.get("producer_id") == reviewer_id:
        reasons.append("reviewer must not be the producer")

    reviewed_hashes = review.get("reviewed_artifact_hashes")
    hashes_canonical = isinstance(reviewed_hashes, Mapping) and all(_canonical_sha256(reviewed_hashes.get(key)) for key in REVIEW_HASH_KEYS)
    expected_hashes_canonical = all(_canonical_sha256(expected_hashes.get(key)) for key in REVIEW_HASH_KEYS)
    reviewed_artifact_hashes_match = isinstance(reviewed_hashes, Mapping) and hashes_canonical and expected_hashes_canonical and all(
        reviewed_hashes.get(key) == expected_hashes.get(key) for key in REVIEW_HASH_KEYS
    )
    if not hashes_canonical or not expected_hashes_canonical:
        reasons.append("reviewed artifact hashes must be canonical sha256:<64hex> and complete")
    if not reviewed_artifact_hashes_match:
        reasons.append("reviewed artifact hashes must match P108 release artifacts")
    raw_freshness = review.get("freshness")
    freshness: Mapping[str, Any] = raw_freshness if isinstance(raw_freshness, Mapping) else {}
    fresh, freshness_reasons = _validate_freshness(freshness, review.get("reviewed_at"), trusted_now)
    reasons.extend(freshness_reasons)
    return {
        "accepted": not reasons,
        "fresh": fresh,
        "reviewed_artifact_hashes_match": reviewed_artifact_hashes_match,
        "reasons": reasons,
        "schema_version": review.get("schema_version"),
        "reviewer": dict(reviewer) if isinstance(reviewer, Mapping) else None,
        "verdict": verdict,
        "review_id": review_id,
        "freshness": dict(freshness),
    }


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _failed_evidence_gates(gates: Any) -> list[str]:
    if not isinstance(gates, Mapping):
        return sorted(REQUIRED_EVIDENCE_GATES)
    failed = [gate for gate in REQUIRED_EVIDENCE_GATES if gates.get(gate) is not True]
    extra = [str(gate) for gate in gates if gate not in REQUIRED_EVIDENCE_GATES]
    return sorted(failed + extra)


def _authority_counter_failures(counters: Any) -> dict[str, Any]:
    if not isinstance(counters, Mapping):
        return dict(ZERO_AUTHORITY_COUNTERS)
    failures: dict[str, Any] = {}
    for key, expected in ZERO_AUTHORITY_COUNTERS.items():
        if counters.get(key) != expected:
            failures[key] = counters.get(key)
    for key, value in counters.items():
        if key not in ZERO_AUTHORITY_COUNTERS:
            failures[str(key)] = value
    return failures


def _recommendation_errors(recommendation: Any) -> list[str]:
    if not isinstance(recommendation, Mapping):
        return ["missing_recommendation"]
    errors = []
    if recommendation.get("applied") is not False:
        errors.append("recommendation_must_be_unapplied")
    if not recommendation.get("rollback_to_version"):
        errors.append("missing_rollback_to_version")
    return errors


def _metric_failures(metrics: Any, *, computed_median_delta: Any | None = None) -> dict[str, str]:
    if not isinstance(metrics, Mapping):
        return {key: "missing" for key in sorted(REQUIRED_METRICS)}
    failures = {key: "missing" for key in sorted(REQUIRED_METRICS) if key not in metrics}
    if metrics.get("harmful_intervention_rate") != 0.0:
        failures["harmful_intervention_rate"] = "must_be_zero"
    if metrics.get("natural_recovery_miscredit_rate") != 0.0:
        failures["natural_recovery_miscredit_rate"] = "must_be_zero"
    if metrics.get("forecast_calibration_drift", 1.0) > 0.01:
        failures["forecast_calibration_drift"] = "drift_above_0.01"
    if computed_median_delta is None:
        failures["median_learning_utility_delta"] = "missing_computed_median_delta"
    elif not isinstance(computed_median_delta, (int, float)) or computed_median_delta < 0.03:
        failures["median_learning_utility_delta"] = "computed_median_delta_below_0.03"
    elif metrics.get("median_learning_utility_delta") != computed_median_delta:
        failures["median_learning_utility_delta"] = "declared_median_must_match_raw_deltas"
    if metrics.get("one_sided_exact_sign_probability") != "1/64":
        failures["one_sided_exact_sign_probability"] = "must_report_1/64"
    return failures


def _statistical_support(cells: Any) -> dict[str, Any]:
    raw_cells = [cell for cell in cells if isinstance(cell, Mapping)] if isinstance(cells, Sequence) and not isinstance(cells, (str, bytes)) else []
    seeds = sorted({seed for cell in raw_cells if isinstance((seed := cell.get("seed")), int)})
    splits = sorted({split for cell in raw_cells if isinstance((split := cell.get("time_split")), str)})
    deltas = [cell.get("delta") for cell in raw_cells]
    positive = all(isinstance(delta, (int, float)) and delta > 0 for delta in deltas)
    computed_median_delta = _median([float(delta) for delta in deltas if isinstance(delta, (int, float))])
    nontrivial = isinstance(computed_median_delta, float) and computed_median_delta >= 0.03
    accepted = len(raw_cells) == 6 and len(seeds) == 3 and len(splits) == 2 and positive and nontrivial
    return {
        "accepted": accepted,
        "cell_count": len(raw_cells),
        "seeds": seeds,
        "time_splits": splits,
        "all_deltas_positive": positive,
        "computed_median_delta": computed_median_delta,
        "nontrivial_median_delta": nontrivial,
    }


def _family_failures(families: Any) -> dict[str, list[str]]:
    if not isinstance(families, Mapping):
        return {"_all": ["missing_family_results"]}
    failures: dict[str, list[str]] = {}
    for family, result in families.items():
        errors = []
        if not isinstance(result, Mapping):
            failures[str(family)] = ["invalid_family_result"]
            continue
        if result.get("episode_count", 0) < 6:
            errors.append("episode_count_below_6")
        if result.get("evaluated_rows", 0) < 12:
            errors.append("evaluated_rows_below_12")
        if result.get("effect_delta", -1.0) < -0.01:
            errors.append("effect_delta_below_noninferiority_margin")
        if result.get("calibration_drift_delta", 1.0) > 0.01:
            errors.append("calibration_drift_above_0.01")
        if errors:
            failures[str(family)] = errors
    return failures


def _validate_freshness(freshness: Mapping[str, Any], reviewed_at_value: Any, trusted_now_value: Any) -> tuple[bool, list[str]]:
    if not _is_rfc3339_utc(freshness.get("evidence_generated_at")) or not _is_rfc3339_utc(reviewed_at_value) or not _is_rfc3339_utc(trusted_now_value):
        return False, ["freshness timestamps must be RFC3339 UTC"]
    evidence_at = _parse_time(freshness.get("evidence_generated_at"))
    reviewed_at = _parse_time(reviewed_at_value)
    trusted_now = _parse_time(trusted_now_value)
    max_age = freshness.get("max_age_seconds")
    if evidence_at is None or reviewed_at is None or trusted_now is None or not isinstance(max_age, int):
        return False, ["freshness requires evidence_generated_at, reviewed_at, trusted_now, and max_age_seconds"]
    if evidence_at.timestamp() > trusted_now.timestamp() or reviewed_at.timestamp() > trusted_now.timestamp():
        return False, ["freshness review is in the future relative to trusted_now"]
    evidence_ts = evidence_at.timestamp()
    reviewed_ts = reviewed_at.timestamp()
    trusted_now_ts = trusted_now.timestamp()
    fresh = evidence_ts <= reviewed_ts <= evidence_ts + max_age and trusted_now_ts <= reviewed_ts + max_age
    if freshness.get("fresh") is not True or not fresh:
        return False, ["freshness is stale or backdated"]
    return True, []


def _evaluate_fixture_episode(fixture: Mapping[str, Any]) -> dict[str, Any]:
    raw = fixture.get("episode_input")
    if not isinstance(raw, Mapping):
        return {
            "actual_label": "rejected",
            "failed_before_ledger": True,
            "ledger_admitted": False,
            "computed_gates": {gate: False for gate in REQUIRED_EVIDENCE_GATES},
        }
    ingress_valid = _p107_ingress_valid(raw.get("p107_ingress"))
    authority_clean = _authority_requests_clean(raw.get("authority_requests")) and _authority_counter_failures(fixture.get("authority_counters")) == {}
    temporal_valid = _temporal_cutoff_valid(raw)
    counterfactual_valid = _counterfactual_valid(raw.get("counterfactual"))
    recommendation_valid = _recommendation_errors(fixture.get("recommendation")) == []
    holdout_disjoint = _holdout_disjoint(fixture.get("episode_group"), raw.get("training_episode_groups"))
    ledger_bound = ingress_valid and authority_clean and _ledger_bound(raw.get("p107_ingress"), raw.get("ledger_candidate"))
    failed_before_ledger = not ingress_valid or not authority_clean
    ledger_admitted = ledger_bound and not failed_before_ledger
    actual_label = "rejected" if failed_before_ledger else _classify_outcome(raw.get("outcome"))
    computed_gates = {
        "ingress_recomputed": ingress_valid,
        "ledger_content_bound": ledger_bound,
        "temporal_cutoff_enforced": temporal_valid,
        "counterfactual_identifiable_or_abstained": counterfactual_valid,
        "recommendation_unapplied": recommendation_valid,
        "holdout_disjoint": holdout_disjoint,
        "authority_zero": authority_clean,
    }
    return {
        "actual_label": actual_label,
        "failed_before_ledger": failed_before_ledger,
        "ledger_admitted": ledger_admitted,
        "computed_gates": computed_gates,
    }


def _p107_ingress_valid(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("schema_version") == "p107.prevention_handoff.v1"
        and isinstance(value.get("episode_id"), str)
        and bool(value.get("episode_id"))
        and _canonical_sha256(value.get("payload_hash"))
        and value.get("signed_payload_hash") == value.get("payload_hash")
        and value.get("offline_authority") is True
    )


def _ledger_bound(ingress: Any, ledger_candidate: Any) -> bool:
    return (
        isinstance(ingress, Mapping)
        and isinstance(ledger_candidate, Mapping)
        and ledger_candidate.get("episode_id") == ingress.get("episode_id")
        and ledger_candidate.get("payload_hash") == ingress.get("payload_hash")
    )


def _temporal_cutoff_valid(raw: Mapping[str, Any]) -> bool:
    observed_at = raw.get("observed_at")
    cutoff_at = raw.get("cutoff_at")
    if observed_at is None and cutoff_at is None:
        return True
    if not _is_rfc3339_utc(observed_at) or not _is_rfc3339_utc(cutoff_at):
        return False
    observed = _parse_time(observed_at)
    cutoff = _parse_time(cutoff_at)
    return observed is not None and cutoff is not None and observed.timestamp() <= cutoff.timestamp()


def _counterfactual_valid(counterfactual: Any) -> bool:
    if not isinstance(counterfactual, Mapping):
        return False
    mode = counterfactual.get("mode")
    if mode == "identified":
        return True
    return mode == "abstained" and bool(counterfactual.get("reason"))


def _holdout_disjoint(episode_group: Any, training_groups: Any) -> bool:
    return isinstance(episode_group, str) and isinstance(training_groups, list) and episode_group not in training_groups


def _authority_requests_clean(requests: Any) -> bool:
    if not isinstance(requests, Sequence) or isinstance(requests, (str, bytes)):
        return False
    for request in requests:
        if not isinstance(request, Mapping):
            return False
        if request.get("kind") in FORBIDDEN_AUTHORITY_REQUEST_KINDS:
            return False
    return True


def _classify_outcome(outcome: Any) -> str:
    if not isinstance(outcome, Mapping):
        return "inconclusive"
    if outcome.get("horizon_censored") is True:
        return "censored"
    if outcome.get("intervention_harm") is True or outcome.get("actual_outcome") == "harmful":
        return "harmful"
    if outcome.get("natural_recovery") is True:
        return "naturally_recovered"
    if outcome.get("actual_outcome") == "naturally_recovered":
        return "naturally_recovered"
    if outcome.get("control_available") is not True or outcome.get("telemetry_complete") is False or outcome.get("conflicting_evidence") is True:
        return "inconclusive"
    actual = outcome.get("actual_outcome")
    if actual in {"prevented", "delayed", "unaffected"}:
        return str(actual)
    return "inconclusive"


def _recompute_fixture_matrix_result(fixture_matrix_result: Mapping[str, Any]) -> dict[str, Any]:
    raw_matrix = fixture_matrix_result.get("raw_matrix")
    if not isinstance(raw_matrix, Mapping):
        return {
            "accepted": False,
            "fixture_ids": list(fixture_matrix_result.get("fixture_ids", [])) if isinstance(fixture_matrix_result.get("fixture_ids"), list) else [],
            "matrix_hash": fixture_matrix_result.get("matrix_hash"),
            "reasons": ["missing raw fixture matrix"],
        }
    recomputed = evaluate_prevention_learning_fixture_matrix(raw_matrix)
    supplied_hash = fixture_matrix_result.get("matrix_hash")
    if supplied_hash is not None and supplied_hash != recomputed["matrix_hash"]:
        recomputed = {**recomputed, "accepted": False, "hash_mismatch": {"supplied": supplied_hash, "computed": recomputed["matrix_hash"]}}
    return recomputed


def _recompute_benchmark_result(benchmark_result: Mapping[str, Any]) -> dict[str, Any]:
    statistical_support = _statistical_support(benchmark_result.get("paired_learning_utility_deltas"))
    metric_failures = _metric_failures(benchmark_result.get("metrics"), computed_median_delta=statistical_support.get("computed_median_delta"))
    family_failures = _family_failures(benchmark_result.get("family_results"))
    accepted = (
        benchmark_result.get("accepted") is True
        and _canonical_sha256(benchmark_result.get("benchmark_hash"))
        and statistical_support["accepted"]
        and not metric_failures
        and not family_failures
    )
    return {"accepted": accepted, "statistical_support": statistical_support, "metric_failures": metric_failures, "family_failures": family_failures}


def _recommendation_manifest_valid(value: Mapping[str, Any]) -> bool:
    return (
        value.get("accepted") is True
        and _canonical_sha256(value.get("recommendation_manifest_hash") or value.get("manifest_hash"))
        and value.get("applied") is False
        and bool(value.get("rollback_to_version"))
    )


def _section_accepted_with_hash(section: Mapping[str, Any], hash_key: str) -> bool:
    return section.get("accepted") is True and _canonical_sha256(section.get(hash_key))


def _canonical_sha256(value: Any) -> bool:
    return isinstance(value, str) and CANONICAL_SHA256_PATTERN.fullmatch(value) is not None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return round((ordered[midpoint - 1] + ordered[midpoint]) / 2, 10)


def _is_rfc3339_utc(value: Any) -> bool:
    return isinstance(value, str) and RFC3339_UTC_PATTERN.fullmatch(value) is not None and _parse_time(value) is not None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
