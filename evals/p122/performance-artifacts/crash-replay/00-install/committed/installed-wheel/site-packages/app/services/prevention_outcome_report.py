"""Deterministic P107 outcome report and P108 review validation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.prevention_replay_gate import (
    validate_recovery_replay_contract as _validate_recovery_replay_contract,
)
from app.services.prevention_replay_gate import (
    validate_release_replay_contract as _validate_release_replay_contract,
)

ZERO_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "production_adapter_calls": 0,
    "production_mutation": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "cloud_calls": 0,
    "db_mutation": 0,
}
P107_INDEPENDENT_REVIEW_SCHEMA = "p107.independent_review.v1"
INDEPENDENT_REVIEW_VERDICTS = frozenset({"pass", "fail", "blocked"})
INDEPENDENT_REVIEWER_ROLES = frozenset({"code-reviewer", "architect", "verifier", "independent-reviewer"})
RFC3339_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")


def build_prevention_outcome_report(
    *,
    episode: Mapping[str, Any],
    recovery_replay: Mapping[str, Any],
    release_replay: Mapping[str, Any],
    independent_review: Mapping[str, Any],
    audit_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    recovery = _validate_recovery_replay_contract(recovery_replay)
    release = _validate_release_replay_contract(release_replay, audit_records or ())
    audit_head_hash = str(episode.get("audit_head_hash", release_replay.get("source_audit_head_hash", "")))

    reasons: list[str] = []
    if not recovery["accepted"]:
        reasons.extend(f"recovery replay: {reason}" for reason in recovery["reasons"])
    if not release["accepted"]:
        reasons.extend(f"release replay: {reason}" for reason in release["reasons"])
    if recovery_replay.get("hash") == release_replay.get("hash") or recovery_replay.get("purpose") != "recovery_outcome":
        reasons.append("recovery replay must be separate from release replay")
    canonical = {
        "schema_version": "p107.outcome_report.v1",
        "source_episode_id": episode.get("episode_id"),
        "audit_head_hash": audit_head_hash,
        "terminal_state": episode.get("terminal_state"),
        "candidate_id": episode.get("candidate_id"),
        "treatment_cohort_hash": episode.get("treatment_cohort_hash"),
        "control_cohort_hash": episode.get("control_cohort_hash"),
        "preflight_policy_hash": episode.get("preflight_policy_hash"),
        "recovery_replay_hash": recovery_replay.get("hash"),
        "release_replay_hash": release_replay.get("hash"),
        "release_replay_used_as_recovery_evidence": recovery_replay.get("hash") == release_replay.get("hash"),
        "metrics": _metrics_from_episode(episode, recovery_replay, release_replay),
        "authority_counters": _authority_counters(episode.get("authority_counters")),
    }
    report_hash = compute_canonical_report_hash(canonical)
    canonical["report_hash"] = report_hash
    independent_review_hash = _stable_hash(independent_review)
    review = validate_independent_review(
        independent_review,
        artifacts={
            "audit_head_hash": audit_head_hash,
            "report_hash": report_hash,
            "replay_hash": release_replay.get("hash"),
        },
        now=independent_review.get("reviewed_at"),
    )
    if not review["accepted"]:
        reasons.extend(f"P107 independent review: {reason}" for reason in review["reasons"])

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "report_hash": report_hash,
        "canonical_report": canonical,
        "source_episode_id": canonical["source_episode_id"],
        "audit_head_hash": audit_head_hash,
        "recovery_replay_hash": recovery_replay.get("hash"),
        "release_replay_hash": release_replay.get("hash"),
        "release_replay_used_as_recovery_evidence": canonical["release_replay_used_as_recovery_evidence"],
        "independent_review_hash": independent_review_hash,
        "independent_review": dict(independent_review),
        "metrics": canonical["metrics"],
        "uses_production_state": False,
    }


def build_prevention_outcome_report_from_audit(
    *,
    audit_records: Sequence[Mapping[str, Any]],
    recovery_replay: Mapping[str, Any],
    release_replay: Mapping[str, Any],
    independent_review: Mapping[str, Any],
) -> dict[str, Any]:
    last = audit_records[-1] if audit_records else {}
    episode = {
        "episode_id": last.get("episode_id"),
        "audit_head_hash": last.get("head_hash"),
        "terminal_state": last.get("terminal_state", last.get("state", "succeeded")),
        "attempts": [record for record in audit_records if record.get("attempt_id")],
        "metric_windows": [],
        "authority_counters": ZERO_COUNTERS,
    }
    report = build_prevention_outcome_report(
        episode=episode,
        recovery_replay=recovery_replay,
        release_replay=release_replay,
        independent_review=independent_review,
        audit_records=audit_records,
    )
    report["derived_from"] = "audit_records"
    report["source_episode_id"] = last.get("episode_id")
    report["audit_head_hash"] = last.get("head_hash")
    report["uses_production_state"] = False
    return report


def validate_independent_review(review: Mapping[str, Any], *, artifacts: Mapping[str, Any], now: str | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    if review.get("schema_version") != P107_INDEPENDENT_REVIEW_SCHEMA:
        reasons.append("schema_version must be p107.independent_review.v1")
    if "reviewer_role" in review or "artifact_hashes" in review:
        reasons.append("legacy independent review keys are not accepted")
    if not isinstance(review.get("review_id"), str) or not review.get("review_id"):
        reasons.append("review_id must be non-empty")

    verdict = review.get("verdict")
    verdict_allowed = verdict in INDEPENDENT_REVIEW_VERDICTS
    if not verdict_allowed:
        reasons.append("verdict must use the lowercase independent-review vocabulary")
    if verdict != "pass":
        reasons.append("independent review verdict must be pass")

    reviewer = review.get("reviewer")
    if not (
        isinstance(reviewer, Mapping)
        and reviewer.get("role") in INDEPENDENT_REVIEWER_ROLES
        and isinstance(reviewer.get("id"), str)
        and bool(reviewer.get("id"))
    ):
        reasons.append("reviewer must use an approved independent role and non-empty id")

    reviewed_hashes = review.get("reviewed_artifact_hashes")
    reviewed_artifact_hashes_match = isinstance(reviewed_hashes, Mapping) and all(reviewed_hashes.get(key) == value for key, value in artifacts.items())
    if not reviewed_artifact_hashes_match:
        reasons.append("reviewed artifact hashes must match")

    raw_freshness = review.get("freshness")
    freshness: Mapping[str, Any] = raw_freshness if isinstance(raw_freshness, Mapping) else {}
    fresh, freshness_reasons = _validate_freshness(freshness, review.get("reviewed_at"), now)
    reasons.extend(freshness_reasons)

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "schema_version": review.get("schema_version"),
        "reviewer": dict(reviewer) if isinstance(reviewer, Mapping) else None,
        "verdict": verdict,
        "verdict_allowed": verdict_allowed,
        "reviewed_artifact_hashes_match": reviewed_artifact_hashes_match,
        "freshness": dict(freshness),
        "fresh": fresh,
    }


def render_prevention_outcome_report(report: Mapping[str, Any]) -> dict[str, str]:
    canonical = dict(report.get("canonical_report", {}))
    if not canonical:
        canonical = {key: value for key, value in report.items() if key != "canonical_report"}
    payload = dict(report)
    payload["canonical_report"] = canonical
    json_text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    markdown = "\n".join(
        [
            "# P107 Prevention Outcome Report",
            "",
            f"- report hash: {report.get('report_hash')}",
            f"- recovery replay: {report.get('recovery_replay_hash')}",
            f"- release replay: {report.get('release_replay_hash')}",
            f"- terminal state: {canonical.get('terminal_state')}",
            "",
        ]
    )
    return {"json": json_text, "markdown": markdown}


def build_prevention_release_evidence(audit_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    boundary = next((record for record in audit_records if record.get("event_type") == "authority_boundary"), {})
    return {
        "static_authority_boundary_passed": bool(boundary.get("static_authority_boundary_passed")),
        "runtime_authority_sentinel_passed": bool(boundary.get("runtime_authority_sentinel_passed")),
        "authority_counters": _authority_counters(boundary.get("authority_counters")),
    }


def validate_recovery_replay_contract_public(replay: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_recovery_replay_contract(replay)


def validate_release_replay_contract_public(replay: Mapping[str, Any], audit_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return _validate_release_replay_contract(replay, audit_records)


def _metrics_from_episode(episode: Mapping[str, Any], recovery_replay: Mapping[str, Any], release_replay: Mapping[str, Any]) -> dict[str, float | int]:
    raw_attempts = episode.get("attempts")
    raw_windows = episode.get("metric_windows")
    attempts = [item for item in raw_attempts if isinstance(item, Mapping)] if isinstance(raw_attempts, Sequence) else []
    windows = [item for item in raw_windows if isinstance(item, Mapping)] if isinstance(raw_windows, Sequence) else []
    rollback_attempts = [attempt for attempt in attempts if attempt.get("rollback_attempted")]
    breached = [window for window in windows if window.get("guardrail_breached")]
    counters = _authority_counters(episode.get("authority_counters"))
    return {
        "episode_count": 1,
        "attempt_count": len(attempts),
        "recovery_success_rate": 1.0 if recovery_replay.get("recovered") else 0.0,
        "rollback_success_rate": _rate(
            sum(1 for attempt in rollback_attempts if attempt.get("rollback_status") in {"rolled_back", "not_required"}),
            len(rollback_attempts),
            default=1.0,
        ),
        "release_gate_success_rate": 1.0 if release_replay.get("release_gates_passed") else 0.0,
        "guardrail_breach_rate": _rate(len(breached), len(windows), default=0.0),
        "authority_breach_rate": 1.0 if any(counters.values()) else 0.0,
    }


def _validate_freshness(freshness: Mapping[str, Any], reviewed_at_value: Any, now_value: str | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    evidence_at_value = freshness.get("evidence_generated_at")
    if not _is_rfc3339_utc(evidence_at_value) or not _is_rfc3339_utc(reviewed_at_value):
        return False, ["freshness timestamps must be RFC3339 UTC"]
    evidence_at = _parse_time(evidence_at_value)
    reviewed_at = _parse_time(reviewed_at_value)
    now_at = _parse_time(now_value) if now_value else reviewed_at
    max_age = freshness.get("max_age_seconds")
    if evidence_at is None or reviewed_at is None or now_at is None or not isinstance(max_age, int):
        return False, ["freshness requires evidence_generated_at, reviewed_at, now, and max_age_seconds"]
    if evidence_at.timestamp() > now_at.timestamp() or reviewed_at.timestamp() > now_at.timestamp():
        return False, ["freshness timestamps cannot be future-dated later than trusted now"]
    deadline = evidence_at.timestamp() + max_age
    fresh = evidence_at.timestamp() <= reviewed_at.timestamp() <= deadline and now_at.timestamp() <= deadline
    if freshness.get("fresh") is not True or not fresh:
        reasons.append("freshness is stale or backdated")
    return fresh, reasons


def _is_rfc3339_utc(value: Any) -> bool:
    return (
        isinstance(value, str)
        and RFC3339_UTC_PATTERN.fullmatch(value) is not None
        and _parse_time(value) is not None
    )


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _authority_counters(value: Any) -> dict[str, int]:
    source = value if isinstance(value, Mapping) else {}
    return {key: int(source.get(key, 0) or 0) for key in ZERO_COUNTERS}


def _rate(numerator: int, denominator: int, *, default: float) -> float:
    if denominator <= 0:
        return default
    return max(0.0, min(1.0, numerator / denominator))


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def compute_canonical_report_hash(canonical_report: Mapping[str, Any]) -> str:
    """Hash report content without trusting its self-reported hash field."""
    payload = dict(canonical_report)
    payload.pop("report_hash", None)
    return _stable_hash(payload)


validate_recovery_replay_contract = validate_recovery_replay_contract_public
validate_release_replay_contract = validate_release_replay_contract_public
