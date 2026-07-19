"""P181 offline real-shadow readiness validators."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import file_hash, stable_hash, write_canonical_json
from app.services.p177_release import validate_predecessor_release_on_disk

READINESS_SCHEMA_VERSION = "p181.readiness_offline_substrate.v1"
REQUIRED_P180_SCHEMA = "p180.release_evidence.v1"
REQUIRED_P180_CLAIM = "statistically_qualified_hidden_eval_soak"
MAXIMUM_QUALIFIED_CLAIM = "real_shadow_operator_ready"
OFFLINE_CLAIM = "readiness_offline_substrate_only"
LIMITATION = "not general operator replacement"
REQUIRED_REDACTION_PATHS = frozenset({"prompt", "log", "trace", "exception", "report", "release"})
FORBIDDEN_CLAIMS = (MAXIMUM_QUALIFIED_CLAIM, "limited_staging_auto_approval_qualified", "production_autonomy_qualified")
SOURCE_PATHS = (
    "app/services/p181_shadow_readiness.py",
    "scripts/build_p181_readiness.py",
    "tests/test_p181_shadow_readiness.py",
    "docs/tickets/p181/README.md",
    "docs/tickets/p181/PRD.md",
    "docs/tickets/p181/test-spec.md",
    "docs/operations/p176-p182-roadmap.md",
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class P181ReadinessError(ValueError):
    """Raised when P181 evidence is unsafe, incomplete, or overclaims."""


def validate_shadow_ledger(days: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(days) < 28:
        raise P181ReadinessError("shadow_calendar_days")
    parsed_days = [_parse_date(day.get("utc_date")) for day in days]
    ordered = sorted(parsed_days)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if (current - previous).days != 1:
            raise P181ReadinessError("shadow_days_not_consecutive")
    hours = 0.0
    shifts: set[str] = set()
    operators: set[str] = set()
    heartbeat_ok = 0
    previous_receipt_hash: str | None = None
    for day in days:
        if _non_negative_int(day.get("mutation_count"), "mutation_count") != 0:
            raise P181ReadinessError("mutation_counter_nonzero")
        if "heartbeat_receipt_valid" in day or "deadman_receipt_valid" in day:
            raise P181ReadinessError("self_asserted_shadow_receipt")
        receipt_payload = _mapping(day.get("custody_payload"), "custody_payload")
        receipt = _mapping(day.get("custody_receipt"), "custody_receipt")
        if receipt.get("previous_receipt_hash") != previous_receipt_hash:
            raise P181ReadinessError("shadow_receipt_chain_gap")
        _validate_local_receipt(receipt, payload=receipt_payload, schema_version="p181.shadow_day_custody_receipt.v1")
        if receipt_payload.get("utc_date") != day.get("utc_date"):
            raise P181ReadinessError("shadow_receipt_payload_mismatch")
        if receipt_payload.get("heartbeat") != "observed" or receipt_payload.get("deadman") != "observed":
            raise P181ReadinessError("heartbeat_deadman_coverage")
        heartbeat_ok += 1
        previous_receipt_hash = _text(receipt.get("receipt_hash"), "receipt_hash")
        hours += float(day.get("covered_operator_hours", -1.0))
        shifts.update(_text_sequence(day.get("shift_ids"), "shift_ids"))
        operators.update(_text_sequence(day.get("operator_ids"), "operator_ids"))
    if hours < 320:
        raise P181ReadinessError("covered_operator_hours")
    if len(shifts) < 40:
        raise P181ReadinessError("covered_operator_shift_count")
    if len(operators) < 8:
        raise P181ReadinessError("distinct_operator_count")
    if heartbeat_ok != len(days):
        raise P181ReadinessError("heartbeat_deadman_coverage")
    return {
        "schema_version": "p181.shadow_ledger_validation.v1",
        "shadow_calendar_days": len(set(parsed_days)),
        "covered_operator_hours": int(hours) if hours.is_integer() else hours,
        "covered_operator_shift_count": len(shifts),
        "distinct_operator_count": len(operators),
        "heartbeat_deadman_coverage": 1.0,
        "action_execution_count": 0,
        "auto_approval_count": 0,
        "staging_mutation_count": 0,
        "production_mutation_count": 0,
    }


def validate_read_only_shadow_gate(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    required_zero = (
        "action_execution_count",
        "auto_approval_count",
        "staging_mutation_count",
        "production_mutation_count",
        "runtime_principal_write_permission_count",
        "out_of_allowlist_observation_count",
    )
    for key in required_zero:
        if _non_negative_int(snapshot.get(key), key) != 0:
            raise P181ReadinessError("mutation_counter_nonzero" if "mutation" in key or key == "action_execution_count" else key)
    if _non_negative_int(snapshot.get("configured_provider_count"), "configured_provider_count") < 1:
        raise P181ReadinessError("configured_provider_count")
    if float(snapshot.get("runtime_principal_allowlist_binding_coverage", -1.0)) != 1.0:
        raise P181ReadinessError("runtime_principal_allowlist_binding_coverage")
    if _non_negative_int(snapshot.get("runtime_token_ttl_seconds"), "runtime_token_ttl_seconds") > 3600:
        raise P181ReadinessError("runtime_token_ttl_seconds")
    if float(snapshot.get("provider_allowlist_receipt_coverage", -1.0)) != 1.0:
        raise P181ReadinessError("provider_allowlist_receipt_coverage")
    if "read_only_attested" in snapshot:
        raise P181ReadinessError("self_asserted_read_only_gate")
    custody_payload = _mapping(snapshot.get("custody_payload"), "custody_payload")
    custody_receipt = _mapping(snapshot.get("custody_receipt"), "custody_receipt")
    _validate_local_receipt(custody_receipt, payload=custody_payload, schema_version="p181.read_only_runtime_custody_receipt.v1")
    if custody_payload.get("runtime_principal_allowlist_binding_coverage") != snapshot.get("runtime_principal_allowlist_binding_coverage"):
        raise P181ReadinessError("read_only_receipt_payload_mismatch")
    if custody_payload.get("provider_allowlist_receipt_coverage") != snapshot.get("provider_allowlist_receipt_coverage"):
        raise P181ReadinessError("read_only_receipt_payload_mismatch")
    result = dict(snapshot)
    result["schema_version"] = "p181.read_only_shadow_gate.v1"
    result["read_only"] = True
    return result


def validate_redaction_proof(proof: Mapping[str, Any]) -> dict[str, Any]:
    if float(proof.get("redaction_canary_removal_rate", -1.0)) != 1.0:
        raise P181ReadinessError("redaction_canary_removal_rate")
    if _non_negative_int(proof.get("persisted_raw_credential_or_sensitive_value_match_count"), "persisted_raw_credential_or_sensitive_value_match_count") != 0:
        raise P181ReadinessError("persisted_raw_credential_or_sensitive_value_match_count")
    if _non_negative_int(proof.get("unique_redaction_canary_count"), "unique_redaction_canary_count") < 20:
        raise P181ReadinessError("unique_redaction_canary_count")
    if _non_negative_int(proof.get("sensitive_field_class_count"), "sensitive_field_class_count") < 5:
        raise P181ReadinessError("sensitive_field_class_count")
    classes = set(_text_sequence(proof.get("artifact_path_classes"), "artifact_path_classes"))
    if classes != REQUIRED_REDACTION_PATHS:
        raise P181ReadinessError("redaction_artifact_path_class_count")
    if _non_negative_int(proof.get("credential_leak_count"), "credential_leak_count") != 0:
        raise P181ReadinessError("credential_leak_count")
    result = dict(proof)
    result["schema_version"] = "p181.redaction_proof.v1"
    result["redaction_artifact_path_class_count"] = len(classes)
    result["redacted"] = True
    return result


def build_p181_readiness_artifact(*, project_root: Path, p180_release_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    p180_status = _predecessor_status(p180_release_evidence, project_root=project_root)
    stop_reasons = ["offline_substrate_only", "missing_real_28_day_shadow_ledger", "missing_read_only_runtime_principal_proof", "missing_redaction_proof"]
    if not p180_status["valid"]:
        stop_reasons.insert(0, "missing_qualified_p180_release_evidence")
    artifact: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "phase": "p181",
        "status": "p181_readiness_offline_substrate_only",
        "qualified": False,
        "maximum_claim": OFFLINE_CLAIM,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "limitations": [LIMITATION],
        "p180_release_evidence": p180_status,
        "release_artifact_status": {"status": "absent", "blocking": True, "reason": "offline_readiness_only_no_release_artifact"},
        "stop_reasons": stop_reasons,
        "substrate_capabilities": ["real_calendar_shadow_ledger_validation", "read_only_runtime_gate", "heartbeat_deadman_evidence_gate", "redaction_proof_validation", "operator_claim_limiter"],
        "safety_counters": _zero_safety_counters(),
        "source_hashes": _source_hashes(project_root),
    }
    artifact["readiness_hash"] = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    return artifact


def validate_p181_readiness_artifact(artifact: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    if artifact.get("schema_version") != READINESS_SCHEMA_VERSION or artifact.get("phase") != "p181":
        raise P181ReadinessError("invalid_readiness_schema")
    if artifact.get("qualified") is not False or artifact.get("maximum_claim") != OFFLINE_CLAIM:
        raise P181ReadinessError("qualification_forbidden")
    if MAXIMUM_QUALIFIED_CLAIM not in artifact.get("forbidden_claims", []):
        raise P181ReadinessError("forbidden_claim_missing")
    if LIMITATION not in artifact.get("limitations", []):
        raise P181ReadinessError("limitation_missing")
    counters = _mapping(artifact.get("safety_counters"), "safety_counters")
    if any(int(counters.get(key, 1)) != 0 for key in counters):
        raise P181ReadinessError("safety_counter_nonzero")
    if artifact.get("source_hashes") != _source_hashes(project_root):
        raise P181ReadinessError("source_hash_mismatch")
    expected = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    if artifact.get("readiness_hash") != expected:
        raise P181ReadinessError("readiness_hash_invalid")
    return dict(artifact)


def write_p181_readiness_artifact(*, project_root: Path, output_path: Path, p180_release_evidence: Mapping[str, Any] | None = None) -> Path:
    artifact = build_p181_readiness_artifact(project_root=project_root, p180_release_evidence=p180_release_evidence)
    validate_p181_readiness_artifact(artifact, project_root=project_root)
    return write_canonical_json(output_path, artifact)


def _predecessor_status(evidence: Mapping[str, Any] | None, *, project_root: Path) -> dict[str, Any]:
    if evidence is None:
        return {"valid": False, "reason": "not_supplied", "evidence_hash": None}
    evidence_hash = evidence.get("evidence_hash")
    valid = (
        validate_predecessor_release_on_disk(
            evidence,
            project_root=project_root,
            phase="p180",
            schema_version=REQUIRED_P180_SCHEMA,
            claim=REQUIRED_P180_CLAIM,
            receipt_key="independent_scorer_receipt",
        )
        if isinstance(evidence_hash, str) and _HEX64_RE.fullmatch(evidence_hash) is not None
        else False
    )
    return {
        "valid": valid,
        "reason": "qualified_p180_evidence_supplied" if valid else "invalid_or_unqualified_p180_evidence",
        "evidence_hash": evidence_hash if valid else None,
    }


def _zero_safety_counters() -> dict[str, int]:
    return {"action_execution_count": 0, "auto_approval_count": 0, "staging_mutation_count": 0, "production_mutation_count": 0, "credential_leak_count": 0}


def _source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = project_root / relative
        if not path.exists():
            raise P181ReadinessError(f"missing_source_path:{relative}")
        result[relative] = file_hash(path)
    return result


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise P181ReadinessError("invalid_utc_date")
    return date.fromisoformat(value)


def _text_sequence(value: Any, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise P181ReadinessError(f"invalid_{field}")
    result = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise P181ReadinessError(f"invalid_{field}")
        result.append(item)
    return result


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P181ReadinessError(f"invalid_{field}")
    return value


def _validate_local_receipt(receipt: Mapping[str, Any], *, payload: Mapping[str, Any], schema_version: str) -> None:
    if receipt.get("schema_version") != schema_version:
        raise P181ReadinessError("invalid_custody_receipt")
    if not isinstance(receipt.get("signer_id"), str) or not receipt.get("signer_id"):
        raise P181ReadinessError("invalid_custody_receipt")
    expected_signature = stable_hash({key: value for key, value in receipt.items() if key not in {"signature_hash", "receipt_hash"}})
    if receipt.get("signature_hash") != expected_signature:
        raise P181ReadinessError("invalid_custody_receipt")
    expected_hash = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    if receipt.get("receipt_hash") != expected_hash:
        raise P181ReadinessError("invalid_custody_receipt")
    if receipt.get("payload_hash") != stable_hash(dict(payload)):
        raise P181ReadinessError("shadow_receipt_payload_mismatch")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P181ReadinessError(f"invalid_{field}")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise P181ReadinessError(f"invalid_{field}")
    return value
