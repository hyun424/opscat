"""P108 offline recommendation artifacts.

The functions in this module build reviewable data artifacts only. They do not
write policy, prompt, registry, threshold, or runbook files.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

_SCHEMA_VERSION = "p108.recommendation_manifest.v1"
_VERSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_SHA256_PATTERN = re.compile(r"^[A-Fa-f0-9]{64}$")
_CONSERVATIVE_OUTCOMES = {"harmful_guardrail_breach", "false_positive_intervention"}
_CONSERVATIVE_FAILURES = {"harmful_intervention", "unnecessary_intervention"}
_CONSERVATIVE_DIRECTIONS = {
    "tighten_threshold",
    "narrow_cohort",
    "reduce_action_scope",
    "disable_capability",
    "require_human_review",
}
_MUTATION_BOUNDARY = {
    "file_mutation_enabled": False,
    "policy_write_enabled": False,
    "prompt_write_enabled": False,
    "registry_write_enabled": False,
    "threshold_write_enabled": False,
    "runbook_write_enabled": False,
    "production_mutation_enabled": False,
}


def build_prevention_learning_recommendation_manifest(
    *, base_version: Mapping[str, Any], feedback_items: Sequence[Mapping[str, Any]], producer_id: str
) -> dict[str, Any]:
    """Return a deterministic, unapplied P108 recommendation manifest."""

    base = _base_version(base_version)
    rollback = {
        "base_version_id": base["version_id"],
        "base_content_hash_sha256": base["content_hash"],
        "target_version_id": base["rollback_target"],
    }
    version_block_reasons = _base_version_block_reasons(base)
    recommendations = [
        _recommendation(index=index, item=item, producer_id=producer_id, base=base, rollback=rollback, version_block_reasons=version_block_reasons)
        for index, item in enumerate(feedback_items, start=1)
    ]
    blocked_count = sum(1 for item in recommendations if item["blocked"])
    conservative_count = sum(1 for item in recommendations if item["review_binding"]["automatic_direction_allowed"])
    broader_count = len(recommendations) - conservative_count
    manifest_without_hash = {
        "schema_version": _SCHEMA_VERSION,
        "summary": {
            "passed": blocked_count == 0 and not version_block_reasons,
            "recommendation_count": len(recommendations),
            "applied_count": sum(1 for item in recommendations if item["applied"]),
            "blocked_count": blocked_count,
            "conservative_automatic_count": conservative_count,
            "broader_review_required_count": broader_count,
            "version_block_reasons": version_block_reasons,
        },
        "base_version": dict(base),
        "rollback": rollback,
        "recommendations": recommendations,
        "boundary": dict(_MUTATION_BOUNDARY),
    }
    return {**manifest_without_hash, "manifest_hash_sha256": _sha256_json(manifest_without_hash)}


def _recommendation(
    *,
    index: int,
    item: Mapping[str, Any],
    producer_id: str,
    base: Mapping[str, str | None],
    rollback: Mapping[str, str | None],
    version_block_reasons: Sequence[str],
) -> dict[str, Any]:
    episode_id = str(item.get("episode_id", f"unknown-{index}"))
    outcome_label = str(item.get("outcome_label", "unknown"))
    failure_mode = str(item.get("failure_mode", "unknown"))
    direction = str(item.get("recommended_direction", "require_human_review"))
    conservative_source = outcome_label in _CONSERVATIVE_OUTCOMES or failure_mode in _CONSERVATIVE_FAILURES
    conservative_direction = direction in _CONSERVATIVE_DIRECTIONS
    automatic_allowed = conservative_source and conservative_direction
    block_reasons: list[str] = []
    if conservative_source and not conservative_direction:
        block_reasons.append("non_conservative_direction_for_harm_or_false_positive")
    if not rollback.get("target_version_id"):
        block_reasons.append("missing_rollback_pointer")
    block_reasons.extend(reason for reason in version_block_reasons if reason not in block_reasons)
    body = {
        "recommendation_id": f"rec-{episode_id}-{item.get('family', 'general')}",
        "source_episode_id": episode_id,
        "family": str(item.get("family", "general")),
        "outcome_label": outcome_label,
        "failure_mode": failure_mode,
        "metric": str(item.get("metric", "unknown")),
        "direction": direction,
        "direction_class": "conservative" if automatic_allowed else "broader_review_required",
        "rationale": str(item.get("rationale", "")),
        "evidence_hash_sha256": str(item.get("evidence_hash", "")),
        "applied": False,
        "blocked": bool(block_reasons),
        "block_reasons": block_reasons,
        "file_mutation_enabled": False,
        "review_binding": {
            "producer_id": producer_id,
            "required_before_apply": True,
            "independent_review_required": not automatic_allowed or bool(block_reasons),
            "automatic_direction_allowed": automatic_allowed and not block_reasons,
            "base_version_id": str(base["version_id"] or ""),
            "base_content_hash_sha256": str(base["content_hash"] or ""),
            "rollback_target": str(base["rollback_target"] or ""),
        },
        "rollback": dict(rollback),
    }
    return {**body, "recommendation_hash_sha256": _sha256_json(body)}


def _base_version(value: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        "version_id": str(value.get("version_id", "")),
        "content_hash": str(value.get("content_hash", "")),
        "rollback_target": None if value.get("rollback_target") is None else str(value.get("rollback_target", "")),
    }


def _base_version_block_reasons(base: Mapping[str, str | None]) -> list[str]:
    reasons: list[str] = []
    version_id = base.get("version_id")
    content_hash = base.get("content_hash")
    rollback_target = base.get("rollback_target")
    if not _valid_version_id(version_id):
        reasons.append("invalid_base_version_id")
    if not _valid_sha256(content_hash):
        reasons.append("invalid_base_content_hash_sha256")
    if not rollback_target:
        reasons.append("missing_rollback_pointer")
    elif not _valid_version_id(rollback_target):
        reasons.append("invalid_rollback_target")
    elif version_id and rollback_target == version_id:
        reasons.append("rollback_target_matches_base_version")
    return reasons


def _valid_version_id(value: str | None) -> bool:
    return value is not None and bool(_VERSION_ID_PATTERN.fullmatch(value))


def _valid_sha256(value: str | None) -> bool:
    return value is not None and bool(_SHA256_PATTERN.fullmatch(value))


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
