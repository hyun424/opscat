"""Import-only P109 MicroRemed result adapter.

The adapter validates a clean-room result schema and derives outcomes from
health windows plus independent verifier evidence. It never creates or runs a
remediation attempt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self, cast

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_OUTCOMES = ("verified_recovery", "harmful", "unnecessary", "no_effect", "unverified")
_ALLOWED_ACTIONS = frozenset(
    {
        "rollback_deploy",
        "restart_service",
        "observe_only",
        "bypass_cache",
        "restart_consumer",
        "scale_consumer",
        "recycle_connection_pool",
        "enable_dependency_fallback",
        "shed_load",
        "disable_faulty_feature",
        "restore_known_config",
        "restore_feature_flag",
    }
)
ZERO_RUNTIME_AUTHORITY: dict[str, int] = {
    "auth": 0,
    "credentials": 0,
    "shell": 0,
    "subprocess": 0,
    "kubernetes": 0,
    "ansible": 0,
    "cloud": 0,
    "database": 0,
    "production_adapter": 0,
    "mutation": 0,
    "executor": 0,
    "online_policy_write": 0,
}


class MicroRemedImportError(ValueError):
    """Raised when a submitted MicroRemed bundle violates the P109 import contract."""


@dataclass(frozen=True)
class ImportedMicroRemedBundle:
    bundle_id: str
    source_revision: str
    external_execution: bool
    smoke_only: bool
    release_trusted: bool
    runs: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        release_trusted = self.release_trusted and not self.smoke_only
        return {
            "schema_version": "p109.microremed_import.v1",
            "bundle_id": self.bundle_id,
            "source_revision": self.source_revision,
            "external_execution": self.external_execution,
            "smoke_only": self.smoke_only,
            "release_trusted": release_trusted,
            "authority": dict(ZERO_RUNTIME_AUTHORITY),
            "outcomes": list(_OUTCOMES),
            "runs": [{**run, "release_trusted": bool(run.get("release_trusted")) and release_trusted} for run in self.runs],
        }

    @classmethod
    def from_path(cls, path: str | Path, *, trusted_signers: Sequence[Mapping[str, str]] | None = None) -> Self:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cast(Self, import_microremed_bundle(payload, trusted_signers=trusted_signers))


def import_microremed_bundle(
    payload: Mapping[str, Any],
    *,
    trusted_signers: Sequence[Mapping[str, str]] | None = None,
) -> ImportedMicroRemedBundle:
    if payload.get("schema_version") != "p109.microremed_bundle.v1":
        raise MicroRemedImportError("unsupported MicroRemed bundle schema")
    if payload.get("external_execution") is not True:
        raise MicroRemedImportError("external_execution must be true for imported MicroRemed results")

    source_revision = _require_hash(payload.get("source_revision"), "source_revision")
    runs = payload.get("runs")
    if not isinstance(runs, Sequence) or isinstance(runs, (str, bytes)) or not runs:
        raise MicroRemedImportError("bundle requires at least one run")

    seen_run_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw_run in runs:
        if not isinstance(raw_run, Mapping):
            raise MicroRemedImportError("run must be an object")
        run = _normalize_run(raw_run, bundle_revision=source_revision, trusted_signers=trusted_signers)
        if run["run_id"] in seen_run_ids:
            raise MicroRemedImportError(f"duplicate run_id: {run['run_id']}")
        seen_run_ids.add(str(run["run_id"]))
        normalized.append(run)

    normalized.sort(key=lambda item: str(item["run_id"]))
    return ImportedMicroRemedBundle(
        bundle_id=str(payload.get("bundle_id", "")),
        source_revision=source_revision,
        external_execution=True,
        smoke_only=payload.get("smoke_only") is True,
        release_trusted=bool(normalized) and all(bool(run["release_trusted"]) for run in normalized),
        runs=tuple(normalized),
    )


def _normalize_run(
    raw: Mapping[str, Any],
    *,
    bundle_revision: str,
    trusted_signers: Sequence[Mapping[str, str]] | None,
) -> dict[str, Any]:
    if raw.get("schema_version") != "p109.microremed_run.v1":
        raise MicroRemedImportError("unsupported MicroRemed run schema")
    run_id = _require_text(raw.get("run_id"), "run_id")
    source_revision = _require_hash(raw.get("source_revision"), f"{run_id} source_revision")
    if source_revision != bundle_revision:
        raise MicroRemedImportError(f"{run_id} source_revision does not match bundle")

    started_at = _parse_time(raw.get("started_at"), f"{run_id} started_at")
    ended_at = _parse_time(raw.get("ended_at"), f"{run_id} ended_at")
    if ended_at < started_at:
        raise MicroRemedImportError(f"{run_id} timestamp order is impossible")

    actor = _require_mapping(raw.get("actor"), f"{run_id} actor")
    actor_id = _require_text(actor.get("id"), f"{run_id} actor.id")
    attempts = _normalize_attempts(raw, run_id=run_id)
    before_health = _normalize_health(raw.get("before_health"), f"{run_id} before_health")
    after_health = _normalize_health(raw.get("after_health"), f"{run_id} after_health")
    failure_injection = _require_mapping(raw.get("failure_injection"), f"{run_id} failure_injection")
    if failure_injection.get("status") != "succeeded":
        injection_succeeded = False
    else:
        injection_succeeded = True
        injection_started = _parse_time(failure_injection.get("started_at"), f"{run_id} failure_injection.started_at")
        injection_ended = _parse_time(failure_injection.get("ended_at"), f"{run_id} failure_injection.ended_at")
        if injection_ended < injection_started:
            raise MicroRemedImportError(f"{run_id} failure injection timestamp order is impossible")
        _require_inside_run(injection_started, injection_ended, started_at=started_at, ended_at=ended_at, label=f"{run_id} failure injection")
    for attempt in attempts:
        _require_inside_run(
            _parse_time(attempt["started_at"], f"{run_id} attempt.started_at"),
            _parse_time(attempt["ended_at"], f"{run_id} attempt.ended_at"),
            started_at=started_at,
            ended_at=ended_at,
            label=f"{run_id} attempt",
        )
    for label, health in (("before_health", before_health), ("after_health", after_health)):
        _require_inside_run(
            _parse_time(health["window_started_at"], f"{run_id} {label}.window_started_at"),
            _parse_time(health["window_ended_at"], f"{run_id} {label}.window_ended_at"),
            started_at=started_at,
            ended_at=ended_at,
            label=f"{run_id} {label}",
        )

    verifier = _normalize_verifier(raw.get("verifier"), run_id=run_id, actor_id=actor_id, trusted_signers=trusted_signers)
    independent_replay_passed = bool(verifier["replay_passed"])
    complete_windows = _has_complete_window(before_health) and _has_complete_window(after_health)
    eligible = bool(injection_succeeded and complete_windows and independent_replay_passed)
    safety_violation = any(bool(attempt["safety_violation"]) for attempt in attempts)
    non_noop = any(attempt["action_kind"] != "noop" for attempt in attempts)
    recovery_duration = int((ended_at - started_at).total_seconds()) if bool(after_health["healthy"]) else None
    credited = _credited_to_intervention(
        before_unhealthy=not bool(before_health["healthy"]),
        after_healthy=bool(after_health["healthy"]),
        non_noop=non_noop,
        safety_violation=safety_violation,
        independent_replay_passed=independent_replay_passed,
        recovery_duration_seconds=recovery_duration,
        matched_control=raw.get("matched_no_action_control"),
    )
    outcome = _classify(
        eligible=eligible,
        before_health=before_health,
        after_health=after_health,
        non_noop=non_noop,
        safety_violation=safety_violation,
        credited_to_intervention=credited,
    )

    return {
        "schema_version": "p109.microremed_imported_run.v1",
        "run_id": run_id,
        "system": _require_text(raw.get("system"), f"{run_id} system"),
        "fault_family": _require_text(raw.get("fault_family"), f"{run_id} fault_family"),
        "difficulty": _require_text(raw.get("difficulty"), f"{run_id} difficulty"),
        "environment": _require_text(raw.get("environment"), f"{run_id} environment"),
        "source_revision": source_revision,
        "started_at": _format_time(started_at),
        "ended_at": _format_time(ended_at),
        "submitted_success": raw.get("submitted_success"),
        "trusted_submitted_success": False,
        "actor": {"id": actor_id, "model": str(actor.get("model", "")), "method": str(actor.get("method", ""))},
        "failure_injection": dict(failure_injection),
        "attempts": attempts,
        "attempt_count": len(attempts),
        "before_health": before_health,
        "after_health": after_health,
        "verifier": verifier,
        "release_trusted": bool(verifier["release_trusted"]),
        "eligible": eligible,
        "outcome": outcome,
        "safety_violation": safety_violation,
        "non_noop_intervention": non_noop,
        "credited_to_intervention": credited,
        "recovery_duration_seconds": recovery_duration if outcome == "verified_recovery" else None,
    }


def _normalize_attempts(raw: Mapping[str, Any], *, run_id: str) -> list[dict[str, Any]]:
    playbook_hash = _require_hash(raw.get("actions_playbook_hash"), f"{run_id} actions_playbook_hash")
    attempts = raw.get("attempts")
    if not isinstance(attempts, Sequence) or isinstance(attempts, (str, bytes)) or not attempts:
        raise MicroRemedImportError(f"{run_id} requires at least one attempt")
    normalized: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    seen_attempts: set[str] = set()
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            raise MicroRemedImportError(f"{run_id} attempt must be an object")
        if attempt.get("schema_version") != "p109.microremed_attempt.v1":
            raise MicroRemedImportError(f"{run_id} unsupported attempt schema")
        attempt_id = _require_text(attempt.get("attempt_id"), f"{run_id} attempt_id")
        if attempt_id in seen_attempts:
            raise MicroRemedImportError(f"{run_id} duplicate attempt_id")
        seen_attempts.add(attempt_id)
        action_id = _require_text(attempt.get("action_id"), f"{run_id} action_id")
        if action_id not in _ALLOWED_ACTIONS:
            raise MicroRemedImportError(f"{run_id} unknown action: {action_id}")
        attempt_hash = _require_hash(attempt.get("action_playbook_hash"), f"{run_id} action_playbook_hash")
        if attempt_hash != playbook_hash:
            raise MicroRemedImportError(f"{run_id} hash mismatch between attempt and playbook")
        started = _parse_time(attempt.get("started_at"), f"{run_id} attempt.started_at")
        ended = _parse_time(attempt.get("ended_at"), f"{run_id} attempt.ended_at")
        if ended < started or (previous_end is not None and started < previous_end):
            raise MicroRemedImportError(f"{run_id} attempt timestamp order is impossible")
        previous_end = ended
        kind = _require_text(attempt.get("action_kind"), f"{run_id} action_kind")
        if kind not in {"intervention", "noop"}:
            raise MicroRemedImportError(f"{run_id} action_kind must be intervention or noop")
        normalized.append(
            {
                "schema_version": "p109.microremed_attempt.v1",
                "attempt_id": attempt_id,
                "action_id": action_id,
                "action_kind": kind,
                "action_playbook_hash": attempt_hash,
                "started_at": _format_time(started),
                "ended_at": _format_time(ended),
                "safety_violation": attempt.get("safety_violation") is True,
            }
        )
    return normalized


def _normalize_verifier(
    value: Any,
    *,
    run_id: str,
    actor_id: str,
    trusted_signers: Sequence[Mapping[str, str]] | None,
) -> dict[str, Any]:
    verifier = _require_mapping(value, f"{run_id} verifier")
    if verifier.get("schema_version") != "p109.microremed_verifier.v1":
        raise MicroRemedImportError(f"{run_id} unsupported verifier schema")
    verifier_id = _require_text(verifier.get("verifier_id"), f"{run_id} verifier_id")
    if verifier_id == actor_id:
        raise MicroRemedImportError(f"{run_id} requires independent verifier")
    signature = _require_mapping(verifier.get("signature"), f"{run_id} verifier.signature")
    signer_id = _require_text(signature.get("signer_id"), f"{run_id} signer_id")
    if signer_id in {actor_id, verifier_id}:
        raise MicroRemedImportError(f"{run_id} requires independent public attestation signer")
    key_id = signature.get("key_id")
    if key_id is not None and not isinstance(key_id, str):
        raise MicroRemedImportError(f"{run_id} signature.key_id must be text")
    signature_type = _require_text(signature.get("type"), f"{run_id} signature.type")
    release_trusted = _release_trusted_signature(
        signature_type=signature_type,
        signer_id=signer_id,
        key_id=key_id,
        trusted_signers=trusted_signers,
    )
    observations = verifier.get("raw_observations")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)) or not observations:
        raise MicroRemedImportError(f"{run_id} verifier requires raw observations")
    return {
        "schema_version": "p109.microremed_verifier.v1",
        "verifier_id": verifier_id,
        "implementation_hash": _require_hash(verifier.get("implementation_hash"), f"{run_id} verifier implementation_hash"),
        "policy_version": _require_text(verifier.get("policy_version"), f"{run_id} verifier policy_version"),
        "health_check_spec_hash": _require_hash(verifier.get("health_check_spec_hash"), f"{run_id} health_check_spec_hash"),
        "command_hash": _require_hash(verifier.get("command_hash"), f"{run_id} command_hash"),
        "observation_window_seconds": _require_positive_int(verifier.get("observation_window_seconds"), f"{run_id} observation_window_seconds"),
        "raw_observation_count": len(observations),
        "replay_passed": verifier.get("replay_passed") is True,
        "release_trusted": release_trusted,
        "signature": {
            "type": signature_type,
            "signer_id": signer_id,
            "key_id": key_id,
            "binding": _require_hash(signature.get("binding"), f"{run_id} signature.binding"),
        },
    }


def _release_trusted_signature(
    *,
    signature_type: str,
    signer_id: str,
    key_id: str | None,
    trusted_signers: Sequence[Mapping[str, str]] | None,
) -> bool:
    if key_id is None:
        return False
    if trusted_signers is not None:
        return any(signer.get("signer_id") == signer_id and signer.get("key_id") == key_id for signer in trusted_signers)
    return signature_type == "reviewed_public_attestation"


def _normalize_health(value: Any, label: str) -> dict[str, Any]:
    health = _require_mapping(value, label)
    started = _parse_time(health.get("window_started_at"), f"{label}.window_started_at")
    ended = _parse_time(health.get("window_ended_at"), f"{label}.window_ended_at")
    if ended < started:
        raise MicroRemedImportError(f"{label} timestamp order is impossible")
    if not isinstance(health.get("healthy"), bool):
        raise MicroRemedImportError(f"{label}.healthy must be boolean")
    return {
        "healthy": health["healthy"],
        "slo_passed": health.get("slo_passed") is True,
        "window_started_at": _format_time(started),
        "window_ended_at": _format_time(ended),
    }


def _credited_to_intervention(
    *,
    before_unhealthy: bool,
    after_healthy: bool,
    non_noop: bool,
    safety_violation: bool,
    independent_replay_passed: bool,
    recovery_duration_seconds: int | None,
    matched_control: Any,
) -> bool:
    if not (before_unhealthy and after_healthy and non_noop and not safety_violation and independent_replay_passed):
        return False
    if matched_control is None:
        return True
    if not isinstance(matched_control, Mapping):
        raise MicroRemedImportError("matched_no_action_control must be an object")
    if matched_control.get("recovered") is not True:
        return True
    control_duration = _require_positive_int(matched_control.get("recovery_duration_seconds"), "matched_no_action_control recovery_duration_seconds")
    effect_window = _require_positive_int(matched_control.get("minimum_effect_window_seconds"), "matched_no_action_control minimum_effect_window_seconds")
    return recovery_duration_seconds is not None and recovery_duration_seconds + effect_window <= control_duration


def _classify(
    *,
    eligible: bool,
    before_health: Mapping[str, Any],
    after_health: Mapping[str, Any],
    non_noop: bool,
    safety_violation: bool,
    credited_to_intervention: bool,
) -> str:
    if not eligible:
        return "unverified"
    if safety_violation:
        return "harmful"
    if bool(before_health["healthy"]) or not non_noop:
        return "unnecessary"
    if credited_to_intervention and bool(after_health["healthy"]):
        return "verified_recovery"
    return "no_effect"


def _has_complete_window(health: Mapping[str, Any]) -> bool:
    return bool(health.get("window_started_at") and health.get("window_ended_at"))


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MicroRemedImportError(f"{label} is required")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise MicroRemedImportError(f"{label} is required")
    return value


def _require_hash(value: Any, label: str) -> str:
    text = _require_text(value, label)
    if not _SHA256_RE.fullmatch(text):
        raise MicroRemedImportError(f"{label} must be an immutable sha256 revision/hash")
    return text


def _require_positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise MicroRemedImportError(f"{label} must be a positive integer")
    return value


def _parse_time(value: Any, label: str) -> datetime:
    text = _require_text(value, label)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MicroRemedImportError(f"{label} must be an ISO timestamp") from exc


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _require_inside_run(window_start: datetime, window_end: datetime, *, started_at: datetime, ended_at: datetime, label: str) -> None:
    if window_start < started_at or window_end > ended_at:
        raise MicroRemedImportError(f"{label} timestamp is outside the run interval")
