"""P106 adapter for P105 release-qualified prerequisite artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.failure_forecast_engine import (
    G006_P106_GATE_ROWS,
    G006_ZERO_AUTHORITY,
    validate_p105_release_qualified_artifact,
)


@dataclass(frozen=True)
class P105ReleaseGateEvidence:
    row: str
    canonical_paths: tuple[str, ...]
    observed_values: Mapping[str, Any]
    passed: bool
    failure_reason: str | None = None


@dataclass(frozen=True)
class P105ReleaseGateEvidenceMap:
    rows: Mapping[str, P105ReleaseGateEvidence]

    @property
    def passed(self) -> bool:
        return all(row.passed for row in self.rows.values())


@dataclass(frozen=True)
class P106ReleasePrerequisiteResult:
    release_qualified: bool
    p106_unlocked: bool
    downstream_allowed: bool
    reasons: tuple[str, ...]
    evidence_map: P105ReleaseGateEvidenceMap
    authority: Mapping[str, Any]
    validator_report: Mapping[str, Any]
    artifact_identity: Mapping[str, Any]
    artifact_manifests: Mapping[str, Any]
    freshness: Mapping[str, Any]


class P106ReleasePrerequisite:
    """Validate P105 eligibility from the validator report only."""

    def __init__(
        self,
        *,
        maximum_age: timedelta = timedelta(hours=24),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.maximum_age = maximum_age
        self.clock = clock or (lambda: datetime.now(UTC))

    def validate(self, path: str | Path) -> P106ReleasePrerequisiteResult:
        report = validate_p105_release_qualified_artifact(path)
        evidence_map = _build_evidence_map(report)
        reasons: list[str] = []
        release_gate = report.get("release_gate", {})
        if not isinstance(release_gate, Mapping):
            release_gate = {}
            reasons.append("release_gate missing or non-mapping")

        if release_gate.get("release_qualified") is not True:
            reasons.append("release_qualified is not exactly true")
        if release_gate.get("p106_unlocked") is not True:
            reasons.append("p106_unlocked is not exactly true")
        for row in evidence_map.rows.values():
            if not row.passed:
                reasons.append(f"{row.row}: {row.failure_reason}")

        validation_error_codes = _validation_error_codes(report)
        if validation_error_codes:
            reasons.extend(str(code) for code in validation_error_codes)

        authority = report.get("authority", {})
        if authority != G006_ZERO_AUTHORITY:
            reasons.append("authority does not exactly equal G006_ZERO_AUTHORITY")

        identity = _artifact_identity(path, report)
        if not identity["valid"]:
            reasons.extend(identity["reasons"])

        freshness = _freshness(identity.get("run_timestamp"), self.maximum_age, self.clock())
        if not freshness["fresh"]:
            reasons.append(str(freshness["reason"]))

        allowed = not reasons
        return P106ReleasePrerequisiteResult(
            release_qualified=allowed,
            p106_unlocked=allowed,
            downstream_allowed=allowed,
            reasons=tuple(reasons),
            evidence_map=evidence_map,
            authority=authority if isinstance(authority, Mapping) else {},
            validator_report=report,
            artifact_identity=identity,
            artifact_manifests=report.get("artifact_manifests", {}) if isinstance(report.get("artifact_manifests"), Mapping) else {},
            freshness=freshness,
        )

    validate_artifact = validate
    evaluate = validate


def _build_evidence_map(report: Mapping[str, Any]) -> P105ReleaseGateEvidenceMap:
    release_gate = report.get("release_gate", {})
    if not isinstance(release_gate, Mapping):
        release_gate = {}
    rows = {
        "held_out_calibration": _boolean_row(
            "held_out_calibration",
            ("release_gate.held_out_calibration.pass",),
            release_gate.get("held_out_calibration"),
        ),
        "per_family_release_metrics": _families_row(release_gate.get("families")),
        "global_release_metrics": _boolean_row(
            "global_release_metrics",
            ("release_gate.global.pass",),
            release_gate.get("global"),
        ),
        "real_derived_transfer": _boolean_row(
            "real_derived_transfer",
            ("release_gate.real_derived_transfer.pass",),
            release_gate.get("real_derived_transfer"),
        ),
        "safety_boundary": _boolean_row(
            "safety_boundary",
            ("release_gate.safety_boundary.pass",),
            release_gate.get("safety_boundary"),
        ),
    }
    required = set(G006_P106_GATE_ROWS)
    if set(rows) != required:
        missing = sorted(required - set(rows))
        extra = sorted(set(rows) - required)
        raise AssertionError(f"P105 gate evidence map parity failed; missing={missing}, extra={extra}")
    return P105ReleaseGateEvidenceMap(rows=rows)


def _boolean_row(row: str, paths: tuple[str, ...], container: Any) -> P105ReleaseGateEvidence:
    if not isinstance(container, Mapping):
        return P105ReleaseGateEvidence(row, paths, {"container": container}, False, "canonical container missing or non-mapping")
    value = container.get("pass")
    passed = value is True
    reason = None if passed else f"{paths[0]} is not exactly true"
    return P105ReleaseGateEvidence(row, paths, {"pass": value}, passed, reason)


def _families_row(families: Any) -> P105ReleaseGateEvidence:
    path = "release_gate.families"
    if not isinstance(families, Mapping):
        return P105ReleaseGateEvidence(
            "per_family_release_metrics",
            (path, "release_gate.families[*].pass"),
            {"families": families},
            False,
            "release_gate.families missing or non-mapping",
        )
    if not families:
        return P105ReleaseGateEvidence(
            "per_family_release_metrics",
            (path, "release_gate.families[*].pass"),
            {"families": {}},
            False,
            "release_gate.families is empty",
        )
    observed: dict[str, Any] = {}
    failures: list[str] = []
    for family, row in families.items():
        if not isinstance(row, Mapping):
            observed[str(family)] = row
            failures.append(f"{family}: family row missing or non-mapping")
            continue
        value = row.get("pass")
        observed[str(family)] = value
        if value is not True:
            failures.append(f"{family}: release_gate.families[{family}].pass is not exactly true")
    return P105ReleaseGateEvidence(
        "per_family_release_metrics",
        (path, "release_gate.families[*].pass"),
        observed,
        not failures,
        "; ".join(failures) if failures else None,
    )


def _validation_error_codes(report: Mapping[str, Any]) -> tuple[Any, ...]:
    candidates: tuple[Any, ...] = (report.get("validation_error_codes"),)
    release_gate = report.get("release_gate", {})
    if isinstance(release_gate, Mapping):
        candidates = (*candidates, release_gate.get("validation_error_codes"))
    codes: list[Any] = []
    for candidate in candidates:
        if isinstance(candidate, (list, tuple, set, frozenset)):
            codes.extend(candidate)
    return tuple(codes)


def _artifact_identity(path: str | Path, report: Mapping[str, Any]) -> dict[str, Any]:
    requested = Path(path)
    identity = report.get("artifact_identity")
    if not isinstance(identity, Mapping):
        identity = {}
    manifests = report.get("artifact_manifests", {})
    if not isinstance(manifests, Mapping):
        manifests = {}
    result: dict[str, Any] = {
        "path": identity.get("path", str(requested)),
        "sha256": identity.get("sha256") or identity.get("root_hash"),
        "root_hash": identity.get("root_hash") or identity.get("sha256"),
        "size_bytes": identity.get("size_bytes"),
        "run_timestamp": identity.get("run_timestamp") or identity.get("timestamp"),
        "valid": True,
        "reasons": [],
    }
    if identity.get("path") is not None and _resolved_path(Path(str(identity["path"])), requested) != requested.resolve():
        result["valid"] = False
        result["reasons"].append("artifact path mismatch")
    root_hash = result["root_hash"]
    sha256 = result["sha256"]
    if not root_hash or not sha256:
        result["valid"] = False
        result["reasons"].append("artifact hash identity missing")
    if root_hash and sha256 and root_hash != sha256:
        result["valid"] = False
        result["reasons"].append("artifact root hash mismatch")
    try:
        artifact_bytes = requested.read_bytes()
    except OSError:
        result["valid"] = False
        result["reasons"].append("artifact bytes unavailable after validation")
        artifact_bytes = None
    if artifact_bytes is not None:
        current_hash = hashlib.sha256(artifact_bytes).hexdigest()
        result["validated_size_bytes"] = len(artifact_bytes)
        result["validated_sha256"] = current_hash
        if sha256 != current_hash:
            result["valid"] = False
            result["reasons"].append("artifact hash changed after validation")
        expected_size = identity.get("size_bytes")
        if expected_size is not None and expected_size != len(artifact_bytes):
            result["valid"] = False
            result["reasons"].append("artifact size changed after validation")
    if report.get("schema_version") == "p105.release_qualified_artifact_validation.v1" and identity.get("size_bytes") is None:
        result["valid"] = False
        result["reasons"].append("artifact size identity missing")
    for name, manifest in manifests.items():
        if not isinstance(manifest, Mapping):
            result["valid"] = False
            result["reasons"].append(f"artifact manifest {name} is non-mapping")
            continue
        manifest_path = manifest.get("path")
        manifest_hash = manifest.get("sha256")
        if not manifest_path or not manifest_hash:
            result["valid"] = False
            result["reasons"].append(f"artifact manifest {name} identity missing")
            continue
        resolved_manifest = _resolved_path(Path(str(manifest_path)), requested)
        try:
            current_manifest_hash = hashlib.sha256(resolved_manifest.read_bytes()).hexdigest()
        except OSError:
            result["valid"] = False
            result["reasons"].append(f"artifact manifest {name} unavailable")
            continue
        if manifest_hash != current_manifest_hash:
            result["valid"] = False
            result["reasons"].append(f"artifact manifest {name} hash mismatch")
        if name == "rows" and (resolved_manifest != requested.resolve() or manifest_hash != sha256):
            result["valid"] = False
            result["reasons"].append("artifact rows manifest identity mismatch")
    return result


def _resolved_path(candidate: Path, requested: Path) -> Path:
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate == requested:
        return requested.resolve()
    sibling = requested.parent / candidate
    return sibling.resolve() if sibling.exists() else candidate.resolve()


def _freshness(raw_timestamp: Any, maximum_age: timedelta, now: datetime) -> dict[str, Any]:
    if raw_timestamp is None:
        return {"fresh": False, "reason": "stale: missing run timestamp", "age_seconds": None}
    try:
        parsed = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
    except ValueError:
        return {"fresh": False, "reason": "stale: invalid run timestamp", "age_seconds": None}
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    age = now - parsed
    return {
        "fresh": age <= maximum_age,
        "reason": None if age <= maximum_age else "stale: run timestamp exceeds maximum age",
        "age_seconds": age.total_seconds(),
        "maximum_age_seconds": maximum_age.total_seconds(),
    }
