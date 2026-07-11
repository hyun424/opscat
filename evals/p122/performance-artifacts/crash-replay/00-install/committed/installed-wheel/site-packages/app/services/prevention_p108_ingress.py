"""P108 raw P107 ingress validation.

The ingress gate accepts only raw, local/mock P107 evidence. It recomputes the
canonical P107 release decision and treats caller-supplied readiness booleans as
non-authoritative telemetry.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p107_release_evidence import produce_p107_release_evidence
from app.services.prevention_canary_fixture_matrix import ZERO_AUTHORITY_COUNTERS
from app.services.prevention_outcome_report import (
    validate_independent_review,
    validate_recovery_replay_contract_public,
    validate_release_replay_contract_public,
)
from app.services.prevention_replay_gate import compute_audit_record_hash, compute_replay_hash

P108_INGRESS_PACK_SCHEMA = "p108.raw_p107_ingress_pack.v1"
REQUIRED_RAW_COMPONENTS = (
    "raw_audit_records",
    "raw_recovery_replay",
    "raw_release_replay",
    "raw_independent_review",
    "fixture_matrix_result",
    "outcome_report",
    "verify_profile",
    "docs_scan",
)
FORBIDDEN_EXACT_VALUES = frozenset({"staging", "production", "prod", "live"})
FORBIDDEN_VALUE_FRAGMENTS = ("production", "live-", "-live", "staging", "credential", "secret", "token", "network", "http")
FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "credential_scope",
        "credentials",
        "credential",
        "secret",
        "token",
        "network_evidence",
        "socket_evidence",
        "live_transport",
        "staging_label",
    }
)
ALLOWED_LOCAL_VALUES = frozenset({"local_mock", "isolated_harness", "audit", "recovery_outcome", "release_regression"})


def validate_raw_p107_ingress_pack(pack: Mapping[str, Any], *, trusted_now: str | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    if pack.get("schema_version") != P108_INGRESS_PACK_SCHEMA:
        reasons.append("schema_version must be p108.raw_p107_ingress_pack.v1")
    if trusted_now is None:
        reasons.append("trusted_now is required for P108 raw P107 ingress")

    for component in REQUIRED_RAW_COMPONENTS:
        if component not in pack:
            reasons.append(f"{component} is required")

    fixture_matrix_result = _mapping(pack.get("fixture_matrix_result"))
    outcome_report = _mapping(pack.get("outcome_report"))
    verify_profile = _mapping(pack.get("verify_profile"))
    docs_scan = _mapping(pack.get("docs_scan"))
    raw_recovery_replay = _mapping(pack.get("raw_recovery_replay"))
    raw_release_replay = _mapping(pack.get("raw_release_replay"))
    raw_independent_review = _mapping(pack.get("raw_independent_review"))
    raw_audit_records = _audit_records(pack.get("raw_audit_records"))

    p107_release_evidence = produce_p107_release_evidence(
        fixture_matrix_result=fixture_matrix_result,
        outcome_report=outcome_report,
        verify_profile=verify_profile,
        docs_scan=docs_scan,
        trusted_now=trusted_now,
    )
    if p107_release_evidence.get("release_qualified") is not True:
        reasons.append("canonical P107 release evidence did not recompute release_qualified=true")
        reasons.extend(f"P107: {reason}" for reason in _strings(p107_release_evidence.get("reasons")))

    recovery_validation = validate_recovery_replay_contract_public(raw_recovery_replay)
    if recovery_validation.get("accepted") is not True:
        reasons.append("canonical P107 recovery replay validator rejected raw replay")
        reasons.extend(f"recovery replay: {reason}" for reason in _strings(recovery_validation.get("reasons")))

    release_validation = validate_release_replay_contract_public(raw_release_replay, raw_audit_records)
    if release_validation.get("accepted") is not True:
        reasons.append("canonical P107 release replay validator rejected raw replay")
        reasons.extend(f"release replay: {reason}" for reason in _strings(release_validation.get("reasons")))

    bindings = _bindings(outcome_report)
    binding_reasons = _binding_reasons(
        bindings=bindings,
        outcome_report=outcome_report,
        raw_audit_records=raw_audit_records,
        raw_recovery_replay=raw_recovery_replay,
        raw_release_replay=raw_release_replay,
        raw_independent_review=raw_independent_review,
        trusted_now=trusted_now,
    )
    reasons.extend(binding_reasons)

    authority_reasons = _authority_counter_reasons(pack)
    reasons.extend(authority_reasons)

    offline_boundary_reasons = _offline_boundary_reasons(pack)
    reasons.extend(offline_boundary_reasons)

    accepted = not reasons
    return {
        "schema_version": "p108.ingress_validation.v1",
        "accepted": accepted,
        "p108_ingress_gate": accepted,
        "reasons": reasons,
        "trusted_submitted_readiness": False,
        "submitted_readiness_present": isinstance(pack.get("submitted_readiness"), Mapping),
        "recomputed_p107_release_qualified": p107_release_evidence.get("release_qualified") is True,
        "p107_release_evidence": p107_release_evidence,
        "bindings": bindings,
        "authority_counters": dict(ZERO_AUTHORITY_COUNTERS) if not authority_reasons else _collected_authority_counters(pack),
        "offline_boundary_passed": not offline_boundary_reasons,
        "recovery_replay_validation": recovery_validation,
        "release_replay_validation": release_validation,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _audit_records(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [record for record in value if isinstance(record, Mapping)]


def _bindings(outcome_report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "audit_head_hash": outcome_report.get("audit_head_hash"),
        "recovery_replay_hash": outcome_report.get("recovery_replay_hash"),
        "release_replay_hash": outcome_report.get("release_replay_hash"),
        "outcome_report_hash": outcome_report.get("report_hash"),
        "independent_review_hash": outcome_report.get("independent_review_hash"),
    }


def _binding_reasons(
    *,
    bindings: Mapping[str, Any],
    outcome_report: Mapping[str, Any],
    raw_audit_records: Sequence[Mapping[str, Any]],
    raw_recovery_replay: Mapping[str, Any],
    raw_release_replay: Mapping[str, Any],
    raw_independent_review: Mapping[str, Any],
    trusted_now: str | None,
) -> list[str]:
    reasons: list[str] = []
    canonical_audit_head_hash, audit_hash_reasons = _canonical_audit_hash_reasons(raw_audit_records)
    reasons.extend(audit_hash_reasons)
    terminal_record = raw_audit_records[-1] if raw_audit_records else {}
    if terminal_record.get("head_hash") != bindings["audit_head_hash"]:
        reasons.append("raw audit terminal head does not match outcome report audit_head_hash")
    if canonical_audit_head_hash is not None and canonical_audit_head_hash != bindings["audit_head_hash"]:
        reasons.append("canonical audit terminal head does not match outcome report audit_head_hash")
    if any(record.get("event_type") == "terminal_state" for record in raw_audit_records[:-1]):
        reasons.append("raw audit chain contains append-after-terminal records")
    if terminal_record.get("event_type") != "terminal_state":
        reasons.append("raw audit chain must end with a terminal_state record")

    recovery_replay_hash = compute_replay_hash(raw_recovery_replay)
    release_replay_hash = compute_replay_hash(raw_release_replay)
    if raw_recovery_replay.get("hash") != recovery_replay_hash:
        reasons.append("raw recovery replay hash does not match canonical replay content")
    if raw_recovery_replay.get("hash") != bindings["recovery_replay_hash"]:
        reasons.append("raw recovery replay hash does not match outcome report recovery_replay_hash")
    if recovery_replay_hash != bindings["recovery_replay_hash"]:
        reasons.append("canonical recovery replay hash does not match outcome report recovery_replay_hash")
    if raw_release_replay.get("hash") != release_replay_hash:
        reasons.append("raw release replay hash does not match canonical replay content")
    if raw_release_replay.get("hash") != bindings["release_replay_hash"]:
        reasons.append("raw release replay hash does not match outcome report release_replay_hash")
    if release_replay_hash != bindings["release_replay_hash"]:
        reasons.append("canonical release replay hash does not match outcome report release_replay_hash")
    if raw_release_replay.get("source_audit_head_hash") != bindings["audit_head_hash"]:
        reasons.append("raw release replay source audit hash does not match outcome report audit_head_hash")
    if raw_recovery_replay.get("source_audit_head_hash") != bindings["audit_head_hash"]:
        reasons.append("raw recovery replay source audit hash does not match outcome report audit_head_hash")
    if canonical_audit_head_hash is not None and raw_release_replay.get("source_audit_head_hash") != canonical_audit_head_hash:
        reasons.append("raw release replay source audit hash does not match canonical audit head")
    if canonical_audit_head_hash is not None and raw_recovery_replay.get("source_audit_head_hash") != canonical_audit_head_hash:
        reasons.append("raw recovery replay source audit hash does not match canonical audit head")

    canonical_report = _mapping(outcome_report.get("canonical_report"))
    canonical_report_hash = _hash_without(canonical_report, "report_hash") if canonical_report else None
    if canonical_report_hash is not None and canonical_report.get("report_hash") != canonical_report_hash:
        reasons.append("canonical outcome report hash does not match report content")
    if canonical_report_hash is not None and outcome_report.get("report_hash") != canonical_report_hash:
        reasons.append("outcome report hash does not match canonical report content")

    report_review = outcome_report.get("independent_review")
    if not isinstance(report_review, Mapping) or dict(raw_independent_review) != dict(report_review):
        reasons.append("raw independent review does not match outcome report independent review")
    independent_review_hash = _stable_hash(raw_independent_review)
    if independent_review_hash != bindings["independent_review_hash"]:
        reasons.append("raw independent review hash does not match outcome report independent_review_hash")
    review_validation = validate_independent_review(
        raw_independent_review,
        artifacts={
            "audit_head_hash": bindings["audit_head_hash"],
            "report_hash": bindings["outcome_report_hash"],
            "replay_hash": bindings["release_replay_hash"],
        },
        now=trusted_now,
    )
    if review_validation.get("accepted") is not True:
        reasons.append("raw independent review contract did not pass")
        reasons.extend(f"raw independent review: {reason}" for reason in _strings(review_validation.get("reasons")))
    return reasons


def _canonical_audit_hash_reasons(raw_audit_records: Sequence[Mapping[str, Any]]) -> tuple[str | None, list[str]]:
    reasons: list[str] = []
    if not raw_audit_records:
        return None, ["canonical audit chain requires records"]
    previous_hash: str | None = None
    seen_heads: set[str] = set()
    for index, record in enumerate(raw_audit_records, start=1):
        expected_previous = "GENESIS" if index == 1 and record.get("previous_hash") == "GENESIS" else previous_hash
        if index == 1 and record.get("previous_hash") not in {None, "GENESIS"}:
            reasons.append("canonical audit chain must start at genesis")
        elif index > 1 and record.get("previous_hash") != previous_hash:
            reasons.append("canonical audit chain previous hash does not match recomputed predecessor")
        if record.get("sequence") != index:
            reasons.append("canonical audit chain sequence does not match record order")
        if index > 1 and record.get("event_type") == "episode_started":
            reasons.append("canonical audit chain contains fabricated episode start")
        expected_head = compute_audit_record_hash({**record, "previous_hash": expected_previous})
        if record.get("head_hash") != expected_head:
            reasons.append("canonical audit head hash does not match event content")
        if record.get("head_hash") in seen_heads:
            reasons.append("canonical audit chain contains duplicate or forked head hash")
        if isinstance(record.get("head_hash"), str):
            seen_heads.add(str(record.get("head_hash")))
        previous_hash = expected_head
    return previous_hash, list(dict.fromkeys(reasons))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    payload = dict(value)
    payload.pop(key, None)
    return _stable_hash(payload)


def _authority_counter_reasons(value: Any) -> list[str]:
    failures: list[str] = []
    if isinstance(value, Mapping):
        failures.extend(_required_authority_counter_reasons(value))
    for path, counters in _walk_authority_counters(value):
        if not isinstance(counters, Mapping):
            failures.append(f"authority counters at {path} are missing or malformed")
            continue
        unknown = sorted(str(key) for key in counters if key not in ZERO_AUTHORITY_COUNTERS)
        nonzero = sorted(str(key) for key, expected in ZERO_AUTHORITY_COUNTERS.items() if counters.get(key) != expected)
        if unknown:
            failures.append(f"authority counters at {path} contain unknown keys: {', '.join(unknown)}")
        if nonzero:
            failures.append(f"authority counters at {path} contain nonzero or missing values: {', '.join(nonzero)}")
    return failures


def _required_authority_counter_reasons(pack: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    for path in ("outcome_report", "raw_recovery_replay", "raw_release_replay"):
        component = pack.get(path)
        if not isinstance(component, Mapping) or "authority_counters" not in component:
            failures.append(f"authority counters at $.{path}.authority_counters are required")
    canonical_report = _mapping(_mapping(pack.get("outcome_report")).get("canonical_report"))
    if "authority_counters" not in canonical_report:
        failures.append("authority counters at $.outcome_report.canonical_report.authority_counters are required")
    raw_audit_records = pack.get("raw_audit_records")
    if not isinstance(raw_audit_records, Sequence) or isinstance(raw_audit_records, (str, bytes)) or not raw_audit_records:
        failures.append("authority counters at $.raw_audit_records are required")
    else:
        for index, record in enumerate(raw_audit_records):
            if not isinstance(record, Mapping) or "authority_counters" not in record:
                failures.append(f"authority counters at $.raw_audit_records[{index}].authority_counters are required")
    return failures


def _walk_authority_counters(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "authority_counters":
                found.append((child_path, child))
            else:
                found.extend(_walk_authority_counters(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            found.extend(_walk_authority_counters(child, f"{path}[{index}]"))
    return found


def _collected_authority_counters(value: Any) -> dict[str, Any]:
    collected: dict[str, Any] = {}
    for path, counters in _walk_authority_counters(value):
        collected[path] = dict(counters) if isinstance(counters, Mapping) else counters
    return collected


def _offline_boundary_reasons(value: Any) -> list[str]:
    violations: list[str] = []
    for path, key, item in _walk_values(value):
        key_lower = key.lower()
        if key_lower in FORBIDDEN_METADATA_KEYS:
            violations.append(f"offline boundary forbids {path}")
            continue
        if isinstance(item, str) and _forbidden_string(item):
            violations.append(f"offline boundary forbids {path}={item}")
    return list(dict.fromkeys(violations))


def _walk_values(value: Any, path: str = "$", key: str = "") -> list[tuple[str, str, Any]]:
    found: list[tuple[str, str, Any]] = []
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            child_key_text = str(child_key)
            child_path = f"{path}.{child_key_text}"
            found.append((child_path, child_key_text, child))
            found.extend(_walk_values(child, child_path, child_key_text))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            found.extend(_walk_values(child, f"{path}[{index}]", key))
    return found


def _forbidden_string(value: str) -> bool:
    lowered = value.lower()
    if lowered in ALLOWED_LOCAL_VALUES:
        return False
    return lowered in FORBIDDEN_EXACT_VALUES or any(fragment in lowered for fragment in FORBIDDEN_VALUE_FRAGMENTS)


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _stable_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
