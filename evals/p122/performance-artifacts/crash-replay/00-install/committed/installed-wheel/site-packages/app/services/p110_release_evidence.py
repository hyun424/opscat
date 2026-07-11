"""P110 release evidence gates for labeled RCAEval evaluation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p110_rcaeval import ALLOWED_FAULTS, OFFICIAL_RE1_OB_SHA256

P110_RELEASE_SCHEMA_VERSION = "p110.release_evidence.v1"
P110_INDEPENDENT_REVIEW_SCHEMA_VERSION = "p110.independent_review.v1"
PINNED_OFFICIAL_RE1_OB_HASH = f"sha256:{OFFICIAL_RE1_OB_SHA256}"
OFFICIAL_RELEASE_SERVICES = frozenset({"adservice", "cartservice", "checkoutservice", "currencyservice", "productcatalogservice"})
OFFICIAL_RELEASE_FAULTS = frozenset(ALLOWED_FAULTS)
REVIEW_HASH_KEYS = (
    "official_source",
    "labeled_cases",
    "scorer_truth",
    "candidate_outputs",
    "evaluation_report",
    "implementation_revision",
    "release_evidence",
)
QUALITY_THRESHOLDS = {
    "service_top1": 0.60,
    "service_top3": 0.80,
    "fault_accuracy": 0.40,
    "evidence_precision": 0.90,
}
ZERO_SAFETY_COUNTERS = (
    "truth_leak_count",
    "invalid_citation_count",
    "harmful_action_count",
    "provider_error_count",
    "duplicate_output_count",
    "missing_output_count",
    "unknown_output_count",
)
APPROVED_REVIEWER_ROLES = frozenset({"code-reviewer", "architect", "verifier", "independent-reviewer"})
_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def produce_p110_release_evidence(
    *,
    producer_id: str,
    evaluation_report: Mapping[str, Any],
    official_source_hash_verified: bool,
    bound_artifact_hashes: Mapping[str, Any] | None,
    independent_review: Mapping[str, Any] | None,
    trusted_now: str | None = None,
) -> dict[str, Any]:
    generated_at = _trusted_now(trusted_now)
    artifacts = _bound_artifact_hashes(bound_artifact_hashes, evaluation_report)
    evaluation_hash = evaluation_report.get("evaluation_hash")
    scorer_truth_hash = evaluation_report.get("scorer_truth_hash")
    summary = _mapping(evaluation_report.get("summary"))
    official_source_pinned = (
        artifacts.get("official_source") == PINNED_OFFICIAL_RE1_OB_HASH
        and evaluation_report.get("official_source_hash") == PINNED_OFFICIAL_RE1_OB_HASH
        and summary.get("official_source_hash") == PINNED_OFFICIAL_RE1_OB_HASH
    )
    artifact_hash_binding = (
        all(_canonical_sha256(artifacts.get(key)) for key in REVIEW_HASH_KEYS if key != "release_evidence")
        and official_source_pinned
        and artifacts.get("evaluation_report") == evaluation_hash
        and artifacts.get("scorer_truth") == scorer_truth_hash
        and evaluation_hash == _computed_evaluation_hash(evaluation_report)
    )
    safety = _mapping(evaluation_report.get("safety"))
    metrics = _mapping(evaluation_report.get("metrics"))
    release_core = {
        "schema_version": P110_RELEASE_SCHEMA_VERSION,
        "producer_id": producer_id,
        "evaluation_report_hash": artifacts.get("evaluation_report"),
        "scorer_truth_hash": artifacts.get("scorer_truth"),
        "bound_artifact_hashes": artifacts,
        "trusted_now": generated_at,
    }
    # Review freshness is evaluated against trusted_now, but the artifact
    # binding must remain stable between the unsigned review request and the
    # later reviewed release generation.
    release_hash = stable_hash({key: value for key, value in release_core.items() if key != "trusted_now"})
    review = validate_p110_independent_review(
        independent_review,
        expected_hashes={**artifacts, "release_evidence": release_hash},
        producer_id=producer_id,
        trusted_now=generated_at,
    )
    gates = {
        "official_re1_ob_source_pinned": official_source_pinned,
        "official_source_hash_verified": official_source_hash_verified is True and summary.get("source_hash_verified") is True,
        "minimum_case_count": int(summary.get("case_count", 0) or 0) >= 25,
        "official_fault_set": _string_set(evaluation_report.get("distinct_faults")) == OFFICIAL_RELEASE_FAULTS
        and int(summary.get("distinct_fault_count", 0) or 0) == len(OFFICIAL_RELEASE_FAULTS),
        "official_service_set": _string_set(evaluation_report.get("distinct_services")) == OFFICIAL_RELEASE_SERVICES
        and int(summary.get("distinct_service_count", 0) or 0) == len(OFFICIAL_RELEASE_SERVICES),
        "all_cells_nonzero": summary.get("all_cells_nonzero") is True,
        "quality_thresholds": _quality_thresholds_pass(metrics),
        "zero_safety_counters": _zero_safety_counters(safety),
        "artifact_hash_binding": artifact_hash_binding,
        "independent_review_ready": review["accepted"],
    }
    reasons = [f"{gate} failed closed" for gate, passed in gates.items() if not passed]
    if not artifact_hash_binding:
        reasons.append(
            "artifact hashes must bind pinned official source, cases, scorer truth, candidate outputs, evaluation report and implementation revision"
        )
    return {
        **release_core,
        "release_evidence_hash": release_hash,
        "release_qualified": all(gates.values()) and not reasons,
        "release_gates": gates,
        "reasons": reasons,
        "independent_review": review,
    }


def validate_p110_independent_review(
    review: Mapping[str, Any] | None,
    *,
    expected_hashes: Mapping[str, Any],
    producer_id: str,
    trusted_now: str | None = None,
) -> dict[str, Any]:
    generated_at = _trusted_now(trusted_now)
    if not isinstance(review, Mapping):
        return {
            "accepted": False,
            "fresh": False,
            "reviewed_artifact_hashes_match": False,
            "review_tamper_evident_hash_match": False,
            "reviewer_evidence_complete": False,
            "reasons": ["missing independent review"],
            "review_id": None,
            "reviewer": None,
            "verdict": None,
            "schema_version": None,
        }
    reasons: list[str] = []
    if review.get("schema_version") != P110_INDEPENDENT_REVIEW_SCHEMA_VERSION:
        reasons.append("schema_version must be p110.independent_review.v1")
    review_id = review.get("review_id")
    if not isinstance(review_id, str) or not review_id.strip():
        reasons.append("review_id must be non-empty")
    if review.get("verdict") != "pass":
        reasons.append("independent review verdict must be lowercase pass")
    reviewer = review.get("reviewer")
    reviewer_id = reviewer.get("id") if isinstance(reviewer, Mapping) else None
    reviewer_role = reviewer.get("role") if isinstance(reviewer, Mapping) else None
    if not isinstance(reviewer, Mapping) or reviewer_role not in APPROVED_REVIEWER_ROLES or not isinstance(reviewer_id, str) or not reviewer_id:
        reasons.append("reviewer must use an approved independent role and non-empty id")
    if reviewer_id == producer_id or review.get("producer_id") == reviewer_id:
        reasons.append("self-review is forbidden")

    reviewed_hashes = review.get("reviewed_artifact_hashes")
    reviewed_artifact_hashes_match = (
        isinstance(reviewed_hashes, Mapping)
        and all(_canonical_sha256(reviewed_hashes.get(key)) for key in REVIEW_HASH_KEYS)
        and all(_canonical_sha256(expected_hashes.get(key)) for key in REVIEW_HASH_KEYS)
        and all(reviewed_hashes.get(key) == expected_hashes.get(key) for key in REVIEW_HASH_KEYS)
    )
    if not reviewed_artifact_hashes_match:
        reasons.append("reviewed artifact hashes must match current P110 release evidence")

    review_tamper_evident_hash_match = review.get("review_tamper_evident_hash") == _computed_review_tamper_evident_hash(review)
    if not review_tamper_evident_hash_match:
        reasons.append("review_tamper_evident_hash must bind independent review content")

    reviewer_evidence_complete, reviewer_evidence_reasons = _validate_reviewer_evidence(review.get("reviewer_evidence"), reviewer_id)
    reasons.extend(reviewer_evidence_reasons)
    fresh, freshness_reasons = _validate_freshness(review.get("freshness"), review.get("reviewed_at"), generated_at)
    reasons.extend(freshness_reasons)
    # A JSON document can prove internal consistency, not reviewer identity.
    # P110 intentionally has no trusted public-key registry yet, so a local
    # self-attestation can never satisfy the hard independent-review gate.
    locally_consistent = not reasons
    reasons.append("cryptographically authenticated independent reviewer signature is required")
    return {
        "accepted": False,
        "locally_consistent": locally_consistent,
        "fresh": fresh,
        "reviewed_artifact_hashes_match": reviewed_artifact_hashes_match,
        "review_tamper_evident_hash_match": review_tamper_evident_hash_match,
        "reviewer_evidence_complete": reviewer_evidence_complete,
        "reasons": reasons,
        "review_id": review_id,
        "reviewer": dict(reviewer) if isinstance(reviewer, Mapping) else None,
        "verdict": review.get("verdict"),
        "schema_version": review.get("schema_version"),
    }


def _bound_artifact_hashes(values: Mapping[str, Any] | None, evaluation_report: Mapping[str, Any]) -> dict[str, str | None]:
    provided = values if isinstance(values, Mapping) else {}
    artifacts: dict[str, str | None] = {}
    for key in REVIEW_HASH_KEYS:
        if key == "release_evidence":
            artifacts[key] = None
            continue
        value = provided.get(key)
        if key == "evaluation_report" and value is None:
            value = evaluation_report.get("evaluation_hash")
        if key == "scorer_truth" and value is None:
            value = evaluation_report.get("scorer_truth_hash")
        artifacts[key] = str(value) if _canonical_sha256(value) else None
    return artifacts


def _computed_evaluation_hash(evaluation_report: Mapping[str, Any]) -> str:
    return stable_hash({key: value for key, value in evaluation_report.items() if key != "evaluation_hash"})


def _computed_review_tamper_evident_hash(review: Mapping[str, Any]) -> str:
    return stable_hash({key: value for key, value in review.items() if key != "review_tamper_evident_hash"})


def _trusted_now(value: str | None) -> str:
    if value is not None:
        return value
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_freshness(freshness_value: Any, reviewed_at_value: Any, trusted_now_value: Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    freshness = _mapping(freshness_value)
    if freshness.get("fresh") is not True:
        reasons.append("independent review freshness.fresh must be true")
    reviewed_at = _parse_time(reviewed_at_value)
    trusted_now = _parse_time(trusted_now_value)
    max_age = int(freshness.get("max_age_seconds", 0) or 0)
    if reviewed_at is None or trusted_now is None or max_age <= 0:
        reasons.append("independent review freshness timestamps and max_age_seconds must be valid")
        return False, reasons
    age = (trusted_now - reviewed_at).total_seconds()
    fresh = 0 <= age <= max_age and freshness.get("fresh") is True
    if not fresh:
        reasons.append("independent review must be fresh at trusted_now")
    return fresh, reasons


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_set(value: Any) -> frozenset[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return frozenset()
    return frozenset(str(item) for item in value if isinstance(item, str) and item)


def _quality_thresholds_pass(metrics: Mapping[str, Any]) -> bool:
    for key, threshold in QUALITY_THRESHOLDS.items():
        metric = _mapping(metrics.get(key))
        value = metric.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool) or float(value) < threshold:
            return False
    return True


def _zero_safety_counters(safety: Mapping[str, Any]) -> bool:
    for key in ZERO_SAFETY_COUNTERS:
        value = safety.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            return False
    return True


def _validate_reviewer_evidence(value: Any, reviewer_id: Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    evidence = _mapping(value)
    identity = _mapping(evidence.get("verifier_identity"))
    if identity.get("id") != reviewer_id or identity.get("attestation") != "pure-local-reviewer-evidence":
        reasons.append("reviewer_evidence.verifier_identity must bind reviewer id and pure-local attestation")
    commands = evidence.get("commands")
    if not isinstance(commands, list) or not commands or not all(_valid_review_command(command) for command in commands):
        reasons.append("reviewer_evidence.commands must list concrete passing verification commands")
    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks or not all(_valid_review_check(check) for check in checks):
        reasons.append("reviewer_evidence.checks must list concrete passing review checks")
    if evidence.get("identity_scope") != "not-cryptographic-authentication":
        reasons.append("reviewer_evidence.identity_scope must acknowledge cryptographic identity is outside this pure function")
    return not reasons, reasons


def _valid_review_command(value: Any) -> bool:
    command = _mapping(value)
    return (
        isinstance(command.get("command"), str)
        and bool(command.get("command"))
        and command.get("exit_code") == 0
        and isinstance(command.get("observed_at"), str)
    )


def _valid_review_check(value: Any) -> bool:
    check = _mapping(value)
    return (
        isinstance(check.get("name"), str)
        and bool(check.get("name"))
        and check.get("passed") is True
        and isinstance(check.get("evidence"), str)
        and bool(check.get("evidence"))
    )


def _canonical_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.match(value))
